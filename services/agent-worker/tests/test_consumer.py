from datetime import datetime, timezone

from tori_shared_types import STREAM_LEAD_QUALIFIED, STREAM_PLACE_EXTRACTED, PlaceExtractedEvent, dlq_stream_name

from tori_seda_consumer import run_cycle

BASE_KWARGS = dict(
    run_id="run-1",
    tenant_id="alba",
    place_id="place-1",
    display_name="Taquería El Buen Sazón",
    formatted_address="Av. Siempre Viva 123",
    extracted_at=datetime.now(timezone.utc),
)


def _publish_place_extracted(redis_client, **overrides):
    event = PlaceExtractedEvent(**{**BASE_KWARGS, **overrides})
    return redis_client.xadd(STREAM_PLACE_EXTRACTED, {"data": event.model_dump_json()})


def test_qualified_lead_is_published_and_original_message_acked(redis_client, deps):
    _publish_place_extracted(redis_client, website_uri=None, international_phone_number="+52 33 1234 5678")

    stats = run_cycle(deps)

    assert stats.processed == 1
    assert stats.succeeded == 1
    assert stats.skipped == 0

    qualified_entries = redis_client.xrange(STREAM_LEAD_QUALIFIED)
    assert len(qualified_entries) == 1

    pending = redis_client.xpending_range(STREAM_PLACE_EXTRACTED, "agent-worker-cg", min="-", max="+", count=10)
    assert pending == []  # acked, no queda en el PEL


def test_disqualified_lead_is_not_published_but_is_acked(redis_client, deps):
    _publish_place_extracted(redis_client, website_uri="https://tiene-sitio.com")

    stats = run_cycle(deps)

    assert stats.skipped == 1
    assert stats.succeeded == 0
    assert redis_client.xrange(STREAM_LEAD_QUALIFIED) == []

    pending = redis_client.xpending_range(STREAM_PLACE_EXTRACTED, "agent-worker-cg", min="-", max="+", count=10)
    assert pending == []


def test_second_cycle_does_not_reprocess_already_acked_messages(redis_client, deps):
    _publish_place_extracted(redis_client, website_uri=None, international_phone_number="+523312345678")

    run_cycle(deps)
    second_cycle = run_cycle(deps)

    assert second_cycle.processed == 0
    assert len(redis_client.xrange(STREAM_LEAD_QUALIFIED)) == 1


def test_processing_failure_is_retried_and_then_moved_to_dlq(redis_client, deps):
    # 'data' no es JSON válido -> PlaceExtractedEvent.model_validate_json revienta,
    # process_entry propaga, el mensaje no se ackea y queda en el PEL.
    redis_client.xadd(STREAM_PLACE_EXTRACTED, {"data": "not-json"})

    first = run_cycle(deps)   # XREADGROUP lo entrega, falla -> queda pending (times_delivered=1)
    assert first.processed == 1
    assert first.errors == 1

    second = run_cycle(deps)  # max_retries=1: 1 no es > 1 todavía -> se reclama y se reintenta
    assert second.reclaimed == 1
    assert second.errors == 1
    assert second.dlq == 0

    third = run_cycle(deps)   # ahora times_delivered=2 > max_retries=1 -> a la DLQ
    assert third.dlq == 1

    dlq_entries = redis_client.xrange(dlq_stream_name(STREAM_PLACE_EXTRACTED))
    assert len(dlq_entries) == 1

    pending = redis_client.xpending_range(STREAM_PLACE_EXTRACTED, "agent-worker-cg", min="-", max="+", count=10)
    assert pending == []  # se ackeó al mandarlo a la DLQ, no bloquea el stream


def test_disqualified_duplicate_event_is_not_republished(redis_client, deps):
    # Simula redelivery: dos negocios idénticos (mismo place_id) en el stream, como si el
    # extractor hubiera fallado en deduplicar o el consumer group hubiera redespachado.
    _publish_place_extracted(redis_client, website_uri=None, international_phone_number="+523312345678")
    _publish_place_extracted(redis_client, website_uri=None, international_phone_number="+523312345678")

    stats = run_cycle(deps)

    assert stats.succeeded == 1
    assert stats.duplicate == 1
    assert len(redis_client.xrange(STREAM_LEAD_QUALIFIED)) == 1
