"""Task 29: testers' 👍 and 👎 on an answer are recorded on that answer's trace, with the reason a 👎 can carry.

No API key or Langfuse needed: the answer is scripted and ``observability.score`` is captured.

Run:
    uv run pytest tests/test_feedback.py -v
"""

from types import SimpleNamespace

import pytest

from creditcoach import config
from creditcoach import observability as obs

TRACE = "ab" * 16


@pytest.fixture
def app(monkeypatch, tmp_path):
    from creditcoach.app import main

    monkeypatch.setattr(config, "MEMORY_DIR", tmp_path / "memory")
    monkeypatch.setattr(main, "_sessions", {})
    monkeypatch.setattr(main, "_answer_traces", main.OrderedDict())
    fake = SimpleNamespace(text="Your score is 650.", model="m", passages=[], tool_calls=[], retrieval_seconds=0.1,
                           generation_seconds=1.0, sources="650", trace_id=TRACE)
    monkeypatch.setattr(main, "answer", lambda q, user_id, **kw: fake)
    return main


@pytest.fixture
def scores(monkeypatch):
    sent = []
    monkeypatch.setattr(obs, "score", lambda trace_id, name, value, comment=None: sent.append((trace_id, name, value,
                                                                                               comment)) or True)
    return sent


def request():
    return SimpleNamespace(username="creditcoach_user1", session_hash="s1")


def rate(app, reply, liked):
    app.feedback(SimpleNamespace(value=reply, liked=liked, index=1), request())


def test_a_thumbs_up_is_attached_to_the_answers_trace(app, scores):
    reply = app.final_reply("What is my score?", [], request())
    rate(app, reply, True)
    assert scores == [(TRACE, "user.feedback", True, "helpful")]


@pytest.mark.parametrize("value", [
    lambda reply: reply,                                      # the text
    lambda reply: {"role": "assistant", "content": reply},    # a message
    lambda reply: [{"type": "text", "text": reply}],          # a list of parts
])
def test_the_reply_is_recognised_however_gradio_hands_it_back(app, scores, value):
    reply = app.final_reply("What is my score?", [], request())
    rate(app, value(reply), False)
    assert scores == [(TRACE, "user.feedback", False, "not helpful")]


def test_a_thumbs_down_reason_is_kept_as_its_own_score(app, scores):
    reply = app.final_reply("What is my score?", [], request())
    rate(app, reply, "Too slow")
    assert scores == [(TRACE, "user.feedback", False, "Too slow"), (TRACE, "user.feedback.reason", "Too slow", None)]


def test_ratings_on_anything_but_a_known_answer_are_ignored(app, scores):
    app.final_reply("What is my score?", [], request())
    rate(app, "What is my score?", True)              # the user's own message
    rate(app, "an answer from before a restart", False)
    reply = app.final_reply("What is my score?", [], request())
    rate(app, reply, "")                               # un-liking
    app.feedback(SimpleNamespace(value=reply, liked=True, index=1), SimpleNamespace(username=None, session_hash="x"))
    assert scores == []


def test_the_chat_offers_the_feedback_reasons():
    from creditcoach.app import main

    chatbots = [b for b in main.build().blocks.values() if type(b).__name__ == "Chatbot"]
    assert chatbots and tuple(chatbots[0].feedback_options) == main.FEEDBACK_OPTIONS
