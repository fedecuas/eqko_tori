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

## Fuentes de negocios (`EXTRACTION_PROVIDER`)

`PlacesProvider` es la interfaz; `pipeline.py` no sabe cuál hay detrás. Se elige con
`EXTRACTION_PROVIDER` en el `.env` (una sola fuente por proceso, no por run):

- **`google`** (default) — Places API (New). Ojo: sus Términos prohíben guardar nombres/teléfonos.
- **`denue`** — DENUE de INEGI (datos abiertos, se pueden guardar). Necesita `DENUE_TOKEN`
  (gratis, se saca en inegi.org.mx/servicios/api_denue.html). Los `place_id` salen como
  `denue:<Id>` para no chocar con los de Google.
- Apify sigue **sin implementar**.

### `DenueProvider` — lo que hay que saber (probado contra la API real, 2026-09-24)

- **Busca por coordenadas + radio (máx. 5000 m) y palabra clave**, no por texto libre: el run
  tiene que traer `latitude` y `longitude`; `query` se reduce a las palabras antes de "en"
  (`"taquerías, tortas en Naucalpan"` → busca `taqueria` y `torta`, separadas por coma). Las
  palabras se pasan a **singular**: DENUE busca por subcadena en el nombre y "taquerias" no
  aparece en "TAQUERIA EL FAROLITO" (0 resultados).
- **La API es muy intermitente** y, medido, **por ventanas**: durante segundos o minutos rechaza
  todo con 503 (en 0.1 s), y fuera de la ventana responde a la primera — no es un problema de
  conexiones (probado con keep-alive y sin él). Los reintentos cortos se quedan dentro de una
  ventana caída: el proveedor reintenta 8 veces con backoff exponencial + jitter (~90 s en total),
  y si una palabra nunca responde pero otra sí, devuelve lo que hay y avisa en el log; solo falla
  si todas caen. En una tarde de pruebas, 3 de 5 corridas completas fallaron por esto y la siguiente
  devolvió 60 resultados en 1 s: **el run debe poder relanzarse**, y para producción la salida real
  es la descarga masiva en CSV de INEGI (consulta local, sin depender de esta API).
- **Los errores llegan como texto con HTTP 200** (`No hay resultados.` = lista vacía;
  `Radio máximo 5000 metros.` = error) y **un token inválido también da 503**.
- Los datos vienen sin acentos y en MAYÚSCULAS: se normalizan. Sin teléfono no hay lead, así que
  al recortar a `max_results` se quedan primero los que lo tienen.
- Limitaciones de la fuente (ver la prueba del 2026-09-24): el teléfono cubre ~36% de los
  negocios y suele no coincidir con el de Google; el campo de sitio web casi nunca viene lleno, así
  que "sin sitio" produce falsos positivos; no trae fotos (los sitios de leads DENUE salen sin
  fotos y con tema por nombre, porque `site-generator` no consulta a Google ids que no son suyos).

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
