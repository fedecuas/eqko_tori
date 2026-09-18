from datetime import datetime, timezone

from idempotency import IdempotencyStore
from tori_seda_consumer import CycleStats
from tori_shared_types import LeadApprovedEvent, LeadDispatchedEvent, dispatched_idempotency_key

from .outputs import OutputRouter
from .rate_limiter import RateLimiter
from .streams import DispatchedLeadPublisher


class DispatchHandler:
    """Handler del Módulo 5 para el consumer genérico de packages/seda-consumer — consume
    leadgen.lead_approved, publica leadgen.lead_dispatched.

    Desde el Módulo 6 consume lead_approved (no message_drafted directo): el gate de
    aprobación humana de CLAUDE.md sección 2 vive en services/approval-gate, que es quien
    publica lead_approved recién cuando un humano aprueba desde su API. Antes del Módulo 6
    esto consumía message_drafted sin gate — brecha ya cerrada, ver CLAUDE.md."""

    def __init__(
        self,
        output_router: OutputRouter,
        rate_limiter: RateLimiter,
        idempotency_store: IdempotencyStore,
        publisher: DispatchedLeadPublisher,
    ):
        self._output_router = output_router
        self._rate_limiter = rate_limiter
        self._idempotency_store = idempotency_store
        self._publisher = publisher

    def __call__(self, fields: dict, stats: CycleStats) -> None:
        raw = fields.get(b"data") or fields.get("data")
        event = LeadApprovedEvent.model_validate_json(raw)

        output = self._output_router.get_output(event.tenant_id)
        self._rate_limiter.acquire(f"dispatch:{output.name}:{event.tenant_id}")
        # Idempotente por diseño (performUpsert de Airtable / find-or-update de Sheets): una
        # redelivery que vuelve a llamar acá no crea una fila duplicada, solo reescribe la
        # misma — más barato de aceptar que en el nodo Gemini (Módulo 4), donde el costo de
        # una llamada de más sí importaba.
        output.upsert(event)

        dispatched = LeadDispatchedEvent(
            run_id=event.run_id,
            tenant_id=event.tenant_id,
            place_id=event.place_id,
            output=output.name,
            dispatched_at=datetime.now(timezone.utc),
        )

        if not self._idempotency_store.mark_if_new(dispatched_idempotency_key(event.place_id)):
            stats.duplicate += 1
            return

        self._publisher.publish(dispatched)
        stats.succeeded += 1
