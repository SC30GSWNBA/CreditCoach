"""CreditCoach chat UI, built with Gradio (Task 11).

A chat window where users ask credit questions and get grounded, cited answers. Each message runs the
pipeline (``agent.pipeline.answer``): retrieval, then an agent loop in which the model reads the user's score
history and accounts through the MCP tools (Task 15). The reply lists the library passages and the tools it
used. Memory isn't connected yet (Tasks 16-17), so each question is answered on its own.

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
import sys
import time

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")  # before importing gradio, so startup pings are off too

import gradio as gr  # noqa: E402

from creditcoach import auth, config  # noqa: E402
from creditcoach.agent.pipeline import answer  # noqa: E402
from creditcoach.rag.retrieve import retrieve  # noqa: E402
from creditcoach.user_data import load_user_data  # noqa: E402

log = logging.getLogger("creditcoach.app")

TITLE = "CreditCoach"
DESCRIPTION = (
    "Plain-language answers about your credit score, grounded in your own score history and accounts and in "
    "CreditCoach's credit-education library. Your score history and accounts are read live through CreditCoach's "
    "data tools. Memory isn't connected yet, so each question is answered on its own. Not financial advice."
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


def respond(message: str, history: list, request: gr.Request) -> str:
    """Answer one chat message for the signed-in user; this is the function Gradio calls for every message.

    The user whose data is used comes only from the login session (``request.username``), so nothing typed
    in the chat can switch to another user's data. Errors never reach the user as a stack trace: they are
    logged, and the user sees a short apology.

    Args:
        message: What the user typed.
        history: Earlier messages in the chat. Unused for now, because each question is answered on its
            own; goal memory arrives in Tasks 16-17.
        request: Injected by Gradio; carries the signed-in username.

    Returns:
        The formatted reply, a prompt to type a question if the message was empty, a request to sign in
        again if the session has no known user, or an apology if the answer service failed.
    """
    user_id = auth.user_id_for(getattr(request, "username", None))
    if user_id is None:
        return "Please sign in again to continue."
    if not message or not message.strip():
        return "Please type a question about your credit."
    try:
        return format_reply(answer(message.strip(), user_id=user_id))
    except Exception:
        log.exception("Failed to answer for %s", user_id)
        return ("Sorry, I couldn't reach the answer service just now. Please try again in a moment. "
                "Nothing about your credit has changed because of this.")


def signed_in_as(request: gr.Request) -> str:
    """Return the "Signed in as ..." line shown above the chat for the current session."""
    user_id = auth.user_id_for(getattr(request, "username", None))
    if user_id is None:
        return "Not signed in."
    name = load_user_data(user_id)["user_profile"].get("first_name", user_id)
    return f"Signed in as **{name}** ({user_id}). Answers use only your own score history and accounts."


def build() -> gr.Blocks:
    """Create the page: a "Signed in as" line with a Log out button, then the chat interface.

    Returns:
        A configured ``gr.Blocks`` (not yet launched). Analytics are off, flagging is disabled, and at most 2
        questions are answered at the same time.
    """
    with gr.Blocks(title=TITLE, analytics_enabled=False) as demo:  # don't send usage telemetry from a finance app
        with gr.Row():
            who = gr.Markdown()
            gr.Button("Log out", link="/logout", size="sm", scale=0)
        gr.ChatInterface(
            fn=respond,
            title=TITLE,
            description=DESCRIPTION,
            examples=EXAMPLES,
            cache_examples=False,
            flagging_mode="never",
            concurrency_limit=2,
            autofocus=True,
            analytics_enabled=False,
        )
        demo.load(signed_in_as, outputs=who)
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
                                          prevent_thread_lock=True)
    log.info("CreditCoach running at %s (login required; %d user logins)", local_url, len(auth.logins()))
    if share_url:
        log.info("Public share link (expires in about 1 week, stops when this process stops): %s", share_url)
    elif args.share:
        log.warning("Could not create a share link; the app is available locally only.")
    demo.block_thread()


if __name__ == "__main__":
    main()
