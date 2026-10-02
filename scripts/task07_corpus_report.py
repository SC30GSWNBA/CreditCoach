"""Task 7: validate the RAG corpus and write the evidence summary (document count and coverage).

Checks that:
    - every document in ``corpus/`` has complete front matter (id, title, category, source, queries) with
      a known category and a unique id;
    - each of the 50 requirements.md queries (§3 sample queries #1-6 and §4 additional queries #7-50, read from
      ``creditcoach.evals.golden``) has at least one tagged document containing the key facts its answer needs
      (``KEY_FACTS``), except the queries in ``NO_CORPUS``, whose answers need no corpus content;
    - no document covers a topic that a query expects the corpus not to have (``ABSENT``: buy now, pay later,
      for §4 #48, whose expected answer is "I don't have specific information on that");
    - every section (§1-§7) of credit_score_factors_guide.pdf is represented in at least one document.

Writes:
    docs/evidence/week-1/task-07-corpus-summary.md   Document table, category counts, and coverage tables.
    Also printed to the terminal. Exit code 1 if any check fails.

Run after adding or editing corpus documents (no API key needed):
    uv run python scripts/task07_corpus_report.py
"""

import re
import sys

from creditcoach import config
from creditcoach.evals import golden
from creditcoach.rag.corpus import parse_front_matter

CORPUS = config.ROOT / "corpus"
EVIDENCE = config.ROOT / "docs" / "evidence" / "week-1" / "task-07-corpus-summary.md"
REQUIRED = ["id", "title", "category", "source", "queries"]
CATEGORIES = {"scoring_factor": "Credit-scoring factors", "financial_literacy": "Financial literacy",
              "product_risk": "Product risk"}

QUERIES = golden.load()
# Facts each query's answer depends on; every phrase must appear in at least one document tagged for that query.
# Phrases are quoted from the corpus, so a reworded document fails here instead of silently losing a fact.
KEY_FACTS = {
    1: ["utilization spike", "hard inquiry", "10 to 40 points", "2 to 10 points"],
    2: ["balance divided by your limit", "30%"],
    3: ["car loan", "hard inquiry", "utilization"],
    4: ["payday", "instant loan app", "don't report to the credit bureaus", "safer"],
    5: ["target score", "target date", "purpose"],
    6: ["guarantee", "not public"],
    7: ["two events in the same month", "10 to 40 points", "2 to 10 points"],
    8: ["2 to 10 points", "12 months"],
    9: ["within a short window", "small, temporary"],
    10: ["30%", "one reporting cycle"],
    11: ["60 to 110 points", "up to seven years", "about two years"],
    12: ["free credit counselling", "borrowing from one app to repay another", "30%"],
    13: ["small ups and downs of a few points are normal"],
    14: ["new to credit", "secured credit card"],
    15: ["not part of utilization"],
    16: ["divide the total balance by the total limit", "30%"],
    18: ["30%"],
    19: ["not part of utilization"],
    20: ["no record of you", "new to credit"],
    21: ["into emis", "payment plan", "stop adding new spending"],
    23: ["within a short window", "car loan", "30%"],
    24: ["check your credit report early", "keep old cards open", "pause new credit applications"],
    25: ["a goal can be ambitious", "fastest lever"],
    26: ["your income, and your existing emis", "better interest rate"],
    27: ["interest is charged on the unpaid balance", "pay the full statement balance"],
    28: ["pay every bill on time", "a target score, a target date, and a purpose"],
    29: ["borrowing from one app to repay another", "payment plan", "free credit counselling"],
    30: ["disputed with the credit bureau for free", "asks for payment before doing any work"],
    31: ["a payday loan is a small, short-term loan", "why they are high-risk"],
    32: ["key fact statement", "rbi-regulated"],
    33: ["balance transfer", "the rate after the offer ends", "hard inquiry"],
    34: ["cannot be removed by a dispute or by paying a company", "disputing is free"],
    35: ["a target score, a target date, and a purpose"],
    36: ["review progress"],
    37: ["target score"],
    38: ["target score"],
    39: ["target score"],
    40: ["a goal can be ambitious"],
    41: ["one reporting cycle after the balance is paid down", "not predictions"],
    42: ["about two years", "guarantee"],
    43: ["not public", "no one can calculate your exact future score"],
    44: ["no one can guarantee", "free credit counselling"],
    50: ["guarantee", "not public"],
}
# Queries whose expected answer needs no corpus content: the user's own figures (#17, #22), a tool failure (#45),
# a period with no data (#46), a clarifying question (#47), a topic the corpus doesn't cover (#48), and another
# user's data (#49). No document may be tagged for them.
NO_CORPUS = {17, 22, 45, 46, 47, 48, 49}
# Topics the corpus must not cover, because a query's expected answer depends on their absence.
ABSENT = {48: ["buy now", "pay later", "bnpl"]}
# Every section of credit_score_factors_guide.pdf must be represented.
GUIDE_SECTIONS = {"§1": "Payment history", "§2": "Credit utilization", "§3": "Length of credit history",
                  "§4": "Hard inquiries", "§5": "Credit mix", "§6": "High-risk products", "§7": "Score impact table"}


def parse(path):
    """Read one corpus file and return ``(front_matter, body)`` using the shared parser."""
    return parse_front_matter(path.read_text(encoding="utf-8"))


def main() -> int:
    """Validate the corpus, write the evidence summary, and print it.

    Returns:
        0 if all checks passed, 1 otherwise (used as the process exit code).
    """
    docs, errors = [], []
    for path in sorted(CORPUS.glob("*.md")):
        if path.name == "README.md":
            continue
        meta, body = parse(path)
        if meta is None:
            errors.append(f"{path.name}: missing front matter")
            continue
        errors += [f"{path.name}: missing '{k}'" for k in REQUIRED if not meta.get(k)]
        if meta.get("category") not in CATEGORIES:
            errors.append(f"{path.name}: unknown category {meta.get('category')!r}")
        docs.append({"file": path.name, **meta, "body": body, "words": len(body.split())})

    if len({d["id"] for d in docs}) != len(docs):
        errors.append("duplicate document ids")

    ids = {q.id for q in QUERIES}
    if set(KEY_FACTS) | NO_CORPUS != ids or set(KEY_FACTS) & NO_CORPUS:
        errors.append("KEY_FACTS and NO_CORPUS must together list every query exactly once")
    unknown = sorted({n for d in docs for n in d.get("queries", [])} - ids)
    if unknown:
        errors.append(f"documents tagged for queries that don't exist: {unknown}")
    coverage = {}
    for q in QUERIES:
        tagged = [d for d in docs if q.id in d.get("queries", [])]
        text = " ".join(d["body"].lower() for d in tagged)
        missing = [f for f in KEY_FACTS.get(q.id, []) if f.lower() not in text]
        coverage[q.id] = (tagged, missing)
        if q.id in NO_CORPUS:
            if tagged:
                errors.append(f"query {q.id}: needs no corpus content but is tagged in {[d['file'] for d in tagged]}")
            continue
        if not tagged:
            errors.append(f"query {q.id}: no document tagged")
        if missing:
            errors.append(f"query {q.id}: key facts not found: {missing}")
    all_text = " ".join(d["body"].lower() for d in docs)
    present = {q: [t for t in terms if t in all_text] for q, terms in ABSENT.items()}
    for q, found in present.items():
        if found:
            errors.append(f"query {q}: the corpus must not cover {found}")

    sources = " ".join(d["source"] for d in docs)
    guide_missing = [s for s in GUIDE_SECTIONS if s not in sources]
    if guide_missing:
        errors.append(f"guide sections not represented: {guide_missing}")

    lines = ["# Task 7 Evidence: RAG Corpus Summary\n",
             "*Generated by `uv run python scripts/task07_corpus_report.py`. Corpus: `corpus/*.md`.*\n",
             f"**{len(docs)} documents · {sum(d['words'] for d in docs):,} words**\n",
             "| Category | Documents |", "|---|---|"]
    for cat, label in CATEGORIES.items():
        lines.append(f"| {label} (`{cat}`) | {sum(d['category'] == cat for d in docs)} |")
    lines += ["", "## Documents", "", "\"Queries\" are the requirements.md queries (§3 #1–6, §4 #7–50) each document helps "
              "answer, from its front matter. Task 9 uses the same tags as relevance labels.", "",
              "| # | Title | Category | Words | Queries | Source |", "|---|---|---|---|---|---|"]
    for d in docs:
        lines.append(f"| {d['file'][:2]} | {d['title']} | {d['category']} | {d['words']} | "
                     f"{', '.join(map(str, d['queries']))} | {d['source']} |")
    covered = [q for q in QUERIES if q.id not in NO_CORPUS and coverage[q.id][0] and not coverage[q.id][1]]
    lines += ["", "## Coverage of all 50 requirements.md queries", "",
              f"**{len(covered)} of {len(QUERIES) - len(NO_CORPUS)} queries that need corpus content are covered**, "
              f"and {len(NO_CORPUS)} need none (#{', #'.join(map(str, sorted(NO_CORPUS)))}). A query is covered when at "
              "least one document is tagged for it and the tagged documents contain every key fact its expected "
              "answer depends on.", ""]
    for section, title in [("3", "§3 Sample queries"), ("4", "§4 Additional queries")]:
        lines += [f"### {title}", "", "| # | User | Query | Documents | Key facts checked | Result |",
                  "|---|---|---|---|---|---|"]
        for q in (q for q in QUERIES if q.section[0] == section):
            tagged, missing = coverage[q.id]
            facts = ", ".join(f'"{f}"' for f in KEY_FACTS.get(q.id, []))
            if q.id in NO_CORPUS:
                result = "✅ needs no corpus content" if not tagged else "❌ tagged but needs none"
                if q.id in ABSENT:
                    found = present[q.id]
                    facts = "absent: " + ", ".join(f'"{t}"' for t in ABSENT[q.id])
                    result = "✅ topic absent, as expected" if not found and not tagged else f"❌ found {found}"
            else:
                result = "✅ covered" if tagged and not missing else "❌ " + (", ".join(missing) or "no document")
            docs_cell = f"{len(tagged)} ({', '.join(d['file'][:2] for d in tagged)})" if tagged else "—"
            lines.append(f"| {q.id} | {q.user_id} | {q.query} | {docs_cell} | {facts or '—'} | {result} |")
        lines.append("")
    lines += ["## Coverage of credit_score_factors_guide.pdf", "",
              "| Section | Topic | Represented in |", "|---|---|---|"]
    for s, topic in GUIDE_SECTIONS.items():
        where = ", ".join(d["file"][:2] for d in docs if s in d["source"])
        lines.append(f"| {s} | {topic} | {where or '❌ none'} |")
    lines += ["", f"**Validation:** {'all checks passed' if not errors else 'FAILED: ' + '; '.join(errors)}."]

    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
