# Task 28 Evidence: Baseline Eval Run

*Answers 2026-10-26 11:30, judged again 11:34 · `uv run python -m creditcoach.evals --all --label baseline`, then `--rejudge --label baseline` · Full report: [eval-baseline.md](eval-baseline.md) · Data: [runs/eval-baseline.json](runs/eval-baseline.json)*

**Definition of Done:** the suite runs successfully and produces a baseline score.

**Evidence of Completion:** saved baseline report (score, timestamp, per-case pass/fail).

**Result: ✅ PASS.** The full suite ran with no crash or harness error and produced a baseline.

## Baseline score

**36 of 50 cases pass (72%)**

| | Cases | Pass | Score |
|---|---|---|---|
| Sample queries (requirements.md §3) | 6 | 4 | 67% |
| Additional queries (§4) | 44 | 32 | 73% |
| of which depend on a stored goal or earlier turn this run doesn't set up (⚑) | 10 | 5 | 50% |
| **All** | **50** | **36** | **72%** |

| Scorer | Cases passing |
|---|---|
| expected (automatic checks against requirements.md) | 44 of 50 |
| figures (§4: every figure traced to the data) | 44 of 44 |
| judge (`gpt-5-mini`: meets expected, grounded ≥ 4, clear ≥ 3) | 39 of 50 |
| run (no crash, main model, not blocked) | 49 of 50 |

- **Judge averages:** grounded 4.82/5, clear 4.92/5.
- **Time per answer:** median 12.5 s, longest 35.5 s. Answering took 5.4 minutes.
- **Langfuse:** scores were sent for all 50 cases (tag `eval:baseline`).

**The data.** The 50 queries ran against the synthetic dataset as 13 of its 15 users (USR-001 to USR-013), each query signed in as the user requirements.md names. Answers came from `openai/gpt-5` with retrieval, both tools over MCP, memory (§3) and the guardrail layer on. The cache was off and memory went to a temporary folder.

## A harness fix before the baseline was recorded

The first judging gave 35 of 50. One failure was the harness's fault, not the agent's. The judge failed §4 #24 (grounded 3/5) for using the user's first name and saying they have a 6+ month emergency fund. Both come from the user's profile, which the agent is given, but the §4 judge was shown only the passages and tool results. (The §3 judge already saw the profile.)

The fix gives the §4 judge the profile too, plus a regression test, and adds `--rejudge`, which judges the saved answers again without asking for new ones. The answers above are exactly the ones from 11:30; only the judging was redone.

**The judge varies.** Between the two judgings, 6 verdicts changed, and the profile is the stated reason only for #24:

| | Cases |
|---|---|
| Judge fail → pass | #24 (the fix), #10, #21, #46 |
| Judge pass → fail | #9, #23 |

That puts about 5 of 50 verdicts near the judge's line on identical answers. Task 29 should treat a judge-only failure as weaker evidence than a failed automatic check, and Task 30 should judge each answer more than once before counting a change as an improvement.

## Per-case pass/fail

| Result | Cases |
|---|---|
| ✅ Pass (36) | §3 #1, #2, #4, #6 · §4 #7, #8, #10, #12, #13, #14, #15, #17, #18, #19, #20, #21, #24, #26, #28, #29, #30, #31, #32, #33, #34, #35 ⚑, #39 ⚑, #40 ⚑, #42, #43, #44, #45 ⚑, #47 ⚑, #48, #49, #50 |
| ❌ Fail (14) | §3 #3, #5 · §4 #9, #11, #16, #22, #23 ⚑, #25 ⚑, #27, #36 ⚑, #37 ⚑, #38 ⚑, #41, #46 |

What failed, in the scorers' own words (Task 29 categorizes these and finds the root causes):

| Case | Scorers failed | What they reported |
|---|---|---|
| §3 #3 | expected, judge, run | The guardrail layer **blocked** the answer. Its trace shows the wording review (G1) read "You're aiming for 720 next year… about 70 points to go" as a score prediction, and the rewrite still tripped it, so the user got the generic "I can't promise a score" reply with no plan. It passed in Task 24 and in the Task 27 first run. |
| §3 #5 | expected | Follows from #3: its last check is "a later session uses the goal", settled by #3. The goal itself was stored correctly (720, 2027, buy a car). |
| §4 #9 | judge | Advises holding off on applications rather than grouping the remaining ones into a short shopping window. |
| §4 #11 | expected, judge | Omits the library's typical impact of a 30+ day late payment (−60 to −110) and how long it lasts. |
| §4 #16 | judge | Gives the overall paydown (₹14,750) but not the ₹36,500 that would take ACC-01 itself under 30%. |
| §4 #22 | judge | States March's score (678) without the change (+5) and its reason (on-time payments). |
| §4 #23 ⚑ | judge | Doesn't recall the two recent hard inquiries or say there are no late payments. Depends on stored facts this run doesn't set up. |
| §4 #25 ⚑ | expected, judge | Doesn't call the shorter timeline ambitious, or ask whether to update the stored target date. No goal was stored in this run. |
| §4 #27 | judge | Puts loan prepayment ahead of paying the card in full. |
| §4 #36 ⚑ | judge | Doesn't recall the goal from #35 (850). That goal was never stored in this run. |
| §4 #37 ⚑ | judge | Doesn't refer to the stored car goal. That goal was never stored in this run. |
| §4 #38 ⚑ | judge | Asks for a target date instead of keeping the stored one. No goal was stored in this run. |
| §4 #41 | expected | Doesn't say when the change would show (next reporting or statement cycle). |
| §4 #46 | expected | Asked for a month outside the data, it correctly says so but then offers October 2025's score (662), which the expected behavior rules out. |

Five of the ten ⚑ cases failed (#23, #25, #36, #37, #38), each on information that a stored goal or an earlier session would hold. That is the setup this run doesn't do.

## Compared with earlier runs

The 6 sample rows passed 6 of 6 in Task 24 and in the Task 27 first run, but 4 of 6 here. The difference is §3 #3: the same wording check passed the earlier answers and blocked this one. Each run gets a fresh GPT-5 answer, so a single run can land on either side of a borderline check. Task 30's re-run should repeat the sample rows a few times before counting a change in them as an improvement.

## Reproducing

```bash
uv run python -m creditcoach.evals --all --label baseline       # a new baseline (overwrites this one)
uv run python -m creditcoach.evals --rescore --label baseline   # re-score with the current checks, no model calls
uv run python -m creditcoach.evals --rejudge --label baseline   # judge the saved answers again (50 small-model calls)
```

Task 30 runs the same command with `--label after-fixes` and compares against [runs/eval-baseline.json](runs/eval-baseline.json).

## What changed

| File | Change |
|---|---|
| [creditcoach/evals/harness.py](../../../creditcoach/evals/harness.py) | The §4 judge sees the user's profile; `--rejudge`; the count of flagged §4 queries corrected to ten (the golden `needs` list has 12, but #3 and #5 are §3 rows the harness sets up) |
| [creditcoach/evals/\_\_main\_\_.py](../../../creditcoach/evals/__main__.py) | `--rejudge` |
| [creditcoach/observability.py](../../../creditcoach/observability.py) | A Langfuse score's id is its trace and name, so judging again replaces the score rather than adding a second one |
| [tests/test_eval_harness.py](../../../tests/test_eval_harness.py) | 2 new tests: the §4 judge sees the profile (the #24 case), and `--rejudge` replaces saved verdicts while `--rescore` keeps them |

## Team sign-off

| Member | Reviewed | Date |
|---|---|---|
| Aman | [ ] | |
| Anil | [ ] | |
| Sudip | [ ] | |
