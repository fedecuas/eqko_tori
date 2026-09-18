# .github/workflows

## ci.yml

Corre en cada push/PR a `master`. Dos jobs independientes:

- **python-tests** — instala los paquetes en orden de dependencia (`shared-types` →
  `seda-consumer`/`idempotency` → cada servicio con su extra `[test]`) y corre `pytest` en cada
  directorio (142 tests en total: `seda-consumer`, `idempotency`, `extractor`, `agent-worker`,
  `site-generator`, `approval-gate`, `dispatcher`). Todas las suites mockean lo externo
  (fakeredis, `httpx.MockTransport`, `litellm`/`langfuse` mockeados) — no necesita ningún
  secret real configurado en GitHub.
- **dashboard-build** — `npm ci` + `next build` en `apps/dashboard` (incluye el type-check de
  TypeScript), con env vars placeholder. No hay ESLint configurado ni suite de tests ahí todavía.

Conventional Commits obligatorio (`feat`, `fix`, `refactor`, `test`, `chore`, `docs`, `ci`) desde
el primer commit, ver `../../CLAUDE.md` sección 5 y el estándar `eqko-agents-architecture`
sección 7.
