"""LLM client: LiteLLM is the only seam between the app and any model.

The model is chosen in .env (LLM_MODEL, e.g. "ollama/qwen2.5:3b"); swapping
providers later is a config change, not a code change. Nothing here computes
flood numbers: the LLM narrates text given to it, and numeric grounding
(check_numbers in briefing) stays mandatory wherever numbers appear.
"""

from dataclasses import dataclass

import litellm

litellm.suppress_debug_info = True  # no "Give Feedback" banner on every failed local call

from app.config import settings

SYSTEM = (
    "You are the KADAL assistant for coastal flood response. "
    "Be concise and specific. If you state any number, it must come from "
    "data the user gave you in this conversation; never invent one. "
    "Mark anything simulated as simulated."
)

_THINK_OPEN = "<think"
_THINK_CLOSE = "</think>"


class ThinkStripper:
    """Drops <think>...</think> spans from a token stream, chunk by chunk.

    Tags may split across chunk boundaries, so a short tail is held back
    until the next feed. An unclosed span at flush is dropped: thinking
    must never leak into user-visible text, not even truncated.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    def feed(self, chunk: str) -> str:
        s = self._buf + chunk
        self._buf = ""
        out = []
        while True:
            if self._in_think:
                j = s.find(_THINK_CLOSE)
                if j == -1:
                    self._buf = (
                        s[-len(_THINK_CLOSE) :] if len(s) > len(_THINK_CLOSE) else s
                    )
                    break
                s = s[j + len(_THINK_CLOSE) :]
                self._in_think = False
            else:
                i = s.find(_THINK_OPEN)
                if i == -1:
                    if len(s) > len(_THINK_OPEN):
                        out.append(s[: -len(_THINK_OPEN)])
                        self._buf = s[-len(_THINK_OPEN) :]
                    else:
                        self._buf = s
                    break
                out.append(s[:i])
                s = s[i:]
                self._in_think = True
        return "".join(out)

    def flush(self) -> str:
        s, self._buf = self._buf, ""
        return "" if self._in_think else s


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
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        )
    return "" if content is None else str(content)


async def chat(
    messages: list[dict[str, str]], *, system: str | None = None,
    max_tokens: int | None = None, timeout_s: float | None = None,
    model: str | None = None, temperature: float | None = None,
) -> ChatResult:
    """One chat turn. Raises LLMUnavailable when the model cannot answer."""
    name = model or settings.llm_model
    convo = [{"role": "system", "content": system or SYSTEM}, *messages]
    try:
        resp = await litellm.acompletion(
            model=name,
            messages=convo,
            api_base=settings.ollama_base_url or None,
            api_key=settings.llm_api_key or None,
            temperature=temperature if temperature is not None else settings.llm_temperature,
            timeout=timeout_s or settings.llm_timeout_s,
            max_tokens=max_tokens,
        )
    except Exception as exc:  # timeout, connection refused, unknown model
        raise LLMUnavailable(
            f"model {name!r} did not answer "
            f"(is `ollama serve` running at {settings.ollama_base_url}?): {exc}"
        ) from exc
    raw = _content_to_text(resp.choices[0].message.content)
    # Same stripping as the streaming path: thinking spans (even unclosed ones)
    # are dropped, never leaked; only the visible answer survives.
    stripper = ThinkStripper()
    text = (stripper.feed(raw) + stripper.flush()).strip()
    if not text:
        raise LLMUnavailable(f"model {name!r} returned an empty reply")
    return ChatResult(text=text, model=name)


async def chat_stream(messages: list[dict[str, str]], *, system: str | None = None):
    """Yields answer tokens with <think> spans removed incrementally.

    Provider reasoning channels (e.g. delta.reasoning_content) are never
    forwarded. Raises LLMUnavailable on transport failure; if the stream
    dies mid-answer the caller gets the error instead of more tokens.
    """
    convo = [{"role": "system", "content": system or SYSTEM}, *messages]
    try:
        stream = await litellm.acompletion(
            model=settings.llm_model,
            messages=convo,
            api_base=settings.ollama_base_url or None,
            api_key=settings.llm_api_key or None,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_s,
            stream=True,
        )
    except Exception as exc:  # timeout, connection refused, unknown model
        raise LLMUnavailable(
            f"model {settings.llm_model!r} did not answer "
            f"(is `ollama serve` running at {settings.ollama_base_url}?): {exc}"
        ) from exc
    stripper = ThinkStripper()
    empty = True
    try:
        async for part in stream:
            delta = part.choices[0].delta
            token = stripper.feed(_content_to_text(getattr(delta, "content", None)))
            if token:
                empty = False
                yield token
    except Exception as exc:
        raise LLMUnavailable(
            f"model {settings.llm_model!r} stream broke: {exc}"
        ) from exc
    tail = stripper.flush()
    if tail:
        empty = False
        yield tail
    if empty:
        raise LLMUnavailable(f"model {settings.llm_model!r} returned an empty reply")
