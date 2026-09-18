import logging

from idempotency import IdempotencyStore
from redis import Redis
from tori_seda_consumer import WorkerDependencies, run_cycle
from tori_shared_types import STREAM_LEAD_APPROVED

from .config import Settings
from .dispatch_pipeline import DispatchHandler
from .outputs import AirtableOutput, LeadOutput, StaticOutputRouter
from .rate_limiter import RateLimiter
from .streams import DispatchedLeadPublisher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_dependencies(settings: Settings, output_router: StaticOutputRouter) -> WorkerDependencies:
    """`output_router` se arma afuera (no acá) porque hoy es config hardcodeada por tenant —
    ver TORI-CREDENTIALS.md "CRM del cliente" y packages/database/README.md: sin un lugar real
    donde guardar "qué output usa cada tenant", este mapeo vive en el script de arranque, no en
    Settings. Cuando exista packages/database, este builder pasa a leer de ahí."""
    redis_client = Redis.from_url(settings.redis_url)

    # Un solo RateLimiter, un balde por output+tenant (la key ya los separa) — así Airtable de
    # un tenant no consume la cuota de Sheets de otro.
    airtable_limiter = RateLimiter(redis_client, max_requests=int(settings.airtable_rate_limit_per_second), window_seconds=1.0)
    sheets_limiter = RateLimiter(redis_client, max_requests=int(settings.sheets_rate_limit_per_minute), window_seconds=60.0)

    def rate_limiter_for(key: str) -> RateLimiter:
        return airtable_limiter if key.startswith("dispatch:airtable:") else sheets_limiter

    class _RoutedRateLimiter:
        def acquire(self, key: str) -> None:
            rate_limiter_for(key).acquire(key)

    handler = DispatchHandler(
        output_router=output_router,
        rate_limiter=_RoutedRateLimiter(),
        idempotency_store=IdempotencyStore(redis_client),
        publisher=DispatchedLeadPublisher(redis_client),
    )
    return WorkerDependencies(
        redis_client=redis_client,
        handler=handler,
        consumer_group=settings.consumer_group,
        consumer_name=settings.consumer_name,
        stream=STREAM_LEAD_APPROVED,
        base_backoff_ms=settings.retry_base_backoff_ms,
        max_retries=settings.max_retries,
    )


def _build_output_router(settings: Settings) -> StaticOutputRouter:
    # TODO Módulo 6: reemplazar por lookup real desde packages/database — esto es un mapeo
    # hardcodeado de un solo tenant ("alba") mientras no exista esa tabla. Sin
    # AIRTABLE_ACCESS_TOKEN/AIRTABLE_BASE_ID configurados, el router queda vacío y cualquier
    # evento levanta ValueError (a la DLQ), no falla en silencio.
    outputs_by_tenant: dict[str, LeadOutput] = {}
    if settings.airtable_access_token and settings.airtable_base_id:
        shared_airtable = AirtableOutput(
            access_token=settings.airtable_access_token,
            base_id=settings.airtable_base_id,
            table_name=settings.airtable_table_name,
        )
        # "fredy" comparte la misma base/tabla que "alba" a propósito (decisión 2026-09-18,
        # sin base separada todavía) — mismo objeto de output, no una config duplicada.
        outputs_by_tenant["alba"] = shared_airtable
        outputs_by_tenant["fredy"] = shared_airtable
    return StaticOutputRouter(outputs_by_tenant)


def main() -> None:
    """Stateless — correr N instancias en paralelo escala horizontalmente; el rate limiter
    vive en Redis, no en memoria del proceso, así que la cuota se respeta entre instancias."""
    settings = Settings()  # type: ignore[call-arg]
    output_router = _build_output_router(settings)

    deps = build_dependencies(settings, output_router)
    logger.info("dispatcher %s arrancando, grupo=%s", settings.consumer_name, settings.consumer_group)

    while True:
        stats = run_cycle(deps)
        if stats.processed or stats.reclaimed or stats.dlq:
            logger.info("cycle: %s", stats)


if __name__ == "__main__":
    main()
