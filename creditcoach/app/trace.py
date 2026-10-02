"""The agent trace in the chat (Task 18): live progress while an answer is built, then an expandable record of it.

The pipeline reports each step (``agent.pipeline.Progress``). ``Trace`` turns those events into Gradio chat messages
with metadata, which the chat window shows as one collapsible "Agent trace" block above the answer:

    While the user waits  Each step appears as it starts, with a spinner and a running timer: searching the library,
                          recalling memory, checking score history or accounts, writing the answer. While the model
                          writes (the slowest step), a short credit tip from the library rotates under it, so the
                          wait is visibly busy rather than blank.
    After the answer      The block collapses to "Agent trace · N steps · Xs" and can be expanded: every tool call
                          with its arguments and a one-line result, the recalled goal, and the passages used.

Results are summarised, never dumped: the answer itself carries the figures, and the trace says where they came from.

Example:
    >>> t = Trace(question="Why did my score drop?")
    >>> t.update("retrieval", {"status": "start"})
    >>> t.messages()            # list of gr.ChatMessage for the chat window
"""

import time
from dataclasses import dataclass, field

import gradio as gr

TRACE_ID = "trace"
TIP_EVERY = 6.0  # seconds each waiting tip stays on screen
TIP_AFTER = 2.0  # don't show a tip for a step that finishes quickly
# Short facts from the credit library (corpus/), labelled typical where they are ranges. Shown only while waiting.
TIPS = [
    "Checking your own credit score is a soft inquiry. It never lowers your score.",
    "Payment history is usually the biggest single factor in a credit score.",
    "Keeping each card below about 30% of its limit is commonly associated with healthier scores.",
    "A hard inquiry typically costs about 2 to 10 points, and its effect usually fades within about 12 months.",
    "Paying before your statement date can lower the balance that gets reported to the bureaus.",
    "In India you can get one free full credit report a year from each credit bureau.",
    "Keeping an old no-fee card open helps both your credit history length and your total limit.",
]
TOOL_TITLES = {
    "get_score_history": "📈 Checking your score history",
    "get_account_summary": "💳 Reading your accounts and card limits",
    "save_goal": "🎯 Saving your goal",
    "clear_goal": "🗑️ Clearing your goal",
}


@dataclass
class Step:
    """One line in the trace."""
    id: str
    title: str
    started: float
    ended: float | None = None
    log: str = ""
    waiting: bool = False  # a model turn: shows a rotating tip while pending

    @property
    def done(self) -> bool:
        return self.ended is not None


def _goal(goal) -> str:
    if goal is None:
        return "No goal saved yet."
    bits = [f"target {goal.target_score}" if goal.target_score else None,
            f"by {goal.target_date}" if goal.target_date else None,
            goal.purpose]
    return "Goal: " + ", ".join(b for b in bits if b) + f" (saved {goal.set_at[:10]})."


def summarise(call) -> str:
    """A one-line description of a tool call's result, with no more figures than the answer itself shows."""
    r = call.result
    if not call.ok:
        retried = " after a retry" if getattr(call, "attempts", 1) > 1 else ""
        return f"Couldn't complete{retried}: {call.code}. {r.get('error', {}).get('message', '')}".strip()
    if call.tool == "get_score_history":
        if not r.get("has_credit_file"):
            return "No credit history on file yet."
        p, s = r["period"], r["summary"]
        latest = r["points"][-1]
        change = f", {latest['change']:+d} that month" if latest.get("change") is not None else ""
        return (f"{len(r['points'])} month(s), {p['start']} to {p['end']}. Latest: {latest['score']} "
                f"({latest['date'][:7]}{change}, {latest['factor_change']}). Net change {s['net_change']:+d}.")
    if call.tool == "get_account_summary":
        if not r.get("has_credit_file"):
            return "No accounts on file yet."
        t = r["totals"]
        ratio = t["overall_utilization_ratio"]
        risky = sum(a["high_risk_product"] for a in r["accounts"])
        return (f"{t['revolving_count']} card(s), {t['installment_count']} loan(s). "
                + (f"Overall card utilization {ratio * 100:.1f}%." if ratio is not None else "No credit card, so no utilization.")
                + (f" {risky} high-risk product flagged." if risky else ""))
    if call.tool == "save_goal":
        g, prev = r["goal"], r.get("previous")
        now = ", ".join(str(v) for v in (g["target_score"], g["target_date"], g["purpose"]) if v)
        was = ", ".join(str(v) for v in (prev["target_score"], prev["target_date"], prev["purpose"]) if v) if prev else None
        return f"Saved: {now}." + (f" Was: {was}." if was else "")
    if call.tool == "clear_goal":
        return "Goal cleared." if r.get("cleared") else "There was no goal to clear."
    return "Done."


@dataclass
class Trace:
    """The trace for one answer. Feed it pipeline progress events with ``update``; render it with ``messages``."""
    question: str = ""
    started: float = field(default_factory=time.monotonic)
    ended: float | None = None
    failed: bool = False
    steps: list[Step] = field(default_factory=list)

    def _open(self, id_: str, title: str, waiting: bool = False) -> Step:
        step = Step(id=id_, title=title, started=time.monotonic(), waiting=waiting)
        self.steps.append(step)
        return step

    def _close_waiting(self, outcome: str) -> None:
        """Finish an open model step, titled by what the model did: called a tool, or wrote the answer."""
        for s in self.steps:
            if s.waiting and not s.done:
                s.ended, s.log = time.monotonic(), ""
                s.title = ("🤔 Read your question and decided what to check" if s.id == "model-1" else
                           "🤔 Decided to check more of your data") if outcome == "tool" else "✍️ Wrote your answer"

    def update(self, step: str, details: dict) -> None:
        """Apply one ``pipeline.Progress`` event."""
        now = time.monotonic()
        if step == "retrieval" and details.get("status") == "start":
            self._open("retrieval", "📚 Searching the CreditCoach library")
        elif step == "retrieval":
            s = next(s for s in self.steps if s.id == "retrieval")
            s.ended, s.title = now, "📚 Searched the CreditCoach library"
            s.log = "\n".join(f"• {p.title}" for p in details.get("passages", [])) or "No matching passages."
        elif step == "memory":
            s = self._open("memory", "🧠 Recalled your memory")
            n = details.get("sessions", 0)
            s.ended = now
            s.log = f"{_goal(details.get('goal'))}\n{n} earlier conversation{'s' if n != 1 else ''}."
        elif step == "model":
            self._close_waiting("tool")
            first = details.get("round", 1) == 1
            self._open(f"model-{details.get('round', 1)}",
                       "🤔 Reading your question and deciding what to check" if first else "✍️ Writing your answer",
                       waiting=True)
        elif step == "tool" and details.get("status") == "start":
            self._close_waiting("tool")
            args = ", ".join(f"{k}={v}" for k, v in (details.get("arguments") or {}).items() if k != "quote")
            title = TOOL_TITLES.get(details["name"], f"🔧 {details['name']}")
            self._open(f"tool-{len(self.steps)}", title + (f" ({args})" if args else ""))
        elif step == "tool":
            call = details["call"]
            s = next(s for s in reversed(self.steps) if s.id.startswith("tool-") and not s.done)
            s.ended, s.log = now, summarise(call)
            if not call.ok:
                s.title = "⚠️ " + s.title.split(" ", 1)[1]
        elif step == "answer":
            self.finish()

    def finish(self, failed: bool = False) -> None:
        """Close every open step and the trace itself."""
        if not failed:
            self._close_waiting("answer")
        now = time.monotonic()
        for s in self.steps:
            if not s.done:
                s.ended = now
                if s.waiting:
                    s.log = ""
        self.ended, self.failed = now, failed

    def _tip(self, step: Step, now: float) -> str:
        waited = now - step.started
        if waited < TIP_AFTER:
            return ""
        return f"💡 While you wait: {TIPS[int(waited // TIP_EVERY + len(self.question)) % len(TIPS)]}"

    def messages(self) -> list[gr.ChatMessage]:
        """The trace as chat messages: a parent block and one child per step."""
        now = time.monotonic()
        total = (self.ended or now) - self.started
        tools = sum(s.id.startswith("tool-") for s in self.steps)
        if self.ended is None:
            title = f"🧭 Working on your answer… {total:.0f}s"
        elif self.failed:
            title = f"🧭 Agent trace · stopped after {total:.1f}s"
        else:
            title = f"🧭 Agent trace · {len(self.steps)} steps, {tools} tool call{'s' if tools != 1 else ''} · {total:.1f}s"
        out = [gr.ChatMessage(role="assistant", content="", metadata={
            "id": TRACE_ID, "title": title, "status": "done" if self.ended else "pending",
            **({"duration": round(total, 1)} if self.ended else {})})]
        for s in self.steps:
            elapsed = (s.ended or now) - s.started
            content = s.log if s.done else (self._tip(s, now) if s.waiting else "")
            meta = {"id": s.id, "parent_id": TRACE_ID, "status": "done" if s.done else "pending",
                    "title": s.title if s.done else f"{s.title}… {elapsed:.0f}s"}
            if s.done:
                meta["duration"] = round(elapsed, 1)
            out.append(gr.ChatMessage(role="assistant", content=content, metadata=meta))
        return out
