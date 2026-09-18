# apps/

- `dashboard/` — **implementado y verificado de punta a punta** (ver su README). Panel de runs y
  leads por estado, UI del gate de aprobación humana. Next.js, toda la lógica vive en
  `services/extractor` y `services/approval-gate` — esto es solo UI + Server Actions que las
  llaman server-side (las API keys nunca llegan al browser).

No hay Ingress Gate acá — TORI no recibe webhooks en tiempo real, su trigger es Manual/Chat/Cron
(ver `services/extractor/README.md`).

Ver roadmap completo en `../CLAUDE.md` (sección 7).
