"""Chat-model client: sends messages to OpenRouter and falls back to a second model on failure.

All calls to a large language model go through ``chat()``. It uses the OpenAI Python SDK pointed at
OpenRouter, so any model on OpenRouter can be used by changing ``CHAT_MODEL`` in ``.env``. If the main
model errors (for example a timeout, rate limit, or bad model ID), the call is retried once on
``FALLBACK_MODEL`` and a warning with the original error is logged, so fallbacks are never silent.

Example:
    >>> from creditcoach.llm import chat
    >>> reply, model_used = chat([{"role": "user", "content": "What is a credit score?"}])
"""

import logging

from openai import OpenAI

from creditcoach import config

log = logging.getLogger(__name__)


def get_client() -> OpenAI:
    """Create an OpenAI-compatible client that talks to OpenRouter.

    Returns:
        An ``openai.OpenAI`` client configured with the OpenRouter URL and your API key.

    Raises:
        RuntimeError: If ``OPENROUTER_API_KEY`` is missing from ``.env``.
    """
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your key.")
    return OpenAI(base_url=config.OPENROUTER_BASE_URL, api_key=config.OPENROUTER_API_KEY)


def chat(messages: list[dict], model: str | None = None) -> tuple[str, str]:
    """Send a conversation to the chat model and return its reply, falling back once if it fails.

    For GPT-5-family models, ``REASONING_EFFORT`` from the config is passed to OpenRouter to control
    how long the model reasons before answering.

    Args:
        messages: OpenAI-style chat messages, e.g. ``[{"role": "system", "content": ...},
            {"role": "user", "content": ...}]``.
        model: OpenRouter model ID to try first. Defaults to ``config.CHAT_MODEL``.

    Returns:
        A tuple ``(reply_text, model_used)``. ``model_used`` shows whether the fallback model answered.

    Raises:
        RuntimeError: If no API key is configured.
        openai.OpenAIError: If both the primary and the fallback model fail.
    """
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
