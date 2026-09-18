from datetime import datetime, timezone

import fakeredis
import pytest
from idempotency import IdempotencyStore
from tori_shared_types import STREAM_MESSAGE_DRAFTED, LeadQualifiedEvent

from tori_seda_consumer import CycleStats
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


def _make_handler(redis_client, drafter=None, examples_repository=None):
    return DraftHandler(
        examples_repository=examples_repository or StubMessageExamplesRepository(),
        drafter=drafter or StubMessageDrafter(),
        idempotency_store=IdempotencyStore(redis_client),
        publisher=DraftedMessagePublisher(redis_client),
    )


def _fields_for(lead: LeadQualifiedEvent) -> dict:
    return {"data": lead.model_dump_json().encode()}


def test_handler_publishes_the_drafted_message():
    redis_client = fakeredis.FakeRedis()
    handler = _make_handler(redis_client)
    lead = LeadQualifiedEvent(**LEAD_KWARGS)
    stats = CycleStats()

    handler(_fields_for(lead), stats)

    assert stats.succeeded == 1
    assert len(redis_client.xrange(STREAM_MESSAGE_DRAFTED)) == 1


def test_handler_passes_rag_examples_to_the_drafter():
    redis_client = fakeredis.FakeRedis()
    drafter = StubMessageDrafter()
    examples_repository = StubMessageExamplesRepository()
    handler = _make_handler(redis_client, drafter=drafter, examples_repository=examples_repository)
    lead = LeadQualifiedEvent(**LEAD_KWARGS)

    handler(_fields_for(lead), CycleStats())

    assert examples_repository.calls[0]["tenant_id"] == "alba"
    assert drafter.calls[0]["lead"].place_id == "place-1"


def test_handler_does_not_call_the_drafter_twice_for_an_already_drafted_lead():
    redis_client = fakeredis.FakeRedis()
    drafter = StubMessageDrafter()
    handler = _make_handler(redis_client, drafter=drafter)
    lead = LeadQualifiedEvent(**LEAD_KWARGS)

    handler(_fields_for(lead), CycleStats())
    second_stats = CycleStats()
    handler(_fields_for(lead), second_stats)

    assert second_stats.duplicate == 1
    assert len(drafter.calls) == 2  # sí se vuelve a llamar al LLM -- ver comentario en draft_pipeline.py
    assert len(redis_client.xrange(STREAM_MESSAGE_DRAFTED)) == 1  # pero no se duplica el publish


def test_handler_propagates_drafter_errors_for_the_generic_retry_dlq_cycle():
    redis_client = fakeredis.FakeRedis()
    handler = _make_handler(redis_client, drafter=StubMessageDrafter(error=RuntimeError("gemini timeout")))
    lead = LeadQualifiedEvent(**LEAD_KWARGS)

    with pytest.raises(RuntimeError):
        handler(_fields_for(lead), CycleStats())


def test_handler_records_a_trace_for_every_successful_draft():
    redis_client = fakeredis.FakeRedis()
    recorded = []

    class RecordingTracer:
        def record(self, lead, examples, result):
            recorded.append((lead.place_id, result.message_text))

    handler = DraftHandler(
        examples_repository=StubMessageExamplesRepository(),
        drafter=StubMessageDrafter(),
        idempotency_store=IdempotencyStore(redis_client),
        publisher=DraftedMessagePublisher(redis_client),
        tracer=RecordingTracer(),
    )
    lead = LeadQualifiedEvent(**LEAD_KWARGS)

    handler(_fields_for(lead), CycleStats())

    assert recorded == [("place-1", "Hola! Vimos que tu negocio no tiene web propia, te contamos cómo ayudamos.")]
