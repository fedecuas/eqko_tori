from datetime import datetime, timezone

import fakeredis
import pytest
from idempotency import IdempotencyStore
from tori_seda_consumer import CycleStats
from tori_shared_types import STREAM_SITE_GENERATED, MessageDraftedEvent

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


def _handler(redis_client, deployer=None, max_per_week=50):
    return SiteGenerationHandler(
        deployer=deployer or StubDeployer(),
        quota=WeeklyQuota(redis_client, max_per_week=max_per_week),
        deployment_store=SiteDeploymentStore(redis_client),
        idempotency_store=IdempotencyStore(redis_client),
        publisher=SiteGeneratedPublisher(redis_client),
    )


def _fields():
    return {"data": MessageDraftedEvent(**EVENT_KWARGS).model_dump_json().encode()}


def test_handler_deploys_and_publishes_with_landing_url():
    redis_client = fakeredis.FakeRedis()
    deployer = StubDeployer()
    handler = _handler(redis_client, deployer=deployer)
    stats = CycleStats()

    handler(_fields(), stats)

    assert stats.succeeded == 1
    assert len(deployer.deploy_calls) == 1
    entries = redis_client.xrange(STREAM_SITE_GENERATED)
    assert len(entries) == 1


def test_handler_reuses_an_existing_deployment_without_redeploying():
    redis_client = fakeredis.FakeRedis()
    deployer = StubDeployer()
    handler = _handler(redis_client, deployer=deployer)

    handler(_fields(), CycleStats())
    # simula redelivery del mismo place_id en un evento nuevo (otro entry, mismo negocio)
    second_stats = CycleStats()
    handler(_fields(), second_stats)

    assert len(deployer.deploy_calls) == 1  # no se volvió a deployar
    assert second_stats.duplicate == 1  # pero sí se detectó como evento duplicado


def test_handler_degrades_gracefully_when_quota_is_exhausted():
    redis_client = fakeredis.FakeRedis()
    deployer = StubDeployer()
    handler = _handler(redis_client, deployer=deployer, max_per_week=0)
    stats = CycleStats()

    handler(_fields(), stats)

    assert stats.skipped == 1
    assert stats.succeeded == 0
    assert len(deployer.deploy_calls) == 0

    entries = redis_client.xrange(STREAM_SITE_GENERATED)
    assert len(entries) == 1  # el evento se publica igual, sin landing_url
    import json

    published = json.loads(entries[0][1][b"data"])
    assert published["landing_url"] is None


def test_handler_propagates_deploy_errors_for_the_generic_retry_dlq_cycle():
    redis_client = fakeredis.FakeRedis()
    handler = _handler(redis_client, deployer=StubDeployer(error=RuntimeError("vercel down")))

    with pytest.raises(RuntimeError):
        handler(_fields(), CycleStats())
