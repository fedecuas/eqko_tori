from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    consumer_group: str = "dispatcher-cg"
    consumer_name: str = "dispatcher-1"

    retry_base_backoff_ms: int = 5_000
    max_retries: int = 5

    # Límites reales por defecto (ver TORI-CREDENTIALS.md): Airtable ~5 req/s por base,
    # Sheets ~60 req/min por proyecto+usuario. Configurable porque el límite real depende del
    # plan de cada tenant, no es un valor universal.
    airtable_rate_limit_per_second: float = 5.0
    sheets_rate_limit_per_minute: float = 60.0

    # Sin packages/database todavía, un solo output/tenant hardcodeado acá para poder probar
    # de verdad — ver TODO en main.py. "alba" porque es el tenant de ejemplo usado en todos los
    # smoke tests reales del pipeline hasta acá.
    airtable_access_token: str | None = None
    airtable_base_id: str | None = None
    airtable_table_name: str = "Leads"
