"""Central configuration for CreditCoach: secrets, model IDs, and file paths.

Every setting lives here so that no other module hard-codes a model name, key, or path. Values come from
the ``.env`` file in the repo root (copy ``.env.example`` to create it), with safe defaults for everything
except the API key.

Settings (environment variable -> default):
    OPENROUTER_API_KEY  Required. Your OpenRouter key; all chat models are called through OpenRouter.
    CHAT_MODEL          "anthropic/claude-sonnet-5.5"  Main model that writes answers.
    SMALL_MODEL         "openai/gpt-5-mini"  Cheaper model for side jobs (guardrail checks, eval judging).
    FALLBACK_MODEL      "openai/gpt-4o"      Used automatically if the chat model fails.
    REASONING_EFFORT    "low"                How long a GPT-5-family model "thinks" before answering; unused by Sonnet.
    MAX_OUTPUT_TOKENS   16000                Cap on each reply's tokens, reasoning included.
    EMBEDDING_MODEL     all-MiniLM-L6-v2     Local model that turns text into vectors for search.
                                             Rebuild the vector store after changing it.
    RERANKER_MODEL      ms-marco-MiniLM-L-6-v2  Local model that reorders search results by relevance.

Paths (fixed, relative to the repo root):
    DATA_DIR     data/        Synthetic users, accounts, and score history (INR, 300-900 scores).
    CORPUS_DIR   corpus/      Markdown credit-education documents used for RAG.
    CHROMA_DIR   .chroma/     Local vector store, rebuilt by ``python -m creditcoach.rag.ingest``.
    SAMPLE_DATA  sample_data/credit_profile_sample.xlsx  Original seed profile (USD).
    LOGINS_FILE  creditcoach/app/logins.json  Chat UI logins: username -> user id + password hash.
    MEMORY_DIR   memory/      Per-user memory (Task 16) for the "files" backend: conversation episodes and dreams.
                              The committed files are the archive from before the Neon move. ``CREDITCOACH_MEMORY_DIR``
                              moves it (tests use a temp dir).

Memory storage (environment variable -> default):
    DATABASE_URL                ""  Neon Postgres connection string. When set, memory is kept in Neon.
    CREDITCOACH_MEMORY_BACKEND  "postgres" if DATABASE_URL is set, else "files". Tests and evidence scripts force
                                "files" so they never write to the shared database.

Cache (Task 22; environment variable -> default):
    REDIS_URL                  ""    Redis connection string, e.g. ``redis://localhost:6379/0``. When set, the cache
                                     is kept in Redis. Without it the cache lives in the app's own memory and is
                                     lost on restart.
    CREDITCOACH_CACHE          "on"  "off" turns every cache layer off. Tests turn it off by default.
    CREDITCOACH_CACHE_CONFIRM  "on"  "off" stops the semantic answer cache asking ``SMALL_MODEL`` whether a reworded
                                     question is the same; only exact and same-words matches are then served.

Observability (Task 26; environment variable -> default):
    CREDITCOACH_TRACES      "on"       "off" stops writing spans to the local trace files.
    CREDITCOACH_TRACES_DIR  .traces/   Where the local trace files go (git-ignored), one JSON line per span.
    LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
                            ""         With both set, every trace is also sent to Langfuse over OTLP.
    LANGFUSE_HOST           "https://cloud.langfuse.com"  Langfuse region or self-hosted URL. LANGFUSE_BASE_URL, the
                            name Langfuse's own setup snippet uses, is read too when LANGFUSE_HOST isn't set.
    OTEL_EXPORTER_OTLP_ENDPOINT  ""    Without Langfuse keys: any OpenTelemetry collector to send traces to.
    CREDITCOACH_ENV         "local"    Tags every trace (for example "railway" for the deployed build).

Sign-up and the weekly allowance (environment variable -> default):
    CREDITCOACH_SIGNUP_MAX         50  How many people may sign up in total. Sign-up closes when it is reached.
    CREDITCOACH_INVITE_CODE        ""  When set, the sign-up form asks for this code and refuses anyone without it.
    CREDITCOACH_WEEKLY_QUESTIONS   5   Questions a signed-up user may ask per week. The 15 team logins have no limit.
    CREDITCOACH_SESSION_SECRET     ""  Signs the sign-in cookie. Blank means a new random secret each start, which
                                       signs everyone out on restart.
    SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM
                                       Mail account for the optional "email me my login" backup at sign-up. Without
                                       it the option isn't offered. Never commit the password.

Example:
    >>> from creditcoach import config
    >>> config.CHAT_MODEL
    'anthropic/claude-sonnet-5.5'
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Sonnet 5.5 replaced GPT-5 on 2026-10-31: on all 50 eval cases it passed as many (43 of 50) at half the time
# (median 10.4 s against 20.4 s, 90th percentile 14.9 s against 30.8 s); docs/evidence/week-4/eval-model-*.md.
# GPT-5 wrote at 30-55 tokens/s on Railway, so a typical answer took 20-35 s. REASONING_EFFORT applies to GPT-5 only.
CHAT_MODEL = os.getenv("CHAT_MODEL", "anthropic/claude-sonnet-5.5")
SMALL_MODEL = os.getenv("SMALL_MODEL", "openai/gpt-5-mini")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "openai/gpt-4o")
# Reasoning effort for GPT-5-family models (minimal | low | medium | high). "low" cut answer time from
# ~14-37s to ~8s in Task 11 with the same grounding and citation behaviour. "minimal" was tried on all 50 eval
# cases in Task 30, side by side with "low": 40% faster, but 39 of 50 passed against 43 (a misstated figure, a
# substitute month, missed advice), so "low" stays.
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "low")
# Cap on each reply's tokens, reasoning included. Without it OpenRouter reserves GPT-5's full 65,536-token
# limit, and a key with less credit than that gets a 402 on every call, so every answer silently came from
# FALLBACK_MODEL (seen 2026-10-03). Answers use a few thousand tokens at "low" effort.
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "16000"))

SAMPLE_DATA = ROOT / "sample_data" / "credit_profile_sample.xlsx"
DATA_DIR = ROOT / "data"  # synthetic dataset (Indian context: INR, 300-900 scores)

CORPUS_DIR = ROOT / "corpus"
CHROMA_DIR = ROOT / ".chroma"  # git-ignored; rebuilt by `python -m creditcoach.rag.ingest`
CORPUS_COLLECTION = "creditcoach_corpus"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

LOGINS_FILE = ROOT / "creditcoach" / "app" / "logins.json"  # committed; holds password hashes, never passwords

MEMORY_DIR = Path(os.getenv("CREDITCOACH_MEMORY_DIR", ROOT / "memory"))  # files backend; committed archive
DATABASE_URL = os.getenv("DATABASE_URL", "")  # Neon Postgres; never commit it
MEMORY_BACKEND = os.getenv("CREDITCOACH_MEMORY_BACKEND", "postgres" if DATABASE_URL else "files")
REDIS_URL = os.getenv("REDIS_URL", "")  # never commit one that holds a password
CACHE = os.getenv("CREDITCOACH_CACHE", "on")
CACHE_CONFIRM = os.getenv("CREDITCOACH_CACHE_CONFIRM", "on") != "off"
# Where users, accounts and score history are read from: Neon (a copy loaded by scripts/data_import.py) or data/
DATA_BACKEND = os.getenv("CREDITCOACH_DATA_BACKEND", "postgres" if DATABASE_URL else "files")

# Observability (creditcoach.observability)
TRACES = os.getenv("CREDITCOACH_TRACES", "on")
TRACES_DIR = Path(os.getenv("CREDITCOACH_TRACES_DIR", ROOT / ".traces"))  # git-ignored
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")  # never commit it
# Langfuse's setup snippet now calls it LANGFUSE_BASE_URL; pasting that left the default region, which refused the keys
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com"
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
ENVIRONMENT = os.getenv("CREDITCOACH_ENV", "local")

# Sign-up (creditcoach.signup) and the weekly allowance (creditcoach.app.limits)
SIGNUP_MAX = int(os.getenv("CREDITCOACH_SIGNUP_MAX", "50"))
INVITE_CODE = os.getenv("CREDITCOACH_INVITE_CODE", "")
WEEKLY_QUESTIONS = int(os.getenv("CREDITCOACH_WEEKLY_QUESTIONS", "5"))
SESSION_SECRET = os.getenv("CREDITCOACH_SESSION_SECRET", "")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # never commit it
SMTP_FROM = os.getenv("SMTP_FROM", "")
