from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ver .env.example y TORI-CREDENTIALS.md para de dónde sale cada valor."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    google_places_api_key: str | None = None
    apify_api_token: str | None = None
    # De dónde salen los negocios: "google" (Places API) o "denue" (INEGI, datos abiertos).
    extraction_provider: Literal["google", "denue"] = "google"
    denue_token: str | None = None
    tori_internal_api_key: str

    idempotency_ttl_seconds: int | None = None
