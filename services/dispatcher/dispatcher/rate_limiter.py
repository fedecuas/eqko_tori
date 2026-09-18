import time
from typing import Callable

from redis import Redis


class RateLimiter:
    """Ventana fija en Redis, compartida entre todos los procesos de `dispatcher` (no es un
    límite en memoria de un solo proceso) — CLAUDE.md sección 1 "Rate limits del canal" y
    sección 7 Módulo 5. Bloquea (duerme) hasta que hay lugar en la ventana actual en vez de
    fallar; para un worker que procesa un mensaje a la vez, esperar unos milisegundos es
    preferible a tratarlo como un error que dispare retry/DLQ."""

    def __init__(
        self,
        redis_client: Redis,
        max_requests: int,
        window_seconds: float,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock_fn: Callable[[], float] = time.time,
    ):
        self._redis = redis_client
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._sleep_fn = sleep_fn
        self._clock_fn = clock_fn

    def acquire(self, key: str) -> None:
        while True:
            now = self._clock_fn()
            window = int(now // self._window_seconds)
            window_key = f"ratelimit:{key}:{window}"

            count = self._redis.incr(window_key)
            if count == 1:
                self._redis.expire(window_key, int(self._window_seconds) + 1)

            if count <= self._max_requests:
                return

            wait_seconds = self._window_seconds - (now % self._window_seconds)
            self._sleep_fn(wait_seconds)
