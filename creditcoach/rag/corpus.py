"""Load the Markdown corpus in corpus/ with its front matter."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from creditcoach import config


@dataclass
class Document:
    file: str
    id: str
    title: str
    category: str
    source: str
    queries: list[int] = field(default_factory=list)
    body: str = ""


def parse_front_matter(text: str) -> tuple[dict | None, str]:
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
