from redis import Redis
from tori_shared_types import SiteGeneratedEvent


def _pending_key(place_id: str) -> str:
    return f"pending_approval:{place_id}"


def _by_tenant_key(tenant_id: str) -> str:
    return f"pending_approval:by_tenant:{tenant_id}"


class PendingApprovalStore:
    """Reemplazo provisorio de una tabla en packages/database (todavía sin schema, ver su
    README) — mismo patrón que RunStore en services/extractor: Redis hasta que exista
    Postgres. HSET es idempotente por diseño: reprocesar el mismo place_id (redelivery del
    consumer group de intake) solo pisa los mismos valores, no duplica nada."""

    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    def add(self, event: SiteGeneratedEvent) -> None:
        self._redis.hset(
            _pending_key(event.place_id),
            mapping={
                "run_id": event.run_id,
                "tenant_id": event.tenant_id,
                "place_id": event.place_id,
                "display_name": event.display_name,
                "phone_e164": event.phone_e164,
                "message_text": event.message_text,
                "gap_analysis": event.gap_analysis,
                "model": event.model,
                # "" en vez de None -- HSET no acepta None y un campo ausente en el hash se
                # distingue mal de "no se llegó a generar" en Redis; get() lo devuelve como
                # cadena vacía, _get_or_404/approve lo tratan como "sin landing page".
                "landing_url": event.landing_url or "",
            },
        )
        self._redis.sadd(_by_tenant_key(event.tenant_id), event.place_id)

    def get(self, place_id: str) -> dict | None:
        data = self._redis.hgetall(_pending_key(place_id))
        if not data:
            return None
        return _decode(data)

    def list_pending(self, tenant_id: str) -> list[dict]:
        place_ids = self._redis.smembers(_by_tenant_key(tenant_id))
        pending = []
        for raw_place_id in place_ids:
            place_id = raw_place_id.decode() if isinstance(raw_place_id, bytes) else raw_place_id
            lead = self.get(place_id)
            if lead is not None:  # pudo haberse removido entre el smembers y el get
                pending.append(lead)
        return pending

    def remove(self, place_id: str, tenant_id: str) -> None:
        self._redis.delete(_pending_key(place_id))
        self._redis.srem(_by_tenant_key(tenant_id), place_id)


def _decode(data: dict) -> dict:
    return {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in data.items()
    }
