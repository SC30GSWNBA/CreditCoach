"""Chat-model client: sends messages to OpenRouter and falls back to a second model on failure.

All calls to a large language model go through ``chat()``, or ``chat_with_tools()`` when the model may call
tools (Task 15). It uses the OpenAI Python SDK pointed at
OpenRouter, so any model on OpenRouter can be used by changing ``CHAT_MODEL`` in ``.env``. If the main
model errors (for example a timeout, rate limit, or bad model ID), the call is retried once on
``FALLBACK_MODEL`` and a warning with the original error is logged, so fallbacks are never silent.

Example:
    >>> from creditcoach.llm import chat, chat_with_tools
    >>> reply, model_used = chat([{"role": "user", "content": "What is a credit score?"}])
    >>> message, model_used = chat_with_tools(messages, tools)   # message.tool_calls, if the model wants tools
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


def _complete(messages: list[dict], model: str | None = None, **kwargs):
    """Run one chat completion, falling back once to ``FALLBACK_MODEL`` if the first model fails.

    Returns:
        ``(message, model_used)``, where ``message`` is the SDK's reply message (content and any tool calls).
    """
    client = get_client()
    primary = model or config.CHAT_MODEL
    for candidate in (primary, config.FALLBACK_MODEL):
        try:
            extra = {}
            if candidate.startswith("openai/gpt-5") and config.REASONING_EFFORT:
                extra["extra_body"] = {"reasoning": {"effort": config.REASONING_EFFORT}}
            kwargs.setdefault("max_tokens", config.MAX_OUTPUT_TOKENS)
            response = client.chat.completions.create(model=candidate, messages=messages, timeout=90, **extra, **kwargs)
            return response.choices[0].message, candidate
        except Exception as exc:
            if candidate == config.FALLBACK_MODEL:
                raise
            log.warning("Chat model %s failed (%s: %s); falling back to %s",
                        candidate, type(exc).__name__, exc, config.FALLBACK_MODEL)
    raise AssertionError("unreachable")


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
    message, model_used = _complete(messages, model)
    return message.content or "", model_used


def chat_with_tools(messages: list[dict], tools: list[dict] | None, model: str | None = None):
    """Like ``chat``, but the model may answer with tool calls instead of text (Task 15 agent loop).

    Args:
        messages: The conversation so far, including earlier assistant tool calls and ``tool`` results.
        tools: OpenAI function definitions the model may call, or None to require a text answer.
        model: OpenRouter model ID to try first. Defaults to ``config.CHAT_MODEL``.

    Returns:
        ``(message, model_used)``: the SDK message, whose ``tool_calls`` is set when the model wants tools run.
    """
    return _complete(messages, model, **({"tools": tools, "tool_choice": "auto"} if tools else {}))
