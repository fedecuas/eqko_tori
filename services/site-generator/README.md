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

- **Cero fotos ni texto de reviews de Google Places** en el teaser — solo datos factuales
  (nombre, teléfono) y, opcionalmente, rating como cita con link a la ficha real.
- **`noindex, nofollow` siempre**, slug hash (no el nombre del negocio) — ver `deploy.slug_for`.
- **El texto de `template.DISCLAIMER` es literal**, acordado en la validación — la baja se
  gestiona por el mismo canal de contacto, no una dirección separada.
- **Cupo de 50 leads/semana** (`WeeklyQuota`) — agotarlo no es un error: el lead sigue el
  pipeline sin sitio (`landing_url=None`), nunca se pierde.

## Piezas

- `quota.py` — `WeeklyQuota`, cupo semanal en Redis. A diferencia de `RateLimiter` en
  `dispatcher`, no bloquea/espera: agotar el cupo es una decisión de negocio, no un error
  transitorio.
- `template.py` — plantilla única genérica (no por categoría — simplificación de v1 documentada
  en el diseño, ver `CLAUDE.md` sección 9).
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

25 tests, todo mockeado (`fakeredis`, `httpx.MockTransport`, un deployer falso) — nunca pega a
Redis ni Vercel reales. Cubre: cupo semanal (independiente por semana ISO), reuso de deployment
existente (no re-deploya en redelivery), degradación sin sitio cuando se agota el cupo (el evento
igual se publica), la plantilla (disclaimer literal, `noindex`, sin texto de reviews, escapeo de
HTML), armado de la request a Vercel, borrado idempotente (404 = no-op), y el ciclo
retry → backoff → DLQ reusando `packages/seda-consumer`.

```bash
pytest
```
