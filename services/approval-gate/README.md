# services/approval-gate

Módulo 6 del roadmap (`../../CLAUDE.md`) — el gate de aprobación humana. Cierra la brecha que
`services/dispatcher` (Módulo 5) dejó documentada: un mensaje generado por Gemini no puede salir
a un output real sin que un humano lo revise primero (outbound frío, riesgo de marca/compliance
— ver `CLAUDE.md` sección 2).

No es parte de `apps/dashboard` (Next.js, todavía no existe) a propósito: la lógica real —
guardar pendientes, aprobar, rechazar, publicar `leadgen.lead_approved` — vive acá, en Python,
consistente con el resto del backend. `apps/dashboard` cuando se construya es solo la UI que
llama a esta API; no tiene por qué reimplementar nada de esto.

Dos procesos, como `agent-worker`:

| Proceso | Qué hace |
|---|---|
| `python -m approval_gate.intake_main` | Consumer de `leadgen.site_generated` (grupo `approval-gate-cg`) — guarda cada lead en `PendingApprovalStore` (Redis, reemplazo provisorio de una tabla real hasta que exista `packages/database`) |
| `uvicorn approval_gate.api:app` | `GET /pending?tenant_id=`, `POST /leads/{place_id}/approve?tenant_id=`, `POST /leads/{place_id}/reject?tenant_id=` |

Desde el Módulo 7 consume `leadgen.site_generated` (no `message_drafted` directo): el gate ahora
revisa mensaje **y** el teaser de sitio que generó `services/site-generator` juntos, antes de
aprobar — `landing_url` puede ser `None` si se agotó el cupo semanal de sitios, el lead sigue
existiendo igual.

`approve` arma un `LeadApprovedEvent` (con `landing_url` incluido) a partir del pendiente y lo
publica a `leadgen.lead_approved` — el stream que `dispatcher` consume desde este módulo.
`reject` solo borra el pendiente; no hay stream `lead_rejected` porque nada lo consume todavía.

`tenant_id` se valida en cada approve/reject, no solo en el listado — evita que alguien con la
API key apruebe un lead de otro tenant adivinando el `place_id`.

## Correr local

```bash
pip install -e ../../packages/shared-types
pip install -e ../../packages/seda-consumer
pip install -e ".[test]"
cp .env.example .env
python -m approval_gate.intake_main   # consumer
uvicorn approval_gate.api:app --reload --port 8001   # API, en otro proceso
```

```bash
curl "localhost:8001/pending?tenant_id=alba" -H "X-Internal-Api-Key: $TORI_INTERNAL_API_KEY"
curl -X POST "localhost:8001/leads/PLACE_ID/approve?tenant_id=alba" -H "X-Internal-Api-Key: $TORI_INTERNAL_API_KEY"
```

## Tests

13 tests, todo con `fakeredis` — nunca pega a Redis real. Cubre: el store (dedupe al re-agregar,
scoping por tenant), el intake handler, y la API completa (auth, listar, aprobar publica y
remueve, rechazar remueve sin publicar, 404 al aprobar un lead de otro tenant).

```bash
pytest
```
