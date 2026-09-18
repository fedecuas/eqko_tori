# apps/dashboard

**Implementado y verificado de punta a punta contra servicios reales (2026-09-18).** Next.js
(App Router, TypeScript, Tailwind). Toda la lógica de negocio vive en `services/extractor` y
`services/approval-gate` — este paquete es solo UI + un puente server-side hacia esas dos APIs,
como ya documentaba `CLAUDE.md` antes de que esto existiera.

## Por qué Server Actions, no un cliente en el browser

Todas las llamadas a `extractor`/`approval-gate` (`app/actions.ts`, con `"use server"`) corren en
el servidor de Next.js — las API keys internas (`EXTRACTOR_INTERNAL_API_KEY`,
`APPROVAL_GATE_INTERNAL_API_KEY`) nunca llegan al bundle del browser. Ningún componente cliente
llama a esas APIs directo; siempre pasa por una Server Action.

## Qué hace

- **Disparar un run** (`components/TriggerRunForm.tsx`): `tenant_id` + query → `POST /runs` de
  `extractor`, y hace poll de `GET /runs/:id` cada 2s (hasta 15 veces) para mostrar el resultado
  sin que el usuario tenga que refrescar.
- **Pendientes de aprobación** (`app/page.tsx` + `components/PendingLeadCard.tsx`): lista
  `GET /pending` de `approval-gate` — mensaje, análisis de brecha digital, y el link al preview
  del sitio (Módulo 7) si se generó. Aprobar/rechazar llaman `POST /leads/:id/approve` o
  `/reject`, y `revalidatePath("/")` refresca la lista automáticamente.
- **Selector de tenant**: vía query param (`?tenant=`), no estado de cliente — un form GET nativo,
  sin JS extra para algo tan simple.

## Correr local

Necesita `extractor` y `approval-gate` corriendo (ver sus READMEs) antes de arrancar esto —
si no están, la página lo dice explícitamente en vez de fallar en silencio.

```bash
npm install
cp .env.local.example .env.local   # completar con las mismas keys que extractor/.env y approval-gate/.env
npm run dev
```

O con el preview del proyecto (`.claude/launch.json` del working directory, configuración
`tori-dashboard`, puerto 3001).

## Verificación real (no solo build)

Probado en el browser contra `extractor`, `approval-gate`, `agent-worker`, `site-generator` y
`dispatcher` reales — no mocks: se disparó un run real desde el formulario, se calificó y
redactó un lead real (Gemini), se generó y desplegó su sitio (Vercel), apareció como pendiente en
la UI con el link al sitio, se aprobó con el botón, y el evento aprobado (con `landing_url`)
llegó hasta una fila real en Airtable. Screenshot y verificación completa en la conversación que
construyó esto.

## Pendiente / no cubierto

- Sin historial de runs — `extractor` no tiene un endpoint de "listar todos los runs" (solo
  `GET /runs/:id` puntual), es una limitación real del backend, no de esta UI.
- Sin autenticación de quien usa el dashboard — corre asumiendo acceso de confianza (red interna
  o localhost). Antes de exponerlo fuera de eso, hace falta agregar auth real.
- Un solo tenant a la vez en pantalla — cambiar de tenant es manual (`?tenant=`), no hay un
  selector con lista de tenants conocidos (no existe todavía un catálogo de tenants en
  `packages/database`).
