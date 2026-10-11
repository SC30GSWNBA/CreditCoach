"""CreditCoach: a grounded, guardrailed credit coach for first-time borrowers in India.

CreditCoach explains why a user's credit score changed and how to improve it steadily. Answers are grounded
in a curated credit-education library (RAG) and in the signed-in user's own simulated account data, read
through the MCP tools specified in ``docs/tools.md``. It never guarantees a score, never recommends predatory
products, and never invents a figure.

Subpackages:
    agent/       Orchestration: question -> guardrails -> retrieval -> MCP tools and memory -> guardrails ->
                 grounded answer (``pipeline.py``), and the MCP host (``mcp_host.py``).
    app/         Gradio chat UI (``python -m creditcoach.app``).
    cache/       The cache: embeddings, retrieval, tool lookups and finished answers (``docs/caching.md``).
    evals/       The 50 requirements.md queries with their checks, and the red-team set.
    guardrails/  The guardrail layer around every question and answer (``docs/guardrails.md``).
    memory/      Per-user memory: episodes, the goal, dreaming and recall (``docs/memory.md``).
    prompts/     The system prompt that sets tone and the hard rules.
    rag/         Corpus loading, ingestion into the vector store, and retrieval.
    tools/       The two data tools and the MCP server that exposes them (``docs/tools.md``).

Modules:
    config     All settings (API key, model IDs, file paths), read from ``.env``.
    llm        OpenRouter chat client with an automatic fallback model.
    check      Setup check for a fresh clone (``python -m creditcoach.check``).
    auth       Per-user chat UI logins.
    dataset    Users, accounts and score history, from Neon or ``data/``.
    user_data  One signed-in user's profile, scores and accounts, nobody else's.
"""
