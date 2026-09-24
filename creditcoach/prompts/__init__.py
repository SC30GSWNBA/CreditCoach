"""Prompt files for the CreditCoach agent."""

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent


def load_system_prompt() -> str:
    return (PROMPTS_DIR / "system_prompt.md").read_text(encoding="utf-8")
