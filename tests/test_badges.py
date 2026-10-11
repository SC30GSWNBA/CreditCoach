"""Task 25: the guardrail and cache badges above each chat answer, and their steps in the agent trace.

No API key needed: decisions and cache reports are built by hand.

Run:
    uv run pytest tests/test_badges.py -v
"""

from types import SimpleNamespace

import pytest

from creditcoach.app import badges
from creditcoach.app.trace import Trace
from creditcoach.guardrails import Decision, Finding, Screen
from creditcoach.memory import recall

PRODUCT = Finding("G2", "detect product mention", "the question mentions a predatory product", ["payday loan"])
SOFT = Finding("G2", "check product answer", "the answer softens the refusal with advice on going ahead anyway", ["If you still"])
PROMISE = Finding("G1", "check guarantee", "the answer promises a score outcome or uses guarantee wording", ["you'll hit 720"])
FIGURE = Finding("G3", "check figures", "figures that don't trace to this turn's tool output or the library", ["413000"])
PAN = Finding("S3", "mask identifiers", "personal identifiers removed from the message", ["PAN", "card number"])
ATTACK = Finding("S1", "detect attack attempt", "the message asks CreditCoach to drop its rules", ["Ignore your rules"])
LEAK = Finding("S2", "detect attack attempt", "the message asks for CreditCoach's instructions", ["system prompt"])


def decision(action="passed", asked=(), found=(), **kw):
    return Decision(action, Screen("q", findings=list(asked)), findings=list(found), **kw)


@pytest.mark.parametrize("d, kind, text", [
    (decision(), "ok", "🛡️ Guardrails: passed"),
    (decision(asked=[PRODUCT], reviewed=True), "refuse", "🛡️ Guardrails: high-risk product, not endorsed"),
    (decision(reviewed=True, projection=True), "refuse", "🛡️ Guardrails: no guarantee given"),
    (decision("reframed", found=[PROMISE]), "rewrite", "🛡️ Guardrails: answer rewritten <small>· it promised or predicted a score"),
    (decision("reframed", asked=[PRODUCT], found=[SOFT]), "rewrite", "answer rewritten <small>· it went soft on a high-risk product"),
    (decision("blocked", found=[FIGURE]), "block", "🛡️ Guardrails: answer blocked <small>· a figure couldn&#x27;t be traced to your data"),
])
def test_the_guardrail_badge_says_what_the_layer_did(d, kind, text):
    first = badges.guardrail(d)[0]
    assert first.startswith(f'<span class="cc-badge cc-{kind}">') and text in first


def test_input_rails_get_their_own_badges_and_reasons_are_not_repeated():
    out = badges.guardrail(decision(asked=[PAN, ATTACK, LEAK]))
    assert len(out) == 4 and "Personal details hidden <small>· PAN, card number" in out[1]
    assert "switch the rules off: ignored" in out[2] and "hidden instructions: declined" in out[3]
    twice = badges.guardrail(decision("reframed", asked=[PRODUCT], found=[SOFT, SOFT, PROMISE]))
    assert twice[0].count("went soft") == 1 and "; it promised" in twice[0] and "High-risk product asked about" in twice[1]
    assert badges.guardrail(None) == []


@pytest.mark.parametrize("report, kind, text", [
    ({"status": "hit", "how": "exact", "saved_seconds": 10.9}, "hit", "⚡ Cache hit · saved 11 s <small>· same question<"),
    ({"status": "hit", "how": "model-confirmed", "saved_seconds": 7.2}, "hit", "saved 7 s <small>· same question, reworded"),
    ({"status": "hit", "how": "same words", "saved_seconds": 0.2}, "hit", "⚡ Cache hit <small>· same question, reworded"),
    ({"status": "miss", "stored": True}, "miss", "Cache miss · answered live <small>· saved for next time"),
    ({"status": "miss", "stored": False, "reason": "a tool call failed"}, "miss", "Cache miss · answered live</span>"),
    ({"status": "skip", "reason": "the input rails flagged the question"}, "miss", "Cache not used <small>· the input rails flagged the question"),
])
def test_the_cache_badge_shows_hit_miss_or_why_not(report, kind, text):
    (badge,) = badges.cached(report)
    assert badge.startswith(f'<span class="cc-badge cc-{kind}">') and text in badge


def test_no_cache_badge_when_the_answer_cache_is_off():
    assert badges.cached({"status": "off", "events": []}) == badges.cached(None) == []


def answer(**kw):
    base = dict(text="Your score is 650.", model="m", passages=[], tool_calls=[], retrieval_seconds=0.0,
                generation_seconds=0.1, sources="score 650", guardrail=decision(), cache={"status": "hit", "how": "exact",
                                                                                           "saved_seconds": 11.0})
    return SimpleNamespace(**{**base, **kw})


def test_the_reply_starts_with_the_badge_row_then_the_answer():
    from creditcoach.app import main as app
    reply = app.format_reply(answer())
    assert reply.startswith('<div class="cc-badges"><span class="cc-badge cc-ok">🛡️ Guardrails: passed</span> '
                            '<span class="cc-badge cc-hit">⚡ Cache hit · saved 11 s')
    assert "</div>\n\nYour score is 650.\n\n---\n" in reply
    plain = app.format_reply(SimpleNamespace(text="Hi.", model="m", passages=[], tool_calls=[], retrieval_seconds=0,
                                             generation_seconds=0))
    assert plain.startswith("Hi.")  # an answer with no guardrail decision or cache report gets no row


def test_a_broken_badge_never_hides_the_answer(monkeypatch):
    from creditcoach.app import main as app
    monkeypatch.setattr(badges, "row", lambda a: 1 / 0)
    assert app.format_reply(answer()).startswith("Your score is 650.")


def test_badges_and_footer_are_stripped_from_the_history_sent_to_the_model():
    from creditcoach.app import main as app
    reply = app.format_reply(answer())
    history = [{"role": "user", "content": "What's my score?"}, {"role": "assistant", "content": reply}]
    assert recall.history_messages(history)[1] == {"role": "assistant", "content": "Your score is 650."}
    assert badges.STRIP.sub("", reply).startswith("Your score is 650.")


def test_text_in_badges_is_escaped():
    odd = Finding("S3", "mask identifiers", "x", ["<b>PAN</b>"])
    assert "<b>" not in badges.guardrail(decision(asked=[odd]))[1]


# ---- In the agent trace ----

def test_the_trace_shows_the_guardrail_check_and_its_outcome():
    t = Trace(question="q")
    t.update("model", {"round": 1})
    t.update("guardrail", {"status": "start"})
    assert [s.title for s in t.steps] == ["✍️ Wrote your answer", "🛡️ Checking the answer against the guardrails"]
    assert not t.steps[-1].done
    t.update("guardrail", {"status": "done", "decision": decision("reframed", asked=[PRODUCT], found=[SOFT], reviewed=True)})
    step = t.steps[-1]
    assert step.done and step.title == "🛡️ Guardrails: answer rewritten"
    assert "Input: the question mentions a predatory product (payday loan)" in step.log
    assert "Draft: the answer softens the refusal" in step.log and "rewrite passed (rules: G2)" in step.log
    assert "Wording reviewed" in step.log
    t.update("answer", {"status": "done", "model": "m"})
    assert t.ended is not None and "3 steps" not in t.messages()[0].metadata["title"]  # model + guardrail = 2 steps


def test_the_trace_says_no_rule_was_triggered_for_a_clean_pass():
    t = Trace(question="q")
    t.update("guardrail", {"status": "start"})
    t.update("guardrail", {"status": "done", "decision": decision()})
    assert (t.steps[-1].title, t.steps[-1].log) == ("🛡️ Guardrails: passed", "No rule was triggered.")
    t.update("guardrail", {"status": "done", "decision": decision("blocked", found=[FIGURE])})
    assert t.steps[-1].title == "🛡️ Guardrails: answer blocked" and "fixed safe message" in t.steps[-1].log


def test_the_trace_shows_a_cache_hit_as_its_only_step():
    t = Trace(question="q")
    t.update("cache", {"status": "hit", "report": {"how": "exact", "age_seconds": 42, "saved_seconds": 10.9}})
    t.update("answer", {"status": "done", "model": "m"})
    (step,) = t.steps
    assert step.title == "⚡ Answered from the cache" and "stored 42 s ago" in step.log and "about 11 s" in step.log
    assert "haven't changed" in step.log and "1 step, 0 tool calls" in t.messages()[0].metadata["title"]
