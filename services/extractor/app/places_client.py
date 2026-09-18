from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx


@dataclass
class PlaceResult:
    place_id: str
    display_name: str
    formatted_address: str | None
    website_uri: str | None
    international_phone_number: str | None


class PlacesProvider(ABC):
    """Interfaz común para las dos fuentes de extracción que contempla el README de TORI
    (Google Places API / Apify) — CLAUDE.md sección 3. `pipeline.py` no sabe cuál está detrás."""

    @abstractmethod
    def search(
        self,
        query: str,
        latitude: float | None,
        longitude: float | None,
        radius_meters: int | None,
        max_results: int,
    ) -> list[PlaceResult]:
        ...


class GooglePlacesProvider(PlacesProvider):
    """Text Search (New). Requiere una API key restringida a 'Places API (New)'
    — ver TORI-CREDENTIALS.md."""

    BASE_URL = "https://places.googleapis.com/v1/places:searchText"
    FIELD_MASK = (
        "places.id,places.displayName,places.formattedAddress,"
        "places.websiteUri,places.internationalPhoneNumber"
    )

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=15.0)

    def search(
        self,
        query: str,
        latitude: float | None,
        longitude: float | None,
        radius_meters: int | None,
        max_results: int,
    ) -> list[PlaceResult]:
        body: dict = {"textQuery": query, "pageSize": min(max_results, 20)}
        if latitude is not None and longitude is not None and radius_meters:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": radius_meters,
                }
            }

        response = self._client.post(
            self.BASE_URL,
            json=body,
            headers={
                "X-Goog-Api-Key": self._api_key,
                "X-Goog-FieldMask": self.FIELD_MASK,
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        payload = response.json()

        results = []
        for place in payload.get("places", [])[:max_results]:
            results.append(
                PlaceResult(
                    place_id=place["id"],
                    display_name=place.get("displayName", {}).get("text", ""),
                    formatted_address=place.get("formattedAddress"),
                    website_uri=place.get("websiteUri"),
                    international_phone_number=place.get("internationalPhoneNumber"),
                )
            )
        return results
