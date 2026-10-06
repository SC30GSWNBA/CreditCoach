"""CreditCoach chat UI, built with Gradio (Task 11).

A chat window where users ask credit questions and get grounded, cited answers. Each message runs the
pipeline (``agent.pipeline.answer``): retrieval, then an agent loop in which the model reads the user's score
history and accounts through the MCP tools (Task 15). The reply lists the library passages and the tools it
used.

Memory (Task 16): every session is recorded as an episode in ``memory/<user_id>/episodes/`` (``creditcoach.memory``):
the login, each question and reply (with the tools and passages used), errors, and the logout or closed tab. On
sign-in, the user's earlier sessions are consolidated in the background ("dreaming", ``creditcoach.memory.dream``),
and a "Your memory and past conversations" panel shows the stored goal, what has been consolidated, and every
earlier session, including sessions other teammates recorded and committed.

Recall (Task 17): every answer gets the user's memory (stored goal, consolidated facts and preferences, where the
last conversation left off) and this session's earlier turns, so CreditCoach connects its advice to the user's goal
unprompted and picks up where they left off. When the user states or changes a goal, the model saves it with the
``save_goal`` tool, in the user's own words (``creditcoach.memory.recall``).

Agent trace (Task 18): while an answer is being built, the chat shows live progress above it: each step as it
starts (searching the library, recalling memory, checking score history or accounts, writing the answer) with a
spinner and timer, and a rotating credit tip during the slowest step. When the answer arrives, that block collapses
into an expandable "Agent trace" listing every tool call with a one-line result and the recalled goal
(``creditcoach.app.trace``).

My credit tab: next to the chat, a tab charts the signed-in user's own data (``creditcoach.app.charts``): snapshot
tiles, "Your score story" (score line, monthly change bars and the reasons behind them, with a reason picker that
highlights its months), card utilization with a what-if pay-down slider, and every account by balance. It reads the
same two tools the chat uses, directly and only for the signed-in user, with no model call. Picking a month and
pressing "Ask in chat" fills the chat box with a question about that month and switches to the chat tab; it
doesn't send until the user presses Enter.

Per-user logins: every visitor signs in as one of the 15 dataset users (``creditcoach.auth``; usernames
``creditcoach_user1`` to ``creditcoach_user15`` map to USR-001 to USR-015). Answers use that user's own
profile, score history and accounts from ``data/``, and nobody else's: the user id comes from the signed-in
session, never from the message, and the MCP host runs every tool call for that user only.

How to run:
    uv run python -m creditcoach.app                 # local only: http://127.0.0.1:7860
    uv run python -m creditcoach.app --share         # also create a public gradio.live link (about 1 week)
    uv run python -m creditcoach.app --port 7861     # use a different local port

Login is always required, locally and on a share link. The logins are committed as password hashes in
``creditcoach/app/logins.json``; the passwords are shared with the team privately. A share link is public
and every answer uses your OpenRouter key, so stop the app (Ctrl+C) when you're done; the link closes with it.

Startup: the embedding and reranker models are loaded before the UI opens (about 15 s), so the first user
gets a fast answer. The local URL and any share link are written to the log. Gradio's usage analytics are
turned off.
"""

import argparse
import logging
import os
import queue
import sys
import threading
import time
from collections.abc import Iterator

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")  # before importing gradio, so startup pings are off too

import gradio as gr  # noqa: E402

from creditcoach import auth, config  # noqa: E402
from creditcoach.agent.pipeline import answer  # noqa: E402
from creditcoach.app import charts  # noqa: E402
from creditcoach.app.trace import Trace  # noqa: E402
from creditcoach.memory import dream, store  # noqa: E402
from creditcoach.rag.retrieve import retrieve  # noqa: E402
from creditcoach.tools.account_summary import get_account_summary  # noqa: E402
from creditcoach.tools.score_history import get_score_history  # noqa: E402
from creditcoach.user_data import load_user_data  # noqa: E402

log = logging.getLogger("creditcoach.app")

TITLE = "CreditCoach"
DESCRIPTION = (
    "Plain-language answers about your credit score, grounded in your own score history and accounts and in "
    "CreditCoach's credit-education library. Your score history and accounts are read live through CreditCoach's "
    "data tools. CreditCoach remembers your goal and earlier conversations (see the panel above): tell it your goal "
    "and it will plan around it next time. Not financial advice."
)
EXAMPLES = [
    "Why did my credit score change recently?",
    "What is my credit utilization, and why does 30% matter?",
    "Should I take out this payday loan to pay off my credit card?",
    "Can you guarantee my score will hit 720 if I do what you said?",
]


def format_reply(a) -> str:
    """Turn a pipeline answer into the Markdown shown in the chat window.

    Args:
        a: An ``agent.pipeline.Answer``.

    Returns:
        The answer text, followed by a "Sources from the CreditCoach library" list (passage titles and ids)
        and a small line with the tools called, the model name and timings.
    """
    sources = "\n".join(f"{i}. {p.title} (`{p.id}`)" for i, p in enumerate(a.passages, 1))
    tools = ", ".join(f"{c.tool}" + ("" if c.ok else f" ({c.code})") for c in a.tool_calls) or "none"
    return (f"{a.text}\n\n---\n**Sources from the CreditCoach library**\n{sources}\n\n"
            f"<sub>data tools: {tools} · {a.model} · retrieval {a.retrieval_seconds:.1f}s · "
            f"answer {a.generation_seconds:.1f}s</sub>")


_sessions: dict[str, store.Session] = {}  # Gradio session hash -> open memory episode


def session_for(request: gr.Request, user_id: str) -> store.Session:
    """The open memory episode for this browser session, starting one (with a login event) if needed."""
    key = getattr(request, "session_hash", None) or f"no-session-{user_id}"
    s = _sessions.get(key)
    if s is None or s.user_id != user_id:
        s = _sessions[key] = store.start_session(user_id, meta={"gradio_session": key})
    return s


def remember(request: gr.Request, user_id: str, type_: str, text: str = "", meta: dict | None = None) -> None:
    """Record one event in the user's episode. Memory problems are logged and never stop the chat."""
    try:
        store.record(session_for(request, user_id), type_, text, meta)
    except Exception:
        log.exception("Couldn't record %s for %s in memory", type_, user_id)


def answer_meta(a) -> dict:
    """What an episode keeps about a reply: model, tools (no tool output: figures always come live), passages."""
    return {"model": a.model, "passages": [p.id for p in a.passages],
            "tools": [{"tool": c.tool, "arguments": c.arguments, "ok": c.ok, "code": c.code} for c in a.tool_calls],
            "seconds": round(a.retrieval_seconds + a.generation_seconds, 1)}


REFRESH_SECONDS = 1.0  # how often the trace redraws while waiting (timers and tips move even with no new event)
APOLOGY = ("Sorry, I couldn't reach the answer service just now. Please try again in a moment. "
           "Nothing about your credit has changed because of this.")


def respond(message: str, history: list, request: gr.Request) -> Iterator[str | list[gr.ChatMessage]]:
    """Answer one chat message for the signed-in user; this is the function Gradio calls for every message.

    It is a generator: while the answer is built on a worker thread, it yields the live agent trace about once a
    second (Task 18), and finally the collapsed trace followed by the answer.

    The user whose data is used comes only from the login session (``request.username``), so nothing typed
    in the chat can switch to another user's data. Errors never reach the user as a stack trace: they are
    logged, and the user sees a short apology.

    Args:
        message: What the user typed.
        history: Earlier messages in this chat session, passed to the model so follow-ups have context.
        request: Injected by Gradio; carries the signed-in username.

    Yields:
        The live trace (a list of chat messages), then the trace and the formatted reply. Instead: a prompt to type
        a question if the message was empty, a request to sign in again if the session has no known user, or the
        trace and an apology if the answer service failed.
    """
    user_id = auth.user_id_for(getattr(request, "username", None))
    if user_id is None:
        yield "Please sign in again to continue."
        return
    if not message or not message.strip():
        yield "Please type a question about your credit."
        return
    question = message.strip()
    remember(request, user_id, "user_message", question)
    session = session_for(request, user_id)
    events: queue.Queue = queue.Queue()
    outcome: dict = {}

    def work():
        try:
            outcome["answer"] = answer(question, user_id=user_id, session=session, history=history,
                                       progress=lambda step, details: events.put((step, details)))
        except Exception as exc:  # reported below, on the request's own thread
            outcome["error"] = exc
        finally:
            events.put(None)

    trace = Trace(question=question)
    threading.Thread(target=work, name=f"answer-{user_id}", daemon=True).start()
    yield trace.messages()
    while True:
        try:
            event = events.get(timeout=REFRESH_SECONDS)
        except queue.Empty:
            yield trace.messages()  # nothing new: redraw so timers and tips keep moving
            continue
        if event is None:
            break
        trace.update(*event)
        yield trace.messages()

    if "error" in outcome:
        exc = outcome["error"]
        log.error("Failed to answer for %s", user_id, exc_info=exc)
        remember(request, user_id, "error", f"{type(exc).__name__}: answer service failed")
        trace.finish(failed=True)
        yield trace.messages() + [gr.ChatMessage(role="assistant", content=APOLOGY)]
        return
    a = outcome["answer"]
    remember(request, user_id, "assistant_message", a.text, answer_meta(a))
    trace.finish()
    yield trace.messages() + [gr.ChatMessage(role="assistant", content=format_reply(a))]


def final_reply(message: str, history: list, request) -> str:
    """Run ``respond`` to the end and return the text of its last message (for scripts and tests)."""
    last = None
    for last in respond(message, history, request):
        pass
    return last if isinstance(last, str) else last[-1].content


def memory_panel(user_id: str, current: str | None = None, shown: int = 5) -> str:
    """Markdown for the memory panel: the goal, the consolidated memory, and earlier sessions."""
    m = store.load(user_id)
    g = m.goal
    lines = ["*This panel shows memory as of when you signed in; reload the page to see this session's changes.*", "",
             "**Goal:** " + (f"{g.purpose or 'no purpose stated'}; target score {g.target_score or 'not set'}; "
                             f"by {g.target_date or 'no date set'} (set {g.set_at[:10]}: \"{g.quote}\")"
                             if g else "none saved yet. Tell CreditCoach your goal (for example \"Remember I want "
                             "720 by next year to buy a car\") and it will save it.")]
    d = m.dream or {}
    facts = d.get("semantic", {}).get("facts", [])
    prefs = d.get("procedural", {}).get("preferences", [])
    when = f"consolidated {d['created'][:16].replace('T', ' ')} UTC" if d else "not consolidated yet"
    lines += ["", f"**What CreditCoach remembers** ({when}):"]
    lines += [f"- {f['text']}" for f in facts] or ["- nothing yet"]
    if prefs:
        lines += ["", "**How you like to be helped:**", *[f"- {p['text']}" for p in prefs]]
    summaries = {s["session"]: s["summary"] for s in d.get("episodic", {}).get("sessions", [])}
    past = [e for e in m.episodes if e.session != current and e.turns()]
    lines += ["", f"**Past conversations:** {len(past)}" + (f" (latest {shown} below)" if len(past) > shown else "")]
    for e in past[-shown:][::-1]:
        who = e.events[0].meta.get("recorded_by", "unknown") if e.events else "unknown"
        lines += ["", f"<details><summary>{e.started[:16].replace('T', ' ')} UTC · {len(e.turns()) // 2 or len(e.turns())} "
                  f"question(s) · recorded by {who}</summary>", "",
                  f"*{summaries.get(e.session, 'Not consolidated yet.')}*", ""]
        lines += [f"**{'You' if role == 'user' else 'CreditCoach'}:** {text[:500]}{'…' if len(text) > 500 else ''}  "
                  for role, text in e.turns()]
        lines += ["", "</details>"]
    return "\n".join(lines)


def start(request: gr.Request) -> tuple[str, str]:
    """On page load: start the memory episode (login), consolidate earlier sessions, and fill the header and panel."""
    user_id = auth.user_id_for(getattr(request, "username", None))
    if user_id is None:
        return "Not signed in.", ""
    try:
        s = session_for(request, user_id)
        dream.dream_in_background(user_id, exclude_session=s.session)
        panel = memory_panel(user_id, current=s.session)
    except Exception:
        log.exception("Couldn't open memory for %s", user_id)
        panel = "Memory is unavailable right now; this chat still works."
    return signed_in_as(request), panel


def log_out(request: gr.Request) -> None:
    """Record the logout before the browser goes to Gradio's /logout route."""
    user_id = auth.user_id_for(getattr(request, "username", None))
    if user_id:
        remember(request, user_id, "logout")
        _sessions.pop(getattr(request, "session_hash", None), None)


def closed(request: gr.Request) -> None:
    """Record that the tab was closed or reloaded (Gradio's unload event), unless the user already logged out."""
    s = _sessions.pop(getattr(request, "session_hash", None), None)
    if s:
        try:
            store.record(s, "session_end")
        except Exception:
            log.exception("Couldn't record session_end for %s", s.user_id)


def signed_in_as(request: gr.Request) -> str:
    """Return the "Signed in as ..." line shown above the chat for the current session."""
    user_id = auth.user_id_for(getattr(request, "username", None))
    if user_id is None:
        return "Not signed in."
    name = load_user_data(user_id)["user_profile"].get("first_name", user_id)
    return f"Signed in as **{name}** ({user_id}). Answers use only your own score history and accounts."


UNAVAILABLE = ('<div class="cc-empty"><b>Your charts are unavailable right now.</b> '
               '<p class="cc-note">Reload the page to try again. The chat still works.</p></div>')


def goal_line(user_id: str) -> str | None:
    """The goal under the snapshot tiles: the one saved in memory, else the 2-year goal from the user's profile."""
    try:
        g = store.load(user_id).goal
    except Exception:
        log.exception("Couldn't read the goal for %s", user_id)
        g = None
    if g:
        return " · ".join(part for part in (g.purpose, g.target_score and f"target {g.target_score}",
                                            g.target_date and f"by {g.target_date}") if part)
    return load_user_data(user_id)["user_profile"].get("goals_2yr") or None


def credit_story(months: int, request: gr.Request) -> tuple:
    """V1 and V2 for the period switch: snapshot tiles, the score story, its reasons, months to ask about, table."""
    user_id = auth.user_id_for(getattr(request, "username", None))
    history = get_score_history(user_id, charts.period_arg(months)) if user_id else {"ok": False}
    accounts = get_account_summary(user_id) if user_id else {"ok": False}
    if not (history.get("ok") and accounts.get("ok") and history["has_credit_file"]):
        return UNAVAILABLE, None, gr.update(choices=[], value=None), gr.update(choices=[], value=None), []
    months_ = charts.month_choices(history)
    return (charts.snapshot_html(history, accounts, goal_line(user_id)), charts.story_figure(history),
            gr.update(choices=charts.reason_choices(history), value=""),
            gr.update(choices=months_, value=months_[0][1]), charts.history_rows(history))


def credit_highlight(reason: str, months: int, request: gr.Request):
    """Redraw the score story with one reason's months highlighted ("" shows every month)."""
    user_id = auth.user_id_for(getattr(request, "username", None))
    history = get_score_history(user_id, charts.period_arg(months)) if user_id else {"ok": False}
    if not (history.get("ok") and history["has_credit_file"]):
        return None
    return charts.story_figure(history, highlight=reason or None)


def credit_cards(card_id: str | None, pay: float, request: gr.Request) -> tuple[str, str]:
    """V5 after paying ``pay`` on ``card_id``: the utilization bars and the sentence under the slider."""
    user_id = auth.user_id_for(getattr(request, "username", None))
    accounts = get_account_summary(user_id) if user_id else {"ok": False}
    if not accounts.get("ok"):
        return UNAVAILABLE, ""
    return charts.cards_html(accounts, card_id, int(pay or 0)), charts.whatif_note(accounts, card_id, int(pay or 0))


def credit_card_picked(card_id: str | None, request: gr.Request) -> tuple:
    """A different card in the what-if: reset the slider to 0 with that card's balance as its maximum."""
    user_id = auth.user_id_for(getattr(request, "username", None))
    accounts = get_account_summary(user_id) if user_id else {"ok": False}
    card = next((a for a in charts.cards(accounts) if a["account_id"] == card_id), None) if accounts.get("ok") else None
    slider = gr.update(maximum=card["balance_inr"] if card else 1, value=0)
    return (slider, *credit_cards(card_id, 0, request))


def load_credit(months: int, request: gr.Request) -> tuple:
    """On page load: fill the My credit tab, or show the empty state for a user with no credit file."""
    user_id = auth.user_id_for(getattr(request, "username", None))
    accounts = get_account_summary(user_id) if user_id else {"ok": False}
    history = get_score_history(user_id, charts.period_arg(months)) if user_id else {"ok": False}
    if not (accounts.get("ok") and history.get("ok")):
        log.error("Charts unavailable for %s: %s", user_id, (accounts.get("error") or history.get("error")))
        return (gr.update(visible=False), gr.update(visible=True), UNAVAILABLE, gr.update(visible=False),
                *[gr.skip()] * 11)
    if not history["has_credit_file"]:
        name = load_user_data(user_id)["user_profile"].get("first_name", user_id)
        return (gr.update(visible=False), gr.update(visible=True), charts.empty_html(name), gr.update(visible=True),
                *[gr.skip()] * 11)
    card_id = charts.highest_card(accounts)
    card = next((a for a in charts.cards(accounts) if a["account_id"] == card_id), None)
    return (gr.update(visible=True), gr.update(visible=False), "", gr.update(visible=False),
            *credit_story(months, request),
            charts.cards_html(accounts, card_id), gr.update(visible=card is not None),
            gr.update(choices=charts.card_choices(accounts), value=card_id),
            gr.update(maximum=card["balance_inr"] if card else 1, value=0),
            charts.whatif_note(accounts, card_id), charts.debt_html(accounts))


def ask_in_chat(question: str) -> tuple:
    """Put ``question`` in the chat box and switch to the chat tab. The user still presses Enter to send it."""
    return gr.update(value=question), gr.Tabs(selected="chat")


def ask_about_month(day: str | None) -> tuple:
    """"Ask in chat" for the month picked under the score story (nothing happens if no month is picked)."""
    return ask_in_chat(charts.month_question(day)) if day else (gr.skip(), gr.skip())


def build() -> gr.Blocks:
    """Create the page: a "Signed in as" line with a Log out button, the memory panel, then two tabs: the chat
    interface and "My credit" (the signed-in user's charts).

    Returns:
        A configured ``gr.Blocks`` (not yet launched). Analytics are off, flagging is disabled, and at most 2
        questions are answered at the same time.
    """
    with gr.Blocks(title=TITLE, analytics_enabled=False) as demo:  # don't send usage telemetry from a finance app
        with gr.Row():
            who = gr.Markdown()
            logout = gr.Button("Log out", size="sm", scale=0)
        with gr.Accordion("Your memory and past conversations", open=False):
            panel = gr.Markdown()
        logout.click(log_out).then(None, js="() => { window.location.href = '/logout'; }")
        with gr.Tabs(selected="chat") as tabs:
            with gr.Tab("Ask CreditCoach", id="chat"):
                chat = gr.ChatInterface(
                    fn=respond,
                    chatbot=gr.Chatbot(height=680, show_label=False),  # room for the agent trace above each answer
                    title=TITLE,
                    description=DESCRIPTION,
                    examples=EXAMPLES,
                    cache_examples=False,
                    flagging_mode="never",
                    concurrency_limit=2,
                    autofocus=True,
                    analytics_enabled=False,
                )
            with gr.Tab("My credit", id="credit"):
                with gr.Column(visible=False) as empty_view:
                    empty = gr.HTML()
                    start_ask = gr.Button(f"Ask in chat: {charts.START_QUESTION}", size="sm", variant="primary")
                with gr.Column(visible=False) as credit_view:
                    period = gr.Radio(charts.PERIODS, value=12, show_label=False, container=False,
                                      info="Period for the snapshot and the score story")
                    snapshot = gr.HTML()
                    gr.Markdown("### Your score story\nYour score each month, how much it moved, and why. Hover a "
                                "month for its reason, or pick a reason to highlight its months.")
                    with gr.Row(equal_height=False):
                        with gr.Column(scale=3, min_width=320):
                            story = gr.Plot(show_label=False, container=False)
                            gr.HTML(charts.STORY_LEGEND)
                        with gr.Column(scale=1, min_width=240):
                            reasons = gr.Radio(label="What moved it", info="Pick one to highlight its months",
                                               choices=[], value="")
                    with gr.Row(equal_height=False):
                        month = gr.Dropdown(label="Ask CreditCoach about a month", choices=[], scale=3)
                        ask = gr.Button("Ask in chat", scale=0, min_width=160, variant="primary",
                                        elem_classes="cc-ask")
                    with gr.Accordion("Show the score story as a table", open=False):
                        table = gr.Dataframe(headers=["Month", "Score", "Change", "Main reason"],
                                             interactive=False, wrap=True)
                    with gr.Row(equal_height=False):
                        with gr.Column(min_width=320):
                            gr.Markdown("### Card utilization\nBalance ÷ limit for each card. The dashed line is 30%.")
                            cards = gr.HTML()
                            with gr.Group(visible=False) as whatif:
                                card = gr.Dropdown(label="What if I pay down a card?", choices=[])
                                pay = gr.Slider(0, 1, value=0, step=500, label="Amount to pay (₹)")
                                note = gr.Markdown(elem_classes="cc-whatif-note")
                        with gr.Column(min_width=320):
                            gr.Markdown("### What you owe\nEvery account by balance. Loans don't count toward "
                                        "utilization.")
                            debt = gr.HTML()

        story_outputs = [snapshot, story, reasons, month, table]
        period.change(credit_story, inputs=period, outputs=story_outputs)
        reasons.change(credit_highlight, inputs=[reasons, period], outputs=story)
        card.input(credit_card_picked, inputs=card, outputs=[pay, cards, note])
        pay.change(credit_cards, inputs=[card, pay], outputs=[cards, note], show_progress="hidden")
        ask.click(ask_about_month, inputs=month, outputs=[chat.textbox, tabs])
        start_ask.click(lambda: ask_in_chat(charts.START_QUESTION), outputs=[chat.textbox, tabs])
        demo.load(start, outputs=[who, panel])
        demo.load(load_credit, inputs=period,
                  outputs=[credit_view, empty_view, empty, start_ask, *story_outputs, cards, whatif, card, pay, note,
                           debt])
        demo.unload(closed)
    return demo


def warm_up() -> None:
    """Load the embedding and reranker models at startup, so the first user doesn't wait about 15 s.

    Runs one throwaway search, which loads both models into memory, and logs how long it took.
    """
    t0 = time.perf_counter()
    retrieve("warm up")
    log.info("Retrieval models loaded in %.1fs", time.perf_counter() - t0)


def main() -> None:
    """Parse command-line options, load the models, and start the chat UI.

    Command-line options:
        --share   Also create a public gradio.live link.
        --port    Local port to serve on (default 7860).

    Blocks until the app is stopped with Ctrl+C.
    """
    parser = argparse.ArgumentParser(description="Run the CreditCoach chat UI.")
    parser.add_argument("--share", action="store_true", help="create a public gradio.live link")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if not auth.logins():
        log.error("No logins found in %s, so nobody could sign in. Add one with scripts/set_login.py.",
                  config.LOGINS_FILE)
        sys.exit(1)
    warm_up()
    demo = build()
    _, local_url, share_url = demo.launch(share=args.share, auth=auth.check_login,
                                          auth_message="Sign in with your CreditCoach username and password.",
                                          server_name="127.0.0.1", server_port=args.port, theme=gr.themes.Soft(),
                                          css=charts.CSS, prevent_thread_lock=True)
    log.info("CreditCoach running at %s (login required; %d user logins)", local_url, len(auth.logins()))
    if share_url:
        log.info("Public share link (expires in about 1 week, stops when this process stops): %s", share_url)
    elif args.share:
        log.warning("Could not create a share link; the app is available locally only.")
    demo.block_thread()


if __name__ == "__main__":
    main()
