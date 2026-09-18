from datetime import datetime, timezone

from redis import Redis
from tori_shared_types import RunStatus


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    """Estado de cada run en Redis. Reemplazo provisorio de la persistencia en Postgres
    (packages/database, Módulo 4) — solo lo que necesita GET /runs/:id hoy."""

    def __init__(self, redis_client: Redis):
        self._redis = redis_client

    @staticmethod
    def _key(run_id: str) -> str:
        return f"run:{run_id}"

    def create(self, run_id: str, tenant_id: str, query: str) -> None:
        self._redis.hset(
            self._key(run_id),
            mapping={
                "run_id": run_id,
                "tenant_id": tenant_id,
                "query": query,
                "status": RunStatus.QUEUED.value,
                "places_found": 0,
                "places_published": 0,
                "places_duplicate": 0,
                "created_at": _utcnow_iso(),
            },
        )

    def set_running(self, run_id: str) -> None:
        self._redis.hset(self._key(run_id), "status", RunStatus.RUNNING.value)

    def set_completed(self, run_id: str, found: int, published: int, duplicates: int) -> None:
        self._redis.hset(
            self._key(run_id),
            mapping={
                "status": RunStatus.COMPLETED.value,
                "places_found": found,
                "places_published": published,
                "places_duplicate": duplicates,
                "finished_at": _utcnow_iso(),
            },
        )

    def set_failed(self, run_id: str, error: str) -> None:
        self._redis.hset(
            self._key(run_id),
            mapping={"status": RunStatus.FAILED.value, "error": error, "finished_at": _utcnow_iso()},
        )

    def get(self, run_id: str) -> dict | None:
        data = self._redis.hgetall(self._key(run_id))
        if not data:
            return None
        return {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in data.items()
        }
