from datetime import datetime, timezone

from idempotency import IdempotencyStore
from tori_shared_types import LeadQualifiedEvent, MessageDraftedEvent, drafted_idempotency_key

from .brain import MessageDrafter
from tori_seda_consumer import CycleStats
from .rag import MessageExamplesRepository
from .streams import DraftedMessagePublisher
from .tracing import DraftTracer, NullTracer


class DraftHandler:
    """Handler del Módulo 4 para el consumer genérico de consumer.py — consume
    leadgen.lead_qualified, publica leadgen.message_drafted. Mismo tipo de resiliencia que
    QualifyHandler (Módulo 3): una excepción acá (JSON inválido del LLM, timeout, etc.) no se
    ackea y entra al ciclo de retry/backoff/DLQ genérico, sin código nuevo."""

    def __init__(
        self,
        examples_repository: MessageExamplesRepository,
        drafter: MessageDrafter,
        idempotency_store: IdempotencyStore,
        publisher: DraftedMessagePublisher,
        examples_limit: int = 3,
        tracer: DraftTracer = NullTracer(),
    ):
        self._examples_repository = examples_repository
        self._drafter = drafter
        self._idempotency_store = idempotency_store
        self._publisher = publisher
        self._examples_limit = examples_limit
        self._tracer = tracer

    def __call__(self, fields: dict, stats: CycleStats) -> None:
        raw = fields.get(b"data") or fields.get("data")
        lead = LeadQualifiedEvent.model_validate_json(raw)

        examples = self._examples_repository.find_similar(
            lead.tenant_id, lead.display_name, limit=self._examples_limit
        )
        result = self._drafter.draft(lead, examples)
        # Se traza el draft haya terminado en duplicado o no -- el LLM ya corrió, y es
        # exactamente ese paso el que Langfuse tiene que poder auditar (Módulo 6).
        self._tracer.record(lead, examples, result)

        event = MessageDraftedEvent(
            run_id=lead.run_id,
            tenant_id=lead.tenant_id,
            place_id=lead.place_id,
            display_name=lead.display_name,
            phone_e164=lead.phone_e164,
            message_text=result.message_text,
            gap_analysis=result.gap_analysis,
            model=result.model,
            drafted_at=datetime.now(timezone.utc),
        )

        # A propósito DESPUÉS de llamar al LLM, no antes: si se marcara la llave antes de
        # intentar redactar, un draft() que falla (JSON inválido, timeout) dejaría la llave
        # marcada igual, y el reintento posterior (que sí necesita volver a llamar al LLM)
        # se leería como "duplicado" y se ackearía sin publicar nunca el mensaje — el lead se
        # perdería en silencio. El costo real de este orden es una llamada al LLM de más en
        # el caso raro de redelivery entre publish y xack, que es preferible a esa pérdida.
        if not self._idempotency_store.mark_if_new(drafted_idempotency_key(lead.place_id)):
            stats.duplicate += 1
            return

        self._publisher.publish(event)
        stats.succeeded += 1
