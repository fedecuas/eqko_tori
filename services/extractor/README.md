# services/extractor

Módulo 1–2 del roadmap (`../../CLAUDE.md`) — Módulo 2 implementado.

Trigger Layer de TORI: expone `POST /runs` (query de búsqueda + ubicación + radio + `tenant_id`),
valida el input y dispara la extracción vía Google Places API (Text Search New). Responde
`202` de inmediato con un `run_id` — la extracción corre en background, nunca bloquea al caller
(dashboard, comando de chat vía Jarvis, o cron).

Por cada negocio devuelto, pasa primero por `services/idempotency` (`event:leadgen:<place_id>`)
y, si no es duplicado, publica un evento `leadgen.place_extracted` al Event Channel (Redis
Streams) para que lo tome `agent-worker` (Módulo 3, todavía no implementado). **No filtra** por
`website`/`phone` acá — ese paso vive en `agent-worker` (CLAUDE.md sección 2).

`GET /runs/{run_id}` devuelve el estado (`queued` → `running` → `completed`/`failed`) guardado en
un hash de Redis — reemplazo provisorio hasta que `packages/database` (Postgres, Módulo 4) exista.

Apify como proveedor alternativo a Places API (mencionado en `CLAUDE.md` sección 3) **todavía no
está implementado** — `PlacesProvider` ya es una interfaz para poder agregarlo sin tocar
`pipeline.py`, pero hoy `get_places_provider()` solo instancia `GooglePlacesProvider`.

## Correr local

```bash
pip install -e ../../packages/shared-types
pip install -e ".[test]"
cp .env.example .env   # completar con TORI-CREDENTIALS.md
uvicorn app.main:app --reload
```

```bash
curl -X POST localhost:8000/runs \
  -H "X-Internal-Api-Key: $TORI_INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "alba", "query": "restaurantes en Guadalajara"}'
```

## Tests

Sin credenciales reales — todo mockeado (`fakeredis` para Redis, `httpx.MockTransport` para
Places API, un `PlacesProvider` stub para los tests de endpoints).

```bash
pytest
```
