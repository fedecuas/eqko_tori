from redis import Redis
from tori_shared_types import STREAM_LEAD_DISPATCHED, LeadDispatchedEvent


class DispatchedLeadPublisher:
    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    def publish(self, event: LeadDispatchedEvent) -> str:
        entry_id = self._redis.xadd(STREAM_LEAD_DISPATCHED, {"data": event.model_dump_json()})
        return entry_id.decode() if isinstance(entry_id, bytes) else entry_id
