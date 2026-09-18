from functools import lru_cache

from idempotency import IdempotencyStore
from redis import Redis

from .config import Settings
from .places_client import GooglePlacesProvider, PlacesProvider
from .run_store import RunStore
from .streams import StreamsPublisher


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # valores vienen de env/.env


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


@lru_cache
def get_places_provider() -> PlacesProvider:
    settings = get_settings()
    if not settings.google_places_api_key:
        raise RuntimeError(
            "GOOGLE_PLACES_API_KEY no está configurada — ver TORI-CREDENTIALS.md. "
            "Apify como proveedor alternativo todavía no está implementado (Módulo 2 solo "
            "cubre Places API)."
        )
    return GooglePlacesProvider(api_key=settings.google_places_api_key)


@lru_cache
def get_idempotency_store() -> IdempotencyStore:
    return IdempotencyStore(get_redis(), ttl_seconds=get_settings().idempotency_ttl_seconds)


@lru_cache
def get_publisher() -> StreamsPublisher:
    return StreamsPublisher(get_redis())


@lru_cache
def get_run_store() -> RunStore:
    return RunStore(get_redis())
