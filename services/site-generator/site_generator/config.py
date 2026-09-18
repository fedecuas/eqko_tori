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

    # Aprobado en el documento de validación del Módulo 7 (CLAUDE.md sección 9,
    # 2026-09-18): 50 leads/semana, no escalar sin revisar de nuevo.
    weekly_quota: int = 50

    # Sin mecanismo real de "el negocio respondió" (TORI no ingesta respuestas de WhatsApp
    # todavía) — expiración incondicional a los N días desde que se generó, ver
    # site_generator/expiry_main.py.
    expiry_days: int = 14
