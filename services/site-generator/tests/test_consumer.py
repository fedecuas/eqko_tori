from datetime import datetime, timezone

import fakeredis
from idempotency import IdempotencyStore
from tori_seda_consumer import WorkerDependencies, run_cycle
from tori_shared_types import (
    STREAM_MESSAGE_DRAFTED,
    STREAM_SITE_GENERATED,
    MessageDraftedEvent,
    dlq_stream_name,
)

from site_generator.handler import SiteGenerationHandler
from site_generator.quota import WeeklyQuota
from site_generator.store import SiteDeploymentStore
from site_generator.streams import SiteGeneratedPublisher

from .fakes import StubDeployer

EVENT_KWARGS = dict(
    run_id="run-1",
    tenant_id="alba",
    place_id="place-1",
    display_name="Taquería El Buen Sazón",
    phone_e164="+523312345678",
    message_text="Hola! Vimos tu taquería...",
    gap_analysis="Sin web propia.",
    model="stub-model",
    drafted_at=datetime.now(timezone.utc),
)


def _deps(redis_client, deployer):
    handler = SiteGenerationHandler(
        deployer=deployer,
        quota=WeeklyQuota(redis_client, max_per_week=50),
        deployment_store=SiteDeploymentStore(redis_client),
        idempotency_store=IdempotencyStore(redis_client),
        publisher=SiteGeneratedPublisher(redis_client),
    )
    return WorkerDependencies(
        redis_client=redis_client,
        handler=handler,
        consumer_group="site-generator-cg",
        consumer_name="test-site-generator",
        stream=STREAM_MESSAGE_DRAFTED,
        base_backoff_ms=0,
        max_retries=1,
        jitter_fn=lambda: 1.0,
    )


def _publish_message_drafted(redis_client):
    event = MessageDraftedEvent(**EVENT_KWARGS)
    redis_client.xadd(STREAM_MESSAGE_DRAFTED, {"data": event.model_dump_json()})


def test_successful_generation_is_published_and_original_message_acked():
    redis_client = fakeredis.FakeRedis()
    _publish_message_drafted(redis_client)

    stats = run_cycle(_deps(redis_client, StubDeployer()))

    assert stats.succeeded == 1
    assert len(redis_client.xrange(STREAM_SITE_GENERATED)) == 1
    pending = redis_client.xpending_range(STREAM_MESSAGE_DRAFTED, "site-generator-cg", min="-", max="+", count=10)
    assert pending == []


def test_deploy_failure_is_retried_and_then_moved_to_dlq_via_the_generic_loop():
    """Cero código nuevo de retry/backoff/DLQ para este servicio, igual que agent-worker y
    dispatcher -- es la misma infraestructura de packages/seda-consumer."""
    redis_client = fakeredis.FakeRedis()
    _publish_message_drafted(redis_client)
    deployer = StubDeployer(error=RuntimeError("vercel deploy failed"))
    deps = _deps(redis_client, deployer)

    first = run_cycle(deps)
    assert first.errors == 1

    second = run_cycle(deps)
    assert second.reclaimed == 1

    third = run_cycle(deps)
    assert third.dlq == 1

    assert len(redis_client.xrange(dlq_stream_name(STREAM_MESSAGE_DRAFTED))) == 1
