"""Task 22 follow-up: do more candidates and remembered rewordings raise the answer cache's hits without a wrong one?

Two changes to ``creditcoach.cache.answers.match`` (2026-11-12), measured on the 44 pairs of
``task22_confirm_band.py`` (22 rewordings, 22 look-alikes):

    #1 candidates   The ``CANDIDATES`` closest stored questions are tried in turn (at most ``MAX_CONFIRMS`` model
                    calls), not only the closest one.
    #2 remembered   A rewording the model confirms is kept as a phrasing of the stored question, so the next one only
                    has to come close to either, and asking it again needs no model call.

``task22_confirm_band.py`` puts each pair to the cache alone, one stored question and one asked, where neither change
can make a difference. So this is a session: one user, the 17 distinct stored questions stored first, then the 44
asked questions in a random order (3 orders). A miss is answered and stored, as in the app, so later questions can
match it. A hit is right if the stored question it matched asks the same thing (the same pair's stored question, or a
rewording of it stored earlier), and wrong otherwise; every wrong hit is listed, to be judged by hand.

The model's answer for a pair of questions is asked once and reused by every configuration and order, so the
configurations differ only in what they do with it.

A third change, ``SMALL_MODEL`` writing 3 rewordings of each newly stored question, was measured the same way and not
adopted: no more hits (19 of 22 either way), one more paid call per stored answer, and the one rewording out of reach
("How much of my card limit am I using right now?", 0.562) only rose to 0.581, as the rewordings kept the stored
question's words (docs/caching.md §3).

Run (needs OPENROUTER_API_KEY; about 150 confirmation calls to SMALL_MODEL, under $0.02):
    uv run python scripts/task22_cache_recall.py
"""

import importlib.util
import random

from creditcoach import config
from creditcoach.cache import answers
from creditcoach.rag.retrieve import embed, normalize_query

ORDERS = (1, 2, 3)  # random seeds for the session's question order
CONFIGS = [  # (name, candidates, max confirms, remember confirmed rewordings)
    ("Before (closest only)", 1, 1, False),
    ("#1 top-3 candidates", answers.CANDIDATES, answers.MAX_CONFIRMS, False),
    ("#1 + #2 remembered rewordings (now)", answers.CANDIDATES, answers.MAX_CONFIRMS, True),
]

_confirmed: dict[tuple[str, str], bool] = {}
calls = {"confirm": 0}
_real_confirm = answers.confirm


def confirm(asked: str, stored: str) -> bool:
    """The model's answer, asked once per pair; every use is still counted as a call the app would make."""
    calls["confirm"] += 1
    if (asked, stored) not in _confirmed:
        _confirmed[asked, stored] = _real_confirm(asked, stored)
    return _confirmed[asked, stored]


def vector(question: str) -> list[float]:
    return embed(normalize_query(question))  # as agent.pipeline embeds it, years already resolved


def band_module():
    spec = importlib.util.spec_from_file_location("band", config.ROOT / "scripts" / "task22_confirm_band.py")
    band = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(band)
    return band


def entry(question: str, cluster: str) -> dict:
    resolved = answers.resolve(question)
    return {"key": f"{cluster}|{question}", "question": question, "resolved": resolved, "plain": answers.plain(resolved),
            "embedding": vector(resolved), "cluster": cluster, "phrasings": []}


def run(asked: list[tuple[str, str, str]], stored: list[tuple[str, str]], candidates: int, max_confirms: int,
        remember: bool) -> dict:
    """``asked`` is (question, its cluster, kind); ``stored`` is (question, cluster) stored beforehand."""
    answers.CANDIDATES, answers.MAX_CONFIRMS = candidates, max_confirms
    entries = [entry(q, c) for q, c in stored]
    before = calls["confirm"]
    out = {"rewording": 0, "look-alike": 0, "right": 0, "wrong": [], "asked": len(asked)}
    for question, cluster, kind in asked:
        resolved = answers.resolve(question)
        embedding = vector(resolved)
        found, how, _ = answers.match(resolved, embedding, entries)
        if found is None:
            if not any(e["plain"] == answers.plain(resolved) for e in entries):
                entries.append(entry(question, cluster))  # answered live, then stored
            continue
        if found["cluster"] == cluster:
            out["right"] += 1
            out[kind] += kind == "rewording"
        else:
            out[kind] += kind == "look-alike"
            out["wrong"].append((question, found["question"], how))
        if remember and how == "model-confirmed":
            phrasing = {"text": resolved, "embedding": embedding}
            found["phrasings"] = (found["phrasings"] + [phrasing])[-answers.MAX_PHRASINGS:]
    out["confirms"] = calls["confirm"] - before
    return out


def main() -> None:
    answers.confirm = confirm
    band = band_module()
    same, diff = band.task23_pairs()
    same, diff = same + band.REWORDINGS, diff + band.LOOK_ALIKES
    # a look-alike's stored question is the same as a rewording's when the text is: cluster by stored question
    pairs = [(s, a, "rewording") for s, a in same] + [(s, a, "look-alike") for s, a in diff]
    cluster_of = {answers.plain(answers.resolve(s)): f"C{i}" for i, s in enumerate(dict.fromkeys(s for s, _, _ in pairs))}

    def cluster(stored: str, question: str, kind: str) -> str:  # an asked question that is a stored one is that one
        return cluster_of.get(answers.plain(answers.resolve(question))) or (
            cluster_of[answers.plain(answers.resolve(stored))] if kind == "rewording" else f"L|{question}")
    asked = [(a, cluster(s, a, kind), kind) for s, a, kind in pairs]
    stored = [(s, cluster_of[answers.plain(answers.resolve(s))]) for s in dict.fromkeys(s for s, _, _ in pairs)]
    print(f"{len(same)} rewordings, {len(diff)} look-alikes; {len(stored)} questions stored, then {len(asked)} asked "
          f"in {len(ORDERS)} random orders\n")
    print("| | Rewordings that hit (right) | Look-alikes that hit (wrong) | Wrong hits of any kind | Model calls per question |")
    print("|---|---|---|---|---|")
    wrongs = []
    for name, *setting in CONFIGS:
        runs = []
        for seed in ORDERS:
            order = asked[:]
            random.Random(seed).shuffle(order)
            runs.append(run(order, stored, *setting))
        rewording = [r["rewording"] for r in runs]
        look = [r["look-alike"] for r in runs]
        wrong = [len(r["wrong"]) for r in runs]
        wrongs += [(name, *w) for r in runs for w in r["wrong"]]
        print(f"| {name} | {'–'.join(map(str, sorted(set(rewording))))} of {len(same)} | "
              f"{'–'.join(map(str, sorted(set(look))))} of {len(diff)} | {'–'.join(map(str, sorted(set(wrong))))} | "
              f"{sum(r['confirms'] for r in runs) / sum(r['asked'] for r in runs):.2f} |")
    if wrongs:
        print("\n| Configuration | Asked | Matched | How |\n|---|---|---|---|")
        for name, q, matched, how in dict.fromkeys(wrongs):
            print(f"| {name} | {q} | {matched} | {how} |")


if __name__ == "__main__":
    main()
