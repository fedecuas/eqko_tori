import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

from tori_shared_types import LeadQualifiedEvent

from .rag import MessageExample

SYSTEM_PROMPT = """Sos un asistente de EQKO que redacta mensajes de prospección en frío para \
negocios locales sin sitio web. Respondé SIEMPRE con un JSON válido de la forma \
{"gap_analysis": "...", "message_text": "..."} y nada más, sin markdown ni texto extra.

- gap_analysis: 1-2 frases sobre qué pierde el negocio concreto por no tener presencia digital \
propia (no genérico).
- message_text: el mensaje de WhatsApp/llamada, corto, directo, sin sonar a spam, mencionando \
el nombre del negocio. En español, tono cercano.

Los ejemplos de mensajes exitosos que te pasen son referencia de tono — no los copies literal."""


@dataclass
class DraftResult:
    message_text: str
    gap_analysis: str
    model: str


class MessageDrafter(ABC):
    @abstractmethod
    def draft(self, lead: LeadQualifiedEvent, examples: list[MessageExample]) -> DraftResult:
        ...


class LiteLLMMessageDrafter(MessageDrafter):
    """LiteLLM como gateway (CLAUDE.md sección 3) permite fallback a otro proveedor cambiando
    solo `model`, sin tocar esta clase.

    `api_key` se pasa explícito a litellm en cada llamada, no por variable de entorno: los
    `.env` de este monorepo los carga `pydantic-settings` (Settings, config.py) hacia sus
    propios campos, no hacia `os.environ` — litellm nunca vería `GEMINI_API_KEY` si dependiera
    de leerlo del entorno del proceso. Confirmado corriendo esto contra Gemini real."""

    def __init__(self, model: str = "gemini/gemini-2.5-flash", api_key: str | None = None):
        self._model = model
        self._api_key = api_key

    def draft(self, lead: LeadQualifiedEvent, examples: list[MessageExample]) -> DraftResult:
        import litellm  # import perezoso: no forzar litellm en quien solo usa el stub en tests

        response = litellm.completion(
            model=self._model,
            api_key=self._api_key,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(lead, examples)},
            ],
            response_format={"type": "json_object"},
        )
        content = response["choices"][0]["message"]["content"]

        # Un JSON inválido acá es un fallo real de procesamiento, no un "no califica" — se
        # propaga y el consumer genérico lo manda al ciclo de retry/backoff/DLQ (Módulo 3),
        # igual que un evento de entrada corrupto.
        parsed = json.loads(content)
        return DraftResult(
            message_text=parsed["message_text"],
            gap_analysis=parsed["gap_analysis"],
            model=self._model,
        )


def _build_user_prompt(lead: LeadQualifiedEvent, examples: list[MessageExample]) -> str:
    lines = [
        f"Negocio: {lead.display_name}",
        f"Dirección: {lead.formatted_address or 'sin dato'}",
        f"Teléfono: {lead.phone_e164}",
    ]
    if examples:
        lines.append("\nMensajes exitosos previos (referencia de tono, no copiar literal):")
        lines.extend(f"- {example.message_text}" for example in examples)
    return "\n".join(lines)
