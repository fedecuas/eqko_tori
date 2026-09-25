from datetime import datetime

from pydantic import BaseModel

# Naming: <dominio>.<evento> — ver CLAUDE.md sección 5
STREAM_PLACE_EXTRACTED = "leadgen.place_extracted"
STREAM_LEAD_QUALIFIED = "leadgen.lead_qualified"
STREAM_MESSAGE_DRAFTED = "leadgen.message_drafted"
STREAM_SITE_GENERATED = "leadgen.site_generated"
STREAM_LEAD_APPROVED = "leadgen.lead_approved"
STREAM_LEAD_DISPATCHED = "leadgen.lead_dispatched"

# `place_id` es el id del negocio en su fuente de origen. Los de Google Places van tal cual
# ("ChIJ..."); los de DENUE (INEGI) llevan este prefijo para no colisionar y para que quien
# necesite hablar con Google (fotos en site-generator) pueda saltárselos.
DENUE_PLACE_ID_PREFIX = "denue:"


def is_google_place_id(place_id: str) -> bool:
    return not place_id.startswith(DENUE_PLACE_ID_PREFIX)


class PlaceExtractedEvent(BaseModel):
    """Publicado por services/extractor, consumido por services/agent-worker."""

    run_id: str
    tenant_id: str
    place_id: str
    display_name: str
    formatted_address: str | None = None
    website_uri: str | None = None
    international_phone_number: str | None = None
    extracted_at: datetime

    def idempotency_key(self) -> str:
        # Dedupe global por negocio, no por run — ver CLAUDE.md sección 5.
        return f"event:leadgen:{self.place_id}"


def drafted_idempotency_key(place_id: str) -> str:
    # Función aparte (no solo un método de instancia) porque agent-worker necesita esta
    # llave ANTES de llamar al LLM para no pagar una redacción que ya se descarta por
    # duplicada — ver DraftHandler en services/agent-worker.
    return f"event:leadgen:drafted:{place_id}"


class MessageDraftedEvent(BaseModel):
    """Publicado por services/agent-worker (nodo Gemini/RAG, Módulo 4) — consumido por
    services/dispatcher tras el gate de aprobación humana (CLAUDE.md sección 2)."""

    run_id: str
    tenant_id: str
    place_id: str
    display_name: str
    phone_e164: str
    message_text: str
    gap_analysis: str
    model: str
    drafted_at: datetime

    def idempotency_key(self) -> str:
        return drafted_idempotency_key(self.place_id)


def site_generated_idempotency_key(place_id: str) -> str:
    return f"event:leadgen:site_generated:{place_id}"


class SiteGeneratedEvent(BaseModel):
    """Publicado por services/site-generator (Módulo 7) — mismos campos que
    MessageDraftedEvent más `landing_url`. Consumido por services/approval-gate, que ahora
    revisa mensaje + sitio juntos antes de aprobar (CLAUDE.md sección 9).

    `landing_url` es `None` si se agotó la cuota semanal (`WeeklyQuota`, 50 leads/semana
    aprobado) — el lead sigue el pipeline igual, sin sitio, degradando a como funcionaba
    antes del Módulo 7. Nunca se pierde un lead por falta de cupo."""

    run_id: str
    tenant_id: str
    place_id: str
    display_name: str
    phone_e164: str
    message_text: str
    gap_analysis: str
    model: str
    landing_url: str | None
    generated_at: datetime

    def idempotency_key(self) -> str:
        return site_generated_idempotency_key(self.place_id)


class LeadQualifiedEvent(BaseModel):
    """Publicado por services/agent-worker tras el filtro (website==null && phone!=null) y el
    formateo E.164 — consumido por el nodo Gemini/RAG del Módulo 4."""

    run_id: str
    tenant_id: str
    place_id: str
    display_name: str
    formatted_address: str | None = None
    phone_e164: str
    qualified_at: datetime

    def idempotency_key(self) -> str:
        # Dedupe distinto al de extracción: protege contra redelivery del consumer group,
        # no contra negocios repetidos entre runs (eso ya lo filtró el extractor).
        return f"event:leadgen:qualified:{self.place_id}"


def dlq_stream_name(stream: str) -> str:
    return f"{stream}.dlq"


def approved_idempotency_key(place_id: str) -> str:
    return f"event:leadgen:approved:{place_id}"


class LeadApprovedEvent(BaseModel):
    """Publicado por services/approval-gate (Módulo 6) cuando un humano aprueba un mensaje
    redactado desde el dashboard — reemplaza a MessageDraftedEvent como lo que
    services/dispatcher realmente consume: cierra la brecha documentada en el Módulo 5
    (dispatcher no debía salir directo de message_drafted sin este gate).

    `landing_url` viaja desde SiteGeneratedEvent (Módulo 7) — puede ser `None` si no había
    cupo semanal cuando se generó."""

    run_id: str
    tenant_id: str
    place_id: str
    display_name: str
    phone_e164: str
    message_text: str
    gap_analysis: str
    model: str
    landing_url: str | None = None
    approved_at: datetime

    def idempotency_key(self) -> str:
        return approved_idempotency_key(self.place_id)


def dispatched_idempotency_key(place_id: str) -> str:
    return f"event:leadgen:dispatched:{place_id}"


class LeadDispatchedEvent(BaseModel):
    """Publicado por services/dispatcher (Módulo 5) tras un upsert exitoso en el output del
    tenant (Airtable/Sheets/CRM) — terminal del pipeline SEDA de TORI."""

    run_id: str
    tenant_id: str
    place_id: str
    output: str
    dispatched_at: datetime

    def idempotency_key(self) -> str:
        return dispatched_idempotency_key(self.place_id)
