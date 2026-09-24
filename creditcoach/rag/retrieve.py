"""Retrieve the most relevant corpus chunks for a question from the ChromaDB vector store.

    uv run python -m creditcoach.rag.retrieve "why did my credit score drop 20 points?"

Build the store first with `uv run python -m creditcoach.rag.ingest`.
"""

import re
import sys
from dataclasses import dataclass
from functools import lru_cache

from creditcoach import config


@dataclass
class Result:
    rank: int
    id: str
    score: float  # cosine similarity, higher is more similar
    title: str
    category: str
    text: str
    metadata: dict


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(config.EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def _reranker():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(config.RERANKER_MODEL)


@lru_cache(maxsize=1)
def _collection():
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
    """'my cibil score fell' -> 'my cibil (credit) score fell'"""
    return BUREAU_NAMES.sub(lambda m: f"{m.group(0)} (credit)", query)


def _dense(query: str, n: int, where: dict | None) -> list[Result]:
    embedding = _model().encode([query], normalize_embeddings=True).tolist()
    r = _collection().query(query_embeddings=embedding, n_results=n, where=where)
    return [Result(rank=i + 1, id=cid, score=round(1 - dist, 4), title=meta["title"], category=meta["category"],
                   text=doc, metadata=meta)
            for i, (cid, dist, doc, meta) in enumerate(zip(r["ids"][0], r["distances"][0], r["documents"][0],
                                                           r["metadatas"][0]))]


def retrieve(query: str, k: int = 3, where: dict | None = None, *, rerank: bool = True, fusion: bool = False,
             max_per_doc: int | None = 2, candidates: int = 12) -> list[Result]:
    """Return the top-k chunks for a query.

    0. Normalize: add "(credit)" after Indian bureau names such as CIBIL.
    1. Dense search: embed the query and take the `candidates` nearest chunks (cosine similarity).
    2. Rerank (optional): a cross-encoder scores each (query, chunk) pair. With `fusion`, the dense and
       cross-encoder rankings are combined by reciprocal rank fusion, so neither ranking alone decides.
    3. Diversity: keep at most `max_per_doc` chunks from any one document.

    `where` is an optional ChromaDB metadata filter, e.g. {"category": "product_risk"} or {"q4": True}.
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
    lines = []
    for r in results:
        body = r.text.split("\n\n", 1)[-1].replace("\n", " ")
        lines.append(f"  {r.rank}. [{r.score:.3f}] {r.id}  ({r.category})\n     {body[:preview]}...")
    return "\n".join(lines)


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "why did my credit score drop 20 points?"
    print(f"Query: {question}\n{format_results(retrieve(question))}")
