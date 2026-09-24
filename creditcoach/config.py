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
# Reasoning effort for GPT-5-family models (minimal | low | medium | high). "low" cut answer time from
# ~14-37s to ~8s in Task 11 with the same grounding and citation behaviour.
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "low")

SAMPLE_DATA = ROOT / "sample_data" / "credit_profile_sample.xlsx"
DATA_DIR = ROOT / "data"  # synthetic dataset (Indian context: INR, 300-900 scores)

CORPUS_DIR = ROOT / "corpus"
CHROMA_DIR = ROOT / ".chroma"  # git-ignored; rebuilt by `python -m creditcoach.rag.ingest`
CORPUS_COLLECTION = "creditcoach_corpus"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
