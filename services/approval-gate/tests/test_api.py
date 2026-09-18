from datetime import datetime, timezone

from tori_shared_types import STREAM_LEAD_APPROVED, SiteGeneratedEvent

from approval_gate.store import PendingApprovalStore

from .conftest import INTERNAL_API_KEY

AUTH_HEADERS = {"X-Internal-Api-Key": INTERNAL_API_KEY}

EVENT_KWARGS = dict(
    run_id="run-1",
    tenant_id="alba",
    place_id="place-1",
    display_name="Taquería El Buen Sazón",
    phone_e164="+523312345678",
    message_text="Hola! Vimos tu taquería...",
    gap_analysis="Sin web propia.",
    model="stub-model",
    landing_url="https://abc123.vercel.app",
    generated_at=datetime.now(timezone.utc),
)


def _seed_pending(redis_client, **overrides):
    store = PendingApprovalStore(redis_client)
    store.add(SiteGeneratedEvent(**{**EVENT_KWARGS, **overrides}))


def test_health_does_not_require_auth(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_list_pending_without_api_key_is_rejected(client):
    response = client.get("/pending", params={"tenant_id": "alba"})
    assert response.status_code == 401


def test_list_pending_returns_seeded_leads(client, redis_client):
    _seed_pending(redis_client)

    response = client.get("/pending", params={"tenant_id": "alba"}, headers=AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["place_id"] == "place-1"


def test_approve_publishes_lead_approved_and_removes_from_pending(client, redis_client):
    _seed_pending(redis_client)

    response = client.post("/leads/place-1/approve", params={"tenant_id": "alba"}, headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"status": "approved", "place_id": "place-1"}

    assert len(redis_client.xrange(STREAM_LEAD_APPROVED)) == 1
    assert client.get("/pending", params={"tenant_id": "alba"}, headers=AUTH_HEADERS).json() == []


def test_reject_removes_without_publishing_to_lead_approved(client, redis_client):
    _seed_pending(redis_client)

    response = client.post("/leads/place-1/reject", params={"tenant_id": "alba"}, headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"status": "rejected", "place_id": "place-1"}
    assert redis_client.xrange(STREAM_LEAD_APPROVED) == []
    assert client.get("/pending", params={"tenant_id": "alba"}, headers=AUTH_HEADERS).json() == []


def test_approve_a_lead_from_another_tenant_is_404(client, redis_client):
    _seed_pending(redis_client, tenant_id="alba")

    response = client.post("/leads/place-1/approve", params={"tenant_id": "otro-tenant"}, headers=AUTH_HEADERS)

    assert response.status_code == 404
    # y el lead real de "alba" sigue pendiente, no se tocó
    assert len(client.get("/pending", params={"tenant_id": "alba"}, headers=AUTH_HEADERS).json()) == 1


def test_approve_unknown_place_id_is_404(client):
    response = client.post("/leads/does-not-exist/approve", params={"tenant_id": "alba"}, headers=AUTH_HEADERS)
    assert response.status_code == 404
