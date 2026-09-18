import logging
from datetime import datetime, timedelta, timezone

from redis import Redis

from .config import Settings
from .deploy import VercelDeployer
from .store import SiteDeploymentStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_expiry_sweep(settings: Settings) -> dict:
    """Cron, no un consumer (TORI ya es Manual/Chat/Cron-friendly — no hace falta un consumer
    group nuevo para esto). Borra deployments con más de `expiry_days` desde que se crearon.

    ⚠️ Expira incondicionalmente por tiempo, sin chequear si el negocio respondió: TORI no
    tiene ningún mecanismo para ingestar respuestas de WhatsApp (el envío es manual, fuera
    del pipeline) — no hay señal real de "el negocio se interesó" que consultar. Si EQKO
    quiere expiración más inteligente (extender el plazo si el negocio está respondiendo),
    hace falta un módulo nuevo que ingeste esas respuestas — no existe hoy, esto no lo
    resuelve."""
    redis_client = Redis.from_url(settings.redis_url)
    store = SiteDeploymentStore(redis_client)
    deployer = VercelDeployer(
        token=settings.vercel_token,
        project_name=settings.vercel_project_name,
        team_id=settings.vercel_team_id,
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.expiry_days)
    deleted, kept, errors = 0, 0, 0

    for deployment in store.list_all():
        created_at = datetime.fromisoformat(deployment["created_at"])
        if created_at >= cutoff:
            kept += 1
            continue
        try:
            deployer.delete(deployment["deployment_id"])
            store.remove(deployment["place_id"])
            deleted += 1
        except Exception:
            logger.exception("failed to delete deployment for place_id=%s", deployment["place_id"])
            errors += 1

    logger.info("expiry sweep: deleted=%d kept=%d errors=%d", deleted, kept, errors)
    return {"deleted": deleted, "kept": kept, "errors": errors}


def main() -> None:
    settings = Settings()  # type: ignore[call-arg]
    run_expiry_sweep(settings)


if __name__ == "__main__":
    main()
