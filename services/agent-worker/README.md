# services/agent-worker

Módulos 3–4 del roadmap (`../../CLAUDE.md`) — **ambos implementados**.

Dos procesos stateless independientes, cada uno consumer de su propio grupo — correr N instancias
de cualquiera de los dos escala horizontalmente sin coordinación extra (Redis reparte los
mensajes del stream):

| Proceso | Stream que consume | Grupo | Publica |
|---|---|---|---|
| `python -m agent_worker.main` (Módulo 3) | `leadgen.place_extracted` | `agent-worker-cg` | `leadgen.lead_qualified` |
| `python -m agent_worker.draft_main` (Módulo 4) | `leadgen.lead_qualified` | `agent-worker-brain-cg` | `leadgen.message_drafted` |

Grupos separados a propósito: el filtro/formateo (Módulo 3) es determinístico y barato; el nodo
Gemini/RAG (Módulo 4) es lento y caro — conviene poder escalarlos distinto.

## Módulo 3 — filtro + E.164

Aplica el filtro (`website == null && phone != null`) y formatea el teléfono a E.164
(`phonenumbers`). Handler: `pipeline.QualifyHandler`.

## Módulo 4 — RAG + Gemini

Handler: `draft_pipeline.DraftHandler`. Por cada `LeadQualifiedEvent`:

1. **RAG** (`rag.py`): busca mensajes exitosos previos del mismo tenant vía
   `MessageExamplesRepository` — interfaz con dos implementaciones: `PostgresMessageExamplesRepository`
   (pgvector real, `⚠️ sin correr contra Postgres real` — ver TORI-CREDENTIALS.md y
   `packages/database/README.md` para el schema que espera) y stubs para tests.
2. **Brain** (`brain.py`): `LiteLLMMessageDrafter` arma un prompt con el lead + los ejemplos y le
   pide a Gemini (vía LiteLLM, el gateway — cambiar de modelo/proveedor no toca esta clase) un
   JSON con `gap_analysis` + `message_text`. `⚠️ sin correr contra Gemini real` — requiere
   `GEMINI_API_KEY`.
3. Idempotencia propia (`event:leadgen:drafted:<place_id>`), chequeada **después** de llamar al
   LLM a propósito: si se chequeara antes, un draft que falla dejaría la llave marcada sin haber
   publicado nada, y el reintento se leería como duplicado — el lead se perdería en silencio. El
   costo aceptado es una llamada de más al LLM en el caso raro de redelivery entre publish y ack.
4. **Tracing** (`tracing.py`, Módulo 6): `DraftTracer.record()` se llama siempre que el LLM
   respondió, incluso si termina siendo un duplicado — es la llamada al LLM la que hay que poder
   auditar, no solo el publish. `NullTracer` por default (no rompe nada sin credenciales);
   `LangfuseTracer` si están `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`, y atrapa cualquier
   excepción propia — un Langfuse caído nunca debe tumbar un draft que ya salió bien.

Un JSON inválido en la respuesta del LLM, o cualquier error real de la llamada, se propaga tal
cual un evento corrupto en el Módulo 3 — el consumer genérico (`packages/seda-consumer`) lo mete
al mismo ciclo de retry/backoff/DLQ sin necesitar código nuevo para esta etapa.

**No implementado todavía:** LangGraph (el roadmap lo menciona para checkpointing por lead) — el
handler de dos pasos no lo necesitó; se evalúa si hace falta cuando el grafo crezca.

## Resiliencia (compartida por los dos stages — y desde el Módulo 5 también por `services/dispatcher`)

Vive en `packages/seda-consumer`, no acá — se extrajo cuando `dispatcher` se convirtió en el
tercer consumer que la necesitaba (ver `packages/seda-consumer/README.md`).

- Cada ciclo (`run_cycle`) primero revisa el PEL (`XPENDING`) del consumer group — todo mensaje
  que lleva más del backoff esperado sin ackear se reclama (`XCLAIM`) y se reintenta; el backoff
  es exponencial con jitter según cuántas veces ya se entregó (`RETRY_BASE_BACKOFF_MS`, nunca
  intervalo fijo). Si supera `MAX_RETRIES`, se aísla en `<stream>.dlq` y se ackea el original —
  un lead con datos corruptos (o una respuesta de Gemini rota) no bloquea el resto del stream.
- Descalificar por no tener sitio/teléfono (Módulo 3) **no** es un error — se ackea sin reintento.
  Solo un fallo real de procesamiento entra al ciclo de retry/DLQ.

## Correr local

```bash
pip install -e ../../packages/shared-types
pip install -e ../idempotency
pip install -e ../../packages/seda-consumer
pip install -e ".[test]"   # litellm incluido, para poder testear brain.py mockeado
cp .env.example .env
python -m agent_worker.main         # stage 1
python -m agent_worker.draft_main   # stage 2, en otro proceso
```

`draft_main.py` además necesita `psycopg` (`pip install -e ".[postgres]"`) para correr de verdad
contra Postgres — no hace falta para los tests.

## Tests

76 tests en el repo entero, 28 acá. Todo con `fakeredis` (soporta consumer groups:
`XREADGROUP`/`XPENDING`/`XCLAIM`), `litellm.completion` mockeado y `langfuse.Langfuse` mockeado
— nunca pega a Redis, Postgres, Gemini ni Langfuse reales. Cubre: calificación/descalificación,
formateo de teléfono, RAG (stub y Postgres con conexión falsa), armado del prompt y parseo de la
respuesta del LLM, publish+ack del camino feliz de ambos stages, no-reproceso de mensajes ya
ackeados, dedupe ante redelivery, el ciclo completo retry → backoff → DLQ para las dos etapas, y
que `LangfuseTracer` atrapa sus propios errores en vez de propagarlos.

```bash
pytest
```
