"""Chunk the corpus, embed it, and load it into a persistent ChromaDB collection.

    uv run python -m creditcoach.rag.ingest

Each run rebuilds the collection from scratch, so re-running never duplicates chunks.
"""

import re
import sys
import time
from dataclasses import dataclass

from creditcoach import config
from creditcoach.rag.corpus import Document, load_corpus

MAX_TOKENS = 240  # all-MiniLM-L6-v2 reads at most 256 tokens; leave room for special tokens
MIN_WORDS = 40  # smaller chunks (an intro or a closing caveat) are merged into a neighbour when they fit


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict


def blocks(body: str) -> list[str]:
    """Split a document into semantic blocks: paragraphs, whole lists, whole tables. Headings attach to what follows."""
    out, pending_heading = [], ""
    for block in re.split(r"\n\s*\n", body.strip()):
        block = block.strip()
        if not block:
            continue
        if re.fullmatch(r"#{1,6} .+", block):  # a heading on its own: carry it into the next block
            pending_heading = block
            continue
        out.append(f"{pending_heading}\n\n{block}" if pending_heading else block)
        pending_heading = ""
    return out


def split_oversized(block: str, fits) -> list[str]:
    """Split a block that is too long on its own at line boundaries (list items, table rows)."""
    if fits(block):
        return [block]
    lines, parts, current = block.splitlines(), [], []
    for line in lines:
        if current and not fits("\n".join(current + [line])):
            parts.append("\n".join(current))
            current = []
        current.append(line)
    parts.append("\n".join(current))
    return parts


def merge_small(packed: list[list[str]], fits) -> list[list[str]]:
    """Keep intros with the content they introduce and caveats with the content they qualify."""
    words = lambda group: sum(len(b.split()) for b in group)
    i = 0
    while i < len(packed):
        if words(packed[i]) < MIN_WORDS and len(packed) > 1:
            j = i + 1 if i == 0 else i - 1  # intro joins the next chunk, a caveat joins the previous one
            lo, hi = min(i, j), max(i, j)
            merged = packed[lo] + packed[hi]
            if fits("\n\n".join(merged)):
                packed[lo:hi + 1] = [merged]
                i = lo
                continue
        i += 1
    return packed


def chunk_document(doc: Document, count_tokens) -> list[Chunk]:
    """Pack a document's blocks into chunks of at most MAX_TOKENS (title included); blocks split only if oversized."""
    fits = lambda body: count_tokens(f"{doc.title}\n\n{body}") <= MAX_TOKENS
    packed, current = [], []
    for block in [p for b in blocks(doc.body) for p in split_oversized(b, fits)]:
        if current and not fits("\n\n".join(current + [block])):
            packed.append(current)
            current = []
        current.append(block)
    if current:
        packed.append(current)
    packed = merge_small(packed, fits)

    chunks = []
    for i, group in enumerate(packed):
        body = "\n\n".join(group)
        body = re.sub(r"^# .+\n\n", "", body)  # the title is added below; drop the duplicate H1
        text = f"{doc.title}\n\n{body}"
        chunks.append(Chunk(
            id=f"{doc.id}#{i:02d}",
            text=text,
            metadata={
                "doc_id": doc.id, "title": doc.title, "category": doc.category, "source": doc.source,
                "file": doc.file, "chunk_index": i, "chunk_count": len(packed), "words": len(body.split()),
                "tokens": count_tokens(text), "queries": ",".join(map(str, doc.queries)),
                **{f"q{q}": True for q in doc.queries},  # scalar flags so retrieval can filter by sample query
            },
        ))
    return chunks


def main() -> int:
    import chromadb
    from sentence_transformers import SentenceTransformer

    t0 = time.perf_counter()
    model = SentenceTransformer(config.EMBEDDING_MODEL)
    count_tokens = lambda text: len(model.tokenizer(text, add_special_tokens=False)["input_ids"])

    docs = load_corpus()
    chunks = [c for d in docs for c in chunk_document(d, count_tokens)]
    words = [c.metadata["words"] for c in chunks]
    tokens = [c.metadata["tokens"] for c in chunks]
    print(f"[ingest] Loaded {len(docs)} documents from {config.CORPUS_DIR.relative_to(config.ROOT)}/")
    print(f"[ingest] Chunked into {len(chunks)} chunks (max {MAX_TOKENS} tokens each; model limit "
          f"{model.max_seq_length}) - words min {min(words)} / max {max(words)} / avg {sum(words) / len(words):.0f}, "
          f"tokens max {max(tokens)}")
    embeddings = model.encode([c.text for c in chunks], batch_size=32, normalize_embeddings=True,
                              show_progress_bar=False)
    print(f"[ingest] Embedded {len(embeddings)} chunks with {config.EMBEDDING_MODEL} "
          f"(dimension {embeddings.shape[1]})")

    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    if config.CORPUS_COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(config.CORPUS_COLLECTION)
    collection = client.create_collection(
        config.CORPUS_COLLECTION,
        metadata={"hnsw:space": "cosine", "embedding_model": config.EMBEDDING_MODEL},
    )
    collection.add(ids=[c.id for c in chunks], documents=[c.text for c in chunks],
                   metadatas=[c.metadata for c in chunks], embeddings=embeddings.tolist())

    stored = collection.count()
    per_doc = {}
    for c in chunks:
        per_doc[c.metadata["doc_id"]] = per_doc.get(c.metadata["doc_id"], 0) + 1
    print(f"[ingest] Stored {stored} chunks in ChromaDB collection '{config.CORPUS_COLLECTION}' "
          f"at {config.CHROMA_DIR.relative_to(config.ROOT)}/")
    for cat in ("scoring_factor", "financial_literacy", "product_risk"):
        print(f"[ingest]   {cat:<18} {sum(c.metadata['category'] == cat for c in chunks)} chunks")
    for doc_id, n in per_doc.items():
        print(f"[ingest]   {doc_id:<34} {n} chunk{'s' if n > 1 else ''}")

    truncated = [c.id for c in chunks if c.metadata["tokens"] + 2 > model.max_seq_length]  # +2: [CLS] and [SEP]
    ok = stored == len(chunks) == len(embeddings) and not truncated
    print(f"[ingest] Check: expected {len(chunks)} chunks, store has {stored}; "
          f"chunks truncated by the model: {len(truncated)} -> {'OK' if ok else 'PROBLEM ' + str(truncated)}")
    print(f"[ingest] Done in {time.perf_counter() - t0:.1f}s")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
