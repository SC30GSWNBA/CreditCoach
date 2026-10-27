"""Data-aware retrieval (Task 30): search the library for what the user's own data says, not only the question.

The Task 29 error analysis found three answers that missed the library's key fact because the question doesn't name
it; only the user's data does. "Why did my score crash in April?" never says "late payment", but April's entry in
the score history is "Late payment (30+ days)", and searching on that label ranks the payment-history passage (with
the typical −60 to −110 impact) first. With the question alone, that passage isn't in the top 12.

``probes`` turns the question and the signed-in user's data into at most ``MAX_PROBES`` extra searches:

    A month named in the question     that month's factor ("Late payment (30+ days)")
    A question about the score moving the factors behind the last two falls, when no month is named
    A question about paying down debt a carried card balance ("interest on a credit card balance")
    Anything else                     nothing, so most questions retrieve exactly as before

``agent.pipeline`` adds the best new passage for each probe after the usual ones, as it adds the product-risk
passages for a product question.

Example:
    >>> from creditcoach.rag import personal
    >>> personal.probes("Why did my score crash in April?", history, accounts)
    ['Late payment (30+ days)']
"""

import re

MAX_PROBES = 2
MONTHS = {name: i for i, names in enumerate(
    [("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",), ("june", "jun"),
     ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"),
     ("december", "dec")], 1) for name in names}
MOVEMENT = re.compile(r"\b(?:drop\w*|dip\w*|fall\w*|fell|crash\w*|declin\w*|went down|gone down|lower\w*|"
                      r"went from|hurt\w*|why (?:did|has|is|was) my score|what happened)\b", re.I)
# Paying off or ahead on a loan, EMI or debt, in one clause ("pay off my education loan faster")
DEBT = re.compile(r"\b(?:pay(?:ing)? (?:off|down)|prepay\w*|repay\w*|clear\w*)\b[^.?!,]{0,40}\b(?:loans?|emis?|debts?)\b"
                  r"|\b(?:loans?|emis?|debts?)\b[^.?!,]{0,20}\b(?:faster|early|sooner)\b", re.I)
PRODUCT = re.compile(r"\b(?:payday|instant|loan app|cash advance)\b", re.I)  # the product-risk passages cover these
CARD_INTEREST = "interest on a credit card balance you carry, and paying the card in full"
# Rises, no change and the first month: nothing to explain
IGNORED = {"baseline", "on-time payments", "account age increase", "stable (no major change)", "utilization decreased"}


def factors(label: str) -> list[str]:
    """The separate factors in a history label: "Hard inquiry + utilization spike" -> two."""
    return [part.strip() for part in label.split(" + ") if part.strip() and part.strip().lower() not in IGNORED]


def named_months(question: str) -> set[tuple[int, int | None]]:
    """(month, year or None) for each month named in the question: "in April" -> (4, None), "January 2025" -> (1, 2025).

    "May" counts only as "in May" or "May 2026", since it is usually the verb.
    """
    out = set()
    for m in re.finditer(r"\b([a-z]+)\b(?:,?\s+(20\d\d))?", question.lower()):
        word, year = m.group(1), m.group(2)
        if word in MONTHS and (word != "may" or year or question.lower()[max(0, m.start() - 3):m.start()] == "in "):
            out.add((MONTHS[word], int(year) if year else None))
    return out


def probes(question: str, history: list[dict], accounts: list[dict]) -> list[str]:
    """Up to ``MAX_PROBES`` searches drawn from the user's data that the question may depend on.

    Args:
        question: The user's question.
        history: Score-history points, oldest first, each with ``date`` (YYYY-MM-DD), ``score`` and
            ``factor_change``.
        accounts: Account entries with ``type`` and ``balance_inr``.
    """
    out: list[str] = []
    months = named_months(question)
    moves = [(p, p["score"] - prev["score"]) for prev, p in zip(history, history[1:])]
    if months:
        for p, _ in moves:
            month, year = int(p["date"][5:7]), int(p["date"][:4])
            if any(month == m and (y is None or y == year) for m, y in months):
                out += factors(p["factor_change"])
    elif MOVEMENT.search(question):
        for p, change in [m for m in moves if m[1] < 0][-2:][::-1]:
            out += factors(p["factor_change"])
    carried = any("card" in a["type"].lower() and a["balance_inr"] > 0 for a in accounts)
    if carried and DEBT.search(question) and not PRODUCT.search(question):
        out.append(CARD_INTEREST)
    return list(dict.fromkeys(out))[:MAX_PROBES]
