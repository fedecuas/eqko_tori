from tori_seda_consumer import CycleStats
from tori_shared_types import SiteGeneratedEvent

from .store import PendingApprovalStore


class IntakeHandler:
    """Handler del Módulo 6 (extendido en el Módulo 7) para el consumer genérico de
    packages/seda-consumer — consume leadgen.site_generated (no message_drafted directo
    desde el Módulo 7: el gate ahora revisa mensaje + sitio juntos, ver CLAUDE.md sección 9)
    y lo guarda en PendingApprovalStore para que el dashboard/API lo liste. No publica nada:
    la publicación de leadgen.lead_approved ocurre recién cuando un humano aprueba desde la
    API (api.py), no acá."""

    def __init__(self, store: PendingApprovalStore):
        self._store = store

    def __call__(self, fields: dict, stats: CycleStats) -> None:
        raw = fields.get(b"data") or fields.get("data")
        event = SiteGeneratedEvent.model_validate_json(raw)

        self._store.add(event)
        stats.succeeded += 1
