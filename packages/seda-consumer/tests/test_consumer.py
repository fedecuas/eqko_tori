import fakeredis
import pytest
from tori_seda_consumer import CycleStats, WorkerDependencies, dlq_stream_name, run_cycle

STREAM = "test.stream"
GROUP = "test-cg"


def _deps(redis_client, handler, **overrides):
    return WorkerDependencies(
        redis_client=redis_client,
        handler=handler,
        consumer_group=GROUP,
        consumer_name="test-consumer",
        stream=STREAM,
        base_backoff_ms=0,
        max_retries=1,
        jitter_fn=lambda: 1.0,
        **overrides,
    )


def _succeeding_handler(fields: dict, stats: CycleStats) -> None:
    stats.succeeded += 1


def test_new_message_is_processed_and_acked():
    redis_client = fakeredis.FakeRedis()
    redis_client.xadd(STREAM, {"data": "hello"})

    stats = run_cycle(_deps(redis_client, _succeeding_handler))

    assert stats.processed == 1
    assert stats.succeeded == 1
    pending = redis_client.xpending_range(STREAM, GROUP, min="-", max="+", count=10)
    assert pending == []


def test_empty_stream_processes_nothing():
    redis_client = fakeredis.FakeRedis()

    stats = run_cycle(_deps(redis_client, _succeeding_handler))

    assert stats.processed == 0


def test_a_failing_handler_is_retried_then_moved_to_dlq():
    redis_client = fakeredis.FakeRedis()
    redis_client.xadd(STREAM, {"data": "hello"})

    def failing_handler(fields, stats):
        raise RuntimeError("boom")

    deps = _deps(redis_client, failing_handler)

    first = run_cycle(deps)
    assert first.errors == 1
    assert first.dlq == 0

    second = run_cycle(deps)
    assert second.reclaimed == 1
    assert second.errors == 1

    third = run_cycle(deps)
    assert third.dlq == 1

    assert len(redis_client.xrange(dlq_stream_name(STREAM))) == 1
    pending = redis_client.xpending_range(STREAM, GROUP, min="-", max="+", count=10)
    assert pending == []


def test_second_call_to_ensure_consumer_group_does_not_raise():
    redis_client = fakeredis.FakeRedis()
    redis_client.xadd(STREAM, {"data": "hello"})

    run_cycle(_deps(redis_client, _succeeding_handler))
    # segunda vez: BUSYGROUP debe ignorarse silenciosamente
    run_cycle(_deps(redis_client, _succeeding_handler))
