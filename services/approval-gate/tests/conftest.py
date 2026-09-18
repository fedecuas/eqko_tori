import fakeredis
import pytest
from fastapi.testclient import TestClient

from approval_gate.api import app
from approval_gate.config import Settings
from approval_gate.dependencies import get_publisher, get_settings, get_store
from approval_gate.store import PendingApprovalStore
from approval_gate.streams import ApprovedLeadPublisher

INTERNAL_API_KEY = "test-internal-key"


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis()


@pytest.fixture
def client(redis_client):
    app.dependency_overrides[get_settings] = lambda: Settings(
        redis_url="redis://testing", tori_internal_api_key=INTERNAL_API_KEY
    )
    app.dependency_overrides[get_store] = lambda: PendingApprovalStore(redis_client)
    app.dependency_overrides[get_publisher] = lambda: ApprovedLeadPublisher(redis_client)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
