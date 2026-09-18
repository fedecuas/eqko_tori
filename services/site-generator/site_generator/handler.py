from datetime import datetime, timezone

from idempotency import IdempotencyStore
from tori_seda_consumer import CycleStats
from tori_shared_types import MessageDraftedEvent, SiteGeneratedEvent, site_generated_idempotency_key

from .builder import SiteBuilder
from .deploy import SiteDeployer, slug_for
from .quota import WeeklyQuota
from .store import SiteDeploymentStore
from .streams import SiteGeneratedPublisher


class SiteGenerationHandler:
    """Handler del Módulo 7 para el consumer genérico de packages/seda-consumer — consume
    leadgen.message_drafted, publica leadgen.site_generated.

    `stats.skipped` acá NO significa "no se publicó" (a diferencia de QualifyHandler) — el
    evento siempre se publica, con o sin sitio. Significa "se agotó el cupo semanal, este
    lead sigue el pipeline sin landing page" — un lead nunca se pierde por falta de cupo,
    degrada al comportamiento de antes del Módulo 7 (solo mensaje)."""

    def __init__(
        self,
        deployer: SiteDeployer,
        site_builder: SiteBuilder,
        quota: WeeklyQuota,
        deployment_store: SiteDeploymentStore,
        idempotency_store: IdempotencyStore,
        publisher: SiteGeneratedPublisher,
    ):
        self._deployer = deployer
        self._site_builder = site_builder
        self._quota = quota
        self._deployment_store = deployment_store
        self._idempotency_store = idempotency_store
        self._publisher = publisher

    def __call__(self, fields: dict, stats: CycleStats) -> None:
        raw = fields.get(b"data") or fields.get("data")
        event = MessageDraftedEvent.model_validate_json(raw)

        landing_url = self._resolve_landing_url(event)

        site_event = SiteGeneratedEvent(
            run_id=event.run_id,
            tenant_id=event.tenant_id,
            place_id=event.place_id,
            display_name=event.display_name,
            phone_e164=event.phone_e164,
            message_text=event.message_text,
            gap_analysis=event.gap_analysis,
            model=event.model,
            landing_url=landing_url,
            generated_at=datetime.now(timezone.utc),
        )

        # Después de deployar, no antes -- mismo motivo que en DraftHandler (Módulo 4): si
        # se marcara la llave antes de intentar deployar, un deploy que falla dejaría la
        # llave marcada sin haber publicado nada, y el reintento se leería como duplicado.
        if not self._idempotency_store.mark_if_new(site_generated_idempotency_key(event.place_id)):
            stats.duplicate += 1
            return

        self._publisher.publish(site_event)
        if landing_url is not None:
            stats.succeeded += 1
        else:
            stats.skipped += 1

    def _resolve_landing_url(self, event: MessageDraftedEvent) -> str | None:
        existing = self._deployment_store.get(event.place_id)
        if existing is not None:
            return existing["landing_url"]

        if not self._quota.try_consume():
            return None

        html = self._site_builder.build(event.place_id, event.display_name, event.phone_e164, event.gap_analysis)
        result = self._deployer.deploy(html, slug_for(event.place_id))
        self._deployment_store.record(event.place_id, result.url, result.deployment_id)
        return result.url
