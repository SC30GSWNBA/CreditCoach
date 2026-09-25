"""Prompt files for the CreditCoach agent.

The system prompt lives in ``system_prompt.md`` next to this file, as plain Markdown, so the team can
review and edit its wording without touching Python code. It defines CreditCoach's tone, tells the model
where facts may come from (TOOL RESULTS and REFERENCE CONTEXT), and states the hard rules: never invent a
figure, never guarantee an outcome, never recommend predatory products, respect the user's goal, and stay
educational.
"""

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent


def load_system_prompt() -> str:
    """Read the CreditCoach system prompt from ``system_prompt.md``.

    Returns:
        The full prompt text, to be sent as the first ``system`` message of every conversation.
    """
    return (PROMPTS_DIR / "system_prompt.md").read_text(encoding="utf-8")
