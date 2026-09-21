# EQKO TORI — Arquitectura técnica

> Agente de prospección inteligente de EQKO AIgency. Extrae negocios locales desde Google Maps, filtra los que no tienen sitio web, formatea sus datos de contacto y redacta mensajes comerciales hiperpersonalizados (WhatsApp / llamada fría) usando Gemini.

Este documento adapta el README original del producto al estándar `eqko-agents-architecture` de EQKO. TORI **no** es un agente conversacional accionado por webhook en tiempo real — su trigger es Manual / Chat / Cron — así que el flujo SEDA se mantiene completo (colas, idempotencia, workers stateless, dispatcher con rate limits) pero sin Ingress Gate de webhook: el trigger publica directo al Event Channel.

Producto compartido de EQKO (vive en `08_AGENTES/`), no atado a un cliente específico — cualquier cliente de EQKO puede correr una prospección con TORI.

---

## 1. Qué resuelve

Automatizar la prospección local B2B: encontrar negocios sin sitio web (la señal de "brecha digital" más fuerte y fácil de detectar), y en vez de solo entregar una lista, entregar el **mensaje de venta ya redactado** para cada lead, listo para mandar por WhatsApp o usar en llamada fría.

## 2. Flujo end-to-end (SEDA adaptado)

```
[ Trigger Layer (Manual / Chat / Cron) ]
        — recibe: query de búsqueda + ubicación + radio + tenant/cliente
        — valida el input, encola UN evento por búsqueda (run) y responde de inmediato
               │
               ▼
[ Capa de Idempotencia ]
        — dedupe por place_id de Google Maps (no se re-extrae/re-contacta el mismo negocio)
               │
               ▼
[ Event Channel — Redis Streams ]
        — un evento por negocio extraído, no un batch gigante: leadgen.place_extracted
               │
               ▼
[ Agent Stage (Worker, stateless) — dos consumers ]
        1. Filtro: website == null && phone != null
        2. Data Cleaning & Formatting → E.164
        3. Brain (Gemini 1.5 Pro/Flash): análisis de brecha digital + redacción del mensaje,
           con RAG (pgvector) sobre mensajes exitosos previos y tono de marca del cliente
               │
               ▼
[ Approval Gate ]
        — guarda cada mensaje redactado como pendiente; un humano aprueba o rechaza desde
          su API (apps/dashboard es solo la UI que la llama). Solo lo aprobado sigue.
               │
               ▼
[ Dispatcher ]
        — rate limiting específico de cada output (Google Sheets API, Airtable, CRM),
          backoff exponencial, escritura idempotente (upsert por place_id, nunca duplica filas)
               │
               ▼
[ Output: CRM / Google Sheets / Airtable ]
```

**Por qué evento-por-negocio y no evento-por-búsqueda:** una búsqueda en Maps puede devolver cientos de resultados. Procesar cada negocio como su propio evento permite reintentar un lead que falla (ej. Gemini rechaza el prompt, el teléfono no formatea) sin repetir el run completo, y escalar el worker horizontalmente cuando hay ráfagas de runs simultáneos de varios clientes.

**DLQ:** todo lead que agota reintentos (fallo de extracción, formato de teléfono inválido, error de la API de Gemini) se mueve a una Dead-Letter Queue para revisión manual — nunca bloquea el resto del run.

**Punto de control humano:** antes de que un mensaje salga a WhatsApp o se marque como "listo para llamar", pasa por el Approval Gate (`services/approval-gate` — la lógica vive ahí, no en `apps/dashboard`, que es solo su UI) — es outbound frío, y un mensaje generado por LLM con datos incorrectos o tono equivocado es un riesgo de marca y de compliance, no solo un detalle de calidad.

## 3. Stack técnico

| Capa | Tecnología | Notas específicas de TORI |
|---|---|---|
| Trigger / API | FastAPI | Expone `POST /runs` (dispara una búsqueda) y `GET /runs/:id` (estado); también invocable desde Jarvis (chat) o un cron |
| Message Broker | Redis Streams | Streams por etapa, ver naming abajo |
| Extracción | Apify (Google Maps Scraper) o Google Places API directo | Apify si se necesita mayor volumen/campos que Places API no expone; Places API si el volumen es bajo y se prioriza estabilidad de cuota |
| Orquestación IA | Handlers Python explícitos (filtro → formateo, RAG → Gemini) | LangGraph evaluado pero no usado todavía — ver Estado actual, Módulo 4 |
| Brain / LLM | Gemini 1.5 Pro/Flash vía LiteLLM | LiteLLM como gateway para permitir fallback (ej. a Claude) si Gemini cae o rate-limitea |
| Base de datos | PostgreSQL + `pgvector` | Persistencia de leads/runs + RAG de mensajes exitosos y tono de marca por cliente |
| Output | Google Sheets API / Airtable API / CRM del cliente | Vía Dispatcher, nunca escritura directa desde el worker |
| Observabilidad de agente | Langfuse | Traza el análisis de brecha digital y la redacción — clave para detectar alucinaciones (ej. inventar datos del negocio) |
| Aprobación humana | Dashboard interno (o Chatwoot si el cliente ya lo usa) | Gate antes de marcar un mensaje como enviable |
| Secretos | Infisical Agent Vault | Apify token, Places API key, Gemini API key, tokens de Sheets/Airtable/CRM — nunca en texto plano ni expuestos al LLM |

## 4. Estructura de carpetas (monorepo)

```
02_EQKO_TORI/
├── apps/
│   └── dashboard/              # Next.js — UI de runs/leads y del Approval Gate (la API vive en services/approval-gate)
├── services/
│   ├── idempotency/            # dedupe por place_id en Redis
│   ├── extractor/               # Trigger Layer + llamada a Apify/Places API, publica al Event Channel
│   ├── agent-worker/            # Agent Stage: filtro + formato E.164, y el nodo Gemini + RAG
│   ├── site-generator/           # Módulo 7 — genera/despliega teaser (Vercel), cupo semanal, expiry
│   ├── approval-gate/            # Gate de aprobación humana — API + consumer, publica lead_approved
│   └── dispatcher/              # Escritura a Sheets/Airtable/CRM, rate limiting, backoff
├── packages/
│   ├── database/                 # Schema (Prisma/Drizzle), migraciones, pgvector
│   ├── shared-types/             # Contratos entre etapas (eventos, Run/RunStatus)
│   ├── seda-consumer/            # Loop genérico de consumer group (retry+backoff+DLQ)
│   └── config/                   # eslint, tsconfig, config compartida
├── infra/
│   ├── redis-streams/            # Config de streams, consumer groups, DLQ
│   ├── helm/
│   └── terraform/                # Redis, Postgres, Infisical
└── .github/workflows/
```

## 5. Naming conventions específicas

| Elemento | Convención | Ejemplo |
|---|---|---|
| Streams | `leadgen.<evento>` | `leadgen.place_extracted`, `leadgen.lead_qualified`, `leadgen.message_drafted`, `leadgen.site_generated`, `leadgen.lead_approved`, `leadgen.lead_dispatched` |
| Consumer groups | `<servicio>-cg` | `agent-worker-cg`, `site-generator-cg`, `approval-gate-cg`, `dispatcher-cg`. Excepción documentada: `agent-worker-brain-cg` para el consumer del nodo Gemini/RAG (Módulo 4) — mismo servicio, pero se separa del filtro/formateo (`agent-worker-cg`) porque las llamadas al LLM son mucho más lentas/caras y conviene poder escalarlas distinto |
| Cupo semanal (Redis) | `site_quota:<año ISO>-W<semana ISO>` | `site_quota:2026-W38` — no es rate limit de proveedor, es un tope de negocio (50/semana, Módulo 7) |
| Llave de idempotencia | `event:leadgen:<place_id>` | `event:leadgen:ChIJN1t_tDeuEmsRUsoyG83frY4` |
| Colas de despacho | `dispatch:<output>:<tenant_id>` | `dispatch:airtable:alba`, `dispatch:sheets:alba` |
| Dead-Letter Queue | `<stream>.dlq` | `leadgen.place_extracted.dlq` |
| Secrets en Infisical | `<env>/<servicio>/<clave>` | `prod/agent-worker/gemini_api_key`, `prod/dispatcher/airtable_token` |
| Traces (Langfuse) | `<etapa>.<accion>` | `agent-worker.gap_analysis`, `agent-worker.message_draft` |

## 6. Multi-tenant

TORI corre búsquedas para distintos clientes de EQKO — cada run está asociado a un `tenant_id`. Aplica el estándar de `eqko-saas-architecture`: Pool con RLS en PostgreSQL (leads y runs de un cliente nunca visibles para otro), salvo que un cliente puntual exija aislamiento por compliance.

## 7. Roadmap de implementación (6 módulos, orden estándar EQKO + extensión propia de TORI)

1. **Infraestructura y seguridad** — credenciales de Apify/Places API, Gemini, Sheets/Airtable/CRM en Infisical; scopes mínimos por integración.
2. **Ingesta blindada** — Trigger Layer (`POST /runs`), validación de input (query, ubicación, radio, tenant), deduplicación estricta por `place_id` en Redis antes de encolar.
3. **SEDA e inferencia asíncrona** — Redis Streams por lead, `agent-worker` stateless, escalamiento horizontal para correr runs de varios clientes en paralelo.
4. **Orquestación de memoria y RAG** — LangGraph con checkpointing por lead; `pgvector` con mensajes exitosos y tono de marca por cliente para personalizar mejor la propuesta.
5. **Despacho de alta precisión** — rate limits de Sheets/Airtable/CRM respetados en `dispatcher`, backoff exponencial, upsert idempotente por `place_id`.
6. **Observabilidad y escalación humana** — Langfuse trazando extracción → filtro → redacción; gate de aprobación humana antes de que un mensaje se marque enviable.
7. **(Extensión, no parte del template estándar de 6 módulos) Generación de landing page** —
   `services/site-generator` arma y despliega un teaser de sitio (Vercel) antes del gate de
   aprobación humana, para subir la tasa de cierre del outreach. **Validado el 2026-09-18,
   en implementación** — consentimiento en dos capas (ToS de Google + dueño del negocio)
   resuelto con disclaimer + `noindex` + auto-expiración + límite de 50 leads/semana, sin
   opt-in previo del negocio. Ver sección 9 para el detalle y el documento de validación.

## 8. Checklist antes de producción

- [ ] Deduplicación por `place_id` antes de cualquier procesamiento (evita re-contactar el mismo negocio)
- [ ] SEDA completo: Trigger → Idempotencia → Event Channel → Agent Worker (stateless) → Dispatcher
- [ ] DLQ configurada para leads que agotan reintentos
- [ ] Rate limits de Places API/Apify, Gemini, Sheets/Airtable/CRM identificados y respetados
- [ ] Backoff exponencial ante throttling de cualquiera de esas APIs
- [ ] Secretos (Apify, Gemini, Sheets/Airtable/CRM) nunca en texto plano ni expuestos al LLM
- [x] Gate de aprobación humana antes de marcar un mensaje como enviable — `services/approval-gate`
  (Módulo 6): `dispatcher` ya solo consume `leadgen.lead_approved`, nunca `message_drafted`
  directo. Falta la UI (`apps/dashboard`), pero la API y el bloqueo real ya existen.
- [x] Langfuse trazando el análisis de brecha digital y la redacción del mensaje —
  `agent-worker/tracing.py`, `LangfuseTracer` (opcional: sin credenciales, `NullTracer` no
  bloquea nada, pero tampoco hay trazas).
- [ ] RLS multi-tenant por `tenant_id` en runs y leads
- [ ] Naming de streams/consumer groups/llaves de idempotencia según sección 5

## 9. Módulo 7 — Generación de landing page (✅ validado e implementado)

Extensión propia de TORI, no parte del template estándar de 6 módulos de `eqko-agents-architecture`.
Inspirado en un caso público (post de LinkedIn) que describe generar y desplegar un sitio real
antes de contactar al negocio — la mecánica es un uso legítimo de reciprocidad en ventas, pero
el post no resuelve ningún problema de consentimiento. Este módulo existe para llegar al mismo
resultado de negocio sin heredar esos riesgos.

**El problema tiene dos capas separadas** (no alcanza con "pedirle permiso al negocio"):

| Capa | Qué dice | Se resuelve con consentimiento del negocio? |
|---|---|---|
| A — Términos de Google Places API | Prohíbe redistribuir/cachear reviews y fotos de Places fuera de una vista basada en Google Maps | No — el negocio no es dueño de ese contenido |
| B — Consentimiento del dueño del negocio | Se publica un sitio con su marca sin que lo haya pedido | Sí, es lo que hay que diseñar |

**Mitigación implementada:**
- Capa A: el teaser usa solo datos factuales (nombre, teléfono); nunca el texto de una review. **Fotos de Places (agregado 2026-09-18, decisión del usuario):** sí se permiten, pero solo enlazadas en vivo — el `<img src>` apunta al endpoint de Google (`places.googleapis.com/v1/{photo}/media`) para que el browser del visitante las pida cada vez; nunca se descargan ni se hostean (los Términos prohíben cachear/guardar contenido de Places). Atribución obligatoria del autor + link a Google Maps, la inyecta el sistema, no el LLM (`site_generator/builder.py`). Requiere una key **pública** de Places restringida por HTTP referrer (`GOOGLE_PLACES_PUBLIC_KEY`), distinta de la key de servidor — va expuesta en el HTML.
- **Sitio generado con Gemini (`AiSiteBuilder`, rediseñado 2026-09-18):** el sistema fija tema (paleta con contraste AA verificado por tests, Google Fonts, tema por categoría de Places) y Gemini solo compone el layout con `var(--token)`. Nunca se despliega crudo — `compose_site` lo audita (sin `<script>`/`<form>`/`<img>` propios/enlaces externos/`url()`/colores literales; SVG con lista blanca) y rechaza afirmaciones inventadas y promesas de servicio (entrega, para llevar, menú, "por generaciones"). El sistema inyecta título, `noindex`, barra "vista previa", disclaimer literal, atribución de Google y la barra móvil WhatsApp/Llamar. Si el HTML sigue inválido tras 3 intentos, degrada a la plantilla fija (`template.py`) — el lead nunca se pierde. Sin `GEMINI_API_KEY` usa la plantilla fija. Modelo: `gemini-3.1-pro-preview` (preview; ~2 min por sitio).
- Capa B: disclaimer literal acordado en la validación (`template.DISCLAIMER`), `noindex, nofollow` siempre, slug hash — no el nombre del negocio (`deploy.slug_for`) —, auto-expira a los 14 días (`expiry_main.py` borra el deployment de Vercel), el link lo manda un humano por WhatsApp igual que el mensaje hoy, y el gate de aprobación humana (`approval-gate`) revisa mensaje + sitio juntos antes de aprobar.

**Dónde se inserta en el pipeline:**

```
... message_drafted → services/site-generator (arma + despliega teaser)
    → leadgen.site_generated → services/approval-gate (revisa mensaje + sitio)
    → leadgen.lead_approved (con landing_url) → services/dispatcher
```

**Desviaciones del plan original, decididas durante la implementación:**
- **Una sola plantilla genérica, no por categoría** (gym/clínica/salón/restaurante) — evita
  tener que agregar un campo "categoría de negocio" a toda la cadena de eventos
  (`PlaceExtractedEvent` → `LeadQualifiedEvent` → `MessageDraftedEvent`) para un v1. El valor
  (mostrar algo terminado rápido) funciona igual con una plantilla buena; categorías quedan
  para cuando el uso real las pida.
- **`services/site-expiry` no es un servicio separado** — es `site_generator/expiry_main.py`,
  un cron dentro de `site-generator` (comparte config/store/deployer). Mismo patrón que
  `agent-worker` con sus dos procesos (`main.py`/`draft_main.py`).
- **El cupo semanal no bloquea/espera** como el `RateLimiter` de `dispatcher` — `WeeklyQuota`
  devuelve `False` de inmediato si se agotó, y el lead sigue el pipeline sin `landing_url`
  (`SiteGeneratedEvent.landing_url: str | None`). Nunca se pierde un lead por falta de cupo.
- **Sin tracking real de "el negocio respondió"** — TORI no ingesta respuestas de WhatsApp (el
  envío es manual). `expiry_main.py` expira incondicionalmente a los 14 días, no "14 días sin
  respuesta" como decía el plan original — es la interpretación honesta de lo que TORI puede
  detectar hoy. Documentado como limitación real en `services/site-generator/README.md`.

**Validado el 2026-09-18** — respuestas registradas en el documento
(https://claude.ai/artifact/2jC2A79wHtaJTQhjCJPCoF):

- Criterio legal revisó la lectura de los Términos de Google — ✅ ok.
- El estándar de mitigación de la Capa B (disclaimer + `noindex` + auto-expiración a 14 días +
  gate humano) alcanza — **no hace falta opt-in explícito previo del dueño del negocio**.
- Límite inicial: **50 leads/semana**, no escalar sin revisar de nuevo.
- Punto de contacto para pedidos de baja: **el mismo canal por el que se contactó al negocio**
  (responder en ese hilo de WhatsApp) — no un contacto separado. El texto del disclaimer en el
  sitio generado debe decir esto explícitamente, no dar una dirección de contacto genérica.
- Aprobado para construir `services/site-generator` y `services/site-expiry`.

Límite de 50/semana enforced en código (`WeeklyQuota`, ventana ISO por semana en Redis) — no
alcanza con confiarlo a que el operador no dispare más runs.

**Implementado y verificado de punta a punta contra Vercel real (2026-09-18)** —
`services/site-generator` (25 tests, hoy 151 con builder, diseño y fotos) + cambios en cascada a `services/approval-gate` (consume
`site_generated`, propaga `landing_url`) y `services/dispatcher` (columna `landing_url` en
Airtable/Sheets). 227 tests en el repo entero.

Verificación real destapó **tres problemas** que ningún test mockeado iba a atrapar — detalle
completo en `TORI-CREDENTIALS.md` sección Vercel:
1. El token no puede crear proyectos nuevos (bug de código, corregido: deploya siempre a un
   proyecto existente).
2. `ssoProtection` del proyecto bloqueaba el acceso público — **esto rompía por completo el
   propósito del Módulo 7**, el negocio le pegaba un login de Vercel en vez de ver el teaser.
   Solo se vio navegando la URL real en el browser, ningún test lo iba a atrapar. Desactivado
   con confirmación explícita del usuario antes de tocar la config de la cuenta.
3. El framework preset del proyecto ("Next.js") rompía el deploy de HTML suelto.

Página real confirmada pública, con el disclaimer literal acordado en la validación y
`noindex, nofollow` presente (verificado con el browser, no solo con la respuesta HTTP).

---

## Estado actual

Monorepo scaffoldeado (sección 4), repo git local inicializado. **Módulo 1 — cerrado**, ver el
resumen completo al final de esta sección; lo que sigue abajo es el detalle histórico módulo por
módulo (sección 7):

- ✅ Convención de secretos y su mapeo a Infisical definidos — ver `TORI-CREDENTIALS.md`.
- ✅ `.env.example` por servicio (`services/*/.env.example`) con el contrato de variables.
- ✅ `.gitignore` protegiendo `TORI-CREDENTIALS.md` y cualquier `.env` real.
- ✅ **Infra local real, no solo mocks**: Redis y Postgres+pgvector corriendo en Docker
  (`tori-redis`, `tori-postgres`), schema de `message_examples` aplicado, `.env` de los cuatro
  servicios con `REDIS_URL`/`DATABASE_URL` reales cargados. `TORI_INTERNAL_API_KEY` generada
  (no depende de ningún proveedor). Verificado contra esta infra, no contra `fakeredis`:
  `IdempotencyStore`, el consumer real de `agent-worker` (`XREADGROUP`/`XCLAIM` de punta a
  punta) y `PostgresMessageExamplesRepository`.
- 🐛 **Bug encontrado y corregido solo por probar contra Postgres real**: `rag.py` mandaba el
  embedding como `list[float]` crudo — psycopg no lo adapta al tipo `vector` de pgvector y el
  operador `<=>` no existía para ese tipo (`UndefinedFunction`). Nunca lo habría atrapado el
  mock de `test_rag.py`. Fix: literal de texto pgvector + cast `::vector` en la query — ver
  `_to_pgvector_literal` en `services/agent-worker/agent_worker/rag.py`.
- ✅ Google Places API, Gemini y Airtable dadas de alta, cargadas y verificadas contra las
  APIs reales — ver el resumen "Módulo 1 — credenciales cerradas" más abajo.
- ⬜ Sin definir todavía: qué CRM (si alguno) usa el primer cliente piloto — no bloquea nada,
  Airtable ya cubre el caso de prueba.

**Módulo 2 implementado** (sección 7) — sin esperar a las credenciales reales, todo probado con
mocks:

- ✅ `packages/shared-types` — `PlaceExtractedEvent`, `RunRequest`/`RunStatus`, nombres de streams.
- ✅ `services/idempotency` — `IdempotencyStore.mark_if_new`, dedupe atómico por `place_id`
  (4 tests, `pytest` en `services/idempotency`).
- ✅ `services/extractor` — FastAPI: `POST /runs` (auth por `X-Internal-Api-Key`, responde `202`
  de inmediato, extracción corre en background), `GET /runs/:id`, `GooglePlacesProvider` (Text
  Search New), `StreamsPublisher` (`XADD` a `leadgen.place_extracted`), `RunStore` (estado en
  Redis mientras no exista Postgres). 11 tests, todo mockeado (`fakeredis`,
  `httpx.MockTransport`, stub de `PlacesProvider`) — nunca pega a APIs reales.
- ⬜ Apify como proveedor alternativo: la interfaz `PlacesProvider` ya lo contempla, falta la
  implementación.
- ⬜ Sin correr contra Redis/Places API reales todavía — bloqueado por las credenciales del
  Módulo 1 (`TORI-CREDENTIALS.md`).

Repo con venv local en `.venv/` (gitignored). Instalación: ver `services/extractor/README.md`.

**Módulo 3 implementado** — `services/agent-worker` (28 tests en total en el repo: 4 + 11 + 13):

- ✅ Consumer group real sobre `leadgen.place_extracted` (`XREADGROUP`/`XPENDING`/`XCLAIM`),
  stateless — escala horizontalmente corriendo más instancias del mismo proceso.
- ✅ Filtro (`website == null && phone != null`) + formateo E.164 (`phonenumbers`); publica
  `leadgen.lead_qualified`.
- ✅ Resiliencia completa, no solo el camino feliz: backoff exponencial con jitter ante
  redelivery, DLQ (`leadgen.place_extracted.dlq`) tras agotar `MAX_RETRIES`, e idempotencia
  propia (`event:leadgen:qualified:<place_id>`) para no duplicar publish si el consumer group
  redespacha un mensaje ya procesado.
- ⬜ Sin correr contra Redis real (bloqueado por Módulo 1, igual que `extractor`).

**Módulo 4 implementado** — 39 tests en total en el repo (4 + 11 + 24):

- ✅ Segundo consumer dentro de `services/agent-worker` (`draft_main.py`, grupo
  `agent-worker-brain-cg`): consume `leadgen.lead_qualified`, publica
  `leadgen.message_drafted`. Reutiliza el loop genérico del consumer sin código nuevo de
  retry/backoff/DLQ — el refactor del Módulo 3 (handler pluggable) se pagó solo acá.
  `MessageDraftedEvent` agregado a `packages/shared-types`.
  `dlq_stream_name(STREAM_LEAD_QUALIFIED)` funciona igual que en el stage 1.
- ✅ RAG: `MessageExamplesRepository` (interfaz) + `PostgresMessageExamplesRepository`
  (pgvector real, `⚠️ sin correr contra Postgres real — ver TORI-CREDENTIALS.md`) +
  `Embedder`/`LiteLLMEmbedder`.
- ✅ Brain: `LiteLLMMessageDrafter` — Gemini vía LiteLLM (gateway, permite fallback cambiando
  solo el nombre del modelo), prompt fuerza salida JSON (`gap_analysis` + `message_text`),
  probado con `litellm.completion` mockeado (nunca pegó a la API real).
  `⚠️ sin correr contra Gemini real — requiere GEMINI_API_KEY`.
- ✅ Idempotencia propia del stage 2 (`event:leadgen:drafted:<place_id>`), chequeada
  **después** de llamar al LLM a propósito — chequearla antes rompería el reintento en un
  draft fallido (quedaría marcado como "ya hecho" sin haberse hecho nunca). El costo
  aceptado: una llamada de más al LLM en el caso raro de redelivery entre publish y ack.
- ⬜ `packages/database` sigue sin schema real — `README.md` ahí ya documenta la tabla
  `message_examples` que `PostgresMessageExamplesRepository` espera, pero no hay migraciones.
- ⬜ Sin conectar con un `packages/database` con RLS multi-tenant real todavía.
- ⬜ LangGraph (mencionado en el roadmap para checkpointing por lead) **no se usó** — el
  handler de dos pasos (RAG → draft) no lo necesitaba todavía; se evaluará si hace falta
  cuando el grafo crezca (ej. reintentos internos con distintos prompts, no solo
  retry/backoff genérico).

**Refactor entre Módulo 4 y 5:** el loop de consumer group (retry exponencial + DLQ, antes
`agent_worker/consumer.py`) se extrajo a `packages/seda-consumer` — con `dispatcher` como
tercer consumer que lo necesitaba, mantenerlo duplicado dejó de tener sentido. `agent-worker`
sigue con sus mismos 24 tests pasando después del refactor, sin cambios de comportamiento.

**Módulo 5 implementado** — inicialmente con una brecha a propósito (ver abajo, cerrada en el
Módulo 6):

- ✅ `services/dispatcher` — consumer que rutea por tenant (`OutputRouter`/`StaticOutputRouter`),
  respeta rate limits por `dispatch:<output>:<tenant_id>` (ventana fija en Redis, `RateLimiter`),
  hace upsert idempotente por `place_id` (`AirtableOutput` con `performUpsert` nativo,
  `GoogleSheetsOutput` con find-or-update) y publica `leadgen.lead_dispatched`.
  Retry/backoff/DLQ reusando `packages/seda-consumer` sin código nuevo.
- ⬜ CRM del cliente sigue TBD (`TORI-CREDENTIALS.md`) — solo Airtable y Sheets implementados.
- ⬜ `main.py` arma el `StaticOutputRouter` con un diccionario vacío por defecto — sin
  `packages/database`, no hay de dónde leer "qué output usa cada tenant" todavía.
- ⬜ Sin correr contra Airtable/Sheets reales (bloqueado por Módulo 1).

**Módulo 6 implementado** — 76 tests en total en el repo (4 + 4 + 11 + 28 + 16 + 13):

- ✅ `services/approval-gate` (nuevo) — consumer de `leadgen.message_drafted` que guarda cada
  lead en `PendingApprovalStore` (Redis, mismo patrón provisorio que `RunStore`), más una API
  FastAPI: `GET /pending`, `POST /leads/{place_id}/approve` (publica `leadgen.lead_approved`),
  `POST /leads/{place_id}/reject` (solo descarta). Auth por `X-Internal-Api-Key`, `tenant_id`
  validado en cada acción — no solo al listar — para que nadie apruebe un lead de otro tenant.
- ✅ **Brecha del Módulo 5 cerrada**: `services/dispatcher` ya no consume `message_drafted`
  directo — consume `leadgen.lead_approved`, que solo existe si un humano aprobó desde la API.
  Cambio real, no cosmético: se actualizaron `DispatchHandler`, `main.py` y los 16 tests de
  `dispatcher` para reflejarlo.
- ✅ `LeadApprovedEvent` + `STREAM_LEAD_APPROVED` agregados a `packages/shared-types`.
- ✅ Langfuse: `agent-worker/tracing.py` — `DraftTracer` (interfaz), `NullTracer` (default,
  sin credenciales no bloquea nada), `LangfuseTracer` (traza cada draft exitoso, atrapa sus
  propios errores para que un Langfuse caído nunca tumbe un draft que ya salió bien).
  `⚠️ sin correr contra Langfuse real — requiere LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY`.
- ⬜ **`apps/dashboard` (la UI) sigue sin construir, a propósito** — la parte que cambiaba
  comportamiento del sistema (el gate real) ya está en `approval-gate`; el frontend Next.js es
  trabajo puramente visual, sin lógica de negocio, y no se armó en este módulo. Ver
  `apps/dashboard/README.md` para qué debería cubrir cuando se construya.

## Módulo 1 — credenciales cerradas, pipeline verificado de punta a punta con servicios reales

Ya no bloqueado. Corrida real completa, sin mocks, encadenando los cinco servicios:

```
Google Places API → extractor (POST /runs real)
    → agent-worker stage 1 (filtro + E.164)
    → agent-worker stage 2 (RAG contra Postgres + redacción con Gemini real)
    → approval-gate (intake real + POST /leads/:id/approve vía su API HTTP real)
    → dispatcher (consumer real) → fila real en Airtable ("TORI Leads" / tabla "Leads")
```

Lead real usado: "Taquería México" (Guadalajara), extraído de una búsqueda real de "taquerias
en Guadalajara", calificado (sin sitio, con teléfono), redactado por Gemini
(`gemini-2.5-flash`), aprobado vía la API de `approval-gate`, y escrito en Airtable con
`gap_analysis` y `message_text` reales, no inventados.

Infra: Redis y Postgres+pgvector en Docker local (`tori-redis`, `tori-postgres`), no gestionados
— para producción sigue pendiente Módulo 1/3 real (`infra/terraform`).

Bugs reales encontrados y corregidos en el camino (ninguno visible con los tests mockeados —
todos requirieron pegarle a un servicio real para aparecer):
1. `rag.py` mandaba el embedding como `list[float]` crudo — pgvector no lo adapta, `<=>` no
   existe para ese tipo. Fix: literal de texto + cast `::vector`.
2. `LiteLLMMessageDrafter`/`LiteLLMEmbedder` esperaban que litellm leyera `GEMINI_API_KEY` de
   `os.environ` — pero los `.env` de este monorepo los carga `pydantic-settings` hacia sus
   propios campos, nunca hacia el entorno real del proceso. Fix: `api_key` explícito.
3. `gemini-1.5-flash` / `text-embedding-004` (defaults originales) ya no existen en la API.
   Actualizados a `gemini-2.5-flash` / `gemini-embedding-001`.
4. `gemini-embedding-001` devuelve 3072 dimensiones por default — pgvector rechaza indexar
   columnas de más de 2000. Fix: `dimensions=768` (parámetro estándar de litellm, no
   `output_dimensionality` — ese es el nombre nativo de Gemini y litellm lo ignora en silencio).
5. `services/dispatcher/main.py` nunca cableaba un output real para ningún tenant (a propósito,
   documentado como pendiente en el Módulo 5) — ahora mapea `alba` → `AirtableOutput` cuando
   `AIRTABLE_ACCESS_TOKEN`/`AIRTABLE_BASE_ID` están configurados.

Ver `TORI-CREDENTIALS.md` para el detalle de cada credencial y los errores de configuración de
Airtable (scopes del token, nombre de tabla, nombre de columna) que también aparecieron en el
camino — esos no eran bugs de código, eran de cómo se armó el token/la base en la UI de Airtable.

Sin resolver, no bloquea nada: `APIFY_API_TOKEN` (alternativa a Places, no hizo falta),
`CRM_TYPE`/`CRM_API_KEY` (TBD hasta el primer cliente con CRM), `LANGFUSE_*` (opcional,
`NullTracer` funciona sin esto), Google Sheets (Airtable ya cubre el caso de prueba).

**Módulo 7 (extensión, sección 9) — validado, implementado y verificado de punta a punta el
2026-09-18.** No es parte del roadmap estándar de 6 módulos: agrega `services/site-generator`
(genera/despliega teaser de sitio antes del gate de aprobación humana) entre `agent-worker` y
`approval-gate`. Parámetros aprobados: sin opt-in previo del negocio (el gate humano interno
alcanza), límite de 50 leads/semana enforced en código, baja gestionada por el mismo canal de
contacto. Cambios en cascada a `approval-gate` (consume `site_generated`, no `message_drafted`)
y `dispatcher` (columna `landing_url`). 101 tests en el repo entero (142 tras el sitio con Gemini + fotos, ver sección 9).

Corrida real contra Vercel destapó 3 problemas reales (permiso de creación de proyecto,
`ssoProtection` bloqueando el acceso público — el que más importaba, rompía el propósito
entero del módulo — y framework preset incompatible), los tres resueltos — ver detalle en
`TORI-CREDENTIALS.md` sección Vercel. Página confirmada pública en el browser, con disclaimer
y `noindex` presentes. Todo lo de Módulo 1 a 7 está ahora verificado de punta a punta contra
servicios reales, ninguna credencial pendiente bloquea nada.

## `apps/dashboard` — implementado y verificado de punta a punta (2026-09-18)

Next.js (App Router, TypeScript, Tailwind). Toda la lógica sigue viviendo en `extractor` y
`approval-gate` — el dashboard es UI + Server Actions server-side que las llaman, las API keys
internas nunca llegan al browser. Detalle completo en `apps/dashboard/README.md`.

Verificado en el browser, con el loop completo real: click "Disparar run" en la UI → `extractor`
real → `agent-worker` (calificar + redactar con Gemini real) → `site-generator` (deploy real a
Vercel) → aparece como pendiente en la UI con el link al sitio → click "Aprobar" → evento
publicado con `landing_url` → `dispatcher` → fila real en Airtable. Cada paso del pipeline se
probó a través de la interfaz real, no solo con `curl`.

Un problema real más en el camino (mismo patrón que los anteriores — Airtable no tenía la
columna): la tabla "Leads" no tenía `landing_url`, dispatcher tiró `422 UNKNOWN_FIELD_NAME`.
Usuario agregó la columna, el mensaje que había quedado en el PEL por el fallo se reclamó
automáticamente (`reclaimed=1`) y se despachó bien en el segundo intento — el sistema de
retry/backoff ya construido en el Módulo 3 lo resolvió solo, sin intervención manual más allá
de agregar la columna.

Con esto, **el roadmap completo de TORI (Módulos 1–7 + `apps/dashboard`) está implementado y
verificado de punta a punta contra servicios reales.** Pendiente, no bloqueante: historial de
runs (requiere un endpoint nuevo en `extractor`, no existe), autenticación del dashboard (corre
asumiendo acceso de confianza), CRM como output alternativo, RLS multi-tenant real, y probar con
un segundo tenant/cliente.
