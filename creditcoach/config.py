"""Central configuration: secrets, model IDs, and paths. Model IDs live here, not in code."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

CHAT_MODEL = os.getenv("CHAT_MODEL", "openai/gpt-5")
SMALL_MODEL = os.getenv("SMALL_MODEL", "openai/gpt-5-mini")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "openai/gpt-4o")

SAMPLE_DATA = ROOT / "sample_data" / "credit_profile_sample.xlsx"
