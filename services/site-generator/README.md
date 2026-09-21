# services/site-generator

Módulo 7 del roadmap (`../../CLAUDE.md` sección 9) — **validado el 2026-09-18, implementado**.
Extensión propia de TORI, no parte del template estándar de 6 módulos.

Consume `leadgen.message_drafted`, genera y despliega un teaser de landing page (Vercel), publica
`leadgen.site_generated` — que consume `services/approval-gate`, para que el gate humano revise
mensaje y sitio juntos antes de aprobar. No manda nada solo: el link sigue el mismo camino que el
mensaje de texto, un humano lo copia y lo manda por su WhatsApp.

## Por qué existe este servicio — leer antes de tocar el código

Este módulo se diseñó explícitamente alrededor de un problema de consentimiento en dos capas
(Términos de Google Places API + consentimiento del dueño del negocio) — ver `CLAUDE.md` sección 9
y el [documento de validación](https://claude.ai/artifact/2jC2A79wHtaJTQhjCJPCoF). Reglas que no
son negociables sin volver a pasar por esa validación:

- **Cero texto de reviews de Google Places.** Fotos de Places: sí (decisión 2026-09-18), pero
  **solo enlazadas en vivo** — `<img src>` directo a `places.googleapis.com`, nunca descargadas ni
  hosteadas (los Términos prohíben guardar contenido de Places), con la atribución del autor y el
  link a Google Maps que inyecta el sistema (`builder.compose_site`), no el LLM.
- **El HTML de Gemini nunca se despliega crudo** — `compose_site` lo audita y lo rechaza si trae
  scripts/forms/imágenes propias/enlaces externos, placeholders sin rellenar o afirmaciones
  inventadas sobre el negocio; tras 2 intentos degrada a la plantilla fija.
- **`noindex, nofollow` siempre**, slug hash (no el nombre del negocio) — ver `deploy.slug_for`.
- **El texto de `template.DISCLAIMER` es literal**, acordado en la validación — la baja se
  gestiona por el mismo canal de contacto, no una dirección separada.
- **Cupo de 50 leads/semana** (`WeeklyQuota`) — agotarlo no es un error: el lead sigue el
  pipeline sin sitio (`landing_url=None`), nunca se pierde.

## Piezas

- `quota.py` — `WeeklyQuota`, cupo semanal en Redis. A diferencia de `RateLimiter` en
  `dispatcher`, no bloquea/espera: agotar el cupo es una decisión de negocio, no un error
  transitorio.
- `design.py` — sistema de diseño: 5 temas (mexicano, oriental, café, bar, general) con paleta,
  tipografías de Google Fonts y estilos base (`.wrap`, `.btn*`, barra de acción móvil). El tema
  se elige por la categoría de Places, luego por el nombre. **Los colores los fija el sistema, no
  el LLM**: `tests/test_design.py` verifica contraste AA de cada par, y `compose_site` rechaza
  cualquier color literal en el CSS de Gemini (solo `var(--token)`).
- `builder.py` — `AiSiteBuilder`: Gemini (`SITE_GEN_MODEL`, hoy `gemini-3.1-pro-preview`, ~2 min
  por sitio) compone el layout; `compose_site` lo audita (sin scripts/forms/`<img>`/enlaces
  externos/colores sueltos; SVG solo con lista blanca) y rechaza afirmaciones inventadas y
  promesas de servicio (entrega, para llevar, menú...). El sistema inyecta título, fuentes,
  `noindex`, barra de vista previa, disclaimer, atribución, fotos y la barra móvil
  WhatsApp/Llamar. `StaticSiteBuilder` (plantilla fija) es el fallback y el modo sin
  `GEMINI_API_KEY`. Verificado contra Gemini, Places y Vercel reales, en el navegador.
  ⚠️ `gemini-3.1-pro-preview` es un modelo *preview* (puede cambiar o retirarse);
  `gemini-2.5-pro` devolvió 404 con esta key.
- `photos.py` — `GooglePlacesPhotosProvider`: pide en vivo solo los metadatos de las fotos
  (nombre del recurso + atribución). Un error de red degrada a "sin fotos", no pierde el lead.
  Necesita `GOOGLE_PLACES_API_KEY` (servidor) **y** `GOOGLE_PLACES_PUBLIC_KEY` (expuesta en el
  HTML, restringida por referrer) — ver `TORI-CREDENTIALS.md`.
- `template.py` — plantilla fija genérica, también es el fallback de `AiSiteBuilder`.
- `deploy.py` — `VercelDeployer`. `⚠️ sin probar contra la API real` — requiere `VERCEL_TOKEN`.
- `store.py` — `SiteDeploymentStore`: idempotencia de negocio (reusar el deployment existente de
  un `place_id` en vez de re-deployar) + índice para `expiry_main.py`.
- `handler.py` — `SiteGenerationHandler`, el handler para el consumer genérico de
  `packages/seda-consumer`.
- `expiry_main.py` — **no es un consumer**, es un cron (`python -m site_generator.expiry_main`):
  borra deployments de más de `EXPIRY_DAYS` (14) desde que se generaron. `⚠️ Expira
  incondicionalmente por tiempo — TORI no tiene forma de detectar "el negocio respondió"` (el
  envío de WhatsApp es manual, fuera del pipeline). Documentado como limitación real, no un bug.

## Correr local

```bash
pip install -e ../../packages/shared-types
pip install -e ../idempotency
pip install -e ../../packages/seda-consumer
pip install -e ".[test]"
cp .env.example .env   # completar con TORI-CREDENTIALS.md
python -m site_generator.main            # consumer
python -m site_generator.expiry_main     # cron, correr una vez al día (ej. cron de sistema)
```

## Tests

151 tests, todo mockeado (`fakeredis`, `httpx.MockTransport`, un deployer y un LLM falsos) — nunca pega a
Redis ni Vercel reales. Cubre: cupo semanal (independiente por semana ISO), reuso de deployment
existente (no re-deploya en redelivery), degradación sin sitio cuando se agota el cupo (el evento
igual se publica), la plantilla (disclaimer literal, `noindex`, sin texto de reviews, escapeo de
HTML), armado de la request a Vercel, borrado idempotente (404 = no-op), y el ciclo
retry → backoff → DLQ reusando `packages/seda-consumer`.

```bash
pytest
```
