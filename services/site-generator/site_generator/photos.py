import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

PLACES_BASE_URL = "https://places.googleapis.com/v1"


@dataclass(frozen=True)
class AuthorAttribution:
    display_name: str
    uri: str | None = None
    photo_uri: str | None = None


@dataclass(frozen=True)
class PlacePhoto:
    name: str
    google_maps_uri: str | None = None
    attributions: tuple[AuthorAttribution, ...] = ()


@dataclass(frozen=True)
class PlaceMedia:
    photos: tuple[PlacePhoto, ...] = field(default_factory=tuple)
    google_maps_uri: str | None = None


class PhotosProvider(ABC):
    @abstractmethod
    def fetch(self, place_id: str) -> PlaceMedia:
        ...


class NoPhotosProvider(PhotosProvider):
    def fetch(self, place_id: str) -> PlaceMedia:
        return PlaceMedia()


def photo_media_url(photo_name: str, public_key: str, max_width_px: int = 800) -> str:
    """URL que el BROWSER del visitante le pide a Google en vivo — nunca se descarga ni se
    hostea la foto (los Términos de Places prohíben cachear/guardar su contenido). Por eso
    `public_key` va expuesta en el HTML público: tiene que ser una key restringida por HTTP
    referrer y solo a Places API, distinta de la key de servidor."""
    return f"{PLACES_BASE_URL}/{quote(photo_name, safe='/')}/media?maxWidthPx={max_width_px}&key={quote(public_key, safe='')}"


class GooglePlacesPhotosProvider(PhotosProvider):
    """Pide en vivo (Place Details, campos `photos` y `googleMapsUri`) solo los metadatos de
    las fotos: el nombre del recurso y la atribución obligatoria. Falla de red/HTTP degrada a
    "sin fotos" en vez de perder el lead — las fotos mejoran el sitio, no son requisito."""

    def __init__(self, api_key: str, max_photos: int = 3, client: httpx.Client | None = None):
        self._api_key = api_key
        self._max_photos = max_photos
        self._client = client or httpx.Client(timeout=15.0)

    def fetch(self, place_id: str) -> PlaceMedia:
        try:
            response = self._client.get(
                f"{PLACES_BASE_URL}/places/{quote(place_id, safe='')}",
                headers={"X-Goog-Api-Key": self._api_key, "X-Goog-FieldMask": "photos,googleMapsUri"},
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("no se pudieron obtener fotos de %s: %s", place_id, exc)
            return PlaceMedia()

        photos = tuple(_parse_photo(raw) for raw in body.get("photos", [])[: self._max_photos])
        return PlaceMedia(photos=photos, google_maps_uri=body.get("googleMapsUri"))


def _parse_photo(raw: dict) -> PlacePhoto:
    attributions = tuple(
        AuthorAttribution(
            display_name=item.get("displayName", ""),
            uri=item.get("uri"),
            photo_uri=item.get("photoUri"),
        )
        for item in raw.get("authorAttributions", [])
    )
    return PlacePhoto(name=raw["name"], google_maps_uri=raw.get("googleMapsUri"), attributions=attributions)
