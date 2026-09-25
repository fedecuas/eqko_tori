import json
import logging
import random
import re
import time
import unicodedata
from collections.abc import Callable
from urllib.parse import quote

import httpx
from tori_shared_types import DENUE_PLACE_ID_PREFIX

from .places_client import PlaceResult, PlacesProvider

logger = logging.getLogger(__name__)

MAX_RADIUS_METERS = 5000
_NO_RESULTS = "no hay resultados"
_PLACEHOLDER_WEBSITES = {"", "0", "-", ".", "na", "n/a", "no", "ninguno", "sin sitio", "no tiene"}


class DenueError(RuntimeError):
    """Error determinista de DENUE (parámetros inválidos, 4xx) — reintentar no lo arregla."""


class DenueUnavailableError(DenueError):
    """DENUE no respondió bien tras agotar los reintentos."""


class DenueProvider(PlacesProvider):
    """Fuente alternativa a Google Places: DENUE de INEGI (datos abiertos, se pueden guardar).

    Cosas que la API real hace y que este cliente absorbe (probadas 2026-09-24, no supuestas):
    - Es **intermitente**: devuelve `503` de forma aleatoria, y peor con búsquedas vacías. De ahí
      los reintentos con backoff exponencial + jitter (nunca intervalo fijo, estándar EQKO).
    - Los errores de negocio llegan como **texto con HTTP 200**: `No hay resultados.` (es una
      lista vacía, no un error) y `Radio máximo 5000 metros.` (error real).
    - Un **token inválido también da 503**, indistinguible de una caída — por eso el mensaje de
      `DenueUnavailableError` menciona ambas causas.
    - Busca por **coordenadas + radio (máx. 5000 m)** y una palabra clave, no por texto libre:
      `query` se reduce a las palabras clave antes de "en" ("taquerías en Huixquilucan" busca
      "taquerias"), separables con coma ("tacos, tortas en Naucalpan"), y `latitude`/`longitude`
      son obligatorias.
    - Los datos vienen sin acentos y en MAYÚSCULAS; se normalizan para que el mensaje que redacta
      Gemini no salga gritando.
    """

    BASE_URL = "https://www.inegi.org.mx/app/api/denue/v1/consulta/Buscar"

    def __init__(
        self,
        token: str,
        client: httpx.Client | None = None,
        max_attempts: int = 8,
        base_delay_seconds: float = 1.0,
        max_delay_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ):
        self._token = token
        self._client = client or httpx.Client(timeout=40.0)
        self._max_attempts = max_attempts
        self._base_delay = base_delay_seconds
        self._max_delay = max_delay_seconds
        self._sleep = sleep
        self._jitter = jitter

    def search(
        self,
        query: str,
        latitude: float | None,
        longitude: float | None,
        radius_meters: int | None,
        max_results: int,
    ) -> list[PlaceResult]:
        if latitude is None or longitude is None:
            raise ValueError("DENUE busca por coordenadas: el run tiene que incluir latitude y longitude")
        keywords = _keywords(query)
        if not keywords:
            raise ValueError(f"No hay palabra clave para DENUE en la búsqueda {query!r}")

        requested = radius_meters or MAX_RADIUS_METERS
        radius = min(requested, MAX_RADIUS_METERS)
        if radius != requested:
            logger.warning("DENUE admite máximo %d m de radio; se pidieron %d", MAX_RADIUS_METERS, requested)

        records: dict[str, dict] = {}
        failed: list[str] = []
        last_error: DenueUnavailableError | None = None
        for keyword in keywords:
            try:
                found = self._fetch(keyword, latitude, longitude, radius)
            except DenueUnavailableError as exc:
                failed.append(keyword)
                last_error = exc
                continue
            for record in found:
                records.setdefault(str(record["Id"]), record)

        # Una palabra que no responde no tumba la corrida si otra sí respondió (las búsquedas con
        # pocos o cero resultados son las que más 503 devuelven); solo falla si cayeron todas.
        if failed and last_error is not None and len(failed) == len(keywords):
            raise last_error
        if failed:
            logger.warning("DENUE no respondió para %s; se devuelven los resultados de las demás palabras", failed)

        results = [_to_place_result(record) for record in records.values()]
        # Sin teléfono no hay lead: si hay que recortar a max_results, se quedan primero los que
        # sí lo tienen (sort estable, conserva el orden de cercanía dentro de cada grupo).
        results.sort(key=lambda place: place.international_phone_number is None)
        return results[:max_results]

    def _fetch(self, keyword: str, latitude: float, longitude: float, radius: int) -> list[dict]:
        # La URL lleva el token: nunca se loguea ni se mete en un mensaje de error.
        url = f"{self.BASE_URL}/{quote(keyword, safe='')}/{latitude},{longitude}/{radius}/{self._token}"
        last_problem = "sin respuesta"
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.get(url)
            except httpx.TransportError as exc:  # incluye timeouts y cortes de conexión
                last_problem = type(exc).__name__
            else:
                if response.status_code == 200:
                    parsed = _parse_body(response.text)
                    if parsed is not None:
                        return parsed
                    last_problem = "respuesta truncada"
                elif response.status_code == 429 or response.status_code >= 500:
                    last_problem = f"HTTP {response.status_code}"
                else:
                    raise DenueError(f"DENUE respondió HTTP {response.status_code}")

            if attempt < self._max_attempts:
                self._sleep(self._delay_for(attempt))

        raise DenueUnavailableError(
            f"DENUE no respondió bien para {keyword!r} tras {self._max_attempts} intentos ({last_problem}). "
            "Puede ser una caída del servicio o un DENUE_TOKEN inválido (la API responde 503 en ambos casos)."
        )

    def _delay_for(self, attempt: int) -> float:
        capped = min(self._max_delay, self._base_delay * 2 ** (attempt - 1))
        return capped * (0.5 + self._jitter())


def _parse_body(text: str) -> list[dict] | None:
    """Lista de registros, `[]` si no hay resultados, `None` si la respuesta vino cortada
    (transitorio). Un texto de error conocido de la API levanta `DenueError`."""
    body = text.strip()
    if body.startswith("["):
        try:
            data = json.loads(body)
        except ValueError:
            return None
        return data if isinstance(data, list) else None
    if _NO_RESULTS in _strip_accents(body).lower():
        return []
    raise DenueError(f"DENUE respondió: {body[:120]}")


def _strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def _keywords(query: str) -> list[str]:
    head = re.split(r"(?:^|\s+)(?:en|cerca de)\s+", query.strip(), maxsplit=1, flags=re.IGNORECASE)[0]
    terms = [_singular(_strip_accents(term).lower().strip()) for term in re.split(r"[,;]|\s+y\s+|\s+o\s+", head)]
    return [term for term in dict.fromkeys(terms) if term]


def _singular(term: str) -> str:
    """DENUE busca por subcadena en el nombre y la actividad: "taquerias" no aparece en
    "TAQUERIA EL FAROLITO" (0 resultados, y las búsquedas vacías son las que más 503 dan), pero
    "taqueria" sí. Heurística de plural español, aplicada palabra por palabra."""
    words = []
    for word in term.split():
        if len(word) > 4 and word.endswith("ones"):
            word = word[:-2]
        elif len(word) > 4 and word.endswith(("ares", "eres", "ores")):
            word = word[:-2]
        elif len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        words.append(word)
    return " ".join(words)


def _smart_title(text: str) -> str:
    """DENUE rellena campos de ancho fijo con espacios (`"HUIXQUILUCAN DE DEGOLLADO      , ..."`) y
    mezcla partes en MAYÚSCULAS con otras en formato título: se colapsan los espacios y el
    formato título se decide por cada parte separada por coma."""
    parts = [part.strip() for part in re.sub(r"\s+", " ", text).split(",")]
    return ", ".join(part.title() if part.isupper() else part for part in parts if part)


def _phone(raw: str | None) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        return f"+52{digits}"
    if len(digits) == 12 and digits.startswith("52"):
        return f"+{digits}"
    if len(digits) == 13 and digits.startswith("521"):
        return f"+52{digits[3:]}"
    return None


def _website(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if value.lower() in _PLACEHOLDER_WEBSITES:
        return None
    return value if re.match(r"https?://", value, re.IGNORECASE) else f"http://{value}"


def _address(record: dict) -> str | None:
    def field(name: str) -> str:
        return _smart_title(record.get(name) or "")

    street = " ".join(part for part in (field("Tipo_vialidad"), field("Calle"), field("Num_Exterior")) if part)
    parts = [
        street,
        f"Col. {field('Colonia')}" if field("Colonia") else "",
        f"C.P. {field('CP')}" if field("CP") else "",
        field("Ubicacion"),
    ]
    address = ", ".join(part for part in parts if part)
    return address or None


def _to_place_result(record: dict) -> PlaceResult:
    return PlaceResult(
        place_id=f"{DENUE_PLACE_ID_PREFIX}{record['Id']}",
        display_name=_smart_title(record.get("Nombre") or ""),
        formatted_address=_address(record),
        website_uri=_website(record.get("Sitio_internet")),
        international_phone_number=_phone(record.get("Telefono")),
    )
