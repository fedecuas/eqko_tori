# packages/shared-types

Paquete Python instalable (`tori-shared-types`) con los contratos entre etapas del pipeline SEDA:

- `events.py` — nombres de los streams (sección 5 de `../../CLAUDE.md`), `dlq_stream_name()`,
  `PlaceExtractedEvent` (publica `extractor`, consume `agent-worker`), `LeadQualifiedEvent`
  (publica `agent-worker` stage 1 tras filtrar y formatear E.164, Módulo 3) y
  `MessageDraftedEvent` (publica `agent-worker` stage 2 tras el nodo Gemini/RAG, Módulo 4).
- `runs.py` — `RunRequest` (input de `POST /runs`) y `RunStatus`.

Se instala en modo editable desde cada servicio que lo consume:

```bash
pip install -e ../../packages/shared-types
```

A medida que avance el roadmap (Módulo 5), acá se va a agregar `LeadDispatchedEvent`.
