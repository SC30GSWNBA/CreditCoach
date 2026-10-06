"""The "My credit" tab: charts of the signed-in user's own score history and accounts.

Built to the approved mockup (revision 2): V1 snapshot tiles, V2 "Your score story" (score line, monthly change
bars and the reasons behind them, merged from the first draft's V2-V4), V5 card utilization with a what-if
slider, and V6 what you owe.

Every figure comes from the tools the chat already uses, ``get_score_history`` and ``get_account_summary``, called
directly with the signed-in user's id, so the tab shows that user's rows and nobody else's. There is no model call,
so the tab fills in well under a second. The functions here are pure: they take tool results and return a Plotly
figure or HTML, and ``creditcoach.app.main`` wires them to the page.

Reference lines come from the corpus, not from invented score bands: 750 ("many lenders treat about 750 or above
as strong", ``corpus/01``) and 30% utilization (``corpus/03``). The what-if slider changes utilization only
(balance minus a payment, over the limit). It never estimates a score (``corpus/13``).
"""

from datetime import date
from html import escape

import plotly.graph_objects as go

from creditcoach.tools.account_summary import ratio

STRONG_SCORE = 750
UTILIZATION_LINE = 0.30
PERIODS = [("3 months", 3), ("6 months", 6), ("12 months", 12)]
HIGH_RISK_NOTE = ("Instant loan apps are marked high risk. Ask CreditCoach about safer alternatives "
                  "before borrowing from one again.")

# Chart colors work on both Gradio themes: the figure background is transparent and text uses a mid grey.
SERIES = "#2a78d6"
UP = "#2a78d6"
DOWN = "#e34948"
INK = "#898781"
GRID = "rgba(137, 135, 129, 0.22)"
REFERENCE = "#898781"
DIMMED = 0.18

CSS = """
.cc-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.cc-tile { background: var(--block-background-fill); border: 1px solid var(--border-color-primary); border-radius: 8px; padding: 12px 14px; display: grid; gap: 4px; align-content: start; }
.cc-k { font-size: .82rem; color: var(--body-text-color-subdued); }
.cc-v { font-size: 1.7rem; font-weight: 600; line-height: 1.15; color: var(--body-text-color); }
.cc-v small { font-size: .85rem; font-weight: 500; color: var(--body-text-color-subdued); }
.cc-n { font-size: .8rem; color: var(--body-text-color-subdued); }
.cc-goal { margin-top: 10px; font-size: .9rem; color: var(--body-text-color-subdued); }
.cc-up { color: #006300; } .dark .cc-up { color: #0ca30c; }
.cc-down { color: #b42626; } .dark .cc-down { color: #f07a7a; }
.cc-pill { display: inline-flex; align-items: center; gap: 5px; width: fit-content; font-size: .78rem; font-weight: 500;
  border: 1px solid var(--border-color-primary); border-radius: 999px; padding: 1px 8px 1px 6px; }
.cc-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex: none; }
.cc-good { color: #006300; } .dark .cc-good { color: #0ca30c; }
.cc-warn { color: #8a5a00; } .dark .cc-warn { color: #fab219; }
.cc-critical { color: #b42626; } .dark .cc-critical { color: #f07a7a; }
.cc-rows { display: grid; gap: 12px; }
.cc-row-top { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-size: .88rem; color: var(--body-text-color); }
.cc-amt { color: var(--body-text-color-subdued); font-variant-numeric: tabular-nums; }
.cc-track { position: relative; height: 14px; background: var(--border-color-primary); border-radius: 4px; margin-top: 4px; }
.cc-fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 4px; }
.cc-paid { position: absolute; top: 0; bottom: 0; border-radius: 0 4px 4px 0;
  background: repeating-linear-gradient(135deg, transparent 0 3px, var(--border-color-primary) 3px 5px); }
.cc-line30 { position: absolute; top: -4px; bottom: -4px; left: 30%; border-left: 2px dashed #898781; }
.cc-debt { display: grid; grid-template-columns: minmax(100px, 140px) 1fr auto; gap: 10px; align-items: center; font-size: .88rem; color: var(--body-text-color); }
.cc-debt .cc-bar { height: 14px; border-radius: 0 4px 4px 0; min-width: 3px; }
.cc-debt .cc-sub { display: block; font-size: .76rem; color: var(--body-text-color-subdued); }
.cc-risk { background: repeating-linear-gradient(45deg, #d03b3b 0 4px, rgba(208, 59, 59, .45) 4px 7px); }
.cc-flag { font-size: .7rem; font-weight: 600; color: #b42626; border: 1px solid currentColor; border-radius: 4px; padding: 0 5px; margin-left: 6px; white-space: nowrap; }
.dark .cc-flag { color: #f07a7a; }
.cc-note { font-size: .84rem; color: var(--body-text-color-subdued); margin-top: 8px; }
.cc-legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: .8rem; color: var(--body-text-color-subdued); }
.cc-legend span { display: inline-flex; align-items: center; gap: 6px; }
.cc-sw { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
.cc-empty { background: var(--block-background-fill); border: 1px solid var(--border-color-primary); border-radius: 8px; padding: 18px; color: var(--body-text-color); }
.cc-empty ul { margin: 8px 0 0; padding-left: 1.2em; color: var(--body-text-color-subdued); }
.cc-ask { align-self: end; }
.cc-whatif-note { padding: 4px 12px 10px; }
@media (max-width: 560px) { .cc-debt { grid-template-columns: 1fr auto; } .cc-debt .cc-bar { grid-column: 1 / -1; grid-row: 2; } }
"""

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def month_label(day: str) -> str:
    """``"2026-08-01"`` (or ``"2026-08"``) to ``"Aug 2026"``."""
    return f"{MONTHS[int(day[5:7]) - 1]} {day[:4]}"


def inr(amount: int) -> str:
    """Rupees with Indian digit grouping: 799750 -> ``"₹7,99,750"``."""
    sign, digits = ("-" if amount < 0 else ""), str(abs(int(amount)))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        digits = ",".join([head, *groups, tail]) if head else ",".join([*groups, tail])
    return f"{sign}₹{digits}"


def percent(r: float) -> str:
    """0.787 -> ``"78.7%"``, 0.11 -> ``"11%"``."""
    return f"{r * 100:.1f}".removesuffix(".0") + "%"


def signed(n: int) -> str:
    """+28, -20, 0."""
    return f"+{n}" if n > 0 else str(n)


def period_arg(months: int) -> str:
    """The ``get_score_history`` period for the 3/6/12-month switch."""
    return f"last_{int(months)}_months"


def utilization_status(r: float) -> tuple[str, str, str]:
    """(css class, icon, label) for a utilization ratio. The icon and label carry the meaning, not color alone."""
    if r <= UTILIZATION_LINE:
        return "cc-good", "✓", "At or under 30%"
    if r <= 0.50:
        return "cc-warn", "!", "Above 30%"
    return "cc-critical", "!!", "Well above 30%"


STATUS_COLOR = {"cc-good": "#0ca30c", "cc-warn": "#fab219", "cc-critical": "#d03b3b"}


# ---------------------------------------------------------------- V1 snapshot

def snapshot_html(history: dict, accounts: dict, goal: str | None = None) -> str:
    """V1: latest score, change over the period, overall card utilization and total owed.

    Args:
        history: A successful ``get_score_history`` result with a credit file.
        accounts: The user's ``get_account_summary`` result.
        goal: The goal to show under the tiles, or None.
    """
    s, points = history["summary"], history["points"]
    totals = accounts["totals"]
    latest = s["end_score"]
    gap = STRONG_SCORE - latest
    net = s["net_change"]
    arrow, cls = ("▲", "cc-up") if net > 0 else ("▼", "cc-down") if net < 0 else ("■", "")
    if totals["overall_utilization_ratio"] is None:
        util = ('<span class="cc-v" style="font-size:1.1rem;padding-block:6px">No credit card</span>'
                '<span class="cc-n">Utilization only applies to cards</span>')
    else:
        r = totals["overall_utilization_ratio"]
        c, icon, label = utilization_status(r)
        util = (f'<span class="cc-v">{percent(r)}</span><span class="cc-pill {c}">'
                f'<span class="cc-dot" style="background:{STATUS_COLOR[c]}"></span>{icon} {label}</span>')
    cards, loans = totals["revolving_count"], totals["installment_count"]
    html = f"""<div class="cc-tiles">
  <div class="cc-tile"><span class="cc-k">Latest score ({month_label(points[-1]['date'])})</span>
    <span class="cc-v">{latest} <small>/ 900</small></span>
    <span class="cc-n">{f"{gap} points below 750" if gap > 0 else f"{-gap} points above 750" if gap < 0 else "Exactly 750"}</span></div>
  <div class="cc-tile"><span class="cc-k">Change over {len(points)} month{"s" if len(points) != 1 else ""}</span>
    <span class="cc-v {cls}">{arrow} {signed(net)}</span>
    <span class="cc-n">from {s["start_score"]} · high {s["highest"]["score"]} in {month_label(s["highest"]["date"])}</span></div>
  <div class="cc-tile"><span class="cc-k">Card utilization (all cards)</span>{util}</div>
  <div class="cc-tile"><span class="cc-k">Total owed</span><span class="cc-v">{inr(totals["total_balance_inr"])}</span>
    <span class="cc-n">{cards} card{"s" if cards != 1 else ""} · {loans} loan{"s" if loans != 1 else ""}</span></div>
</div>"""
    if goal:
        html += f'<p class="cc-goal">Goal on file: <b>{escape(goal)}</b></p>'
    return html


# ---------------------------------------------------------------- V2 score story

def reasons(history: dict) -> list[tuple[str, int, int]]:
    """Points added up by reason over the period, most negative first: ``[(reason, points, months), ...]``.

    The first month on file (``change`` is None, reason "Baseline") has no change, so it isn't counted.
    """
    totals: dict[str, list[int]] = {}
    for p in history["points"]:
        if p["change"] is not None:
            t = totals.setdefault(p["factor_change"], [0, 0])
            t[0] += p["change"]
            t[1] += 1
    return sorted(((f, c, n) for f, (c, n) in totals.items()), key=lambda r: (r[1], r[0]))


def reason_choices(history: dict) -> list[tuple[str, str]]:
    """Radio choices for the reasons list: an "All months" entry, then one per reason with its points."""
    return [("All months", "")] + [(f"{f}: {signed(c)} ({n} month{'s' if n != 1 else ''})", f)
                                   for f, c, n in reasons(history)]


def month_choices(history: dict) -> list[tuple[str, str]]:
    """Dropdown choices for "Ask about a month", latest first."""
    return [(f"{month_label(p['date'])}: {p['score']}" + (f" ({signed(p['change'])})" if p["change"] is not None else ""),
             p["date"]) for p in reversed(history["points"])]


def month_question(day: str) -> str:
    """The chat question a picked month fills in."""
    return f"Why did my score change in {month_label(day)}?"


def history_rows(history: dict) -> list[list]:
    """The table view of V2: month, score, change, main reason."""
    return [[month_label(p["date"]), p["score"], "–" if p["change"] is None else signed(p["change"]), p["factor_change"]]
            for p in history["points"]]


def _axis_step(span: int, steps: tuple[tuple[int, int], ...]) -> int:
    return next(step for limit, step in steps if span > limit)


def story_figure(history: dict, highlight: str | None = None) -> go.Figure:
    """V2: the score line on top and the monthly change bars below, sharing one month axis.

    Two stacked plots with their own y-scales (never one plot with two y-axes). Both use the same x-axis, so
    hovering a month shows one tooltip for both. ``highlight`` fades every month whose reason is different, so a
    reason picked in the list lights up its months in both plots.
    """
    points = history["points"]
    x = [date.fromisoformat(p["date"]) for p in points]
    scores = [p["score"] for p in points]
    lo = (min(*scores, STRONG_SCORE) - 12) // 10 * 10
    hi = -(-(max(*scores, STRONG_SCORE) + 12) // 10) * 10
    lim = -(-max([10, *(abs(p["change"]) for p in points if p["change"] is not None)]) // 10) * 10
    on = [not highlight or p["factor_change"] == highlight for p in points]
    worst = min((p for p in points if p["change"] is not None and p["change"] <= -8), key=lambda p: p["change"],
                default=None)  # only a drop big enough to call out gets marked and labelled

    fig = go.Figure()
    # invisible floor so the score area fills down to the bottom of its own axis, not to 0
    fig.add_trace(go.Scatter(x=x, y=[lo] * len(x), mode="lines", line={"width": 0}, hoverinfo="skip",
                             showlegend=False))
    fig.add_trace(go.Scatter(
        x=x, y=scores, mode="lines+markers", name="Score", fill="tonexty", fillcolor="rgba(42, 120, 214, 0.08)",
        line={"color": SERIES, "width": 2},
        marker={"size": [11 if highlight and o else 7 for o in on],
                "color": [DOWN if p is worst else SERIES for p in points],
                "opacity": [1 if o else DIMMED for o in on], "line": {"width": 2, "color": "rgba(255,255,255,0.9)"}},
        customdata=[[p["factor_change"]] for p in points],
        hovertemplate="Score <b>%{y}</b><br>%{customdata[0]}<extra></extra>"))
    bars = [(xi, p) for xi, p in zip(x, points) if p["change"] is not None]
    fig.add_trace(go.Bar(
        x=[b[0] for b in bars], y=[b[1]["change"] for b in bars], name="Change", yaxis="y2",
        marker={"color": [UP if b[1]["change"] >= 0 else DOWN for b in bars],
                "opacity": [1 if (not highlight or b[1]["factor_change"] == highlight) else DIMMED for b in bars],
                "cornerradius": 4},
        customdata=[[signed(b[1]["change"])] for b in bars],
        hovertemplate="Change <b>%{customdata[0]}</b><extra></extra>"))

    line = {"type": "line", "xref": "paper", "x0": 0, "x1": 1}
    fig.add_shape(**line, yref="y", y0=STRONG_SCORE, y1=STRONG_SCORE,
                  line={"dash": "dash", "color": REFERENCE, "width": 1.5})
    fig.add_shape(**line, yref="y2", y0=0, y1=0, line={"color": INK, "width": 1})
    note = {"showarrow": False, "font": {"size": 11, "color": INK}}
    fig.add_annotation(**note, xref="paper", x=1, xanchor="left", xshift=6, yref="y", y=STRONG_SCORE,
                       text="750 strong")
    fig.add_annotation(**note, xref="paper", x=0, xanchor="left", yref="paper", y=1, yanchor="bottom", yshift=4,
                       text="Score")
    fig.add_annotation(**note, xref="paper", x=0, xanchor="left", yref="paper", y=0.34, yanchor="bottom",
                       text="Change vs the month before (points)")
    last = points[-1]
    fig.add_annotation(x=x[-1], y=last["score"], text=f"<b>{last['score']}</b>", showarrow=False, xanchor="left",
                       xshift=10, font={"size": 13})
    if worst:
        i = points.index(worst)
        reason = worst["factor_change"].replace(" (30+ days)", "")
        left = i > 2
        fig.add_annotation(**note, x=x[i], y=worst["score"], text=f"{worst['change']} · {escape(reason)}",
                           xanchor="right" if left else "left", xshift=-9 if left else 9, yshift=-16)
        fig.add_annotation(x=x[i], y=worst["change"], yref="y2", text=f"<b>{worst['change']}</b>", showarrow=False,
                           yshift=-4, yanchor="top", font={"size": 11})

    axis = {"gridcolor": GRID, "zeroline": False, "tickfont": {"color": INK}}
    fig.update_layout(
        height=430, margin={"l": 48, "r": 84, "t": 28, "b": 28}, showlegend=False, bargap=0.45,
        hovermode="x unified", hoversubplots="axis", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "system-ui, -apple-system, Segoe UI, sans-serif", "size": 12, "color": INK},
        xaxis={"dtick": "M1" if len(points) <= 6 else "M2", "tickformat": "%b", "hoverformat": "%b %Y",
               "showgrid": False, "anchor": "y2", "showspikes": True, "spikemode": "across", "spikesnap": "cursor",
               "spikethickness": 1, "spikedash": "solid", "spikecolor": INK, "tickfont": {"color": INK}},
        yaxis={**axis, "domain": [0.44, 1], "range": [lo, hi],
               "dtick": _axis_step(hi - lo, ((120, 50), (60, 25), (0, 10)))},
        yaxis2={**axis, "domain": [0, 0.32], "range": [-lim * 1.25, lim], "tickformat": "+d",
                "dtick": _axis_step(lim, ((60, 40), (30, 20), (0, 10)))})
    return fig


STORY_LEGEND = f"""<div class="cc-legend">
  <span><i class="cc-sw" style="background:{SERIES};height:3px"></i>Score</span>
  <span><i class="cc-sw" style="background:{UP}"></i>Went up</span>
  <span><i class="cc-sw" style="background:{DOWN}"></i>Went down</span>
  <span><i class="cc-sw" style="height:0;border-top:2px dashed {REFERENCE};border-radius:0"></i>750, which many lenders treat as strong</span>
</div>"""


# ---------------------------------------------------------------- V5 card utilization

def cards(accounts: dict) -> list[dict]:
    """The user's credit cards from ``get_account_summary``, in account order."""
    return [a for a in accounts["accounts"] if a["category"] == "revolving"]


def card_choices(accounts: dict) -> list[tuple[str, str]]:
    """What-if dropdown choices, e.g. ``("ACC-01 (78.7%)", "ACC-01")``."""
    return [(f"{a['account_id']} ({percent(a['utilization_ratio'])})", a["account_id"]) for a in cards(accounts)]


def highest_card(accounts: dict) -> str | None:
    """The card with the highest utilization: the what-if slider starts on it."""
    c = cards(accounts)
    return max(c, key=lambda a: a["utilization_ratio"])["account_id"] if c else None


def paydown_to_30(balance: int, limit: int) -> int:
    """The payment, rounded up to the next ₹100, that brings a card to 30% or less (0 if it already is)."""
    need = -(-(balance * 10 - limit * 3) // 10)  # balance - 30% of the limit, rounded up to a rupee
    return max(0, -(-need // 100) * 100)


def cards_html(accounts: dict, card_id: str | None = None, pay: int = 0) -> str:
    """V5: one bar per card and one for all cards, with the 30% line, after paying ``pay`` on ``card_id``."""
    cs = cards(accounts)
    if not cs:
        return ('<div class="cc-empty"><b>No credit card on file</b><p class="cc-note">Utilization only applies to '
                'credit cards, so there is no ratio to show (it isn\'t 0%). Your score is built from your loan '
                'payments.</p></div>')
    pay = max(0, int(pay or 0))
    rows = []
    for a in cs:
        paid = min(pay, a["balance_inr"]) if a["account_id"] == card_id else 0
        rows.append((f"Card {a['account_id']}", a["balance_inr"], a["credit_limit_inr"], paid))
    t = accounts["totals"]
    rows.append(("<b>All cards</b>", t["revolving_balance_inr"], t["revolving_limit_inr"], sum(r[3] for r in rows)))
    out = []
    for label, balance, limit, paid in rows:
        now, after = ratio(balance, limit), ratio(balance - paid, limit)
        c, icon, text = utilization_status(after)
        was = f' <span class="cc-amt">(now {percent(now)})</span>' if paid else ""
        ghost = (f'<div class="cc-paid" style="left:{after * 100:.2f}%;width:{(now - after) * 100:.2f}%"></div>'
                 if paid else "")
        out.append(f"""<div><div class="cc-row-top"><span>{label} · <b>{percent(after)}</b>{was}
  <span class="cc-pill {c}" style="margin-left:6px"><span class="cc-dot" style="background:{STATUS_COLOR[c]}"></span>{icon} {text}</span></span>
  <span class="cc-amt">{inr(balance - paid)} of {inr(limit)}</span></div>
  <div class="cc-track" title="{percent(after)} of the limit used"><div class="cc-fill" style="width:{min(100, after * 100):.2f}%;background:{STATUS_COLOR[c]}"></div>{ghost}<div class="cc-line30"></div></div></div>""")
    return f'<div class="cc-rows">{"".join(out)}</div>'


def whatif_note(accounts: dict, card_id: str | None, pay: int = 0) -> str:
    """The sentence under the what-if slider: what it takes to reach 30% on the picked card."""
    card = next((a for a in cards(accounts) if a["account_id"] == card_id), None)
    if card is None:
        return ""
    need = paydown_to_30(card["balance_inr"], card["credit_limit_inr"])
    paid = min(max(0, int(pay or 0)), card["balance_inr"])
    if not paid:
        head = (f"Paying **{inr(need)}** brings {card_id} to 30%." if need
                else f"{card_id} is already at or under 30%.")
    else:
        after = ratio(card["balance_inr"] - paid, card["credit_limit_inr"])
        head = f"Paying {inr(paid)} brings {card_id} to **{percent(after)}**."
        if paid < need:
            head += f" It takes {inr(need)} to reach 30%."
    return head + " This changes utilization only; it doesn't predict a score."


# ---------------------------------------------------------------- V6 what you owe

def debt_html(accounts: dict) -> str:
    """V6: every account by balance, largest first, with instant loan apps flagged as high risk."""
    accts = sorted(accounts["accounts"], key=lambda a: -a["balance_inr"])
    total = accounts["totals"]["total_balance_inr"]
    top = max((a["balance_inr"] for a in accts), default=0) or 1
    rows = []
    for a in accts:
        risky = a["high_risk_product"]
        kind = "card" if a["category"] == "revolving" else "loan"
        share = a["balance_inr"] / total * 100 if total else 0
        tip = (f"{a['type']} {a['account_id']}: {inr(a['balance_inr'])} owed"
               + (f" of {inr(a['credit_limit_inr'])} limit" if a["credit_limit_inr"] else "")
               + f" ({share:.1f}% of everything you owe)")
        color = "" if risky else f"background:{SERIES if kind == 'card' else '#1c5cab'}"
        rows.append(f"""<div class="cc-debt" title="{escape(tip)}">
  <span>{escape(a['type'])}{'<span class="cc-flag">⚠ High risk</span>' if risky else ''}<span class="cc-sub">{a['account_id']} · {kind}</span></span>
  <div class="cc-bar{' cc-risk' if risky else ''}" style="width:{max(0.6, a['balance_inr'] / top * 100):.2f}%;{color}"></div>
  <span class="cc-amt">{inr(a['balance_inr'])}</span></div>""")
    html = f'<div class="cc-rows">{"".join(rows)}</div>'
    if any(a["high_risk_product"] for a in accts):
        html += f'<p class="cc-note">⚠ {HIGH_RISK_NOTE}</p>'
    return html


# ---------------------------------------------------------------- no credit file

def empty_html(name: str) -> str:
    """The tab for a user with no credit file: no score is shown or estimated."""
    return f"""<div class="cc-empty"><h3 style="margin:0 0 6px">No credit history yet</h3>
<p style="margin:0">{escape(name)}, you have no cards or loans on file, so there's no score to chart. That's common
before a first credit product, and it isn't the same as a bad score.</p>
<ul><li>Charts appear here once a card or loan has reported for a few months.</li>
<li>Ask CreditCoach how to start building credit safely.</li></ul></div>"""


START_QUESTION = "How do I start building a credit history?"
