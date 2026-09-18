from datetime import datetime, timezone

from idempotency import IdempotencyStore
from tori_shared_types import LeadQualifiedEvent, PlaceExtractedEvent

from tori_seda_consumer import CycleStats
from .phone import format_e164
from .streams import QualifiedLeadPublisher


def qualify(event: PlaceExtractedEvent) -> LeadQualifiedEvent | None:
    """Filtro (website == null && phone != null) + formateo E.164 — CLAUDE.md sección 2.
    None significa "no califica" (dato de negocio, no error): sin sitio propio o sin
    teléfono usable no es un lead viable para TORI. No confundir con una excepción, que sí
    cuenta como fallo de procesamiento y dispara retry/DLQ en el worker."""
    if event.website_uri is not None:
        return None
    if not event.international_phone_number:
        return None

    phone_e164 = format_e164(event.international_phone_number)
    if phone_e164 is None:
        return None

    return LeadQualifiedEvent(
        run_id=event.run_id,
        tenant_id=event.tenant_id,
        place_id=event.place_id,
        display_name=event.display_name,
        formatted_address=event.formatted_address,
        phone_e164=phone_e164,
        qualified_at=datetime.now(timezone.utc),
    )


class QualifyHandler:
    """Handler del Módulo 3 para el consumer genérico de consumer.py — consume
    leadgen.place_extracted, publica leadgen.lead_qualified."""

    def __init__(self, idempotency_store: IdempotencyStore, publisher: QualifiedLeadPublisher):
        self._idempotency_store = idempotency_store
        self._publisher = publisher

    def __call__(self, fields: dict, stats: CycleStats) -> None:
        raw = fields.get(b"data") or fields.get("data")
        event = PlaceExtractedEvent.model_validate_json(raw)

        lead = qualify(event)
        if lead is None:
            stats.skipped += 1
            return

        if not self._idempotency_store.mark_if_new(lead.idempotency_key()):
            # Redelivery del mismo place_id (crash entre publish y xack en un ciclo anterior)
            # — ya se publicó, no duplicar.
            stats.duplicate += 1
            return

        self._publisher.publish(lead)
        stats.succeeded += 1
