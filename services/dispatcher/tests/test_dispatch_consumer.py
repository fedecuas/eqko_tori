from datetime import datetime, timezone

import fakeredis
from idempotency import IdempotencyStore
from tori_seda_consumer import WorkerDependencies, run_cycle
from tori_shared_types import (
    STREAM_LEAD_APPROVED,
    STREAM_LEAD_DISPATCHED,
    LeadApprovedEvent,
    dlq_stream_name,
)

from dispatcher.dispatch_pipeline import DispatchHandler
from dispatcher.outputs import StaticOutputRouter
from dispatcher.rate_limiter import RateLimiter
from dispatcher.streams import DispatchedLeadPublisher

from .fakes import StubOutput

EVENT_KWARGS = dict(
    run_id="run-1",
    tenant_id="alba",
    place_id="place-1",
    display_name="Taquería El Buen Sazón",
    phone_e164="+523312345678",
    message_text="Hola! Vimos tu taquería...",
    gap_analysis="Sin web propia.",
    model="stub-model",
    approved_at=datetime.now(timezone.utc),
)


def _deps(redis_client, output):
    handler = DispatchHandler(
        output_router=StaticOutputRouter({"alba": output}),
        rate_limiter=RateLimiter(redis_client, max_requests=100, window_seconds=1.0, sleep_fn=lambda s: None),
        idempotency_store=IdempotencyStore(redis_client),
        publisher=DispatchedLeadPublisher(redis_client),
    )
    return WorkerDependencies(
        redis_client=redis_client,
        handler=handler,
        consumer_group="dispatcher-cg",
        consumer_name="test-dispatcher",
        stream=STREAM_LEAD_APPROVED,
        base_backoff_ms=0,
        max_retries=1,
        jitter_fn=lambda: 1.0,
    )


def _publish_lead_approved(redis_client):
    event = LeadApprovedEvent(**EVENT_KWARGS)
    redis_client.xadd(STREAM_LEAD_APPROVED, {"data": event.model_dump_json()})


def test_successful_dispatch_is_published_and_original_message_acked():
    redis_client = fakeredis.FakeRedis()
    _publish_lead_approved(redis_client)

    stats = run_cycle(_deps(redis_client, StubOutput(name="airtable")))

    assert stats.succeeded == 1
    assert len(redis_client.xrange(STREAM_LEAD_DISPATCHED)) == 1
    pending = redis_client.xpending_range(STREAM_LEAD_APPROVED, "dispatcher-cg", min="-", max="+", count=10)
    assert pending == []


def test_output_failure_is_retried_and_then_moved_to_dlq_via_the_generic_loop():
    """Igual que en agent-worker: cero código nuevo de retry/backoff/DLQ para este servicio
    — es la misma infraestructura de packages/seda-consumer."""
    redis_client = fakeredis.FakeRedis()
    _publish_lead_approved(redis_client)
    output = StubOutput(name="airtable", error=RuntimeError("airtable rate limited (429)"))
    deps = _deps(redis_client, output)

    first = run_cycle(deps)
    assert first.errors == 1

    second = run_cycle(deps)
    assert second.reclaimed == 1

    third = run_cycle(deps)
    assert third.dlq == 1

    assert len(redis_client.xrange(dlq_stream_name(STREAM_LEAD_APPROVED))) == 1
