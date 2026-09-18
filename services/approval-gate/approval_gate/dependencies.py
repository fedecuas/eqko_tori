from functools import lru_cache

from redis import Redis

from .config import Settings
from .store import PendingApprovalStore
from .streams import ApprovedLeadPublisher


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


@lru_cache
def get_store() -> PendingApprovalStore:
    return PendingApprovalStore(get_redis())


@lru_cache
def get_publisher() -> ApprovedLeadPublisher:
    return ApprovedLeadPublisher(get_redis())
