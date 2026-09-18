# packages/seda-consumer

Loop genérico de consumer group de Redis Streams — retry exponencial con jitter + DLQ (CLAUDE.md
sección 1/2, "Riesgo no negociable"). Extraído de `services/agent-worker` en el Módulo 5, cuando
`services/dispatcher` se convirtió en el tercer consumer que necesitaba exactamente la misma
resiliencia (antes vivía duplicado en `agent-worker`, dos veces, para sus dos stages).

- `consumer.py` — `run_cycle(deps)`: una pasada del loop (reclama mensajes vencidos del PEL o
  los manda a DLQ, lee mensajes nuevos, procesa cada uno con `deps.handler`, ackea lo que salió
  bien). `WorkerDependencies` agrupa todo lo que necesita: cliente de Redis, el `handler`
  específico de cada etapa (la única pieza que varía entre `agent-worker` y `dispatcher`), grupo,
  consumer, backoff y reintentos.
- `dlq.py` — `move_to_dlq()` + reexporta `dlq_stream_name()` de `tori_shared_types`.

Un `handler` (firma `Handler = Callable[[dict, CycleStats], None]`) recibe los fields crudos del
entry y el `CycleStats` del ciclo; si algo falla de verdad debe levantar una excepción — nunca
hace su propio manejo de reintentos, eso ya lo resuelve este paquete.

Quién lo usa hoy: `services/agent-worker` (`pipeline.QualifyHandler`, `draft_pipeline.DraftHandler`)
y `services/dispatcher` (`dispatch_pipeline.DispatchHandler`).

```bash
pip install -e ../../packages/seda-consumer
pytest  # tests genéricos con un handler de prueba, no específicos de ningún servicio
```
