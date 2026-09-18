from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    tori_internal_api_key: str

    # Consumer que ingesta leadgen.message_drafted hacia el store de pendientes (intake_main.py)
    consumer_group: str = "approval-gate-cg"
    consumer_name: str = "approval-gate-1"
    retry_base_backoff_ms: int = 5_000
    max_retries: int = 5
