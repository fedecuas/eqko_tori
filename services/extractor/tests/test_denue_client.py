import json

import httpx
import pytest

from app.denue_client import MAX_RADIUS_METERS, DenueError, DenueProvider, DenueUnavailableError

TOKEN = "secret-token-123"


def _record(id_="1", nombre="TAQUERIA EL FAROLITO", telefono="5512345678", sitio="", **extra):
    return {
        "Id": id_,
        "Nombre": nombre,
        "Telefono": telefono,
        "Sitio_internet": sitio,
        "Tipo_vialidad": "CALLE",
        "Calle": "QUINTANA ROO",
        "Num_Exterior": "12",
        "Colonia": "CENTRO",
        "CP": "52760",
        "Ubicacion": "HUIXQUILUCAN, MEXICO",
        **extra,
    }


class Script:
    """Cliente httpx con respuestas guionadas; registra los pedidos y las esperas."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item

    def provider(self, **kwargs) -> DenueProvider:
        return DenueProvider(
            token=TOKEN,
            client=httpx.Client(transport=httpx.MockTransport(self.handler)),
            sleep=self.sleeps.append,
            jitter=lambda: 0.5,  # factor 1.0 -> el retraso es exactamente base * 2^(n-1)
            **kwargs,
        )


def ok(*records):
    return httpx.Response(200, json=list(records))


def search(provider, query="taquerías en Huixquilucan", lat=19.36, lon=-99.35, radius=5000, max_results=20):
    return provider.search(query, lat, lon, radius, max_results)


def test_search_maps_a_record_into_a_place_result():
    script = Script(ok(_record()))

    result = search(script.provider())[0]

    assert result.place_id == "denue:1"
    assert result.display_name == "Taqueria El Farolito"  # no sale gritando
    assert result.international_phone_number == "+525512345678"
    assert result.website_uri is None
    assert result.formatted_address == "Calle Quintana Roo 12, Col. Centro, C.P. 52760, Huixquilucan, Mexico"


def test_request_carries_keyword_coordinates_radius_and_token():
    script = Script(ok(_record()))

    search(script.provider(), query="taquerías en Huixquilucan", lat=19.3606, lon=-99.3494, radius=3000)

    assert str(script.requests[0].url).endswith(f"/Buscar/taqueria/19.3606,-99.3494/3000/{TOKEN}")


def test_radius_is_clamped_to_the_5000_meters_the_api_accepts_and_defaults_to_it():
    script = Script(ok(_record()))
    provider = script.provider()

    search(provider, radius=50_000)
    search(provider, radius=None)

    assert [str(r.url).split("/")[-2] for r in script.requests] == [str(MAX_RADIUS_METERS)] * 2


def test_coordinates_are_required_because_denue_does_not_search_free_text():
    with pytest.raises(ValueError, match="latitude"):
        Script(ok()).provider().search("taquerías", None, None, 5000, 20)


def test_a_query_with_only_a_place_has_no_keyword_and_is_rejected():
    with pytest.raises(ValueError):
        search(Script(ok()).provider(), query="en Huixquilucan")


def test_comma_separated_keywords_run_one_search_each_and_dedupe_by_id():
    script = Script(ok(_record("1"), _record("2", "TACOS RAY")), ok(_record("2", "TACOS RAY"), _record("3", "TORTAS")))

    results = search(script.provider(), query="taquerías, tortas en Naucalpan")

    assert [str(r.url).split("/")[-4] for r in script.requests] == ["taqueria", "torta"]
    assert sorted(r.place_id for r in results) == ["denue:1", "denue:2", "denue:3"]


def test_when_trimming_to_max_results_records_with_a_phone_are_kept_first():
    script = Script(ok(_record("1", telefono=""), _record("2", telefono=""), _record("3"), _record("4")))

    results = search(script.provider(), max_results=2)

    assert [r.place_id for r in results] == ["denue:3", "denue:4"]


def test_retries_a_503_with_exponential_backoff_and_then_succeeds():
    script = Script(httpx.Response(503, text="Service Unavailable"), httpx.Response(503), httpx.Response(503), ok(_record()))

    results = search(script.provider(base_delay_seconds=1.0))

    assert len(results) == 1
    assert len(script.requests) == 4
    assert script.sleeps == [1.0, 2.0, 4.0]


def test_backoff_has_jitter_and_is_capped():
    script = Script(httpx.Response(503))
    provider = DenueProvider(
        token=TOKEN,
        client=httpx.Client(transport=httpx.MockTransport(script.handler)),
        max_attempts=8,
        base_delay_seconds=1.0,
        max_delay_seconds=10.0,
        sleep=script.sleeps.append,
        jitter=lambda: 1.0,  # jitter máximo: factor 1.5
    )

    with pytest.raises(DenueUnavailableError):
        search(provider)

    assert script.sleeps[0] == 1.5
    assert max(script.sleeps) == 15.0  # tope 10 * 1.5
    assert len(script.sleeps) == 7  # no duerme tras el último intento


def test_retries_transport_errors_and_timeouts():
    script = Script(httpx.ConnectTimeout("t"), httpx.ReadError("r"), ok(_record()))

    assert len(search(script.provider())) == 1
    assert len(script.requests) == 3


def test_retries_a_truncated_json_body():
    script = Script(httpx.Response(200, text='[{"Id": "1", "Nom'), ok(_record()))

    assert len(search(script.provider())) == 1
    assert len(script.requests) == 2


def test_gives_up_after_max_attempts_without_leaking_the_token():
    script = Script(httpx.Response(503))

    with pytest.raises(DenueUnavailableError) as error:
        search(script.provider(max_attempts=4))

    assert len(script.requests) == 4
    assert TOKEN not in str(error.value)
    assert "DENUE_TOKEN" in str(error.value)  # un token inválido también da 503


def test_no_results_text_is_an_empty_list_not_an_error_and_is_not_retried():
    script = Script(httpx.Response(200, text="No hay resultados. "))

    assert search(script.provider()) == []
    assert len(script.requests) == 1


def test_error_texts_returned_with_http_200_raise_without_retrying():
    script = Script(httpx.Response(200, text="Radio máximo 5000 metros."))

    with pytest.raises(DenueError, match="Radio"):
        search(script.provider())

    assert len(script.requests) == 1


def test_client_errors_are_not_retried_and_do_not_leak_the_token():
    script = Script(httpx.Response(401))

    with pytest.raises(DenueError) as error:
        search(script.provider())

    assert len(script.requests) == 1
    assert TOKEN not in str(error.value)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("55 1234 5678", "+525512345678"),
        ("(55) 1234-5678", "+525512345678"),
        ("525512345678", "+525512345678"),
        ("5215512345678", "+525512345678"),
        ("1234567", None),
        ("", None),
    ],
)
def test_phone_numbers_are_normalized_to_a_format_the_qualify_stage_can_parse(raw, expected):
    script = Script(ok(_record(telefono=raw)))

    assert search(script.provider())[0].international_phone_number == expected


@pytest.mark.parametrize(
    "raw,expected",
    [("", None), ("0", None), ("NA", None), ("www.tacos.mx", "http://www.tacos.mx"), ("https://tacos.mx", "https://tacos.mx")],
)
def test_website_placeholders_count_as_no_website(raw, expected):
    script = Script(ok(_record(sitio=raw)))

    assert search(script.provider())[0].website_uri == expected


def test_mixed_case_names_are_left_alone():
    script = Script(ok(_record(nombre="Tacos El Güero")))

    assert search(script.provider())[0].display_name == "Tacos El Güero"


def _keyword_of(request: httpx.Request) -> str:
    return str(request.url).split("/")[-4]


def test_one_keyword_that_never_responds_does_not_sink_the_run_if_another_one_did(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return ok(_record("1")) if _keyword_of(request) == "taqueria" else httpx.Response(503)

    provider = DenueProvider(
        token=TOKEN,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_attempts=3,
        sleep=lambda seconds: None,
    )

    with caplog.at_level("WARNING"):
        results = search(provider, query="taquerías, birria en Huixquilucan")

    assert [r.place_id for r in results] == ["denue:1"]
    assert "birria" in caplog.text


def test_when_every_keyword_fails_the_run_fails_and_names_the_keyword():
    script = Script(httpx.Response(503))

    with pytest.raises(DenueUnavailableError, match="birria"):
        search(script.provider(max_attempts=2), query="taquerías, birria en Huixquilucan")


@pytest.mark.parametrize(
    "query,expected",
    [
        ("taquerías en Huixquilucan", ["taqueria"]),
        ("salones de belleza en Naucalpan", ["salon de belleza"]),
        ("bares, restaurantes en Interlomas", ["bar", "restaurante"]),
        ("gimnasios y tortas", ["gimnasio", "torta"]),
        ("Taquería  en X", ["taqueria"]),
        ("bus en X", ["bus"]),
    ],
)
def test_keywords_are_singularized_because_denue_matches_substrings_of_real_names(query, expected):
    script = Script(httpx.Response(200, text="No hay resultados."))

    search(script.provider(), query=query)

    assert [str(r.url).split("/")[-4].replace("%20", " ") for r in script.requests] == expected


def test_padded_fixed_width_location_from_the_real_api_is_collapsed_and_title_cased():
    padded = "HUIXQUILUCAN DE DEGOLLADO" + " " * 60 + ", Huixquilucan, MÉXICO"
    script = Script(ok(_record(Ubicacion=padded)))

    address = search(script.provider())[0].formatted_address

    assert address.endswith("Huixquilucan De Degollado, Huixquilucan, México")
    assert "  " not in address
