from redis import Redis


class IdempotencyStore:
    """Capa de idempotencia (CLAUDE.md sección 2 y 7, Módulo 2).

    Registra una llave en Redis antes de que cualquier evento se procese o publique.
    `mark_if_new` es la única operación expuesta a propósito: hace el check-and-set en un
    solo comando atómico (`SET key value NX`) para no dejar una ventana de carrera entre
    dos runs que encuentran el mismo negocio al mismo tiempo.
    """

    def __init__(self, redis_client: Redis, ttl_seconds: int | None = None):
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    def mark_if_new(self, key: str) -> bool:
        """True si la llave no existía (evento nuevo, seguir procesando).
        False si ya existía (duplicado, descartar)."""
        was_set = self._redis.set(key, "1", nx=True, ex=self._ttl_seconds)
        return bool(was_set)
