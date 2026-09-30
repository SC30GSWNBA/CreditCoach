"""Task 13: ``get_score_history(user_id, period)``, the signed-in user's monthly scores and what changed.

Built to ``docs/tools.md`` §2. The tool does the arithmetic (each month's change, the net change over the
period, the lowest and highest month), so the model copies figures instead of calculating them.

``period`` forms (case-insensitive, anchored to ``as_of``, the dataset's latest month, not today's date):
    latest            The latest month only.
    last_N_months     The N months ending at ``as_of`` (N = 1-24).
    YYYY-MM           One month.
    YYYY-MM:YYYY-MM   Start to end, both included.
    all               Every month on file.

A window that runs past the months on file is clipped (``period.clipped``); one with no month on file is
``PERIOD_OUT_OF_RANGE``. A user with no credit file gets ``ok: true`` with no points, never an error.

Command line (prints the JSON result):
    uv run python -m creditcoach.tools.score_history USR-001 last_2_months

Example:
    >>> from creditcoach.tools.score_history import get_score_history
    >>> r = get_score_history("USR-001", "latest")
    >>> r["points"]
    [{'date': '2026-09-01', 'score': 650, 'change': -20, 'factor_change': 'Hard inquiry + utilization spike'}]
    >>> get_score_history("USR-001", "2025-01")["error"]["code"]
    'PERIOD_OUT_OF_RANGE'
"""

import argparse
import json
import re

from creditcoach.tools.common import NO_CREDIT_FILE_NOTE, ToolFailure, as_of, check_user, only_user, tables

MAX_MONTHS = 24
MONTH = r"(\d{4})-(0[1-9]|1[0-2])"
FORMS = [
    (re.compile(r"latest"), "latest"),
    (re.compile(r"all"), "all"),
    (re.compile(r"last_(\d+)_months?"), "last"),
    (re.compile(MONTH), "month"),
    (re.compile(rf"{MONTH}:{MONTH}"), "range"),
]


def _index(year: int, month: int) -> int:
    """Months since year 0, so month windows are plain integer ranges."""
    return year * 12 + month - 1


def _label(index: int) -> str:
    """Month index back to ``YYYY-MM``."""
    return f"{index // 12}-{index % 12 + 1:02d}"


def _of(date: str) -> int:
    """``YYYY-MM-DD`` (or ``YYYY-MM``) to a month index."""
    return _index(int(date[:4]), int(date[5:7]))


def parse_period(period, latest: int) -> tuple[int, int] | None:
    """Turn ``period`` into an inclusive (start, end) month-index window.

    Args:
        period: The tool's ``period`` argument.
        latest: Month index of ``as_of``.

    Returns:
        ``(start, end)``, or ``None`` for ``all`` (every month on file).

    Raises:
        ToolFailure: ``INVALID_PERIOD`` if ``period`` matches no form, N is outside 1-24, or start is after end.
    """
    text = period.strip().lower() if isinstance(period, str) else ""
    for pattern, kind in FORMS:
        m = pattern.fullmatch(text)
        if not m:
            continue
        if kind == "latest":
            return latest, latest
        if kind == "all":
            return None
        if kind == "last":
            n = int(m.group(1))
            if 1 <= n <= MAX_MONTHS:
                return latest - n + 1, latest
            break
        if kind == "month":
            month = _index(int(m.group(1)), int(m.group(2)))
            return month, month
        start, end = _index(int(m.group(1)), int(m.group(2))), _index(int(m.group(3)), int(m.group(4)))
        if start <= end:
            return start, end
        break
    raise ToolFailure("INVALID_PERIOD",
                      f"Period {period!r} isn't valid. Use latest, last_N_months (N = 1-{MAX_MONTHS}), YYYY-MM, "
                      "YYYY-MM:YYYY-MM or all.", requested=period)


def get_score_history(user_id: str, period: str) -> dict:
    """Return one user's monthly scores for ``period``, with each month's change and main factor.

    Args:
        user_id: Dataset id such as ``"USR-001"``. From Task 15 the MCP host fills it from the signed-in session.
        period: One of the forms in the module docstring, e.g. ``"latest"`` or ``"last_3_months"``.

    Returns:
        The success object from ``docs/tools.md`` §2 (``ok``, ``user_id``, ``as_of``, ``has_credit_file``,
        ``period``, ``available``, ``points``, ``summary``, and ``note`` when there is no credit file), or the
        error envelope with code ``UNKNOWN_USER``, ``INVALID_PERIOD``, ``PERIOD_OUT_OF_RANGE`` or
        ``DATA_UNAVAILABLE``. Never raises for these cases.
    """
    try:
        return _score_history(user_id, period)
    except ToolFailure as failure:
        return failure.envelope


def _score_history(user_id: str, period: str) -> dict:
    """``get_score_history`` without the error wrapping; raises ``ToolFailure`` instead."""
    check_user(user_id)
    snapshot = as_of()
    window = parse_period(period, _of(snapshot))
    rows = only_user(tables()[2], user_id).sort_values("date")
    base = {"ok": True, "user_id": user_id, "as_of": snapshot}

    if rows.empty:
        return {**base, "has_credit_file": False,
                "period": {"requested": period, "start": None, "end": None, "clipped": False},
                "available": None, "points": [], "summary": None, "note": NO_CREDIT_FILE_NOTE}

    history = [(_of(r.date), str(r.date)[:10], int(r.score), r.primary_factor_change) for r in rows.itertuples()]
    first, last = history[0][0], history[-1][0]
    available = {"start": _label(first), "end": _label(last)}
    start, end = window or (first, last)
    lo, hi = max(start, first), min(end, last)
    if lo > hi:
        requested = _label(start) if start == end else f"{_label(start)} to {_label(end)}"
        raise ToolFailure("PERIOD_OUT_OF_RANGE",
                          f"No score history for {requested}. History on file runs from "
                          f"{available['start']} to {available['end']}.",
                          requested=period, available=available)

    points, before = [], None
    for i, (month, date, score, factor) in enumerate(history):
        if month < lo:
            before = score
        elif month <= hi:
            change = score - history[i - 1][2] if i else None
            points.append({"date": date, "score": score, "change": change, "factor_change": factor})

    start_score = before if before is not None else points[0]["score"]
    lowest = min(points, key=lambda p: p["score"])  # min/max keep the earliest month on a tie
    highest = max(points, key=lambda p: p["score"])
    return {**base, "has_credit_file": True,
            "period": {"requested": period, "start": _label(lo), "end": _label(hi), "clipped": (lo, hi) != (start, end)},
            "available": available,
            "points": points,
            "summary": {"start_score": start_score, "end_score": points[-1]["score"],
                        "net_change": points[-1]["score"] - start_score,
                        "lowest": {"date": lowest["date"], "score": lowest["score"]},
                        "highest": {"date": highest["date"], "score": highest["score"]}}}


def main() -> None:
    """Print ``get_score_history`` for a user and period as JSON."""
    parser = argparse.ArgumentParser(description="Show a user's score history (Task 13 tool).")
    parser.add_argument("user_id", help='e.g. "USR-001"')
    parser.add_argument("period", help='latest, last_N_months, YYYY-MM, YYYY-MM:YYYY-MM or all')
    args = parser.parse_args()
    print(json.dumps(get_score_history(args.user_id, args.period), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
