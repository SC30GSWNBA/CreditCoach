"""Model routing: which chat model answers a question (``CREDITCOACH_ROUTER=on``).

The 50-case eval (2026-11-05) put Sonnet 5.5 at 45, 44 and 46 of 50 for $0.026 an answer, and DeepSeek V4.1 Flash
at 44, 45, 38 and 40 for $0.0015, twice as fast. DeepSeek's misses clustered in three kinds of question, so those go
to ``CHAT_MODEL`` and everything else to ``FAST_MODEL``:

    flagged     The input rails noticed something: a predatory product (G2), an attempt to switch the rules off or
                insert personal data (S1-S3), or a question about how CreditCoach is built (S5). These are the
                answers where a wrong word costs most.
    goal        Goals, plans and memory: saving, changing or recalling a goal, a target score, "what should I focus
                on", a timeframe ("in 6 months", "by 2027"), or a promise about reaching a score.
    multi-step  Arithmetic over the user's figures or a named period: "how much", "how long", "what if", a month and
                year, "last two months", or two figures to compare. DeepSeek once gave 690 -> 650 as a net -20.

The rules are plain patterns on the masked question, so routing adds no model call and no time. They were written
from those kinds of question, not from case numbers, but the eval that measures them is the one they came from:
check the share of real questions each model gets (``router.model`` on the ``creditcoach.answer`` span).

Example:
    >>> route("What is a credit score?", Screen("What is a credit score?")).reason
    'general'
"""

import re
from dataclasses import dataclass

from creditcoach import config
from creditcoach.guardrails.rails import Screen

MONTHS = r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
NUMBER_WORDS = r"\d+|a|an|one|two|three|four|five|six|nine|twelve|eighteen|few|couple of"
GOAL = re.compile(
    r"\b(?:goals?|target|aim(?:ing)?|remember|save|saving|plan|planning|focus|prioriti[sz]e|guarantee|promise)\b"
    r"|\b(?:in|within|over the next|next) (?:" + NUMBER_WORDS + r") (?:months?|years?)\b"
    r"|\bby (?:next|the end of) (?:year|month)\b|\bby (?:" + MONTHS + r")?\s*20\d\d\b"
    r"|\bnext year\b|\bmonths? (?:now|left)\b|\bwill (?:i|my score) (?:hit|reach|get to|be)\b", re.I)
MULTI_STEP = re.compile(
    r"\bhow (?:much|many|long)\b|\bwhat if\b|\bif i (?:pay|clear|close|open|take|miss)\b"
    r"|\b(?:last|past) (?:" + NUMBER_WORDS + r") (?:months?|years?)\b"
    r"|\b(?:" + MONTHS + r")\w*\s+20\d\d\b|\bfrom \d{3} to \d{3}\b", re.I)
TOOL_MARKUP = re.compile(r"<[｜|]?\s*DSML|<\|?tool_calls?\|?>|<function_calls?>|<invoke name=|<\|?tool_call_begin", re.I)


@dataclass
class Route:
    """The model chosen for one question and why: ``reason`` is ``flagged``, ``goal``, ``multi-step``,
    ``general`` (the fast model) or ``off`` (the router is off, so ``CHAT_MODEL``)."""
    model: str
    reason: str


def route(question: str, screened: Screen) -> Route:
    """Pick the model for a question from what the input rails found and the question's wording."""
    if config.ROUTER != "on":
        return Route(config.CHAT_MODEL, "off")
    if screened.findings or screened.products:
        return Route(config.CHAT_MODEL, "flagged")
    if GOAL.search(question):
        return Route(config.CHAT_MODEL, "goal")
    if MULTI_STEP.search(question) or len(re.findall(r"\b\d{3}\b", question)) >= 2:
        return Route(config.CHAT_MODEL, "multi-step")
    return Route(config.FAST_MODEL, "general")


def looks_like_tool_markup(text: str | None) -> bool:
    """True if a reply is a tool call written out as text (seen once from DeepSeek: ``<｜DSML｜ invoke ...>``), which
    must never reach the user."""
    return bool(text and TOOL_MARKUP.search(text))
