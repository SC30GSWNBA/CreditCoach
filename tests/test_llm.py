"""Tests for the chat-model client (``creditcoach.llm``). No API key or model calls needed.

The OpenRouter client is replaced with a fake that records each request, so these check what is sent and
the fallback, not the model.

Run:
    uv run pytest tests/test_llm.py -v
"""

from types import SimpleNamespace

from creditcoach import config, llm


class FakeClient:
    """Records each ``chat.completions.create`` call; fails for the models in ``failing``."""

    def __init__(self, failing=()):
        self.requests, self.failing = [], set(failing)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if kwargs["model"] in self.failing:
            raise RuntimeError("402 This request requires more credits, or fewer max_tokens")
        message = SimpleNamespace(content="ok", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_every_request_caps_output_tokens(monkeypatch):
    """2026-10-03: without a cap OpenRouter reserved GPT-5's 65,536 tokens, and a low-credit key fell back."""
    fake = FakeClient()
    monkeypatch.setattr(llm, "get_client", lambda: fake)
    assert llm.chat([{"role": "user", "content": "hi"}]) == ("ok", config.CHAT_MODEL)
    assert fake.requests[0]["max_tokens"] == config.MAX_OUTPUT_TOKENS


def test_a_failed_chat_model_falls_back_with_the_same_cap(monkeypatch):
    fake = FakeClient(failing={config.CHAT_MODEL})
    monkeypatch.setattr(llm, "get_client", lambda: fake)
    assert llm.chat([{"role": "user", "content": "hi"}]) == ("ok", config.FALLBACK_MODEL)
    assert [r["model"] for r in fake.requests] == [config.CHAT_MODEL, config.FALLBACK_MODEL]
    assert all(r["max_tokens"] == config.MAX_OUTPUT_TOKENS for r in fake.requests)
