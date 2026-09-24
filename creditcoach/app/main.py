"""CreditCoach chat UI (Week 1 prototype: grounded answers from the corpus; no tools or memory yet).

    uv run python -m creditcoach.app            # local only: http://127.0.0.1:7860
    uv run python -m creditcoach.app --share    # also create a public gradio.live link (about 1 week)

A share link is public and every answer uses your OpenRouter key. Set APP_USERNAME and APP_PASSWORD in .env
to require a login.
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
    sources = "\n".join(f"{i}. {p.title} (`{p.id}`)" for i, p in enumerate(a.passages, 1))
    return (f"{a.text}\n\n---\n**Sources from the CreditCoach library**\n{sources}\n\n"
            f"<sub>{a.model} · retrieval {a.retrieval_seconds:.1f}s · answer {a.generation_seconds:.1f}s</sub>")


def respond(message: str, history: list) -> str:
    if not message or not message.strip():
        return "Please type a question about your credit."
    try:
        return format_reply(answer(message.strip()))
    except Exception:
        log.exception("Failed to answer %r", message)
        return ("Sorry, I couldn't reach the answer service just now. Please try again in a moment. "
                "Nothing about your credit has changed because of this.")


def build() -> gr.ChatInterface:
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
    """Load the embedding and reranker models at startup so the first user doesn't wait ~15s."""
    t0 = time.perf_counter()
    retrieve("warm up")
    log.info("Retrieval models loaded in %.1fs", time.perf_counter() - t0)


def main() -> None:
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
