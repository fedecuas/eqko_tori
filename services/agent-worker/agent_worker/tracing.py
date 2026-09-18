import logging
from abc import ABC, abstractmethod

from tori_shared_types import LeadQualifiedEvent

from .brain import DraftResult
from .rag import MessageExample

logger = logging.getLogger(__name__)


class DraftTracer(ABC):
    """CLAUDE.md sección 3/8: Langfuse debe trazar el análisis de brecha digital y la
    redacción — es donde más importa detectar alucinaciones (datos del negocio inventados)."""

    @abstractmethod
    def record(self, lead: LeadQualifiedEvent, examples: list[MessageExample], result: DraftResult) -> None:
        ...


class NullTracer(DraftTracer):
    """Default — sin LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY configuradas, no hay tracing,
    pero el pipeline funciona igual (observabilidad nunca debe ser un punto de falla del
    flujo de negocio)."""

    def record(self, lead: LeadQualifiedEvent, examples: list[MessageExample], result: DraftResult) -> None:
        pass


class LangfuseTracer(DraftTracer):
    """⚠️ Sin probar contra Langfuse real — requiere LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY
    (TORI-CREDENTIALS.md). Un fallo de Langfuse (timeout, credenciales inválidas) nunca debe
    tumbar el draft ya exitoso — por eso record() atrapa cualquier excepción y solo loguea,
    nunca la deja propagar hacia el consumer genérico (que la trataría como fallo real y
    reintentaría un draft que en realidad ya salió bien)."""

    def __init__(self, public_key: str, secret_key: str, host: str = "https://cloud.langfuse.com"):
        import langfuse  # import perezoso: no forzar el paquete en quien usa NullTracer

        self._client = langfuse.Langfuse(public_key=public_key, secret_key=secret_key, host=host)

    def record(self, lead: LeadQualifiedEvent, examples: list[MessageExample], result: DraftResult) -> None:
        try:
            self._client.trace(
                name="agent-worker.message_draft",
                input={
                    "lead": {"place_id": lead.place_id, "display_name": lead.display_name},
                    "examples": [example.message_text for example in examples],
                },
                output={"message_text": result.message_text, "gap_analysis": result.gap_analysis},
                metadata={"model": result.model, "tenant_id": lead.tenant_id, "place_id": lead.place_id},
            )
        except Exception:
            logger.exception("langfuse trace failed for place_id=%s, continuing", lead.place_id)
