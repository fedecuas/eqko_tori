from datetime import datetime, timezone

from redis import Redis

_INDEX_KEY = "site_deployments:index"


def _key(place_id: str) -> str:
    return f"site_deployment:{place_id}"


class SiteDeploymentStore:
    """Reemplazo provisorio de una tabla real (mismo patrón que RunStore/PendingApprovalStore
    en otros servicios). Dos trabajos:

    1. Idempotencia de *negocio*, no solo de evento: si ya existe un deployment para este
       `place_id`, se reusa su `landing_url` en vez de volver a desplegar — más barato que
       repetir el deploy en una redelivery, y evita acumular deployments duplicados en
       Vercel para el mismo negocio.
    2. Índice para `expiry_main.py`: sin esto no hay forma de saber qué deployments tienen
       más de `expiry_days` sin escanear Vercel entero.
    """

    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    def get(self, place_id: str) -> dict | None:
        data = self._redis.hgetall(_key(place_id))
        if not data:
            return None
        return _decode(data)

    def record(self, place_id: str, landing_url: str, deployment_id: str) -> None:
        self._redis.hset(
            _key(place_id),
            mapping={
                "place_id": place_id,
                "landing_url": landing_url,
                "deployment_id": deployment_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._redis.sadd(_INDEX_KEY, place_id)

    def list_all(self) -> list[dict]:
        place_ids = self._redis.smembers(_INDEX_KEY)
        deployments = []
        for raw_place_id in place_ids:
            place_id = raw_place_id.decode() if isinstance(raw_place_id, bytes) else raw_place_id
            deployment = self.get(place_id)
            if deployment is not None:
                deployments.append(deployment)
        return deployments

    def remove(self, place_id: str) -> None:
        self._redis.delete(_key(place_id))
        self._redis.srem(_INDEX_KEY, place_id)


def _decode(data: dict) -> dict:
    return {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in data.items()
    }
