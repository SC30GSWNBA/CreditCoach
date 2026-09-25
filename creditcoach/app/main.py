"""CreditCoach chat UI, built with Gradio (Task 11).

A chat window where users ask credit questions and get grounded, cited answers. Each message runs the
Task 10 pipeline (``agent.pipeline.answer``), and the reply lists the library passages it used. This is the
Week 1 prototype: account tools and memory aren't connected yet, so answers are general education and
each question is answered on its own.

How to run:
    uv run python -m creditcoach.app                 # local only: http://127.0.0.1:7860
    uv run python -m creditcoach.app --share         # also create a public gradio.live link (about 1 week)
    uv run python -m creditcoach.app --port 7861     # use a different local port

Login (recommended with --share): set ``APP_USERNAME`` and ``APP_PASSWORD`` in ``.env``. A share link is
public, and every answer uses your OpenRouter key, so without a login anyone with the link can use it. The
link stops working when you stop the app (Ctrl+C).

Startup: the embedding and reranker models are loaded before the UI opens (about 15 s), so the first user
gets a fast answer. The local URL and any share link are written to the log. Gradio's usage analytics are
turned off.
"""

import argparse
import logging
import os
import time

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")  # before importing gradio, so startup pings are off too

import gradio as gr  # noqa: E402

from creditcoach.agent.pipeline import answer  # noqa: E402
from creditcoach.rag.retrieve import retrieve  # noqa: E402

log = logging.getLogger("creditcoach.app")

TITLE = "CreditCoach"
DESCRIPTION = (
    "Plain-language answers about your credit score, grounded in CreditCoach's credit-education library. "
    "**Week 1 prototype:** account tools and memory aren't connected yet, so answers are general education and "
    "each question is answered on its own. Not financial advice."
)
EXAMPLES = [
    "Why did my credit score drop 20 points this month?",
    "What is credit utilization and why does 30% matter?",
    "Should I take out this payday loan to pay off my credit card?",
    "Can you guarantee my score will hit 720 if I do what you said?",
]


def format_reply(a) -> str:
    """Turn a pipeline answer into the Markdown shown in the chat window.

    Args:
        a: An ``agent.pipeline.Answer``.

    Returns:
        The answer text, followed by a "Sources from the CreditCoach library" list (passage titles and ids)
        and a small line with the model name and timings.
    """
    sources = "\n".join(f"{i}. {p.title} (`{p.id}`)" for i, p in enumerate(a.passages, 1))
    return (f"{a.text}\n\n---\n**Sources from the CreditCoach library**\n{sources}\n\n"
            f"<sub>{a.model} · retrieval {a.retrieval_seconds:.1f}s · answer {a.generation_seconds:.1f}s</sub>")


def respond(message: str, history: list) -> str:
    """Answer one chat message; this is the function Gradio calls for every message.

    Errors never reach the user as a stack trace: they are logged, and the user sees a short apology.

    Args:
        message: What the user typed.
        history: Earlier messages in the chat. Unused in Week 1, because each question is answered on its
            own; goal memory arrives in Week 2.

    Returns:
        The formatted reply, a prompt to type a question if the message was empty, or an apology if the
        answer service failed.
    """
    if not message or not message.strip():
        return "Please type a question about your credit."
    try:
        return format_reply(answer(message.strip()))
    except Exception:
        log.exception("Failed to answer %r", message)
        return ("Sorry, I couldn't reach the answer service just now. Please try again in a moment. "
                "Nothing about your credit has changed because of this.")


def build() -> gr.ChatInterface:
    """Create the Gradio chat interface: title, description, example questions, and settings.

    Returns:
        A configured ``gr.ChatInterface`` (not yet launched). Analytics are off, flagging is disabled, and at
        most 2 questions are answered at the same time.
    """
    return gr.ChatInterface(
        fn=respond,
        title=TITLE,
        description=DESCRIPTION,
        examples=EXAMPLES,
        cache_examples=False,
        flagging_mode="never",
        concurrency_limit=2,
        autofocus=True,
        analytics_enabled=False,  # don't send usage telemetry from a finance app
    )


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

    user, password = os.getenv("APP_USERNAME"), os.getenv("APP_PASSWORD")
    auth = (user, password) if user and password else None
    if args.share and not auth:
        log.warning("Share link without a login: anyone with the link can use the app and your OpenRouter "
                    "credits. Set APP_USERNAME and APP_PASSWORD in .env to require a login.")
    warm_up()
    demo = build()
    _, local_url, share_url = demo.launch(share=args.share, auth=auth, server_name="127.0.0.1",
                                          server_port=args.port, theme=gr.themes.Soft(), prevent_thread_lock=True)
    log.info("CreditCoach running at %s%s", local_url, " (login required)" if auth else "")
    if share_url:
        log.info("Public share link (expires in about 1 week, stops when this process stops): %s", share_url)
    elif args.share:
        log.warning("Could not create a share link; the app is available locally only.")
    demo.block_thread()


if __name__ == "__main__":
    main()
