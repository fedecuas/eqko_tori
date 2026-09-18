from datetime import datetime, timezone

import fakeredis
import pytest
from idempotency import IdempotencyStore
from tori_seda_consumer import CycleStats
from tori_shared_types import STREAM_LEAD_DISPATCHED, LeadApprovedEvent

from dispatcher.dispatch_pipeline import DispatchHandler
from dispatcher.outputs import StaticOutputRouter
from dispatcher.rate_limiter import RateLimiter
from dispatcher.streams import DispatchedLeadPublisher

from .fakes import FakeClock, StubOutput

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


def _handler(redis_client, output, rate_limiter=None):
    return DispatchHandler(
        output_router=StaticOutputRouter({"alba": output}),
        rate_limiter=rate_limiter or RateLimiter(redis_client, max_requests=100, window_seconds=1.0, sleep_fn=lambda s: None),
        idempotency_store=IdempotencyStore(redis_client),
        publisher=DispatchedLeadPublisher(redis_client),
    )


def _fields():
    return {"data": LeadApprovedEvent(**EVENT_KWARGS).model_dump_json().encode()}


def test_handler_upserts_and_publishes_dispatched_event():
    redis_client = fakeredis.FakeRedis()
    output = StubOutput(name="airtable")
    handler = _handler(redis_client, output)
    stats = CycleStats()

    handler(_fields(), stats)

    assert stats.succeeded == 1
    assert len(output.calls) == 1
    assert output.calls[0].place_id == "place-1"
    assert len(redis_client.xrange(STREAM_LEAD_DISPATCHED)) == 1


def test_handler_uses_the_rate_limiter_with_the_output_specific_key():
    redis_client = fakeredis.FakeRedis()
    clock = FakeClock()
    rate_limiter = RateLimiter(redis_client, max_requests=1, window_seconds=1.0, sleep_fn=clock.sleep, clock_fn=clock.time)
    output = StubOutput(name="airtable")
    handler = _handler(redis_client, output, rate_limiter=rate_limiter)

    handler(_fields(), CycleStats())
    handler(_fields(), CycleStats())  # mismo tenant+output, segunda llamada en la misma ventana

    assert clock.sleeps == [1.0]


def test_handler_raises_for_a_tenant_without_configured_output():
    redis_client = fakeredis.FakeRedis()
    handler = DispatchHandler(
        output_router=StaticOutputRouter({}),
        rate_limiter=RateLimiter(redis_client, max_requests=100, window_seconds=1.0, sleep_fn=lambda s: None),
        idempotency_store=IdempotencyStore(redis_client),
        publisher=DispatchedLeadPublisher(redis_client),
    )

    with pytest.raises(ValueError, match="alba"):
        handler(_fields(), CycleStats())


def test_handler_does_not_republish_an_already_dispatched_lead():
    redis_client = fakeredis.FakeRedis()
    output = StubOutput(name="airtable")
    handler = _handler(redis_client, output)

    handler(_fields(), CycleStats())
    second_stats = CycleStats()
    handler(_fields(), second_stats)

    assert second_stats.duplicate == 1
    assert len(output.calls) == 2  # el upsert es idempotente del lado del output, se repite sin drama
    assert len(redis_client.xrange(STREAM_LEAD_DISPATCHED)) == 1  # pero no se duplica el evento


def test_handler_propagates_output_errors_for_the_generic_retry_dlq_cycle():
    redis_client = fakeredis.FakeRedis()
    output = StubOutput(error=RuntimeError("airtable 500"))
    handler = _handler(redis_client, output)

    with pytest.raises(RuntimeError):
        handler(_fields(), CycleStats())
