from redis import Redis
from tori_shared_types import dlq_stream_name

__all__ = ["move_to_dlq", "dlq_stream_name"]


def move_to_dlq(redis_client: Redis, source_stream: str, entry_id: str, fields: dict, reason: str) -> None:
    """Todo evento que agota sus reintentos se aísla acá — nunca bloquea el resto del
    stream (regla no negociable, eqko-agents-architecture sección 1/2)."""
    payload = {
        **_decode_fields(fields),
        "_source_stream": source_stream,
        "_source_entry_id": entry_id,
        "_dlq_reason": reason,
    }
    redis_client.xadd(dlq_stream_name(source_stream), payload)


def _decode_fields(fields: dict) -> dict:
    return {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in fields.items()
    }
