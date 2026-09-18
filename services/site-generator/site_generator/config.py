from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    consumer_group: str = "site-generator-cg"
    consumer_name: str = "site-generator-1"

    retry_base_backoff_ms: int = 5_000
    max_retries: int = 5

    vercel_token: str | None = None
    vercel_team_id: str | None = None
    vercel_project_name: str = "tori-leads"

    # Generación del sitio con Gemini (builder.AiSiteBuilder). Sin GEMINI_API_KEY se usa la
    # plantilla fija de siempre (StaticSiteBuilder).
    gemini_api_key: str | None = None
    site_gen_model: str = "gemini/gemini-2.5-flash"

    # Fotos de Google Places. `google_places_api_key` es la key de SERVIDOR (metadatos de fotos).
    # `google_places_public_key` queda EXPUESTA en el HTML público (<img src> le pide la foto en
    # vivo a Google, los Términos prohíben guardarla): tiene que ser una key distinta, restringida
    # por HTTP referrer (*.vercel.app) y solo a Places API. Sin las dos, el sitio sale sin fotos.
    google_places_api_key: str | None = None
    google_places_public_key: str | None = None
    max_photos: int = 3

    # Aprobado en el documento de validación del Módulo 7 (CLAUDE.md sección 9,
    # 2026-09-18): 50 leads/semana, no escalar sin revisar de nuevo.
    weekly_quota: int = 50

    # Sin mecanismo real de "el negocio respondió" (TORI no ingesta respuestas de WhatsApp
    # todavía) — expiración incondicional a los N días desde que se generó, ver
    # site_generator/expiry_main.py.
    expiry_days: int = 14
