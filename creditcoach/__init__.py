"""CreditCoach: a grounded, guardrailed credit coach for first-time borrowers in India.

CreditCoach explains why a user's credit score changed and how to improve it steadily. Answers are grounded
in a curated credit-education library (RAG) and in the signed-in user's own simulated account data (read
from ``data/`` by ``user_data.py`` today, and through the MCP tools specified in ``docs/tools.md`` from Week 2). It
never guarantees a score, never recommends predatory products, and never invents a figure.

Subpackages:
    agent/    Orchestration: question -> retrieved passages -> grounded answer (``pipeline.py``).
    app/      Gradio chat UI (``python -m creditcoach.app``).
    prompts/  The system prompt that sets tone and the hard rules.
    rag/      Corpus loading, ingestion into the vector store, and retrieval.

Modules:
    config    All settings (API key, model IDs, file paths), read from ``.env``.
    llm       OpenRouter chat client with an automatic fallback model.
    check     Setup check for a fresh clone (``python -m creditcoach.check``).
"""
