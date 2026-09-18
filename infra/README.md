# infra/

Todavía vacío salvo la estructura — nada de esto se ha provisionado.

- `redis-streams/` — config de streams, consumer groups (`agent-worker-cg`, `dispatcher-cg`) y
  DLQ, una vez exista la Capa de Idempotencia y el Event Channel (Módulo 3 del roadmap en
  `../CLAUDE.md`).
- `helm/` — solo aplica si `agent-worker`/`dispatcher` corren en K8s en vez de en un servicio
  gestionado.
- `terraform/` — IaC de Redis/Postgres/Infisical.

Ver Módulo 1 del roadmap (`../CLAUDE.md` sección 7) para el orden de provisión: secretos primero,
infraestructura de colas después.
