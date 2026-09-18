import logging

from redis import Redis
from tori_seda_consumer import WorkerDependencies, run_cycle
from tori_shared_types import STREAM_SITE_GENERATED

from .config import Settings
from .intake_pipeline import IntakeHandler
from .store import PendingApprovalStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_dependencies(settings: Settings) -> WorkerDependencies:
    redis_client = Redis.from_url(settings.redis_url)
    handler = IntakeHandler(store=PendingApprovalStore(redis_client))
    return WorkerDependencies(
        redis_client=redis_client,
        handler=handler,
        consumer_group=settings.consumer_group,
        consumer_name=settings.consumer_name,
        stream=STREAM_SITE_GENERATED,
        base_backoff_ms=settings.retry_base_backoff_ms,
        max_retries=settings.max_retries,
    )


def main() -> None:
    """Proceso separado de api.py: este consume Redis Streams, api.py sirve HTTP. Corren
    juntos para que approval-gate funcione, pero son deployables independientes (mismo patrón
    que main.py/draft_main.py en agent-worker)."""
    settings = Settings()  # type: ignore[call-arg]
    deps = build_dependencies(settings)
    logger.info("approval-gate intake %s arrancando, grupo=%s", settings.consumer_name, settings.consumer_group)

    while True:
        stats = run_cycle(deps)
        if stats.processed or stats.reclaimed or stats.dlq:
            logger.info("cycle: %s", stats)


if __name__ == "__main__":
    main()
