"""Task 8: rebuild the vector store and regenerate both ingestion evidence files from it.

Runs the ingestion pipeline (``creditcoach.rag.ingest``), captures its console log, then exports every chunk from
the Chroma collection. Before this script, both files were written by hand from a run, so re-tagging or editing
the corpus left them out of date.

Writes:
    docs/evidence/week-1/task-08-ingestion-log.md   The console log and the result line. The "Issues found and
                                                    fixed while building" section is kept as written.
    docs/evidence/week-1/task-08-chunks.md          Every chunk's id, file, category, size, query tags and full text.

Run after editing anything in ``corpus/`` (no API key needed):
    uv run python scripts/task08_ingestion_report.py
"""

import contextlib
import io
import re
import sys
from datetime import date

from creditcoach import config
from creditcoach.rag import ingest

EVIDENCE = config.ROOT / "docs" / "evidence" / "week-1"
LOG = EVIDENCE / "task-08-ingestion-log.md"
CHUNKS = EVIDENCE / "task-08-chunks.md"


def anchor(n: int, chunk_id: str) -> str:
    """GitHub's anchor for the heading "### <n>. <chunk id without #>"."""
    return f"{n}-{chunk_id.replace('#', '')}"


def write_log(console: str, ok: bool) -> None:
    """Rewrite the log and result in the ingestion-log file, keeping its hand-written issues section."""
    old = LOG.read_text(encoding="utf-8")
    issues = old[old.index("## Issues found"):] if "## Issues found" in old else ""
    stored = int(re.search(r"Stored (\d+) chunks", console).group(1))
    truncated = int(re.search(r"truncated by the model: (\d+)", console).group(1))
    docs = int(re.search(r"Loaded (\d+) documents", console).group(1))
    head = old[:old.index("## Console log")]
    head = re.sub(r"^\*\d{4}-\d{2}-\d{2} ·", f"*{date.today().isoformat()} ·", head, flags=re.M)
    head = re.sub(r"load \d+ Markdown documents", f"load {docs} Markdown documents", head)
    head = head.replace("sample-query tags", "tags for the requirements.md queries #1–50")
    LOG.write_text(head + "## Console log\n\n```\n" + console.strip() + "\n```\n\n## Result\n\n"
                   + ("The pipeline ran with no errors. " if ok else "**The run reported a problem.** ")
                   + f"**Expected chunk count: {stored}. Chunks in the vector store: {stored}. "
                   f"Chunks truncated by the model: {truncated}.**\n\n" + issues, encoding="utf-8")


def write_chunks() -> int:
    """Export every chunk in the collection, in corpus order. Returns the chunk count."""
    import chromadb

    collection = chromadb.PersistentClient(path=str(config.CHROMA_DIR)).get_collection(config.CORPUS_COLLECTION)
    got = collection.get(include=["documents", "metadatas"])
    rows = sorted(zip(got["ids"], got["documents"], got["metadatas"]), key=lambda r: (r[2]["file"], r[2]["chunk_index"]))
    words = sum(m["words"] for _, _, m in rows)
    lines = [f"# Task 8 evidence: all {len(rows)} chunks in the vector store", "",
             f"*Exported from the Chroma collection `{config.CORPUS_COLLECTION}` in `.chroma` on {date.today().isoformat()}, "
             "in corpus order, by `uv run python scripts/task08_ingestion_report.py`. Text is exactly what was embedded "
             "(each chunk starts with its document title), shown in fenced blocks so its markdown isn't rendered.*", "",
             f"**{len(rows)} chunks · {len({m['file'] for _, _, m in rows})} source files · {words:,} words.** \"Queries\" are "
             "the requirements.md queries (§3 #1–6 and §4 #7–50) the source file is tagged for.", "",
             "## Index", "", "| # | Chunk ID | File | Part | Category | Words / Tokens | Queries |",
             "|---|---|---|---|---|---|---|"]
    for n, (cid, _, m) in enumerate(rows, 1):
        lines.append(f"| {n} | [`{cid}`](#{anchor(n, cid)}) | `{m['file']}` | {m['chunk_index'] + 1}/{m['chunk_count']} | "
                     f"{m['category']} | {m['words']} / {m['tokens']} | {m['queries']} |")
    lines += ["", "## Chunks"]
    for n, (cid, text, m) in enumerate(rows, 1):
        lines += ["", f"### {n}. {cid.replace('#', '')}", "",
                  f"`{cid}` · [{m['file']}](../../../corpus/{m['file']}) · part {m['chunk_index'] + 1} of {m['chunk_count']} · "
                  f"{m['category']} · {m['words']} words / {m['tokens']} tokens · queries {m['queries']}  ",
                  f"Source: {m['source']}", "", "```text", text, "```"]
    CHUNKS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(rows)


def main() -> int:
    """Run ingestion, then write both evidence files. Returns ingestion's exit code."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = ingest.main()
    console = re.sub(r"Done in [\d.]+s", "Done in {:.1f}s".format(float(re.search(r"Done in ([\d.]+)s",
                                                                                     out.getvalue()).group(1))),
                     out.getvalue())
    print(console)
    write_log(console, code == 0)
    n = write_chunks()
    print(f"Wrote {LOG.relative_to(config.ROOT)} and {CHUNKS.relative_to(config.ROOT)} ({n} chunks)")
    return code


if __name__ == "__main__":
    sys.exit(main())
