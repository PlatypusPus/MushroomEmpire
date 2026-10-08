"""LLM client: LiteLLM is the only seam between the app and any model.

The model is chosen in .env (LLM_MODEL, e.g. "ollama/qwen3:4b"); swapping
providers later is a config change, not a code change. Nothing here computes
flood numbers: the LLM narrates text given to it, and numeric grounding
(check_numbers in briefing) stays mandatory wherever numbers appear.
"""

import re
from dataclasses import dataclass

import litellm

from app.config import settings

SYSTEM = (
    "You are the CoastGuard AI assistant for coastal flood response. "
    "Be concise and specific. If you state any number, it must come from "
    "data the user gave you in this conversation; never invent one. "
    "Mark anything simulated as simulated."
)

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMUnavailable(RuntimeError):
    """The model could not answer (daemon down, timeout, empty reply)."""


@dataclass
class ChatResult:
    text: str
    model: str


def _content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content blocks: keep text parts only
        return "".join(
            p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
        )
    return "" if content is None else str(content)


async def chat(messages: list[dict[str, str]], *, system: str | None = None) -> ChatResult:
    """One chat turn. Raises LLMUnavailable when the model cannot answer."""
    convo = [{"role": "system", "content": system or SYSTEM}, *messages]
    try:
        resp = await litellm.acompletion(
            model=settings.llm_model,
            messages=convo,
            api_base=settings.ollama_base_url or None,
            api_key=settings.llm_api_key or None,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_s,
        )
    except Exception as exc:  # timeout, connection refused, unknown model
        raise LLMUnavailable(
            f"model {settings.llm_model!r} did not answer "
            f"(is `ollama serve` running at {settings.ollama_base_url}?): {exc}"
        ) from exc
    text = _THINK.sub("", _content_to_text(resp.choices[0].message.content)).strip()
    if not text:
        raise LLMUnavailable(f"model {settings.llm_model!r} returned an empty reply")
    return ChatResult(text=text, model=settings.llm_model)
