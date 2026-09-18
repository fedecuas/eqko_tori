from redis import Redis
from tori_shared_types import (
    STREAM_LEAD_QUALIFIED,
    STREAM_MESSAGE_DRAFTED,
    LeadQualifiedEvent,
    MessageDraftedEvent,
)

# move_to_dlq vive en tori_seda_consumer (packages/seda-consumer) — es genérico entre
# servicios, no específico de agent-worker. No redefinir acá.


class QualifiedLeadPublisher:
    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    def publish(self, event: LeadQualifiedEvent) -> str:
        entry_id = self._redis.xadd(STREAM_LEAD_QUALIFIED, {"data": event.model_dump_json()})
        return entry_id.decode() if isinstance(entry_id, bytes) else entry_id


class DraftedMessagePublisher:
    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    def publish(self, event: MessageDraftedEvent) -> str:
        entry_id = self._redis.xadd(STREAM_MESSAGE_DRAFTED, {"data": event.model_dump_json()})
        return entry_id.decode() if isinstance(entry_id, bytes) else entry_id
