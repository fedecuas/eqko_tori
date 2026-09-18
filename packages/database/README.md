# packages/database

Schema versionado (Prisma o Drizzle) + migraciones para Postgres.

Tablas mínimas esperadas: `runs` (una por búsqueda disparada, con `tenant_id`), `leads` (un
negocio por fila, `place_id` único, estado del pipeline), `messages` (mensaje generado, estado de
aprobación).

**`message_examples`** — la tabla que ya asume `services/agent-worker/agent_worker/rag.py`
(`PostgresMessageExamplesRepository`, Módulo 4) aunque el schema real todavía no existe acá:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE message_examples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    business_category TEXT,
    message_text TEXT NOT NULL,
    embedding VECTOR(768),  -- dimensión de text-embedding-004, ajustar si cambia el modelo
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON message_examples USING ivfflat (embedding vector_cosine_ops);
```

RLS por `tenant_id` en `runs`/`leads`/`messages`/`message_examples` (estándar
`eqko-saas-architecture`, ver `CLAUDE.md` sección 6).

Sin código todavía — `PostgresMessageExamplesRepository` está escrito contra este schema pero
nunca corrió contra un Postgres real (bloqueado por `DATABASE_URL`, Módulo 1).
