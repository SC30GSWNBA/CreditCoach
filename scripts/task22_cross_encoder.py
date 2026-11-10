"""Task 22 follow-up: would a cross-encoder decide better than cosine similarity which questions go to the model?

The answer cache compares two questions by the cosine of their embeddings, each made without seeing the other, and
puts them to ``SMALL_MODEL`` from ``CONFIRM_FROM`` (``ANCHORED_FROM`` for a score or year). A cross-encoder reads both
questions together, so each word can attend to the other question's words. This script scores the pairs of
``scripts/task22_confirm_band.py`` (rewordings and look-alikes, years written out as the cache does) both ways:

    AUC            How often a rewording scores above a look-alike (1.0: always; 0.5: chance), over all pairs and
                   over those no veto stops, which are the ones the score decides.
    As a filter    With a cut-off that lets every rewording through to the model, how many look-alikes go too
                   (each costs a SMALL_MODEL call, about 3 s; the model still refuses them).
    Speed          Milliseconds to score one pair, as a lookup would score each stored question.

No model calls, and no API key: everything runs locally (the cross-encoders download once, from Hugging Face).

Run:
    uv run python scripts/task22_cross_encoder.py

2026-11-10, 44 pairs (22 rewordings, 22 look-alikes):

    Method                                    AUC (no veto)   Look-alikes to the model   ms a pair
    cosine (the cache's)                      0.826           17 of 17                   1
    cross-encoder/stsb-roberta-base           0.933            6 of 17                   8
    cross-encoder/quora-distilroberta-base    0.930           17 of 17                   7
    cross-encoder/ms-marco-MiniLM-L-6-v2      0.727           17 of 17                   4

The STS cross-encoder separated them best, and would have sent the one rewording cosine can't reach to the model
("How much of my card limit am I using right now?", 0.562 by cosine, 0.655; the model says it is the same question).
Not adopted: its cut-off is fitted to these same pairs (the lowest rewording 0.655, the highest look-alike below it
0.654), neither cross-encoder is safe alone (look-alikes at 0.886 and 0.938), and RoBERTa-base adds about 500 MB to
the app for one more hit in 22. Re-run once real misses are added to the pairs (``scripts/cache_misses.py``).
"""

import importlib.util
import time

from sentence_transformers import CrossEncoder

from creditcoach import config
from creditcoach.cache import answers
from creditcoach.rag.retrieve import embed, normalize_query

CROSS_ENCODERS = ["cross-encoder/stsb-roberta-base", "cross-encoder/quora-distilroberta-base", config.RERANKER_MODEL]


def pairs() -> list[tuple[str, str, bool]]:
    """(stored, asked, is a rewording) for every pair of ``task22_confirm_band.py``, years written out."""
    spec = importlib.util.spec_from_file_location("band", config.ROOT / "scripts" / "task22_confirm_band.py")
    band = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(band)
    same, diff = band.task23_pairs()
    return ([(answers.resolve(a), answers.resolve(b), True) for a, b in same + band.REWORDINGS]
            + [(answers.resolve(a), answers.resolve(b), False) for a, b in diff + band.LOOK_ALIKES])


def cosine(ps: list) -> tuple[list[float], float]:
    t = time.perf_counter()
    scores = [answers.cosine(embed(normalize_query(a)), embed(normalize_query(b))) for a, b, _ in ps]
    return scores, (time.perf_counter() - t) / len(ps)


def cross(name: str, ps: list) -> tuple[list[float], float]:
    """Each pair scored both ways round and averaged (a cross-encoder's score depends on the order)."""
    model = CrossEncoder(name)
    model.predict([("warm", "up")])
    t = time.perf_counter()
    forward = [float(model.predict([(a, b)])[0]) for a, b, _ in ps]  # one pair at a time, as a lookup would
    seconds = (time.perf_counter() - t) / len(ps)
    return [(f + float(model.predict([(b, a)])[0])) / 2 for f, (a, b, _) in zip(forward, ps)], seconds


def auc(scores: list[float], labels: list[bool]) -> float:
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def main() -> None:
    ps = pairs()
    vetoed = [answers.veto(b, a) is not None for a, b, _ in ps]
    results = {"cosine (the cache's)": cosine(ps), **{name: cross(name, ps) for name in CROSS_ENCODERS}}
    print(f"{sum(p[2] for p in ps)} rewordings, {sum(not p[2] for p in ps)} look-alikes\n")
    print("| Method | AUC, all | AUC, no veto | Lowest rewording | Highest look-alike (no veto) | "
          "Look-alikes to the model | ms a pair |\n|---|---|---|---|---|---|---|")
    for name, (scores, seconds) in results.items():
        open_ = [i for i in range(len(ps)) if not vetoed[i]]
        lowest = min(scores[i] for i in range(len(ps)) if ps[i][2])
        neg = [scores[i] for i in open_ if not ps[i][2]]
        print(f"| {name} | {auc(scores, [p[2] for p in ps]):.3f} | "
              f"{auc([scores[i] for i in open_], [ps[i][2] for i in open_]):.3f} | {lowest:.3f} | {max(neg):.3f} | "
              f"{sum(s >= lowest for s in neg)} of {len(neg)} | {seconds * 1000:.0f} |")
    names = list(results)
    print("\n| Kind | Veto | " + " | ".join(names) + " | Stored | Asked |\n|" + "---|" * (len(names) + 4))
    for i in sorted(range(len(ps)), key=lambda i: (not ps[i][2], -results[names[1]][0][i])):
        a, b, same = ps[i]
        print(f"| {'rewording' if same else 'look-alike'} | {'yes' if vetoed[i] else '–'} | "
              + " | ".join(f"{results[n][0][i]:.3f}" for n in names) + f" | {a} | {b} |")


if __name__ == "__main__":
    main()
