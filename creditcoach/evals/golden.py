"""The golden query set: all 50 requirements.md queries (§3 #1-6 and §4 #7-50) in one place, with checks.

Every evaluation in the repo reads its queries from here, so they all cover the same 50 rows: the corpus coverage
report (Task 7), the retrieval eval (Task 9), the prototype and system-prompt runs (Tasks 5 and 10), the tool test
logs (Tasks 13-14), the live MCP run (Task 15), and the Week 4 eval harness (Task 27).

Two sources are merged by query number:
    requirements.md                 The query text, the user (§4's User column; §3 queries are Aravind, USR-001),
                                    the section and the expected behavior. Read as is, never copied, so the set
                                    can't drift from the requirements.
    golden_queries.json (this dir)  What code needs to check each query: the tools it should call, the figures
                                    its answer relies on (checked against the live tools by
                                    ``tests/test_golden_queries.py``), keyword groups for the answer, forbidden
                                    patterns, the later tasks a full check depends on, and any injected fault.

The keyword checks are deliberately lenient. They catch an answer that skips a required figure or behavior; the
judgment of tone and completeness is the Task 27 judge's job.

Example:
    >>> from creditcoach.evals import golden
    >>> q = golden.load()[6]          # query #7
    >>> q.user_id, q.query[:30]
    ('USR-001', 'My score went from 690 to 650.')
    >>> golden.check_answer(q, "Your score fell 690 -> 670 -> 650 ...").missing_figures
"""

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from creditcoach import config

REQUIREMENTS = config.ROOT / "requirements.md"
ANNOTATIONS = Path(__file__).with_name("golden_queries.json")
TOOL_NAMES = {"history": "get_score_history", "account": "get_account_summary"}

# Guarantee language with no negation in the same sentence (shared by Tasks 5, 10 and 15).
GUARANTEE = re.compile(r"\b(guarantee[sd]?|definitely|certainly|promise|will (reach|hit|be at|get to|go up|recover|rise)"
                       r"|you'?ll (reach|hit|be at|get to))\b", re.I)
NEGATION = re.compile(r"(\w+n['’]t\b|cannot|cant|wont|not|no one|nobody|never|unable|no\b"  # any n't, straight or curly
                      r"|red flags?|scams?|false|beware|warning|anyone who"  # a negation, or a warning about promises
                      r"|without|high[- ‑]risk|risky|avoid)", re.I)  # "offers that promise to remove late payments are high-risk"


@dataclass
class Fact:
    """One figure an expected answer relies on, checkable against a tool.

    Attributes:
        tool: "history" (``get_score_history``) or "account" (``get_account_summary``).
        path: Where the value sits in the tool result, e.g. "points.0.score" or "accounts.ACC-01.utilization_ratio".
        user_id: The user to call the tool for (the query's user unless the fact names another).
        period: The ``period`` argument, for the history tool.
        equals: The expected value, if the check is equality.
        excludes: A value no item may equal, for paths with ``*``.
    """
    tool: str
    path: str
    user_id: str
    period: str | None = None
    equals: object = None
    excludes: object = None
    has_equals: bool = False


@dataclass
class Query:
    """One golden query.

    Attributes:
        id: Number in requirements.md (1-50).
        section: "3" for the sample queries, "4.1" ... "4.7" for the additional ones.
        group: The section heading, e.g. "Explaining score changes (variations on #1)".
        user: The User cell from requirements.md (e.g. "USR-003 Vikram (car goal stored)"); "USR-001 Aravind" for §3.
        user_id: The dataset user the query runs as.
        query: The input, without its surrounding quotes.
        note: Context written after the quoted input, e.g. "no loan mentioned earlier" (#47); usually empty.
        expected: The expected agent behavior, verbatim.
        tools: Groups of tool names; each group needs at least one successful call to one of its tools.
        facts: Figures the expected answer relies on.
        figures: Keyword groups the answer must contain that need the user's data.
        behavior: Keyword groups the answer must contain whether or not data was available.
        forbidden: Regexes the answer must not match.
        needs: Later tasks a full check depends on (empty if the query can be fully checked today).
        fault: A failure the live run injects, e.g. "get_account_summary times out".
        expected_errors: Tool error codes that are the correct result for this query (#46: PERIOD_OUT_OF_RANGE), so
            a call that returns one still counts as the tool being called.
    """
    id: int
    section: str
    group: str
    user: str
    user_id: str
    query: str
    note: str
    expected: str
    tools: list[list[str]] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    figures: list[list[str]] = field(default_factory=list)
    behavior: list[list[str]] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    needs: list[str] = field(default_factory=list)
    fault: str | None = None
    expected_errors: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        """Short reference such as "§3 #1" or "§4 #17"."""
        return f"§{self.section[0]} #{self.id}"


@dataclass
class AnswerCheck:
    """Automatic checks of one answer against its golden query (see ``check_answer``)."""
    missing_figures: list[list[str]]
    missing_behavior: list[list[str]]
    forbidden_hits: list[str]
    guarantees: list[str]
    missing_tools: list[list[str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing_figures or self.missing_behavior or self.forbidden_hits or self.guarantees
                    or self.missing_tools)

    def problems(self) -> list[str]:
        """Plain-language list of what failed, for evidence tables."""
        out = [f"no {' / '.join(g)} call" for g in self.missing_tools]
        out += [f"missing {' / '.join(repr(a) for a in g)}" for g in self.missing_figures + self.missing_behavior]
        out += [f"forbidden {p!r}" for p in self.forbidden_hits]
        out += [f"unhedged guarantee: {s[:80]!r}" for s in self.guarantees]
        return out


def _rows() -> list[dict]:
    """Parse the query tables in requirements.md §3 and §4 into dicts, in order."""
    rows, section, group = [], None, None
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        if m := re.match(r"## (\d+)\. ", line):
            section = m.group(1)
            group = "Sample queries" if section == "3" else None
        elif m := re.match(r"### (\d+\.\d+) (.+)", line):
            section, group = m.group(1), m.group(2).strip()
        elif section and section[0] in "34" and re.match(r"\| \d+ \|", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if section == "3":
                number, query, expected = cells
                user = "USR-001 Aravind"
            else:
                number, user, query, expected = cells
            m = re.fullmatch(r'"(.+?)"\s*(?:\((.+)\))?', query)
            rows.append({"id": int(number), "section": section, "group": group, "user": user,
                         "query": m.group(1) if m else query, "note": (m.group(2) or "") if m else "",
                         "expected": expected})
    return rows


@lru_cache(maxsize=1)
def load() -> list[Query]:
    """Return all golden queries, ordered by number, merging requirements.md with ``golden_queries.json``.

    Raises:
        ValueError: If the two sources don't list the same query numbers, or a user id disagrees.
    """
    rows = {r["id"]: r for r in _rows()}
    notes = {q["id"]: q for q in json.loads(ANNOTATIONS.read_text(encoding="utf-8"))["queries"]}
    if set(rows) != set(notes):
        raise ValueError(f"requirements.md has queries {sorted(set(rows) - set(notes))} with no annotation and "
                         f"annotations {sorted(set(notes) - set(rows))} with no query")
    out = []
    for n in sorted(rows):
        row, note = rows[n], notes[n]
        if not row["user"].startswith(note["user_id"]):
            raise ValueError(f"query {n}: requirements.md user {row['user']!r} but annotation says {note['user_id']}")
        facts = [Fact(tool=f["tool"], path=f["path"], user_id=f.get("user_id", note["user_id"]),
                      period=f.get("period"), equals=f.get("equals"), excludes=f.get("excludes"),
                      has_equals="equals" in f) for f in note["facts"]]
        out.append(Query(**row, user_id=note["user_id"],
                         tools=[[TOOL_NAMES[t] for t in g] for g in note["tools"]], facts=facts,
                         figures=note["figures"], behavior=note["behavior"], forbidden=note.get("forbidden", []),
                         needs=note.get("needs", []), fault=note.get("fault"),
                         expected_errors=note.get("expected_errors", [])))
    return out


def by_id() -> dict[int, Query]:
    """Golden queries keyed by number."""
    return {q.id: q for q in load()}


# ---- Facts against the tools ----

def tool_result(fact: Fact) -> dict:
    """Call the tool a fact refers to, directly (no MCP), for the fact's user and period."""
    from creditcoach.tools.account_summary import get_account_summary
    from creditcoach.tools.score_history import get_score_history

    if fact.tool == "history":
        return get_score_history(fact.user_id, fact.period)
    return get_account_summary(fact.user_id)


def resolve(data, path: str):
    """Follow a dotted path through a tool result.

    Tokens are dict keys, list indexes, an ``account_id`` (selects that account from a list), or ``*`` (applies the
    rest of the path to every item and returns a list).

    Raises:
        KeyError: If a token doesn't match.
    """
    tokens = path.split(".")
    for i, token in enumerate(tokens):
        if token == "*":
            rest = ".".join(tokens[i + 1:])
            return [resolve(item, rest) if rest else item for item in data]
        if isinstance(data, list):
            if token.isdigit():
                data = data[int(token)]
            else:
                matches = [item for item in data if isinstance(item, dict) and item.get("account_id") == token]
                if not matches:
                    raise KeyError(f"{token} not in list")
                data = matches[0]
        else:
            data = data[token]
    return data


def check_fact(fact: Fact) -> tuple[bool, object]:
    """Return ``(holds, actual value)`` for one fact, using the live tool."""
    try:
        actual = resolve(tool_result(fact), fact.path)
    except (KeyError, IndexError, TypeError) as exc:
        return False, f"path not found: {exc}"
    if fact.has_equals:
        return actual == fact.equals, actual
    return fact.excludes not in actual, actual


# ---- Answer checks ----

def normalize(text: str) -> str:
    """Lowercase, with ₹/Rs., thousands commas and curly quotes removed and every dash written as "-".

    Applied to both the answer and the keywords, so "₹14,750", "Rs. 14750" and "14750" all match "14750", and
    "−20" matches "-20", "high‑risk" (non-breaking hyphen) matches "high-risk", and "11.0%" matches "11%".
    """
    text = text.lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"[\u2010-\u2015\u2212]", "-", text)  # every dash and hyphen, incl. GPT-5's non-breaking U+2011
    text = re.sub(r"(\d)\.0+%", r"\1%", text)  # 11.0% -> 11%
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = re.sub(r"₹\s?|\brs\.?\s?(?=\d)|\binr\s?(?=\d)", "", text)
    text = text.replace("**", "")
    return re.sub(r"\s+", " ", text)


def missing_groups(text: str, groups: list[list[str]]) -> list[list[str]]:
    """Keyword groups with no alternative present in ``text`` (both normalized)."""
    norm = normalize(text)
    return [g for g in groups if not any(normalize(alt) in norm for alt in g)]


def unhedged_guarantees(text: str) -> list[str]:
    """Sentences with guarantee language and no negation ("I can't guarantee 720" is fine; "you will hit 720" isn't).

    A sentence that warns about promises ("guaranteed points are a red flag") or only mentions the word in quotes
    ("a "guaranteed" fix") is not a guarantee.
    """
    text = text.replace("’", "'")
    unquoted = lambda s: re.sub(r"[“\"][^”\"]{0,40}[”\"]", " ", s)  # noqa: E731
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text)
            if GUARANTEE.search(unquoted(s)) and not NEGATION.search(s)]


def check_answer(q: Query, text: str, tool_calls=None, with_data: bool = True) -> AnswerCheck:
    """Run the automatic checks for one answer.

    Args:
        q: The golden query.
        text: The answer.
        tool_calls: The ``ToolCall`` list from the agent, or None to skip the tool check (no-tools runs).
        with_data: False for runs without the user's data (Task 10): figure groups are skipped.

    Returns:
        An ``AnswerCheck``; ``.ok`` is True when every check passed.
    """
    norm = normalize(text)
    missing_tools = []
    if tool_calls is not None:
        used = {c.tool for c in tool_calls if c.ok or c.code in q.expected_errors}
        missing_tools = [g for g in q.tools if not used & set(g)]
    return AnswerCheck(
        missing_figures=missing_groups(text, q.figures) if with_data else [],
        missing_behavior=missing_groups(text, q.behavior),
        forbidden_hits=[p for p in q.forbidden if re.search(p, norm, re.I)],
        guarantees=unhedged_guarantees(text),
        missing_tools=missing_tools,
    )


def numbers(text: str) -> set[str]:
    """Every number in ``text`` (thousands commas removed), ignoring citation markers [n] and list markers."""
    text = re.sub(r"\[\d+\]", " ", normalize(text))
    text = re.sub(r"(?m)^\s*\d+[.)]\s", " ", text)
    return {n.rstrip(".") for n in re.findall(r"\d+(?:\.\d+)?", text)}


def _one_step(values: set[str]) -> set[str]:
    """Numbers one arithmetic step from ``values``: a + b, a - b, a% of b, a / b as a percentage, ratio as percent."""
    def fmt(v: float) -> set[str]:
        return {f"{v:.0f}", f"{v:.1f}".rstrip("0").rstrip(".")}
    nums = [float(n) for n in values]
    out = set(values)
    for a in nums:
        if 0 < a < 1:
            out |= fmt(a * 100)
    big = [v for v in nums if v > 12]
    for a in big:
        for b in big:
            for v in [a + b, a - b, a * b / 100] + ([100 * a / b] if b else []):
                if v >= 0:
                    out |= fmt(v)
    for a in nums:  # percentages of amounts, e.g. 30% of 200000
        for b in big:
            if a <= 100:
                out |= fmt(a * b / 100)
    return out


def unsourced_numbers(text: str, sources: str) -> list[str]:
    """Numbers in an answer that aren't in its sources or calculated from them (for human review).

    Sources are the question, the passages and the tool results. A number counts as calculated if it is one
    arithmetic step (a + b, a - b, a% of b, a / b as a percentage, a decimal ratio as a percentage) from the
    sources, or one step from such a number that the answer itself states, so a worked calculation such as
    "30% of ₹2,00,000 = ₹60,000, so pay ₹14,750" passes. Numbers up to 12 are ignored (counts, months, list
    positions).
    """
    found = numbers(text)
    first = _one_step(numbers(sources))
    allowed = _one_step(first & found | numbers(sources))
    canon = lambda n: n.rstrip("0").rstrip(".") if "." in n else n  # noqa: E731
    return sorted((n for n in found if float(n) > 12 and n not in allowed and canon(n) not in allowed), key=float)


def untraced_numbers(text: str, sources: str, known: frozenset[str] = frozenset(), steps: int = 4) -> list[str]:
    """Numbers in an answer that can't be traced to its sources, following the answer's own working.

    Like ``unsourced_numbers``, but a calculation may chain through up to ``steps`` numbers the answer states
    ("30% of ₹75,000 is ₹22,500, so pay ₹36,500, leaving ₹38,250 overall"), and a year up to 5 after a year in the
    sources passes ("by 2027" when the data is from 2026). The chat's confidence line uses it
    (``creditcoach.app.confidence``): on the 50 saved Task 15 answers it leaves 2 to review where
    ``unsourced_numbers`` leaves 12.

    Args:
        text: The answer.
        sources: Everything the answer's figures may come from.
        known: Numbers that count as sourced whatever the sources say.
        steps: How many stated numbers a calculation may chain through.
    """
    found, given = numbers(text), numbers(sources) | known
    canon = lambda n: n.rstrip("0").rstrip(".") if "." in n else n  # noqa: E731
    stated: set[str] = set()
    for _ in range(steps):
        allowed = _one_step(given | stated)
        new = {n for n in found if n in allowed or canon(n) in allowed} - stated
        if not new:
            break
        stated |= new
    years = [float(n) for n in given if 2000 <= float(n) <= 2100]
    later_year = lambda v: 2000 <= v <= 2100 and any(0 <= v - y <= 5 for y in years)  # noqa: E731
    return sorted((n for n in found if float(n) > 12 and n not in allowed and canon(n) not in allowed
                   and not later_year(float(n))), key=float)
