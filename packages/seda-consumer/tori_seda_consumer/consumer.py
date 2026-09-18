import logging
import random
from dataclasses import dataclass, field
from typing import Callable

from redis import Redis
from redis.exceptions import ResponseError

from .dlq import move_to_dlq

logger = logging.getLogger(__name__)


def default_jitter() -> float:
    return random.uniform(0.5, 1.5)


def ensure_consumer_group(redis_client: Redis, stream: str, group: str) -> None:
    try:
        redis_client.xgroup_create(name=stream, groupname=group, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _required_backoff_ms(base_backoff_ms: int, times_delivered: int, jitter_fn: Callable[[], float]) -> float:
    # Exponencial con jitter, nunca intervalo fijo (eqko-agents-architecture sección 1).
    exponent = min(max(times_delivered - 1, 0), 6)
    return base_backoff_ms * (2**exponent) * jitter_fn()


@dataclass
class CycleStats:
    """Genérico entre etapas y entre servicios: `succeeded`/`skipped` los define cada
    handler (calificó vs. no calificó, redactó vs. ..., despachó vs. ...), no run_cycle."""

    reclaimed: int = 0
    dlq: int = 0
    processed: int = 0
    succeeded: int = 0
    skipped: int = 0
    duplicate: int = 0
    errors: int = 0


def claim_stale_messages(
    redis_client: Redis,
    stream: str,
    group: str,
    consumer_name: str,
    base_backoff_ms: int,
    max_retries: int,
    stats: CycleStats,
    jitter_fn: Callable[[], float] = default_jitter,
) -> list[tuple[str, dict]]:
    pending = redis_client.xpending_range(stream, group, min="-", max="+", count=200)
    to_reclaim: list[str] = []

    for entry in pending:
        entry_id = entry["message_id"]
        entry_id = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
        times_delivered = entry["times_delivered"]
        idle_ms = entry["time_since_delivered"]

        if times_delivered > max_retries:
            claimed = redis_client.xclaim(stream, group, consumer_name, min_idle_time=0, message_ids=[entry_id])
            for claimed_id, fields in claimed:
                move_to_dlq(
                    redis_client,
                    stream,
                    claimed_id.decode() if isinstance(claimed_id, bytes) else claimed_id,
                    fields,
                    reason=f"exceeded max_retries={max_retries}",
                )
            redis_client.xack(stream, group, entry_id)
            stats.dlq += 1
            continue

        if idle_ms >= _required_backoff_ms(base_backoff_ms, times_delivered, jitter_fn):
            to_reclaim.append(entry_id)

    if not to_reclaim:
        return []

    claimed_messages = redis_client.xclaim(stream, group, consumer_name, min_idle_time=0, message_ids=to_reclaim)
    stats.reclaimed += len(claimed_messages)
    return [
        (mid.decode() if isinstance(mid, bytes) else mid, fields) for mid, fields in claimed_messages
    ]


def read_new_messages(
    redis_client: Redis, stream: str, group: str, consumer_name: str, count: int = 10, block_ms: int = 1000
) -> list[tuple[str, dict]]:
    response = redis_client.xreadgroup(group, consumer_name, {stream: ">"}, count=count, block=block_ms)
    if not response:
        return []
    _, entries = response[0]
    return [(mid.decode() if isinstance(mid, bytes) else mid, fields) for mid, fields in entries]


Handler = Callable[[dict, CycleStats], None]
"""Firma que debe cumplir cada etapa SEDA (Agent Stage o Dispatcher): recibe los fields crudos
de un entry de Redis Streams y el CycleStats del ciclo actual (para incrementar
succeeded/skipped/duplicate). Si algo salió mal de verdad (evento corrupto, la API de un
tercero falló, etc.) debe levantar una excepción — run_cycle la interpreta como fallo de
procesamiento real y entra al ciclo de retry/backoff/DLQ, nunca hace ack de ese mensaje."""


@dataclass
class WorkerDependencies:
    redis_client: Redis
    handler: Handler
    consumer_group: str
    consumer_name: str
    stream: str
    base_backoff_ms: int = 5_000
    max_retries: int = 5
    jitter_fn: Callable[[], float] = field(default=default_jitter)


def run_cycle(deps: WorkerDependencies, count: int = 10, block_ms: int = 1000) -> CycleStats:
    """Una pasada del loop: reclama mensajes vencidos (o los manda a DLQ), lee mensajes
    nuevos, procesa todo y hace ack de lo que salió bien. Separado del loop infinito para
    poder testearlo sin threads ni sleeps."""
    stats = CycleStats()
    ensure_consumer_group(deps.redis_client, deps.stream, deps.consumer_group)

    reclaimed = claim_stale_messages(
        deps.redis_client,
        deps.stream,
        deps.consumer_group,
        deps.consumer_name,
        deps.base_backoff_ms,
        deps.max_retries,
        stats,
        deps.jitter_fn,
    )
    fresh = read_new_messages(deps.redis_client, deps.stream, deps.consumer_group, deps.consumer_name, count, block_ms)

    for entry_id, fields in reclaimed + fresh:
        stats.processed += 1
        try:
            deps.handler(fields, stats)
            deps.redis_client.xack(deps.stream, deps.consumer_group, entry_id)
        except Exception:
            # No se hace ack: el mensaje queda en el PEL para el próximo claim_stale_messages,
            # con backoff exponencial según cuántas veces ya se entregó.
            logger.exception("failed to process entry %s", entry_id)
            stats.errors += 1

    return stats
