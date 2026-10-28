"""Ambiguous references (Task 32): "Should I take this loan?" when no loan has been named.

requirements.md §4 #47: CreditCoach must ask which loan and what terms before judging, and not assume a product.
The model usually does, but only because the prompt asks it to; this check makes it deterministic. When the question
points at a loan, offer or app ("this loan", "that offer", "the app") and neither the question nor the user's earlier
turns in this chat say what it is, the pipeline adds a note telling the model to ask first.

Questions about repaying or closing a loan they already have ("Should I close the loan early?") get no note: the
tools show their loans. What counts as naming it: a kind of loan or credit ("car loan", "credit card", "BNPL"), a predatory product the
guardrails know (G2: payday loan, instant loan app, ...), or terms (an amount in rupees, an interest rate, a tenure).
Once the user describes it, the next turn has no note, and a payday or instant-app loan gets the #4 behavior from
the guardrail layer as usual.

Example:
    >>> note("Should I take this loan?", [])            # a note asking the model to ask which loan
    >>> note("Should I take this loan?", ["My bank offered me a ₹2 lakh personal loan at 14%."])
    ''
"""

import re

from creditcoach.guardrails import checks

REFERENCE = re.compile(r"\b(?:this|that|these|those|the)\s+(?:new\s+)?(?:loans?|offers?|deals?|apps?|products?|schemes?"
                       r"|lenders?|credit lines?)\b", re.I)
NAMED = re.compile(
    r"\b(?:personal|car|auto|vehicle|bike|two[- ]wheeler|home|housing|mortgage|education|student|gold|business"
    r"|consumer[- ]durable|top[- ]up|property|salary|emergency)\s+loans?\b|\bloan against\b|\bcredit cards?\b"
    r"|\bbalance transfer\b|\bbuy now,? pay later\b|\bbnpl\b|\boverdraft\b|\bemi\b"
    r"|₹\s?[\d,]+|\brs\.?\s?[\d,]+|\b\d+(?:\.\d+)?\s?(?:%|percent|lakh|lac|crore|k)\b"
    r"|\b(?:interest|apr|tenure|processing fee)\b|\b\d+\s?(?:months?|years?|days?)\b", re.I)

EXISTING = re.compile(r"\b(?:close|closing|prepay\w*|pay(?:ing)? (?:it |this |that |the loan )?off|foreclos\w*|repay\w*"
                      r"|clear\w*|settle\w*)\b", re.I)  # about a loan they already have: the tools show it

NOTE = ("CLARIFY (from CreditCoach, not from the user): the user refers to {ref!r}, but neither this question nor "
        "their earlier messages say which loan, offer or app it is. Before judging it, ask what it is (the kind of "
        "loan or product and the lender) and its terms (amount, interest rate or fees, and repayment period). Don't "
        "assume a product type and don't say whether to take it yet. You may say briefly what you'll look at once you "
        "know, and which of their figures from the tools will matter.")


def named(text: str) -> bool:
    """Whether ``text`` says what kind of loan or product it is, or gives its terms."""
    return bool(NAMED.search(text) or checks.products(text))


def note(question: str, earlier: list[str]) -> str:
    """The CLARIFY note for an unexplained reference in ``question``, or "" if there is none or the loan was named.

    Args:
        question: The user's question (identifiers already masked).
        earlier: The user's earlier messages in this chat, oldest first.
    """
    ref = REFERENCE.search(question)
    if not ref or EXISTING.search(question) or named(question) or any(named(t) for t in earlier):
        return ""
    return NOTE.format(ref=ref.group(0))
