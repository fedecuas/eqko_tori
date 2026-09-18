# services/

Cada etapa del flujo SEDA adaptado de TORI (ver `CLAUDE.md`, sección 2) vive en su propio servicio
acá, nunca combinadas en un solo proceso. Todos implementados (Módulos 2–7):

- `extractor/` — Trigger Layer (Manual/Chat/Cron) + Google Places API, publica
  `leadgen.place_extracted` al Event Channel. Reemplaza al Ingress Gate de webhook de la
  arquitectura base, porque TORI no recibe eventos externos en tiempo real (Módulo 2).
- `idempotency/` — dedupe por `place_id` en Redis antes de cualquier procesamiento (Módulo 2).
- `agent-worker/` — stateless, dos consumers: filtro (`website == null && phone != null`) +
  formateo E.164 (Módulo 3), y el nodo Gemini/RAG (análisis de brecha digital + redacción,
  con RAG sobre `pgvector`) (Módulo 4).
- `site-generator/` — genera y despliega un teaser de landing page (Vercel) antes del gate de
  aprobación humana, con cupo semanal y auto-expiración (Módulo 7, extensión propia de TORI —
  ver `CLAUDE.md` sección 9 para el análisis de consentimiento).
- `approval-gate/` — el gate de aprobación humana: guarda mensaje + sitio generado, expone
  aprobar/rechazar, publica `leadgen.lead_approved` (Módulo 6, consume `site_generated` desde
  el Módulo 7).
- `dispatcher/` — escritura a Sheets/Airtable/CRM respetando rate limits de cada uno, backoff
  exponencial, upsert idempotente por `place_id`, consume solo lo ya aprobado (Módulo 5, cerrado
  con el Módulo 6).

Naming de streams y consumer groups en `../CLAUDE.md` sección 5. El loop de retry/backoff/DLQ que
usan `agent-worker`, `site-generator`, `approval-gate` y `dispatcher` es compartido — vive en
`packages/seda-consumer`, no en cada servicio.
