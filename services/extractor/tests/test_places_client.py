import httpx

from app.places_client import GooglePlacesProvider


def _client_returning(payload: dict, capture: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        capture["request"] = request
        capture["body"] = request.content
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_search_parses_places_and_sends_field_mask():
    capture: dict = {}
    payload = {
        "places": [
            {
                "id": "place-1",
                "displayName": {"text": "Taquería El Buen Sazón"},
                "formattedAddress": "Av. Siempre Viva 123",
                "internationalPhoneNumber": "+523312345678",
                # sin websiteUri -> candidato ideal para TORI
            },
            {
                "id": "place-2",
                "displayName": {"text": "Con sitio"},
                "formattedAddress": "Calle Falsa 456",
                "websiteUri": "https://tiene-sitio.com",
                "internationalPhoneNumber": "+523398765432",
            },
        ]
    }
    provider = GooglePlacesProvider(api_key="fake-key", client=_client_returning(payload, capture))

    results = provider.search(
        query="restaurantes en Guadalajara",
        latitude=None,
        longitude=None,
        radius_meters=None,
        max_results=20,
    )

    assert len(results) == 2
    assert results[0].place_id == "place-1"
    assert results[0].website_uri is None
    assert results[0].international_phone_number == "+523312345678"
    assert results[1].website_uri == "https://tiene-sitio.com"

    request = capture["request"]
    assert request.headers["X-Goog-Api-Key"] == "fake-key"
    assert request.headers["X-Goog-FieldMask"] == GooglePlacesProvider.FIELD_MASK


def test_search_respects_max_results():
    payload = {"places": [{"id": f"place-{i}", "displayName": {"text": f"Negocio {i}"}} for i in range(5)]}
    capture: dict = {}
    provider = GooglePlacesProvider(api_key="fake-key", client=_client_returning(payload, capture))

    results = provider.search(
        query="negocios", latitude=None, longitude=None, radius_meters=None, max_results=3
    )

    assert len(results) == 3


def test_search_sends_location_bias_when_coordinates_given():
    payload = {"places": []}
    capture: dict = {}
    provider = GooglePlacesProvider(api_key="fake-key", client=_client_returning(payload, capture))

    provider.search(
        query="restaurantes", latitude=20.6597, longitude=-103.3496, radius_meters=5000, max_results=20
    )

    import json

    body = json.loads(capture["body"])
    assert body["locationBias"]["circle"]["radius"] == 5000
    assert body["locationBias"]["circle"]["center"]["latitude"] == 20.6597
