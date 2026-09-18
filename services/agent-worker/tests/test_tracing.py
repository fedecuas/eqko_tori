from datetime import datetime, timezone

from tori_shared_types import LeadQualifiedEvent

from agent_worker.brain import DraftResult
from agent_worker.rag import MessageExample
from agent_worker.tracing import LangfuseTracer, NullTracer

LEAD = LeadQualifiedEvent(
    run_id="run-1",
    tenant_id="alba",
    place_id="place-1",
    display_name="Taquería El Buen Sazón",
    formatted_address="Av. Siempre Viva 123",
    phone_e164="+523312345678",
    qualified_at=datetime.now(timezone.utc),
)
RESULT = DraftResult(message_text="Hola!", gap_analysis="Sin web.", model="stub-model")


def test_null_tracer_does_nothing():
    # Solo no debe explotar -- es literalmente el contrato.
    NullTracer().record(LEAD, [], RESULT)


def test_langfuse_tracer_sends_a_trace(monkeypatch):
    calls = []

    class FakeLangfuseClient:
        def trace(self, **kwargs):
            calls.append(kwargs)

    import langfuse

    monkeypatch.setattr(langfuse, "Langfuse", lambda **kwargs: FakeLangfuseClient())

    tracer = LangfuseTracer(public_key="pk", secret_key="sk")
    tracer.record(LEAD, [MessageExample(tenant_id="alba", message_text="ejemplo")], RESULT)

    assert len(calls) == 1
    assert calls[0]["name"] == "agent-worker.message_draft"
    assert calls[0]["output"]["message_text"] == "Hola!"
    assert calls[0]["metadata"]["place_id"] == "place-1"


def test_langfuse_tracer_swallows_errors_instead_of_raising(monkeypatch):
    class ExplodingLangfuseClient:
        def trace(self, **kwargs):
            raise RuntimeError("langfuse is down")

    import langfuse

    monkeypatch.setattr(langfuse, "Langfuse", lambda **kwargs: ExplodingLangfuseClient())

    tracer = LangfuseTracer(public_key="pk", secret_key="sk")

    # No debe levantar -- un fallo de observabilidad nunca tumba un draft ya exitoso.
    tracer.record(LEAD, [], RESULT)
