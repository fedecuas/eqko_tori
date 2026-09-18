from redis import Redis
from tori_shared_types import STREAM_PLACE_EXTRACTED, PlaceExtractedEvent


class StreamsPublisher:
    """Productor del Event Channel. No crea consumer groups — eso vive en
    infra/redis-streams y en el lado consumidor (services/agent-worker, Módulo 3)."""

    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    def publish_place_extracted(self, event: PlaceExtractedEvent) -> str:
        entry_id = self._redis.xadd(STREAM_PLACE_EXTRACTED, {"data": event.model_dump_json()})
        return entry_id.decode() if isinstance(entry_id, bytes) else entry_id
