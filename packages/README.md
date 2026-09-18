# packages/

Código compartido entre los servicios de `services/`:

- `shared-types/` — contratos entre etapas del pipeline (nombres de streams, `PlaceExtractedEvent`,
  `LeadQualifiedEvent`, `MessageDraftedEvent`, `LeadDispatchedEvent`) usados por `extractor`,
  `agent-worker` y `dispatcher` para no divergir en la forma de los eventos. Implementado.
- `seda-consumer/` — loop genérico de consumer group de Redis Streams (retry exponencial con
  jitter + DLQ), extraído de `agent-worker` en el Módulo 5 cuando `dispatcher` se volvió el
  tercer consumer que lo necesitaba. Implementado.
- `database/` — schema (Prisma/Drizzle o SQL puro), migraciones, y la extensión `pgvector` para
  el RAG de `agent-worker`. Sin código todavía — solo el schema documentado en su README.
- `config/` — eslint/tsconfig compartido entre servicios y `apps/dashboard`. Sin código todavía.

Ver `../CLAUDE.md`.
