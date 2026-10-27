# Task 30 Evidence: Fixes and Re-run

*2026-10-27 · Before: [eval-baseline.md](eval-baseline.md) · After: [eval-after-fixes.md](eval-after-fixes.md) · Before/after report: [eval-baseline-vs-after-fixes.md](eval-baseline-vs-after-fixes.md)*

**Definition of Done:** the score improves measurably over baseline after the fixes.

**Evidence of Completion:** before/after eval report showing the score delta.

**Result: ✅ PASS. 36 → 45 of 50 cases (72 % → 90 %).** Like for like, on the 41 cases whose measurement didn't change, **33 → 36 (+3)**. The other +6 come from cases whose measurement was corrected, reported separately below. Repeated runs showed the like-for-like gain is real for the cases the fixes targeted, and that single-run numbers swing by several cases on unstable questions.

## The score

| | Cases | Before (baseline) | After the fixes | Change |
|---|---|---|---|---|
| **Like for like** (measurement unchanged) | 41 | 33 (80 %) | 36 (88 %) | **+3** |
| Measurement changed (goal stored first; two checks corrected) | 9 | 3 (33 %) | 9 (100 %) | +6 |
| **All** | **50** | **36 (72 %)** | **45 (90 %)** | **+9** |

| | Before | After |
|---|---|---|
| Cases passing *expected* (automatic checks) | 44 | 48 |
| Cases passing *judge* | 39 | 45 |
| Cases passing *run* (no crash, main model, not blocked) | 49 | **50** |
| Judge averages (grounded, clear) | 4.82, 4.92 | 4.98, 4.98 |

Both runs: all 50 requirements.md queries against the synthetic data (13 users), cache off, the same harness. Re-scoring the baseline's saved answers with today's checks moves it from 36 to 37 (#41's check), so changed checks alone account for +1 of the +9.

## The three fixes (Task 29's top 3), each checked on the case that showed it

| # | Fix | What changed | Checked |
|---|---|---|---|
| 1 | **The G1 wording reviewer no longer reads the user's own goal as a prediction** (§3 #3, #5) | The review prompt names the user's own goal, target or date ("You're aiming for 720 by next year to buy a car") and the gap to it ("about 70 points to go") as not predictions. A first verdict that flags something is checked again with more reasoning (`low` instead of `minimal`), and acted on only if both agree. Clean answers make one call, as before ([checks.py](../../../creditcoach/guardrails/checks.py)) | On #3's two blocked drafts, from its baseline trace: flagged **10 of 10** times before, **0 of 10** after. Four drafts that do predict (a date, a points gain, "should hit 700 within six months", "expect 25 points next month") were still flagged **20 of 20**. In the re-run, §3 #3 and #5 pass, and the guardrail layer blocked nothing (*run* 50 of 50) |
| 2 | **Data-aware retrieval** (#9, #11, #27) | Besides the question, retrieval searches on what the user's own data says the question is about: the factor of a month the question names, the factors behind the last two falls for a "why did it drop" question, and the interest content when paying down a loan while a card carries a balance. At most 2 passages are added ([rag/personal.py](../../../creditcoach/rag/personal.py)). 9 of the 50 queries get an extra search; the other 41 retrieve exactly as before | No model call needed: #11 now retrieves `factor-payment-history#00` (the −60 to −110 impact), #27 `minimum-due-and-interest#02`, #9 `factor-hard-inquiries#00`. In the re-run **#11 and #27 pass**. #9 still fails: its missing advice ("apply within a short window") is in the car-loan passage, which the hard-inquiry search doesn't reach |
| 3 | **No substitute figure for a month that isn't on file** (#46) | The system prompt's rule for `PERIOD_OUT_OF_RANGE`: give the range of months on file, never another month's score in its place | Asked 3 times: each answer said January 2025 isn't on file, gave the range, and stated **no score**. #46 passes in the re-run |

## Measurement fixes (reported apart, so they don't inflate the agent's score)

| Change | Cases | Why |
|---|---|---|
| The goal each row assumes is stored first, in a first session, each case in its own memory | #23, #25, #36, #37, #38, #39, #40 | These ran with no memory in the baseline (Task 29: 5 of the 14 failures were this). The judge is also shown that stored goal, as the agent is: without it, #39's judge called the stored 720 "invented" |
| #41's check also accepts "within a cycle" and "statement date" | #41 | The answer made the point; the check only accepted exact phrases |
| §3 #2's "Does not estimate" no longer fires on the general "about 30%" guideline | §3 #2 | Found in the re-run: the answer gave 37.4 % exactly and quoted the 30 % guideline, and the check read the guideline as an estimate. It still catches "about 37%" |

## Was the improvement real, or noise?

Each answer is a fresh GPT-5 answer, so one run can land on either side of a borderline check. Three things were checked.

**1. The cases that went from pass to fail.** In the re-run, §4 #12, #15, #21 and #28 passed in the baseline and failed after the fixes. The fixes didn't reach three of them: same passages, no data search, guardrail passed. Each was run 3 more times on both code versions (the pre-fix code checked out from `main`):

| | #12 | #15 | #21 | #28 | Total |
|---|---|---|---|---|---|
| Before the fixes | 0 of 3 | 1 of 3 | 0 of 3 | 1 of 3 | **2 of 12** |
| After the fixes | 1 of 3 | 1 of 3 | 1 of 3 | 1 of 3 | **4 of 12** |

They are not regressions. These four are unstable under both versions and fail more often than they pass: the baseline happened to catch them on good runs. They are real weaknesses (generation gaps: a credit-counselling suggestion, a line about loans not counting toward utilization, a payment-plan suggestion, a goal the user didn't set), now first in line for the next round.

**2. The judge.** Judging the re-run's answers a second time changed only one verdict, #39, which is the judge-input fix above. The baseline's two judgings differed on 6 verdicts.

**3. The cases that changed to pass.** #9, #11, #16, #22, #27 and #46 were each run 3 times on both code versions **at the same time**, so both saw the same model speed. (A first attempt was cut short when the OpenRouter key reached its $9 limit and every call returned 403; that batch was discarded and run again after the limit was raised.)

| Case | Before the fixes | After the fixes | Reading |
|---|---|---|---|
| #11 | 0 of 3 | **3 of 3** | Fixed by data-aware retrieval, reliably |
| #46 | 1 of 3 | **3 of 3** | Fixed by the out-of-range rule, reliably |
| #16 | 3 of 3 | 3 of 3 | Passes reliably either way: its baseline failure was chance |
| #27 | 3 of 3 | 2 of 3 | The same: the fix wasn't needed |
| #22 | 1 of 3 | 1 of 3 | Unstable either way |
| #9 | 2 of 3 | **0 of 3**, then **3 of 5** after the library fix below | Made worse by data-aware retrieval, then fixed in the library |
| **Total** | **10 of 18** | **12 of 18** | |
| Median time per answer | 18.1 s | 18.7 s | Run together, the fixes cost no noticeable time |

**#9: a regression found and fixed.** Data-aware retrieval now reliably adds the hard-inquiry passage for #9. That passage said to avoid other applications before a big loan, and never that, once you are shopping for the loan, the applications should go in within a short window. That advice was only in the car-loan document. So the answer said "hold off", the opposite of what requirements.md expects. The library contradicted itself: the hard-inquiry document's "What helps" list now also says to submit full applications within a short window when already shopping for the loan, in the car-loan document's words ([corpus/05-hard-inquiries.md](../../../corpus/05-hard-inquiries.md), rebuilt: still 45 chunks, every check passing). #9 then passed 3 of 5; both remaining failures are judge-only (it doesn't always link the dips to car-loan shopping).

So for the cases the fixes targeted: #11 and #46 went from mostly failing to always passing, and #9 went from failing to passing more often than not. Of the six cases that changed to pass in the re-run, #16 and #27 would have passed anyway, so the single-run like-for-like +3 is about right but rests partly on luck. The repeated runs are the firmer evidence.

## Latency

| | Baseline | After the fixes |
|---|---|---|
| Time per answer (median, longest) | 12.5 s, 35.5 s | 19.1 s, 50.6 s |
| GPT-5 output per answer | 828 tokens | 823 tokens |
| GPT-5 input per answer | 4,758 tokens | 4,936 tokens (+4 %: the added passages) |
| Time per GPT-5 call | 9.2 s (about 90 tokens/s) | 14.1 s (about 58 tokens/s) |
| Small-model calls in the run | 30 | 29 |

The answers got slower, but not because of the fixes. GPT-5 wrote the same amount and took 50 % longer per call: the provider was slower during the re-run. The fixes added 4 % to the prompt and no small-model calls. Confirmed by running both code versions at the same time on six cases: median 18.1 s before the fixes, 18.7 s after. Fix 1 removes the worst case, a guardrail block or rewrite (*run* 50 of 50 after, 49 before). **Latency should only be compared between runs made close together in time.** The latency fix Task 29 recommended trying, a lower reasoning effort, was tried next.

## Reasoning-effort trial

Task 29 found GPT-5's own writing time is about three quarters of each answer, and `REASONING_EFFORT=minimal` looked faster on three questions. So all 50 cases were run twice **at the same time**, once at `minimal` and once at the current `low`, with the fixes above in both. Only the answering model's effort changed: the judge, the guardrail review and the cache check set their own. Reports: [eval-effort-low.md](eval-effort-low.md), [eval-effort-minimal.md](eval-effort-minimal.md).

| | `low` (current) | `minimal` |
|---|---|---|
| Cases passing | **43 of 50** | 39 of 50 |
| Time per answer (median, 90th percentile, longest) | 20.4 s, 32.1 s, 48.2 s | **12.3 s, 19.6 s, 35.3 s** |
| Time per GPT-5 call (median) | 16.2 s | 9.2 s |
| GPT-5 output per call (mean, reasoning included) | 783 tokens | 361 tokens |
| GPT-5 cost for the 50 cases | $0.59 | $0.35 |
| Judge averages (grounded, clear) | 4.98, 4.98 | 4.90, 4.98 |

`minimal` failed 6 cases that `low` passed and passed 2 that `low` failed. The 6 are real losses, not borderline calls:

| Case | What `minimal` got wrong |
|---|---|
| §4 #8 | A misstated figure: May's drop as 684 → 676 instead of 682 → 676 |
| §4 #46 | Gave January 2026 in place of January 2025: the substitute month fix 3 removed |
| §4 #27 | Didn't say to pay the card in full first: the advice fix 2 retrieves |
| §4 #16, #24, #25 | Left out one expected point each (the per-card amount for ACC-01, keeping old cards open, asking to update the goal's date) |

The two it gained (#10, #28) are among the cases that pass about 1 run in 3 under either setting. **Decision: keep `low`.** `minimal` would take about 8 s off the median answer, but it writes half as much and drops exactly what the fixes added, plus one wrong figure. The latency goal needs another route, such as `minimal` only for plain lookups ("What's my credit score?"), checked the same way. Streaming the words as they are written doesn't fit as it stands, because the output guardrails check the whole draft before the user sees it.

The `low` run also shows the run-to-run spread: 43 of 50 here, 45 of 50 in the re-run, with the same code. #39 and #44 failed in both trial runs after passing in the re-run: #39's judge counted the user's own words ("by next year"), quoted beside the saved goal, as changing it; #44 left out free credit counselling, as #12 does.

## What still fails (5 of 50)

| Case | Category (Task 29) | Next step |
|---|---|---|
| §4 #9 | Retrieval miss (fixed after the re-run: the library fix above; now 3 of 5) | Linking the dips to car-loan shopping more consistently |
| §4 #12, #15, #21, #28 | Generation gaps, unstable (pass about 1 in 3 under both versions) | System-prompt guidance for each (suggest credit counselling when a card is very high; say loans don't count toward utilization; suggest a payment plan or EMI conversion; don't propose a goal the user didn't set), checked with repeated runs |

## Reproducing

```bash
uv run python -m creditcoach.evals --all --label after-fixes          # the re-run
uv run python -m creditcoach.evals --rejudge --label after-fixes      # judge the saved answers again
uv run python -m creditcoach.evals --compare baseline --label after-fixes   # the before/after report
```

## What changed

| File | Change |
|---|---|
| [creditcoach/guardrails/checks.py](../../../creditcoach/guardrails/checks.py) | Fix 1: the review prompt; the second opinion at `low` reasoning |
| [creditcoach/rag/personal.py](../../../creditcoach/rag/personal.py), [agent/pipeline.py](../../../creditcoach/agent/pipeline.py) | Fix 2: data-aware retrieval (`gather_passages`), recorded on the retrieval span as `retrieval.data_probes` |
| [creditcoach/prompts/system_prompt.md](../../../creditcoach/prompts/system_prompt.md) | Fix 3: no substitute month |
| [creditcoach/evals/harness.py](../../../creditcoach/evals/harness.py), [sample_rows.py](../../../creditcoach/evals/sample_rows.py), [golden_queries.json](../../../creditcoach/evals/golden_queries.json), [\_\_main\_\_.py](../../../creditcoach/evals/__main__.py) | Goals stored first (`GOAL_SEEDS`), and shown to the judge; the two corrected checks; `--compare` |
| [corpus/05-hard-inquiries.md](../../../corpus/05-hard-inquiries.md) | The shopping-window advice, so the library no longer contradicts itself (found by the repeated runs of #9) |
| Tests | [test_personal_retrieval.py](../../../tests/test_personal_retrieval.py) (13); [test_guardrails.py](../../../tests/test_guardrails.py), [test_eval_harness.py](../../../tests/test_eval_harness.py) (4 new) |

## Team sign-off

| Member | Reviewed | Date |
|---|---|---|
| Aman | [ ] | |
| Anil | [ ] | |
| Sudip | [ ] | |
