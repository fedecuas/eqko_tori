import json
from datetime import datetime, timezone

import pytest
from tori_shared_types import LeadQualifiedEvent

from agent_worker.brain import SYSTEM_PROMPT, LiteLLMMessageDrafter
from agent_worker.rag import MessageExample

LEAD = LeadQualifiedEvent(
    run_id="run-1",
    tenant_id="alba",
    place_id="place-1",
    display_name="Taquería El Buen Sazón",
    formatted_address="Av. Siempre Viva 123",
    phone_e164="+523312345678",
    qualified_at=datetime.now(timezone.utc),
)


def _fake_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def test_draft_parses_a_valid_json_response(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _fake_response(
            json.dumps(
                {
                    "gap_analysis": "Sin web propia, depende de que lo encuentren por Maps.",
                    "message_text": "Hola! Vimos tu taquería en Maps y no tenés sitio propio...",
                }
            )
        )

    import litellm

    monkeypatch.setattr(litellm, "completion", fake_completion)

    drafter = LiteLLMMessageDrafter(model="gemini/gemini-1.5-flash")
    result = drafter.draft(LEAD, [MessageExample(tenant_id="alba", message_text="mensaje de ejemplo previo")])

    assert result.message_text.startswith("Hola! Vimos tu taquería")
    assert result.gap_analysis.startswith("Sin web propia")
    assert result.model == "gemini/gemini-1.5-flash"

    assert captured["model"] == "gemini/gemini-1.5-flash"
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    user_content = captured["messages"][1]["content"]
    assert "Taquería El Buen Sazón" in user_content
    assert "+523312345678" in user_content
    assert "mensaje de ejemplo previo" in user_content


def test_draft_works_without_examples(monkeypatch):
    def fake_completion(**kwargs):
        return _fake_response(json.dumps({"gap_analysis": "x", "message_text": "y"}))

    import litellm

    monkeypatch.setattr(litellm, "completion", fake_completion)

    result = LiteLLMMessageDrafter().draft(LEAD, [])

    assert result.message_text == "y"


def test_draft_raises_on_malformed_json_response(monkeypatch):
    import litellm

    monkeypatch.setattr(litellm, "completion", lambda **kwargs: _fake_response("not valid json"))

    with pytest.raises(json.JSONDecodeError):
        LiteLLMMessageDrafter().draft(LEAD, [])
