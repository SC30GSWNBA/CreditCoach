"""Find the corpus chunks most relevant to a question (Task 9).

Build the vector store first (``uv run python -m creditcoach.rag.ingest``), then try it:

    uv run python -m creditcoach.rag.retrieve "why did my credit score drop 20 points?"

How a question is answered, step by step:
    0. Normalize: Indian bureau names get "(credit)" added ("cibil score" -> "cibil (credit) score"),
       because the models were trained on general English text and don't know these names.
    1. Vector search: embed the question and take the 12 most similar chunks from ChromaDB.
    2. Rerank: a cross-encoder reads the question and each of those chunks together and reorders them by
       how well the chunk answers the question. This is slower but more accurate than vector search.
    3. Diversity: keep at most 2 chunks per document, then return the top 3.

This design was chosen in Task 9 by comparing strategies on 10 hand-labelled questions (see
``docs/evidence/week-1/task-09-retrieval-test.md``). Both models run locally and are loaded once, on
first use.

Example:
    >>> from creditcoach.rag.retrieve import retrieve
    >>> for r in retrieve("what is credit utilization?"):
    ...     print(r.rank, r.id, r.score)
"""

import re
import sys
from dataclasses import dataclass
from functools import lru_cache

from creditcoach import config


@dataclass
class Result:
    """One retrieved chunk.

    Attributes:
        rank: Position in the final results (1 = most relevant).
        id: Chunk id, e.g. "why-scores-drop#01".
        score: Cosine similarity from vector search (higher = more similar). The final order may differ
            from this score, because the reranker decides the order.
        title: Title of the document the chunk comes from.
        category: "scoring_factor", "financial_literacy", or "product_risk".
        text: The chunk text (starts with the document title).
        metadata: All stored fields (source, doc id, sample-query tags, ...).
    """
    rank: int
    id: str
    score: float  # cosine similarity, higher is more similar
    title: str
    category: str
    text: str
    metadata: dict


@lru_cache(maxsize=1)
def _model():
    """Load the embedding model once and reuse it for every query."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(config.EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def _reranker():
    """Load the cross-encoder reranker once and reuse it for every query."""
    from sentence_transformers import CrossEncoder

    return CrossEncoder(config.RERANKER_MODEL)


@lru_cache(maxsize=1)
def _collection():
    """Open the ChromaDB collection once, checking it exists and was built with the configured embedding model.

    Raises:
        RuntimeError: If the store is missing (run ingest) or was built with a different ``EMBEDDING_MODEL``.
    """
    import chromadb

    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    try:
        collection = client.get_collection(config.CORPUS_COLLECTION)
    except Exception as exc:
        raise RuntimeError("Vector store not built. Run: uv run python -m creditcoach.rag.ingest") from exc
    built_with = (collection.metadata or {}).get("embedding_model")
    if built_with and built_with != config.EMBEDDING_MODEL:
        raise RuntimeError(f"Vector store was built with {built_with} but EMBEDDING_MODEL is {config.EMBEDDING_MODEL}. "
                           "Rebuild it with: uv run python -m creditcoach.rag.ingest")
    return collection


# Indian users often name the bureau instead of saying "credit score". The embedding and reranking models
# were trained on general English text and don't know these names, so we add the generic term.
BUREAU_NAMES = re.compile(r"\b(cibil|experian|equifax|crif(?: high ?mark)?)\b", re.I)


def normalize_query(query: str) -> str:
    """Add "(credit)" after Indian credit-bureau names so the models recognise them as credit scores.

    Example: "my cibil score fell" -> "my cibil (credit) score fell".

    Args:
        query: The user's question.

    Returns:
        The question with "(credit)" inserted after CIBIL, Experian, Equifax, or CRIF (High Mark).
    """
    return BUREAU_NAMES.sub(lambda m: f"{m.group(0)} (credit)", query)


def _dense(query: str, n: int, where: dict | None) -> list[Result]:
    """Vector search: embed the query and return the ``n`` most similar chunks, ranked by cosine similarity."""
    embedding = _model().encode([query], normalize_embeddings=True).tolist()
    r = _collection().query(query_embeddings=embedding, n_results=n, where=where)
    return [Result(rank=i + 1, id=cid, score=round(1 - dist, 4), title=meta["title"], category=meta["category"],
                   text=doc, metadata=meta)
            for i, (cid, dist, doc, meta) in enumerate(zip(r["ids"][0], r["distances"][0], r["documents"][0],
                                                           r["metadatas"][0]))]


def retrieve(query: str, k: int = 3, where: dict | None = None, *, rerank: bool = True, fusion: bool = False,
             max_per_doc: int | None = 2, candidates: int = 12) -> list[Result]:
    """Return the corpus chunks most relevant to a question, best first.

    Steps: normalize the question, take the ``candidates`` nearest chunks by vector similarity, optionally
    rerank them with the cross-encoder, then keep at most ``max_per_doc`` chunks per document. The defaults
    are the strategy chosen in Task 9.

    Args:
        query: The user's question in plain language.
        k: How many chunks to return (default 3).
        where: Optional ChromaDB metadata filter, e.g. ``{"category": "product_risk"}`` for risk content
            only, or ``{"q4": True}`` for chunks tagged for sample query 4.
        rerank: Reorder candidates with the cross-encoder (default True).
        fusion: Combine the vector and reranker rankings (reciprocal rank fusion) instead of using the
            reranker's order alone (default False; it scored lower in Task 9).
        max_per_doc: Maximum chunks from any one document, so one document can't fill every slot
            (default 2; ``None`` for no limit).
        candidates: How many vector-search results to consider before reranking (default 12).

    Returns:
        Up to ``k`` ``Result`` objects, ranked 1..k. ``score`` is the vector similarity; the order comes
        from the reranker when ``rerank`` is True.

    Raises:
        RuntimeError: If the vector store hasn't been built, or was built with a different embedding model.
    """
    query = normalize_query(query)
    pool = _dense(query, max(candidates, k), where)
    if rerank and pool:
        ce_scores = _reranker().predict([(query, r.text) for r in pool])
        ce_rank = {r.id: i for i, (_, r) in enumerate(sorted(zip(ce_scores, pool), key=lambda x: -x[0]))}
        if fusion:
            key = lambda r: -(1 / (60 + r.rank) + 1 / (60 + ce_rank[r.id] + 1))  # RRF with the standard k=60
        else:
            key = lambda r: ce_rank[r.id]
        pool = sorted(pool, key=key)

    out, per_doc = [], {}
    for r in pool:
        doc = r.metadata["doc_id"]
        if max_per_doc and per_doc.get(doc, 0) >= max_per_doc:
            continue
        per_doc[doc] = per_doc.get(doc, 0) + 1
        out.append(r)
        if len(out) == k:
            break
    for i, r in enumerate(out):
        r.rank = i + 1
    return out


def format_results(results: list[Result], preview: int = 160) -> str:
    """Format retrieval results for the terminal: rank, similarity, chunk id, category, and a text preview.

    Args:
        results: Output of ``retrieve()``.
        preview: How many characters of each chunk to show.

    Returns:
        Multi-line text, one entry per result.
    """
    lines = []
    for r in results:
        body = r.text.split("\n\n", 1)[-1].replace("\n", " ")
        lines.append(f"  {r.rank}. [{r.score:.3f}] {r.id}  ({r.category})\n     {body[:preview]}...")
    return "\n".join(lines)


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "why did my credit score drop 20 points?"
    print(f"Query: {question}\n{format_results(retrieve(question))}")
