from datetime import datetime, timezone

import fakeredis
from tori_shared_types import SiteGeneratedEvent

from approval_gate.store import PendingApprovalStore

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


def test_add_then_get_round_trips():
    store = PendingApprovalStore(fakeredis.FakeRedis())
    event = SiteGeneratedEvent(**EVENT_KWARGS)

    store.add(event)
    lead = store.get("place-1")

    assert lead["place_id"] == "place-1"
    assert lead["message_text"] == "Hola! Vimos tu taquería..."


def test_get_missing_place_id_returns_none():
    store = PendingApprovalStore(fakeredis.FakeRedis())

    assert store.get("does-not-exist") is None


def test_list_pending_is_scoped_to_tenant():
    store = PendingApprovalStore(fakeredis.FakeRedis())
    store.add(SiteGeneratedEvent(**{**EVENT_KWARGS, "place_id": "place-1", "tenant_id": "alba"}))
    store.add(SiteGeneratedEvent(**{**EVENT_KWARGS, "place_id": "place-2", "tenant_id": "otro-tenant"}))

    pending = store.list_pending("alba")

    assert [lead["place_id"] for lead in pending] == ["place-1"]


def test_remove_clears_both_the_lead_and_the_tenant_index():
    store = PendingApprovalStore(fakeredis.FakeRedis())
    event = SiteGeneratedEvent(**EVENT_KWARGS)
    store.add(event)

    store.remove("place-1", "alba")

    assert store.get("place-1") is None
    assert store.list_pending("alba") == []


def test_readding_the_same_place_id_does_not_duplicate_in_the_tenant_index():
    store = PendingApprovalStore(fakeredis.FakeRedis())
    event = SiteGeneratedEvent(**EVENT_KWARGS)

    store.add(event)
    store.add(event)  # redelivery del consumer group de intake

    assert len(store.list_pending("alba")) == 1
