# Task 22 Follow-up: Trying the 3 Closest Stored Questions, and Remembering Confirmed Rewordings

*2026-11-12 · Code: `creditcoach/cache/answers.py` (`match`, `closeness`, `add_phrasings`) · Design: [docs/caching.md](../../caching.md) §3 · Tests: `tests/test_cache.py` · Script: `uv run python scripts/task22_cache_recall.py`*

## What changed

| | Before | Now |
|---|---|---|
| Stored questions the model check may look at | The closest one only | The 3 closest (`CANDIDATES`), with at most 2 model calls (`MAX_CONFIRMS`) |
| A rewording the model confirmed | Forgotten | Kept with the stored question (up to 8, `MAX_PHRASINGS`): asking it again is an exact or same-words match with no model call, and the next rewording only has to come close to either |

The vetoes and the model still compare with the stored question itself, never with a remembered rewording: the stored answer answers that question.

## How it was measured

`scripts/task22_confirm_band.py` puts each pair to the cache alone, one stored question and one asked, where neither change can make a difference. So this is a session: one user, the 17 distinct stored questions of its 44 pairs stored first, then its 44 asked questions (22 rewordings, 22 look-alikes) in 3 random orders. A miss is answered and stored, as in the app. A hit is right if the stored question it matched asks the same thing, and listed below otherwise. The model's answer for each pair of questions is asked once per run and reused by every configuration.

## Results

Two runs, a few hours apart (the model answers a few borderline pairs differently from run to run):

| | Rewordings that hit (right), run 1 | Run 2 | Hits listed as wrong | Model calls per question |
|---|---|---|---|---|
| Before (closest only) | 17 of 22 | 17 of 22 | 1–3 | 0.67 |
| #1 the 3 closest | 19 of 22 | 18 of 22 | 2–4 | 0.86–0.89 |
| **#1 + #2 remembered rewordings (now)** | **19 of 22** | **18 of 22** | 2–4 | **0.83–0.86** |

Trying the 3 closest finds rewordings the closest-only rule missed because a look-alike stood closer and was vetoed or refused. Remembering them gave no further hit on these questions (few of them are a third rewording of the same thing) and saved a few model calls.

## The hits listed as wrong, judged by hand

| Asked | Matched | Seen | Judgement |
|---|---|---|---|
| What accounts a good credit score ? | What counts towards a good credit score? | Now only | **Right.** A tester's "what accounts *for* a good credit score": the same question. Before, the closest stored question was another one, which the model refused |
| How do I get a great credit score? | How do I improve my credit score? | Before and now | Right: both ask how to raise a score |
| Is 840 by December 2027 realistic? | Will I hit 840 by December 2027? | Before and now | Right: both ask whether the goal is reachable |
| What qualifies as a great credit score? | What counts towards a good credit score? | Before and now, run 2 only | **Wrong.** One asks for a score range, the other for the factors. The model confirmed it in one run of two |

So the change adds no wrong hit. The one real wrong hit is the model check's, and it was there before: the pair benchmark never asks it, as it compares a rewording only with its own stored question, never with a neighbour. It is open question 7 in [caching.md](../../caching.md) §6.

## Tried and not adopted: written rewordings

`SMALL_MODEL` wrote 3 rewordings of each newly stored question (159 kept for 59 questions), matched as if they had been asked. In run 1: **no more hits** (19 of 22 with or without them), on both the session and the pairs, and more model calls (0.92 per question, plus one paid call per stored answer). They raised similarity for questions already within reach of the model (0.852 to 0.984 for "What can I do to raise my credit score?") but not for the one out of reach: "How much of my card limit am I using right now?" rose from 0.562 only to 0.581 against "What's my current credit utilization ratio?", as the rewordings kept the stored question's words ("How high is my current credit utilization ratio?").

## Tests

4 new tests in `tests/test_cache.py` (64 in all): a vetoed or refused closest question doesn't hide the next one; one lookup asks the model at most twice; a remembered rewording brings the next one in reach while the model still judges the original; a confirmed rewording is remembered once and needs no model call when asked again. 883 tests in all pass.
