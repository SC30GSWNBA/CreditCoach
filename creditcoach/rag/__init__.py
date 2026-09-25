"""Retrieval-augmented generation (RAG): how CreditCoach finds the right credit-education passages.

The three steps, in order:
    corpus    Load the Markdown documents in ``corpus/`` and their front matter (id, title, category, ...).
    ingest    Split documents into chunks, turn each chunk into a vector, and store them in ChromaDB.
              Run once, and again after editing the corpus: ``uv run python -m creditcoach.rag.ingest``
    retrieve  Find the chunks most relevant to a question (vector search + reranking).
              Try it: ``uv run python -m creditcoach.rag.retrieve "why did my score drop?"``
"""
