import logging

from idempotency import IdempotencyStore
from redis import Redis
from tori_shared_types import STREAM_LEAD_QUALIFIED

from .brain import LiteLLMMessageDrafter
from .config import Settings
from tori_seda_consumer import WorkerDependencies, run_cycle
from .draft_pipeline import DraftHandler
from .rag import LiteLLMEmbedder, PostgresMessageExamplesRepository
from .streams import DraftedMessagePublisher
from .tracing import LangfuseTracer, NullTracer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _build_tracer(settings: Settings):
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return NullTracer()
    return LangfuseTracer(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )


def build_dependencies(settings: Settings) -> WorkerDependencies:
    # psycopg es un extra opcional ([postgres] en pyproject.toml) — solo hace falta para
    # correr esto de verdad, no para los tests (que nunca llegan a esta función).
    import psycopg

    redis_client = Redis.from_url(settings.redis_url)
    connection = psycopg.connect(settings.database_url)
    handler = DraftHandler(
        examples_repository=PostgresMessageExamplesRepository(
            connection, LiteLLMEmbedder(model=settings.embedding_model, api_key=settings.gemini_api_key)
        ),
        drafter=LiteLLMMessageDrafter(model=settings.gemini_model, api_key=settings.gemini_api_key),
        idempotency_store=IdempotencyStore(redis_client),
        publisher=DraftedMessagePublisher(redis_client),
        examples_limit=settings.rag_examples_limit,
        tracer=_build_tracer(settings),
    )
    return WorkerDependencies(
        redis_client=redis_client,
        handler=handler,
        consumer_group=settings.draft_consumer_group,
        consumer_name=settings.draft_consumer_name,
        stream=STREAM_LEAD_QUALIFIED,
        base_backoff_ms=settings.retry_base_backoff_ms,
        max_retries=settings.max_retries,
    )


def main() -> None:
    """Proceso separado de main.py (stage 1): mismo patrón stateless, pero consumiendo
    leadgen.lead_qualified con su propio consumer group, para poder escalarlo distinto del
    filtro/formateo (las llamadas a Gemini son más lentas y caras)."""
    settings = Settings()  # type: ignore[call-arg]
    deps = build_dependencies(settings)
    logger.info(
        "agent-worker (brain) %s arrancando, grupo=%s", settings.draft_consumer_name, settings.draft_consumer_group
    )

    while True:
        stats = run_cycle(deps)
        if stats.processed or stats.reclaimed or stats.dlq:
            logger.info("cycle: %s", stats)


if __name__ == "__main__":
    main()
