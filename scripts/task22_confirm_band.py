"""Task 22 follow-up: from what similarity should the answer cache ask the model whether two questions are the same?

Found on the Railway deployment (2026-10-27): true rewordings such as "How do I improve my credit score?" and "What
can I do to raise my credit score?" score 0.852, below the 0.90 the model check needed, so they always missed. This
script measures, for 28 question pairs, what ``creditcoach.cache.answers.match`` decides when the model check starts
at 0.90, 0.85, 0.80 or 0.75:

    rewordings   15 pairs that ask for exactly the same thing (Task 23's 10, plus 5 more): a hit saves an answer
    look-alikes  13 pairs that look alike but differ (Task 23's 5, plus 8 more, including questions a tester asked on
                 Railway): a hit would be a wrong answer

Each pair runs the real checks (exact, the vetoes on numbers, negation and time words, the same-words rule) and, where
the decision depends on it, the real ``SMALL_MODEL`` confirmation.

Run (needs OPENROUTER_API_KEY; about 20 SMALL_MODEL calls):
    uv run python scripts/task22_confirm_band.py

2026-10-29: 3 rewordings and 3 look-alikes added around "What is a good credit score?", after a tester's "What
qualifies as a great credit score?" missed on Railway (0.871, refused by the model each time).
"""

import importlib.util

from creditcoach import config
from creditcoach.cache import answers
from creditcoach.evals import golden
from creditcoach.rag.retrieve import embed

LOWEST = 0.70  # the model isn't asked below this, whatever the band

REWORDINGS = [
    ("How do I improve my credit score?", "What can I do to raise my credit score?"),
    ("How do I improve my credit score?", "What's the best way to boost my credit score?"),
    ("How do I improve my credit score?", "Tips to improve my credit score?"),
    ("What's my current credit utilization ratio?", "How much of my card limit am I using right now?"),
    ("What counts towards a good credit score?", "What makes up a credit score?"),
    ("What is a good credit score?", "What qualifies as a great credit score?"),           # Railway, 2026-10-28
    ("What is a good credit score?", "What sounds like a great credit score?"),
    ("What is a good credit score?", "Which credit score is considered good?"),
]
LOOK_ALIKES = [
    ("What is the best way to improve a credit score, and what is the safe credit score to get a home loan",
     "How do I improve my credit score ?"),
    ("How do I improve my credit score ?", "What accounts a good credit score ?"),
    ("How do I improve my credit score?", "How do I improve my credit score for a home loan?"),
    ("How do I improve my credit score?", "What hurts my credit score?"),
    ("How do I improve my credit score?", "How long does it take to improve my credit score?"),
    ("How do I improve my credit score?", "How do I improve my credit utilization?"),
    ("What's my current credit utilization ratio?", "What should my credit utilization ratio be?"),
    ("Should I take out this payday loan to pay off my credit card?",
     "Should I take a personal loan to pay off my credit card?"),
    ("What is a good credit score?", "What is my credit score?"),
    ("What is a good credit score?", "What credit score do I need for a home loan?"),
    ("What is a good credit score?", "How do I get a great credit score?"),
]


def task23_pairs() -> tuple[list, list]:
    """Task 23's rewordings and look-alikes, each against its requirements.md question."""
    spec = importlib.util.spec_from_file_location("task23", config.ROOT / "scripts" / "task23_cache_latency.py")
    t23 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(t23)
    q = golden.by_id()
    return ([(q[i].query, t23.REWORDED[i]) for i in t23.BASE],
            [(q[i].query, text) for i, text in t23.LOOK_ALIKE.items()])


def measure(stored: str, asked: str) -> dict:
    sim = answers.cosine(embed(stored), embed(asked))
    vetoed = answers.veto(asked, stored)
    exact = answers.plain(asked) == answers.plain(stored)
    same_words = sim >= answers.THRESHOLD and answers.words(asked) == answers.words(stored)
    ask = not (exact or vetoed or same_words) and sim >= LOWEST
    return {"stored": stored, "asked": asked, "sim": sim, "veto": vetoed, "exact": exact, "same_words": same_words,
            "confirmed": answers.confirm(asked, stored) if ask else None}


def hit(m: dict, band: float) -> bool:
    """What ``match`` decides when the model check starts at ``band``."""
    if m["exact"] or (not m["veto"] and m["same_words"]):
        return True
    return not m["veto"] and m["sim"] >= band and bool(m["confirmed"])


def main() -> None:
    same, diff = task23_pairs()
    same, diff = [measure(*p) for p in same + REWORDINGS], [measure(*p) for p in diff + LOOK_ALIKES]
    print(f"{len(same)} rewordings, {len(diff)} look-alikes\n")
    print("| Model check from | Rewordings that hit | Look-alikes that hit (wrong) |")
    print("|---|---|---|")
    for band in (0.90, 0.85, 0.80, 0.75):
        wrong = [m for m in diff if hit(m, band)]
        print(f"| {band:.2f}{' (now)' if band == answers.CONFIRM_FROM else ''} | {sum(hit(m, band) for m in same)} of "
              f"{len(same)} | {len(wrong)} of {len(diff)} |")
    print("\n| Kind | Similarity | Veto | Model says same | Stored | Asked |\n|---|---|---|---|---|---|")
    for kind, ms in (("rewording", same), ("look-alike", diff)):
        for m in sorted(ms, key=lambda m: -m["sim"]):
            print(f"| {kind} | {m['sim']:.3f} | {m['veto'] or '–'} | "
                  f"{'–' if m['confirmed'] is None else 'yes' if m['confirmed'] else 'no'} | {m['stored']} | {m['asked']} |")


if __name__ == "__main__":
    main()
