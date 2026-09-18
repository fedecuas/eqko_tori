# services/dispatcher

Módulo 5 del roadmap (`../../CLAUDE.md`) — implementado.

Stateless — consumer del grupo `dispatcher-cg` sobre `leadgen.lead_approved`. Correr N
instancias en paralelo escala horizontalmente; el rate limiter vive en Redis (no en memoria del
proceso), así que la cuota se respeta entre instancias, no solo dentro de una.

✅ **Brecha del Módulo 5 cerrada en el Módulo 6:** ya no consume `leadgen.message_drafted`
directo. Consume `leadgen.lead_approved`, que solo publica `services/approval-gate` cuando un
humano aprueba el mensaje desde su API — el gate de aprobación de `CLAUDE.md` sección 2 ya
existe. Ver `services/approval-gate/README.md`.

Desde el Módulo 7 (`services/site-generator`), la fila escrita en Airtable/Sheets incluye una
séptima columna `landing_url` — puede venir vacía si se agotó el cupo semanal de sitios, el resto
del flujo no cambia.

## Qué hace

Por cada `LeadApprovedEvent`:

1. **Rutea** el tenant a su output (`outputs.py`, `OutputRouter`/`StaticOutputRouter`) —
   Airtable o Google Sheets hoy. CRM queda TBD (ver `TORI-CREDENTIALS.md`, sin definir hasta el
   primer cliente con CRM). Un tenant sin output configurado levanta `ValueError`: es un problema
   de configuración real, así que termina en la DLQ para que alguien lo revise, no se descarta
   en silencio.
2. **Respeta el rate limit** del output (`rate_limiter.py`, ventana fija en Redis) antes de
   llamar a la API — `dispatch:<output>:<tenant_id>` como key, así un tenant no consume la cuota
   de otro.
3. **Upsert idempotente por `place_id`**, no por nuestra cuenta sino delegado al proveedor:
   - `AirtableOutput` usa el `performUpsert` nativo de Airtable (`fieldsToMergeOn: ["place_id"]`).
   - `GoogleSheetsOutput` no tiene upsert nativo — busca la fila por `place_id` en la columna A y
     actualiza, o agrega una fila si no existe.
   - Ambos son seguros de llamar dos veces para el mismo lead (redelivery del consumer group)
     sin crear filas duplicadas — por eso acá, a diferencia de `agent-worker` Módulo 4, no
     importa tanto si una redelivery gasta una llamada HTTP de más.
4. Publica `leadgen.lead_dispatched`, con idempotencia propia (`event:leadgen:dispatched:<place_id>`)
   para no duplicar el evento aunque el upsert se repita.

`⚠️ Sin correr contra Airtable/Sheets reales` — requiere `AIRTABLE_ACCESS_TOKEN` /
`GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON` (TORI-CREDENTIALS.md). Todo probado con
`httpx.MockTransport`, igual que `GooglePlacesProvider` en `extractor`.

## Resiliencia

Retry exponencial con jitter + DLQ vía `packages/seda-consumer` — cero código nuevo acá, es la
misma infraestructura que ya prueban `agent-worker`'s tests. Verificado con un test que fuerza a
`AirtableOutput` a fallar y confirma que termina en `leadgen.lead_approved.dlq`.

## Correr local

```bash
pip install -e ../../packages/shared-types
pip install -e ../idempotency
pip install -e ../../packages/seda-consumer
pip install -e ".[test]"
cp .env.example .env   # completar con TORI-CREDENTIALS.md
python -m dispatcher.main
```

`main.py` arma el `StaticOutputRouter` con un dict vacío por defecto — hoy no hay ningún tenant
configurado porque no hay `packages/database` de donde leer "qué output usa cada tenant" (ver
comentario en el código). Para probarlo local hay que instanciar los outputs a mano ahí mismo.

## Tests

16 tests, todo mockeado (`fakeredis`, `httpx.MockTransport`, un reloj falso para el rate
limiter) — nunca pega a Redis, Airtable ni Sheets reales. Cubre: rate limiting (ventanas
independientes por key, reset entre ventanas), armado de la request de upsert para cada output,
ruteo por tenant, dedupe ante redelivery, y el ciclo retry → backoff → DLQ reusando
`packages/seda-consumer`.

```bash
pytest
```
