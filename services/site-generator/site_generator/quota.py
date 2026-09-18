from datetime import datetime, timezone

from redis import Redis


class WeeklyQuota:
    """Cupo de 50 leads/semana aprobado en el documento de validación del Módulo 7
    (CLAUDE.md sección 9) — un tope de negocio, no un rate limit de proveedor externo. Por
    eso NO se comporta como `dispatcher.RateLimiter` (que espera/bloquea): acá agotar el
    cupo no es un error transitorio que valga la pena reintentar, es una decisión real de
    "no generar más sitios esta semana" — `try_consume` devuelve `False` de inmediato, el
    handler sigue el pipeline sin sitio en vez de bloquear al worker."""

    def __init__(self, redis_client: Redis, max_per_week: int, clock_fn=lambda: datetime.now(timezone.utc)):
        self._redis = redis_client
        self._max_per_week = max_per_week
        self._clock_fn = clock_fn

    def _key(self) -> str:
        iso_year, iso_week, _ = self._clock_fn().isocalendar()
        return f"site_quota:{iso_year}-W{iso_week:02d}"

    def try_consume(self) -> bool:
        key = self._key()
        count = self._redis.incr(key)
        if count == 1:
            # 8 días de margen sobre la semana ISO — de sobra para que nunca expire antes
            # de que termine la semana que está contando, sin tener que calcular el corte exacto.
            self._redis.expire(key, 8 * 24 * 60 * 60)
        return count <= self._max_per_week
