import logging

from idempotency import IdempotencyStore
from redis import Redis
from tori_seda_consumer import WorkerDependencies, run_cycle
from tori_shared_types import STREAM_MESSAGE_DRAFTED

from .builder import AiSiteBuilder, GeminiSiteWriter, SiteBuilder, StaticSiteBuilder
from .config import Settings
from .deploy import VercelDeployer
from .handler import SiteGenerationHandler
from .photos import GooglePlacesPhotosProvider, NoPhotosProvider
from .quota import WeeklyQuota
from .store import SiteDeploymentStore
from .streams import SiteGeneratedPublisher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _build_site_builder(settings: Settings) -> SiteBuilder:
    if not settings.gemini_api_key:
        logger.warning("sin GEMINI_API_KEY: sitios con la plantilla fija, sin IA ni fotos")
        return StaticSiteBuilder()

    photos_enabled = bool(settings.google_places_api_key and settings.google_places_public_key)
    if not photos_enabled:
        logger.warning("fotos deshabilitadas: faltan GOOGLE_PLACES_API_KEY y/o GOOGLE_PLACES_PUBLIC_KEY")
    provider = (
        GooglePlacesPhotosProvider(settings.google_places_api_key, max_photos=settings.max_photos)
        if photos_enabled
        else NoPhotosProvider()
    )
    return AiSiteBuilder(
        writer=GeminiSiteWriter(model=settings.site_gen_model, api_key=settings.gemini_api_key),
        photos_provider=provider,
        public_key=settings.google_places_public_key if photos_enabled else None,
    )


def build_dependencies(settings: Settings) -> WorkerDependencies:
    redis_client = Redis.from_url(settings.redis_url)
    deployer = VercelDeployer(
        token=settings.vercel_token,
        project_name=settings.vercel_project_name,
        team_id=settings.vercel_team_id,
    )
    handler = SiteGenerationHandler(
        deployer=deployer,
        site_builder=_build_site_builder(settings),
        quota=WeeklyQuota(redis_client, max_per_week=settings.weekly_quota),
        deployment_store=SiteDeploymentStore(redis_client),
        idempotency_store=IdempotencyStore(redis_client),
        publisher=SiteGeneratedPublisher(redis_client),
    )
    return WorkerDependencies(
        redis_client=redis_client,
        handler=handler,
        consumer_group=settings.consumer_group,
        consumer_name=settings.consumer_name,
        stream=STREAM_MESSAGE_DRAFTED,
        base_backoff_ms=settings.retry_base_backoff_ms,
        max_retries=settings.max_retries,
    )


def main() -> None:
    """Stateless — correr N instancias en paralelo escala horizontalmente. El cupo semanal
    vive en Redis (WeeklyQuota), no en memoria del proceso, así que se respeta entre
    instancias."""
    settings = Settings()  # type: ignore[call-arg]
    deps = build_dependencies(settings)
    logger.info("site-generator %s arrancando, grupo=%s", settings.consumer_name, settings.consumer_group)

    while True:
        stats = run_cycle(deps)
        if stats.processed or stats.reclaimed or stats.dlq:
            logger.info("cycle: %s", stats)


if __name__ == "__main__":
    main()
