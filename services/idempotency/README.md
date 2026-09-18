# services/idempotency

Módulo 2 del roadmap (`../../CLAUDE.md`) — implementado.

`IdempotencyStore.mark_if_new(key)` registra `event:leadgen:<place_id>` en Redis con un único
`SET ... NX` atómico antes de que `services/extractor` publique el evento correspondiente al
Event Channel. Si la llave ya existía, el negocio se descarta — evita re-extraer y, más
importante, re-contactar al mismo negocio en corridas distintas.

Sin TTL por default (dedupe permanente por negocio). Si más adelante se necesita permitir
re-contactar un negocio después de N meses, pasar `ttl_seconds` al construir el store — el
contrato ya lo soporta.

```bash
pip install -e ".[test]"
pytest
```
