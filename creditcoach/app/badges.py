"""The badges above each chat answer (Task 25): what the guardrail layer did, and whether the cache was used.

``row(answer)`` returns one line of HTML that ``app.main.format_reply`` puts above the answer text:

    Guardrails   🛡️ passed                          the draft went out unchanged
                 🛡️ high-risk product: not endorsed  a predatory product was asked about; the answer flags the risk,
                                                    offers a safer alternative and was reviewed for endorsement
                 🛡️ no guarantee given               a projection was asked for; the answer was reviewed for promises
                 🛡️ answer rewritten                 a draft broke a rule and the model rewrote it (with the reason)
                 🛡️ answer blocked                   the rewrite still broke a rule: a fixed safe message was shown
                 plus one small badge for each thing the input rails did: personal details hidden, an attempt to
                 switch the rules off ignored, a request for the hidden prompt declined
    Cache        ⚡ cache hit · saved N s            a stored answer to the same question was served
                 cache miss · answered live         with "saved for next time" when the answer was stored
                 cache not used                     with the reason (for example a follow-up question)

The badges are plain ``<span class="cc-badge ...">`` elements styled by ``CSS``, which the app passes to Gradio
with the chart styles. ``STRIP`` removes the row again when a reply is sent back to the model as chat history.

Example:
    >>> from creditcoach.app import badges
    >>> badges.row(answer)      # an agent.pipeline.Answer
    '<div class="cc-badges"><span class="cc-badge cc-ok">🛡️ Guardrails: passed</span> ...</div>'
"""

import html
import re

CSS = """
.cc-badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 10px 0; }
.cc-badge { display: inline-flex; align-items: center; gap: 4px; font-size: .8rem; font-weight: 600; line-height: 1.5;
  border-radius: 999px; padding: 1px 10px; border: 1px solid transparent; white-space: nowrap; }
.cc-badge small { font-weight: 500; font-size: .76rem; opacity: .9; }
.cc-ok { background: #e6f4ea; color: #0b5c1f; border-color: #b7dfc1; }
.cc-refuse { background: #fff1e0; color: #8a4500; border-color: #f3cf9e; }
.cc-rewrite { background: #fff8d6; color: #6b5200; border-color: #ecd98a; }
.cc-block { background: #fde8e8; color: #9b1c1c; border-color: #f3b8b8; }
.cc-hit { background: #e3effd; color: #0b4a99; border-color: #b3d1f5; }
.cc-miss { background: var(--background-fill-secondary); color: var(--body-text-color-subdued); border-color: var(--border-color-primary); }
.cc-note { background: #f0ebfa; color: #4b2e83; border-color: #d3c5ee; }
.dark .cc-ok { background: #12351c; color: #9ee2b0; border-color: #1f5a30; }
.dark .cc-refuse { background: #40280a; color: #ffcf8f; border-color: #6b4513; }
.dark .cc-rewrite { background: #3a3206; color: #f2dc7a; border-color: #5f520c; }
.dark .cc-block { background: #451313; color: #ffb3b3; border-color: #7a2323; }
.dark .cc-hit { background: #0f2c52; color: #a9cdfb; border-color: #1c4a86; }
.dark .cc-note { background: #2b1f47; color: #d5c6f7; border-color: #47347a; }
"""
STRIP = re.compile(r'^<div class="cc-badges">.*?</div>\n*', re.S)
"""Matches the badge row at the start of a reply, so chat history sent to the model carries the answer only."""

WHY = {  # why a draft was rewritten or blocked, by rule (docs/guardrails.md)
    "G1": "it promised or predicted a score",
    "G2": "it went soft on a high-risk product",
    "G3": "a figure couldn't be traced to your data",
    "S2": "it repeated internal instructions",
    "S4": "it referred to another user",
}
INPUT_NOTES = {  # what an input rail did, by rule
    "S1": "🚧 Attempt to switch the rules off: ignored",
    "S2": "🚧 Request for hidden instructions: declined",
}


def _badge(kind: str, text: str, detail: str = "") -> str:
    return (f'<span class="cc-badge cc-{kind}">{html.escape(text)}'
            + (f" <small>· {html.escape(detail)}</small>" if detail else "") + "</span>")


def guardrail(decision) -> list[str]:
    """The guardrail badges for one ``guardrails.Decision``: the outcome first, then what the input rails did."""
    if decision is None:
        return []
    reasons = "; ".join(dict.fromkeys(WHY[f.rule] for f in decision.findings if f.rule in WHY))
    asked = {f.rule for f in decision.screen.findings}
    if decision.action == "blocked":
        out = [_badge("block", "🛡️ Guardrails: answer blocked", reasons)]
    elif decision.action == "reframed":
        out = [_badge("rewrite", "🛡️ Guardrails: answer rewritten", reasons)]
    elif "G2" in asked:
        out = [_badge("refuse", "🛡️ Guardrails: high-risk product, not endorsed")]
    elif getattr(decision, "projection", False):
        out = [_badge("refuse", "🛡️ Guardrails: no guarantee given")]
    else:
        out = [_badge("ok", "🛡️ Guardrails: passed")]
    if "G2" in asked and decision.action != "passed":
        out.append(_badge("note", "⚠️ High-risk product asked about"))
    for f in decision.screen.findings:
        if f.rule == "S3":
            out.append(_badge("note", "🔒 Personal details hidden", ", ".join(f.matched)))
        elif f.rule in INPUT_NOTES:
            out.append(_badge("note", INPUT_NOTES[f.rule]))
    return out


def cached(report: dict | None) -> list[str]:
    """The cache badge for one ``Answer.cache`` report; nothing when the answer cache is off."""
    status = (report or {}).get("status", "off")
    if status == "hit":
        how = {"exact": "same question", "same words": "same question, reworded",
               "model-confirmed": "same question, reworded"}.get(report.get("how"), "")
        saved = report.get("saved_seconds")
        return [_badge("hit", "⚡ Cache hit" + (f" · saved {saved:.0f} s" if saved and saved >= 1 else ""), how)]
    if status == "miss":
        return [_badge("miss", "Cache miss · answered live", "saved for next time" if report.get("stored") else "")]
    if status == "skip":
        return [_badge("miss", "Cache not used", report.get("reason", ""))]
    return []


def row(a) -> str:
    """The badge row for one answer, or "" when there is nothing to show."""
    items = guardrail(getattr(a, "guardrail", None)) + cached(getattr(a, "cache", None))
    return f'<div class="cc-badges">{" ".join(items)}</div>' if items else ""
