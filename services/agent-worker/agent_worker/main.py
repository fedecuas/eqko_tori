import logging

from idempotency import IdempotencyStore
from redis import Redis
from tori_shared_types import STREAM_PLACE_EXTRACTED

from .config import Settings
from tori_seda_consumer import WorkerDependencies, run_cycle
from .pipeline import QualifyHandler
from .streams import QualifiedLeadPublisher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_dependencies(settings: Settings) -> WorkerDependencies:
    redis_client = Redis.from_url(settings.redis_url)
    handler = QualifyHandler(
        idempotency_store=IdempotencyStore(redis_client),
        publisher=QualifiedLeadPublisher(redis_client),
    )
    return WorkerDependencies(
        redis_client=redis_client,
        handler=handler,
        consumer_group=settings.consumer_group,
        consumer_name=settings.consumer_name,
        stream=STREAM_PLACE_EXTRACTED,
        base_backoff_ms=settings.retry_base_backoff_ms,
        max_retries=settings.max_retries,
    )


def main() -> None:
    """Stateless — correr N instancias de este proceso en paralelo escala horizontalmente
    sin coordinación adicional, el consumer group de Redis reparte los mensajes."""
    settings = Settings()  # type: ignore[call-arg]
    deps = build_dependencies(settings)
    logger.info("agent-worker %s arrancando, grupo=%s", settings.consumer_name, settings.consumer_group)

    while True:
        stats = run_cycle(deps)
        if stats.processed or stats.reclaimed or stats.dlq:
            logger.info("cycle: %s", stats)


if __name__ == "__main__":
    main()
