"""The confidence line under each chat answer: a percentage for how well the answer is backed by the user's data and
the library, with the reason.

It is worked out from the finished answer by fixed checks, with no extra model call (a few milliseconds), so it
appears with the answer. An answer with no problem found gets ``BASE``; each problem takes points off (``floor``
is the least it can show):

    Your data        Each data tool the answer needed returned data this turn. One that never did means the answer
                     can't rest on those figures: ``UNREAD`` points off for each.
    Figures          Every number in the answer is in the user's data, the library passages, their profile, memory or
                     the conversation, or is calculated from those (``golden.untraced_numbers``). Any that isn't is
                     named, so the user knows which figure to double-check, and costs up to ``UNTRACED`` points in
                     proportion to the share of the answer's figures that couldn't be traced (at least
                     ``UNTRACED_MIN``).
    Library          The answer says the library has nothing on the topic (the system prompt's "I don't have specific
                     information on that"): ``GAP`` off. It cites an [n] that isn't a listed passage: ``BAD_CITATION``.
    No promises      A sentence promises a score outcome (``golden.unhedged_guarantees``): ``PROMISE`` off.

Why ``BASE`` is 90 and not 100: of the 46 saved Task 15 answers these checks find nothing wrong with, 41 (89%) pass
the golden checks; the other 5 leave out something the answer should have said, which these checks can't see. The
deductions are judgments about how much each problem matters, not measured error rates, so below 90 the number orders
answers by how well backed they are rather than giving the chance that they are right.

The figure check is weakest on small numbers: measured on the same answers, an invented rupee amount is caught more
than 9 times in 10, but an invented change of a few dozen points only about 1 time in 3, because so many small numbers
are a sum or difference of two real ones.

Example:
    >>> from creditcoach.app import confidence
    >>> c = confidence.assess(answer)       # an agent.pipeline.Answer
    >>> c.percent, confidence.line(c)
"""

import re
from dataclasses import dataclass, field

from creditcoach.evals import golden

DATA_TOOLS = {"get_score_history": "score history", "get_account_summary": "accounts"}
# Figures every answer may use without a source: the 300-900 score range (system prompt) and the 30% utilization and
# 30-days-late thresholds, which the library states but the 3 passages retrieved for a question may not include.
COMMON = frozenset({"300", "900", "30"})
GAP_WORDS = re.compile(r"don't have (?:any )?specific information", re.I)
BASE, FLOOR = 90, 10
UNREAD, UNTRACED, UNTRACED_MIN, GAP, BAD_CITATION, PROMISE = 40, 40, 10, 20, 10, 15
SHOWN = 3  # untraced figures named in the line; the rest are counted


@dataclass
class Confidence:
    """The result for one answer.

    Attributes:
        percent: ``FLOOR`` to ``BASE``.
        reasons: Why, in the user's words: the problems found, or what backs the answer when there are none.
        untraced: Figures in the answer that couldn't be traced to a source, as the answer writes them.
    """
    percent: int
    reasons: list[str]
    untraced: list[str] = field(default_factory=list)


def _as_written(text: str, number: str) -> str:
    """``number`` as the answer shows it ("₹25,000", "18.9%"), so the user can find it."""
    for m in re.finditer(r"(?:₹\s?)?\d+(?:,\d+)*(?:\.\d+)?%?", text):
        if float(m.group().strip("₹ %").replace(",", "")) == float(number):
            return m.group()
    return number


def assess(a) -> Confidence:
    """Check one answer and return its confidence percentage with the reasons.

    Args:
        a: An ``agent.pipeline.Answer``. Its ``sources`` (which include the question) are what the figures are
            traced to.
    """
    text = a.text.replace("’", "'")
    unread = [label for tool, label in DATA_TOOLS.items()
              if any(c.tool == tool for c in a.tool_calls) and not any(c.tool == tool and c.ok for c in a.tool_calls)]
    figures = [n for n in golden.numbers(a.text) if float(n) > 12]
    untraced = [_as_written(a.text, n)
                for n in golden.untraced_numbers(a.text, getattr(a, "sources", ""), known=COMMON)]
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
    off, problems = 0, []
    if unread:
        off += UNREAD * len(unread)
        problems.append(f"couldn't read your {' or '.join(unread)} just now, so this answer isn't based on "
                        f"{'them' if len(unread) > 1 or unread[0] == 'accounts' else 'it'}")
    if untraced:
        off += max(UNTRACED_MIN, round(UNTRACED * len(untraced) / len(figures)))
        more = f" and {len(untraced) - SHOWN} more" if len(untraced) > SHOWN else ""
        problems.append(f"couldn't trace {', '.join(untraced[:SHOWN])}{more} to your data or the library, so "
                        f"double-check {'it' if len(untraced) == 1 else 'them'}")
    if GAP_WORDS.search(text):
        off += GAP
        problems.append("the library doesn't cover this topic, so parts of this are general guidance")
    if any(not 1 <= n <= len(a.passages) for n in cited):
        off += BAD_CITATION
        problems.append("it cites a source that isn't in the list below")
    if golden.unhedged_guarantees(a.text):
        off += PROMISE
        problems.append("some wording may read as a promise, and no one can guarantee a score")
    if problems:
        return Confidence(max(FLOOR, BASE - off), problems, untraced)
    read = any(c.ok and c.tool in DATA_TOOLS for c in a.tool_calls)
    if figures:
        reason = f"every figure traces to {'your live data or ' if read else ''}the library"
    else:
        reason = ("your data was read live, and " if read else "") + "it states no figures that need checking"
    return Confidence(BASE, [reason])


def line(c: Confidence) -> str:
    """The Markdown line shown under the answer, for example "**Confidence: 90%** · every figure traces to …"."""
    return f"**Confidence: {c.percent}%** · {'; '.join(c.reasons)}"
