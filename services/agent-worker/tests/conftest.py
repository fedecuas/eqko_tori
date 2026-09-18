import fakeredis
import pytest
from idempotency import IdempotencyStore
from tori_shared_types import STREAM_PLACE_EXTRACTED

from tori_seda_consumer import WorkerDependencies
from agent_worker.pipeline import QualifyHandler
from agent_worker.streams import QualifiedLeadPublisher


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis()


@pytest.fixture
def deps(redis_client):
    handler = QualifyHandler(
        idempotency_store=IdempotencyStore(redis_client),
        publisher=QualifiedLeadPublisher(redis_client),
    )
    return WorkerDependencies(
        redis_client=redis_client,
        handler=handler,
        consumer_group="agent-worker-cg",
        consumer_name="test-consumer",
        stream=STREAM_PLACE_EXTRACTED,
        base_backoff_ms=0,
        max_retries=1,
        jitter_fn=lambda: 1.0,
    )
