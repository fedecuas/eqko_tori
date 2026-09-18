from datetime import datetime, timezone

import fakeredis
from tori_seda_consumer import CycleStats
from tori_shared_types import SiteGeneratedEvent

from approval_gate.intake_pipeline import IntakeHandler
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


def test_handler_stores_the_drafted_message_as_pending():
    redis_client = fakeredis.FakeRedis()
    store = PendingApprovalStore(redis_client)
    handler = IntakeHandler(store)
    event = SiteGeneratedEvent(**EVENT_KWARGS)
    stats = CycleStats()

    handler({"data": event.model_dump_json().encode()}, stats)

    assert stats.succeeded == 1
    assert store.get("place-1") is not None
