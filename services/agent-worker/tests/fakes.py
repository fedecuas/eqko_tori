from agent_worker.brain import DraftResult, MessageDrafter
from agent_worker.rag import MessageExample, MessageExamplesRepository


class StubMessageExamplesRepository(MessageExamplesRepository):
    def __init__(self, examples: list[MessageExample] | None = None):
        self.examples = examples or []
        self.calls: list[dict] = []

    def find_similar(self, tenant_id: str, query_text: str, limit: int = 3) -> list[MessageExample]:
        self.calls.append({"tenant_id": tenant_id, "query_text": query_text, "limit": limit})
        return self.examples[:limit]


class StubMessageDrafter(MessageDrafter):
    def __init__(self, result: DraftResult | None = None, error: Exception | None = None):
        self._result = result or DraftResult(
            message_text="Hola! Vimos que tu negocio no tiene web propia, te contamos cómo ayudamos.",
            gap_analysis="Sin sitio propio, depende 100% de que lo encuentren por Maps.",
            model="stub-model",
        )
        self._error = error
        self.calls: list[dict] = []

    def draft(self, lead, examples):
        self.calls.append({"lead": lead, "examples": examples})
        if self._error:
            raise self._error
        return self._result
