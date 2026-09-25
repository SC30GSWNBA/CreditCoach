"""Load the credit-education corpus: the Markdown documents in ``corpus/`` and their front matter.

Each document starts with a front-matter block that describes it, for example::

    ---
    id: factor-credit-utilization
    title: Credit utilization
    category: scoring_factor          # scoring_factor | financial_literacy | product_risk
    source: credit_score_factors_guide.pdf §2 and §7
    queries: [1, 2, 3]                # requirements.md sample queries this document helps answer
    ---

Used by ingestion (Task 8) and by the corpus coverage report (Task 7).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from creditcoach import config


@dataclass
class Document:
    """One corpus document, as loaded from a Markdown file.

    Attributes:
        file: File name, e.g. "03-credit-utilization.md".
        id: Unique, stable document id from the front matter, e.g. "factor-credit-utilization".
        title: Human-readable title.
        category: "scoring_factor", "financial_literacy", or "product_risk".
        source: Where the content comes from, e.g. "credit_score_factors_guide.pdf §2".
        queries: Numbers of the requirements.md sample queries this document helps answer.
        body: The Markdown text after the front matter.
    """
    file: str
    id: str
    title: str
    category: str
    source: str
    queries: list[int] = field(default_factory=list)
    body: str = ""


def parse_front_matter(text: str) -> tuple[dict | None, str]:
    """Split a Markdown file into its front-matter fields and its body.

    Handles the simple ``key: value`` format used in the corpus. Surrounding quotes are removed from values,
    and ``queries`` is turned into a list of integers.

    Args:
        text: Full file contents.

    Returns:
        ``(metadata, body)``. ``metadata`` is ``None`` if the file has no front-matter block, in which case
        ``body`` is the whole text.
    """
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        return None, text
    meta = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        meta[key] = [int(x) for x in re.findall(r"\d+", value)] if key == "queries" else value
    return meta, m.group(2)


def load_corpus(corpus_dir: Path = config.CORPUS_DIR) -> list[Document]:
    """Load every corpus document, in file-name order (``README.md`` is skipped).

    Args:
        corpus_dir: Folder containing the Markdown documents. Defaults to ``corpus/``.

    Returns:
        A list of ``Document`` objects.

    Raises:
        ValueError: If a document has no front matter.
        KeyError: If a front-matter block is missing id, title, category, source, or queries.
    """
    docs = []
    for path in sorted(corpus_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        if meta is None:
            raise ValueError(f"{path.name}: missing front matter")
        docs.append(Document(file=path.name, body=body.strip(), **{k: meta[k] for k in
                             ("id", "title", "category", "source", "queries")}))
    return docs
