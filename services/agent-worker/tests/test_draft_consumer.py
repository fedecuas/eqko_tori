from datetime import datetime, timezone

import fakeredis
from idempotency import IdempotencyStore
from tori_shared_types import (
    STREAM_LEAD_QUALIFIED,
    STREAM_MESSAGE_DRAFTED,
    LeadQualifiedEvent,
    dlq_stream_name,
)

from tori_seda_consumer import WorkerDependencies, run_cycle
from agent_worker.draft_pipeline import DraftHandler
from agent_worker.streams import DraftedMessagePublisher

from .fakes import StubMessageDrafter, StubMessageExamplesRepository

LEAD_KWARGS = dict(
    run_id="run-1",
    tenant_id="alba",
    place_id="place-1",
    display_name="Taquería El Buen Sazón",
    formatted_address="Av. Siempre Viva 123",
    phone_e164="+523312345678",
    qualified_at=datetime.now(timezone.utc),
)


def _deps(redis_client, drafter):
    handler = DraftHandler(
        examples_repository=StubMessageExamplesRepository(),
        drafter=drafter,
        idempotency_store=IdempotencyStore(redis_client),
        publisher=DraftedMessagePublisher(redis_client),
    )
    return WorkerDependencies(
        redis_client=redis_client,
        handler=handler,
        consumer_group="agent-worker-brain-cg",
        consumer_name="test-brain-consumer",
        stream=STREAM_LEAD_QUALIFIED,
        base_backoff_ms=0,
        max_retries=1,
        jitter_fn=lambda: 1.0,
    )


def _publish_lead_qualified(redis_client):
    lead = LeadQualifiedEvent(**LEAD_KWARGS)
    redis_client.xadd(STREAM_LEAD_QUALIFIED, {"data": lead.model_dump_json()})


def test_successful_draft_is_published_and_original_message_acked():
    redis_client = fakeredis.FakeRedis()
    _publish_lead_qualified(redis_client)

    stats = run_cycle(_deps(redis_client, StubMessageDrafter()))

    assert stats.succeeded == 1
    assert len(redis_client.xrange(STREAM_MESSAGE_DRAFTED)) == 1
    pending = redis_client.xpending_range(STREAM_LEAD_QUALIFIED, "agent-worker-brain-cg", min="-", max="+", count=10)
    assert pending == []


def test_llm_failure_is_retried_and_then_moved_to_dlq_via_the_generic_loop():
    """Ninguna línea nueva de retry/backoff/DLQ para este stage -- es la misma
    infraestructura de consumer.py que ya probó test_consumer.py para el Módulo 3."""
    redis_client = fakeredis.FakeRedis()
    _publish_lead_qualified(redis_client)
    deps = _deps(redis_client, StubMessageDrafter(error=RuntimeError("gemini timeout")))

    first = run_cycle(deps)
    assert first.errors == 1
    assert first.dlq == 0

    second = run_cycle(deps)
    assert second.reclaimed == 1
    assert second.errors == 1

    third = run_cycle(deps)
    assert third.dlq == 1

    assert len(redis_client.xrange(dlq_stream_name(STREAM_LEAD_QUALIFIED))) == 1
    pending = redis_client.xpending_range(STREAM_LEAD_QUALIFIED, "agent-worker-brain-cg", min="-", max="+", count=10)
    assert pending == []
