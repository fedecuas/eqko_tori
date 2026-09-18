import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import (
    get_idempotency_store,
    get_places_provider,
    get_publisher,
    get_run_store,
    get_settings,
)
from app.main import app
from app.places_client import PlaceResult, PlacesProvider
from app.run_store import RunStore
from app.streams import StreamsPublisher
from idempotency import IdempotencyStore

INTERNAL_API_KEY = "test-internal-key"


class StubPlacesProvider(PlacesProvider):
    def __init__(self, results: list[PlaceResult]):
        self.results = results
        self.calls: list[dict] = []

    def search(self, query, latitude, longitude, radius_meters, max_results):
        self.calls.append(
            {
                "query": query,
                "latitude": latitude,
                "longitude": longitude,
                "radius_meters": radius_meters,
                "max_results": max_results,
            }
        )
        return self.results[:max_results]


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis()


@pytest.fixture
def stub_places_provider():
    return StubPlacesProvider(
        [
            PlaceResult(
                place_id="place-1",
                display_name="Taquería El Buen Sazón",
                formatted_address="Av. Siempre Viva 123, Guadalajara",
                website_uri=None,
                international_phone_number="+523312345678",
            ),
            PlaceResult(
                place_id="place-2",
                display_name="Restaurante Con Sitio Web",
                formatted_address="Calle Falsa 456, Guadalajara",
                website_uri="https://tiene-sitio.com",
                international_phone_number="+523398765432",
            ),
        ]
    )


@pytest.fixture
def client(redis_client, stub_places_provider):
    app.dependency_overrides[get_settings] = lambda: Settings(
        redis_url="redis://testing",
        google_places_api_key="fake-key",
        apify_api_token=None,
        tori_internal_api_key=INTERNAL_API_KEY,
    )
    app.dependency_overrides[get_places_provider] = lambda: stub_places_provider
    app.dependency_overrides[get_idempotency_store] = lambda: IdempotencyStore(redis_client)
    app.dependency_overrides[get_publisher] = lambda: StreamsPublisher(redis_client)
    app.dependency_overrides[get_run_store] = lambda: RunStore(redis_client)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
