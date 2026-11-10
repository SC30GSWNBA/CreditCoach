"""The Dashboard's choices, views and events, shared by the users' Dashboard tab and the admin page.

``build`` lays the Dashboard out inside the page being built and wires its events. Who is looking decides what it
shows, from the session, never from anything the page sends:

    Mode    Built by                      Shows
    user    ``app.main`` (Dashboard tab)  The signed-in user's own questions, real use only. Choices: Timeline,
                                          Performance, Models. No model comparison or test runs, no note on where the
                                          figures come from (``dashboard`` with ``detail=False``).
    admin   ``app.admin_page``            Every user's answers, or one user's (the User choice). Choices: User,
                                          Timeline, Type of runs, Performance, Models; all the detail.

The Models choice lists the models that answered in the period, for that user or everyone, and filters every
figure in both views. A model that turns up later is ticked; one the viewer unticked stays unticked.

Live updates: every ``TICK_SECONDS`` the page asks Neon how many answers the chat has given (``memory.store
.answered``, the user's or everyone's; kept for ``COUNT_SECONDS`` so open pages share one read). When the count
moves, the traces are read again until the new answer is among them, for at most ``CATCH_UP_SECONDS``: Langfuse takes
a few seconds to record a trace. Eval and test runs don't go through the chat, so with them picked the traces are
read again every ``EVAL_SECONDS`` instead. Nothing is read while the Dashboard isn't on screen (``active``).
"""

import logging
import threading
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import gradio as gr

from creditcoach.app import dashboard
from creditcoach.memory import store

log = logging.getLogger("creditcoach.app")

TICK_SECONDS = 15
COUNT_SECONDS = 10
CATCH_UP_SECONDS = 90
EVAL_SECONDS = 60
ALL_USERS = ""  # the User choice for everyone (admin)

SIGNED_OUT = '<div class="cc-empty"><b>Please sign in again to see the dashboard.</b></div>'
LOADING = '<div class="cc-empty">Loading the dashboard…</div>'

_counts: dict = {}
_counts_lock = threading.Lock()


def answered(user: str | None) -> int | None:
    """How many answers the chat has given, one user's or everyone's; None if memory can't be read."""
    with _counts_lock:
        hit = _counts.get(user)
        if hit and time.monotonic() - hit[0] < COUNT_SECONDS:
            return hit[1]
    try:
        n = store.answered(user)["answers"]
    except Exception:
        log.warning("Couldn't count answers for the live dashboard", exc_info=True)
        return None
    with _counts_lock:
        _counts[user] = (time.monotonic(), n)
    return n


def live_line(when: datetime | None = None) -> str:
    when = when or datetime.now(UTC)
    return (f'<div class="cc-dash-live"><i></i>Live · checks for new answers every {TICK_SECONDS} seconds · updated '
            f'{when:%H:%M:%S} UTC</div>')


def ticked(keys: list[str], shown: list[str] | None, known: list[str] | None) -> list[str]:
    """The models to tick: every one the first time, then those still ticked and any that weren't offered before."""
    if known is None:
        return keys
    return [k for k in keys if k in (shown or []) or k not in known]


def build(who, admin: bool = False, users: list[tuple[str, str]] | None = None) -> SimpleNamespace:
    """Lay out the Dashboard in the page being built, and wire its choices, Refresh and live updates.

    Args:
        who: ``who(request)``: the signed-in user's id (user mode), or anything truthy for the admin; None when the
            session is gone, and the Dashboard then asks to sign in again.
        admin: The admin page's Dashboard (see the module's table).
        users: The User choice's entries after "All users" (admin only), as (label, user id).

    Returns:
        A namespace with the handlers ``fill`` (draw the Dashboard) and ``open`` (a tab coming on screen: takes
        whether it was filled before ahead of ``inputs``, gives filled and ``active`` ahead of ``outputs``), their
        ``inputs`` and ``outputs``, ``active`` (the state saying whether the Dashboard is on screen), ``quality``
        and ``user`` (the User choice; a state in user mode).
    """
    if admin:
        gr.Markdown("### How CreditCoach is doing\nQuality (tool-call failures, guardrail triggers, goal recall) and "
                    "cost and speed, counted from the traces every answer leaves, for every user or one of them.")
    else:
        gr.Markdown("### Your CreditCoach activity\nHow CreditCoach handled the questions you asked: quality, cost "
                    "and speed. Only your own questions are counted.")
    # the choices in named groups, one per line, the name beside them (above, on phones; 2026-11-07)
    with gr.Column(elem_classes="cc-dash-controls"):
        if admin:
            user = gr.Dropdown([("All users", ALL_USERS), *(users or [])], value=ALL_USERS, label="User",
                               filterable=True)
        else:
            user = gr.State(ALL_USERS)
        days = gr.Radio(dashboard.PERIODS, value=7, label="Timeline")
        traffic = gr.Radio(dashboard.TRAFFIC, value="real", label="Type of runs") if admin else gr.State("real")
        view = gr.Radio(dashboard.VIEWS, value="quality", label="Performance")
        shown = gr.CheckboxGroup(label="Models", elem_classes="cc-shown")
    with gr.Row(equal_height=True):
        refresh = gr.Button("↻ Refresh", size="sm", scale=0, min_width=140, elem_classes="cc-refresh")
        status = gr.HTML(elem_classes="cc-dash-live-row")
    with gr.Column() as quality_col:
        quality = gr.HTML()
    with gr.Column(visible=False) as cost_col:
        cost_top = gr.HTML()
        gr.Markdown("### Cost vs response time, per answer\nEach dot is one answer: how long "
                    + ("the user" if admin else "you") + " waited and what its model calls cost, the output check "
                    "included. The large dots are each model's median. Lower left is better. The Models choice "
                    "above picks the answers counted here and everywhere below.")
        cost_scatter = gr.Plot(show_label=False)
        cost_models = gr.HTML()
        # the model comparison and its test runs are the admin's: users see only their own answers (2026-11-10)
        gr.Markdown("### Cost against speed and quality\nThe same 50 eval questions put to each model and setting, so "
                    "this is a like-for-like comparison. Each dot is one model and setting, averaged over its runs; "
                    "dot size is cost per answer; the shaded side of the dashed line meets the response-time target. "
                    "Below the table: every test run behind the choice of model.", visible=admin)
        cost_quality = gr.Plot(show_label=False, visible=admin)
        cost_quality_table = gr.HTML(visible=admin)
        # one above the other, full width: Spend by day's key has a line per model (2026-11-07)
        gr.Markdown("### Spend by day\nUS dollars, by answer model, with the output check apart.")
        cost_spend = gr.Plot(show_label=False)
        gr.Markdown("### Response time by day\nSeconds from question to answer. p50 is the typical answer, p95 the "
                    "slowest one in twenty.")
        cost_latency = gr.Plot(show_label=False)
        cost_split = gr.HTML()
        with gr.Row(equal_height=False):
            with gr.Column(min_width=320):
                gr.Markdown("### Tokens by day\nPrompt tokens (instructions, retrieved passages, "
                            + ("the user's" if admin else "your") + " data) and completion tokens (the answer and "
                            "any reasoning).")
                cost_tokens = gr.Plot(show_label=False)
            with gr.Column(min_width=320):
                cost_cache = gr.HTML()
    known = gr.State(None)  # the models offered last time (``ticked``)
    seen = gr.State(None)  # what the live updates last saw (``tick``)
    active = gr.State(admin)  # whether the Dashboard is on screen: always on the admin page, the tab sets it

    cost_parts = [cost_top, cost_scatter, cost_models, cost_quality, cost_quality_table, cost_spend, cost_latency,
                  cost_split, cost_tokens, cost_cache]  # dashboard.COST_PARTS, in order
    inputs = [user, days, traffic, view, shown, known, seen]
    outputs = [quality, *cost_parts, shown, known, seen, status]
    skip = tuple(gr.skip() for _ in outputs)

    def scope(request: gr.Request, user_pick: str) -> tuple[bool, str | None]:
        """Whether the session may see the Dashboard, and whose answers: the admin's pick, else the user's own."""
        viewer = who(request)
        if viewer is None:
            return False, None
        return True, (user_pick or None) if admin else viewer

    def draw(user_pick, days_, traffic_, view_, shown_, known_, seen_, request: gr.Request, fresh: bool = False):
        """Draw the picked view: the Models choice first, then the view's figures for the ticked models."""
        ok, whose = scope(request, user_pick)
        if not ok:
            return SIGNED_OUT, SIGNED_OUT, *skip[2:]
        days_ = int(days_)
        if fresh:
            dashboard.forget(days_, whose)
        counts = dashboard.model_counts(days_, traffic_, whose)
        options, keys = dashboard.model_options(counts), [k for k, _ in counts]
        picked = ticked(keys, shown_, known_)
        only = None if len(picked) == len(keys) else picked
        if view_ == "cost":
            parts = dashboard.cost_view(days_, traffic_, whose, only, detail=admin)
            page = (gr.skip(), *(parts[k] for k in dashboard.COST_PARTS))
        else:
            page = (dashboard.view(days_, traffic_, whose, only, detail=admin), *[gr.skip()] * len(cost_parts))
        seen_ = {**(seen_ or {}), "read": time.time(), "had": sum(n for _, n in counts)}
        return (*page, gr.update(choices=options, value=picked, visible=bool(options)), keys, seen_, live_line())

    def show(user_pick, days_, traffic_, view_, shown_, known_, seen_, request: gr.Request):
        return draw(user_pick, days_, traffic_, view_, shown_, known_, seen_, request)

    def again(user_pick, days_, traffic_, view_, shown_, known_, seen_, request: gr.Request):
        """The Refresh button: read the traces afresh, then draw."""
        return draw(user_pick, days_, traffic_, view_, shown_, known_, seen_, request, fresh=True)

    def tick(user_pick, days_, traffic_, view_, shown_, known_, seen_, on_screen, request: gr.Request):
        """Every ``TICK_SECONDS``: draw again with fresh traces when new answers are due, else leave the page be."""
        ok, whose = scope(request, user_pick)
        if not (ok and on_screen and seen_):
            return skip
        now, seen_ = time.time(), dict(seen_)
        due = False
        if traffic_ != "eval":
            count = answered(whose)
            if count is not None and seen_.get("count") is not None and count != seen_["count"]:
                seen_.update(until=now + CATCH_UP_SECONDS, waiting=seen_.get("had", 0))
            if count is not None:
                seen_["count"] = count
            due = now < seen_.get("until", 0)
        if traffic_ != "real" and now - seen_.get("read", 0) >= EVAL_SECONDS:
            due = True
        if not due:
            return (*skip[:-2], seen_, gr.skip())
        drawn = draw(user_pick, days_, traffic_, view_, shown_, known_, seen_, request, fresh=True)
        after = drawn[-2]
        if after.get("had", 0) > after.get("waiting", -1):  # the new answer is in: stop reading again
            after["until"] = 0
        return drawn

    def open_(filled, user_pick, days_, traffic_, view_, shown_, known_, seen_, request: gr.Request):
        """The Dashboard coming on screen: fill it the first time only, so people who never open it don't wait for
        the traces (2026-11-07). Later visits keep what's shown, and the live updates catch up with new answers."""
        if filled:
            return True, True, *skip
        return True, True, *draw(user_pick, days_, traffic_, view_, shown_, known_, seen_, request)

    def switch(view_: str) -> tuple:
        """Show the picked view: "Quality" (Task 31's measures) or "Cost and speed"."""
        return gr.update(visible=view_ == "quality"), gr.update(visible=view_ == "cost")

    controls = [c for c in (user, days, traffic) if not isinstance(c, gr.State)]
    for control in controls:
        control.change(show, inputs, outputs, api_name=False)
    view.change(switch, view, [quality_col, cost_col], show_progress="hidden", api_name=False).then(
        show, inputs, outputs, api_name=False)
    shown.input(show, inputs, outputs, api_name=False)
    refresh.click(again, inputs, outputs, api_name=False)
    gr.Timer(TICK_SECONDS).tick(tick, [*inputs, active], outputs, show_progress="hidden", trigger_mode="once",
                                api_name=False)
    return SimpleNamespace(fill=show, open=open_, tick=tick, inputs=inputs, outputs=outputs, active=active,
                           quality=quality, user=user)


CSS = """
.cc-dash-live-row {align-self: center;}
.cc-dash-live {display: inline-flex; align-items: center; gap: 8px; font-size: .86rem; color: #047857;}
.dark .cc-dash-live {color: #6ee7b7;}
.cc-dash-live i {width: 8px; height: 8px; border-radius: 50%; background: currentColor; display: block;
  animation: cc-pulse 2s ease-in-out infinite;}
@keyframes cc-pulse {50% {opacity: .35;}}
@media (prefers-reduced-motion: reduce) {.cc-dash-live i {animation: none;}}
"""
