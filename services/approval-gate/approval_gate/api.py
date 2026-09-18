from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from tori_shared_types import LeadApprovedEvent

from .auth import require_internal_api_key
from .dependencies import get_publisher, get_store
from .store import PendingApprovalStore
from .streams import ApprovedLeadPublisher

app = FastAPI(title="TORI Approval Gate", version="0.1.0")


@app.get("/pending", dependencies=[Depends(require_internal_api_key)])
def list_pending(tenant_id: str, store: PendingApprovalStore = Depends(get_store)) -> list[dict]:
    return store.list_pending(tenant_id)


@app.post("/leads/{place_id}/approve", dependencies=[Depends(require_internal_api_key)])
def approve(
    place_id: str,
    tenant_id: str,
    store: PendingApprovalStore = Depends(get_store),
    publisher: ApprovedLeadPublisher = Depends(get_publisher),
) -> dict:
    lead = _get_or_404(store, place_id, tenant_id)

    event = LeadApprovedEvent(
        run_id=lead["run_id"],
        tenant_id=lead["tenant_id"],
        place_id=lead["place_id"],
        display_name=lead["display_name"],
        phone_e164=lead["phone_e164"],
        message_text=lead["message_text"],
        gap_analysis=lead["gap_analysis"],
        model=lead["model"],
        landing_url=lead.get("landing_url") or None,
        approved_at=datetime.now(timezone.utc),
    )
    publisher.publish(event)
    store.remove(place_id, tenant_id)

    return {"status": "approved", "place_id": place_id}


@app.post("/leads/{place_id}/reject", dependencies=[Depends(require_internal_api_key)])
def reject(place_id: str, tenant_id: str, store: PendingApprovalStore = Depends(get_store)) -> dict:
    _get_or_404(store, place_id, tenant_id)
    store.remove(place_id, tenant_id)
    # A propósito no se publica nada -- un lead rechazado nunca llega a dispatcher. No hay
    # stream "lead_rejected" todavía: no hay ningún consumer que lo necesite hoy.
    return {"status": "rejected", "place_id": place_id}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _get_or_404(store: PendingApprovalStore, place_id: str, tenant_id: str) -> dict:
    lead = store.get(place_id)
    # tenant_id se valida acá, no solo se usa para listar: evita que alguien con la API key
    # apruebe/rechace un lead de otro tenant adivinando el place_id.
    if lead is None or lead["tenant_id"] != tenant_id:
        raise HTTPException(status_code=404, detail="lead not found or not pending for this tenant")
    return lead
