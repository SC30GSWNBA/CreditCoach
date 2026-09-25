"""Central configuration for CreditCoach: secrets, model IDs, and file paths.

Every setting lives here so that no other module hard-codes a model name, key, or path. Values come from
the ``.env`` file in the repo root (copy ``.env.example`` to create it), with safe defaults for everything
except the API key.

Settings (environment variable -> default):
    OPENROUTER_API_KEY  Required. Your OpenRouter key; all chat models are called through OpenRouter.
    CHAT_MODEL          "openai/gpt-5"       Main model that writes answers.
    SMALL_MODEL         "openai/gpt-5-mini"  Cheaper model for side jobs (guardrail checks, eval judging).
    FALLBACK_MODEL      "openai/gpt-4o"      Used automatically if the chat model fails.
    REASONING_EFFORT    "low"                How long GPT-5 "thinks" before answering (speed vs depth).
    EMBEDDING_MODEL     all-MiniLM-L6-v2     Local model that turns text into vectors for search.
                                             Rebuild the vector store after changing it.
    RERANKER_MODEL      ms-marco-MiniLM-L-6-v2  Local model that reorders search results by relevance.

Paths (fixed, relative to the repo root):
    DATA_DIR     data/        Synthetic users, accounts, and score history (INR, 300-900 scores).
    CORPUS_DIR   corpus/      Markdown credit-education documents used for RAG.
    CHROMA_DIR   .chroma/     Local vector store, rebuilt by ``python -m creditcoach.rag.ingest``.
    SAMPLE_DATA  sample_data/credit_profile_sample.xlsx  Original seed profile (USD).

Example:
    >>> from creditcoach import config
    >>> config.CHAT_MODEL
    'openai/gpt-5'
"""

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
