from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"

    # Stage 1 (main.py, Módulo 3): consume leadgen.place_extracted
    consumer_group: str = "agent-worker-cg"
    consumer_name: str = "agent-worker-1"

    # Stage 2 (draft_main.py, Módulo 4): consume leadgen.lead_qualified. Grupo propio (no
    # <servicio>-cg genérico) para poder escalar la redacción con Gemini por separado del
    # filtro/formateo, que es mucho más barato y rápido — CLAUDE.md sección 5.
    draft_consumer_group: str = "agent-worker-brain-cg"
    draft_consumer_name: str = "agent-worker-brain-1"
    database_url: str = "postgresql://localhost:5432/tori"
    gemini_api_key: str | None = None
    # gemini-1.5-flash / text-embedding-004 (defaults originales) ya no existen en la API —
    # confirmado con GET /v1beta/models contra una key real (2026-09-18). Estos son los
    # nombres reales disponibles hoy, no una suposición.
    gemini_model: str = "gemini/gemini-2.5-flash"
    embedding_model: str = "gemini/gemini-embedding-001"
    rag_examples_limit: int = 3

    # Módulo 6 — opcional: sin configurar, DraftHandler usa NullTracer y sigue funcionando.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Backoff exponencial con jitter ante redelivery — nunca intervalo fijo
    # (CLAUDE.md / eqko-agents-architecture sección 1). Compartido por ambos stages.
    retry_base_backoff_ms: int = 5_000
    max_retries: int = 5
