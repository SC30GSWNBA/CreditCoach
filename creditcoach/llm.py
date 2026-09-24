"""Thin OpenRouter client with a fallback model."""

import logging

from openai import OpenAI

from creditcoach import config

log = logging.getLogger(__name__)


def get_client() -> OpenAI:
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your key.")
    return OpenAI(base_url=config.OPENROUTER_BASE_URL, api_key=config.OPENROUTER_API_KEY)


def chat(messages: list[dict], model: str | None = None) -> tuple[str, str]:
    """Send messages to the chat model, falling back once on error. Returns (reply, model_used)."""
    client = get_client()
    primary = model or config.CHAT_MODEL
    for candidate in (primary, config.FALLBACK_MODEL):
        try:
            extra = {}
            if candidate.startswith("openai/gpt-5") and config.REASONING_EFFORT:
                extra["extra_body"] = {"reasoning": {"effort": config.REASONING_EFFORT}}
            response = client.chat.completions.create(model=candidate, messages=messages, timeout=90, **extra)
            return response.choices[0].message.content or "", candidate
        except Exception as exc:
            if candidate == config.FALLBACK_MODEL:
                raise
            log.warning("Chat model %s failed (%s: %s); falling back to %s",
                        candidate, type(exc).__name__, exc, config.FALLBACK_MODEL)
    raise AssertionError("unreachable")
