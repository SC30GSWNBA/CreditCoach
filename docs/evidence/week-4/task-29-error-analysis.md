# Task 29 Evidence: Error Analysis

*2026-10-27 · Input: the [Task 28 baseline](task-28-baseline.md) (36 of 50 pass), each failing case's answer, retrieved passages, tool results, guardrail decision and trace, and the first tester session on the Railway deployment*

**Definition of Done:** every failing case is categorized (retrieval miss, tool error, guardrail miss, fabricated figure, latency) with a root cause and prioritized fix.

**Evidence of Completion:** error-analysis table committed.

**Result: ✅ PASS.** All 14 failing cases are categorized, each with a root cause traced to the evidence (not to the judge's one-line reason) and a fix. The top 3 fixes are picked below, for Task 30.

## How each case was analyzed

The judge's reason says *what* is missing ("omits the −60 to −110 figure"). The root cause is *why*, and was found by checking where the missing fact lives:

1. **Is the fact in the user's data or in the corpus?** The tool results are in the run file; the corpus chunks are in the vector store.
2. **If the corpus has it, was a passage holding it retrieved?** If not, it's a retrieval miss. Retrieval was then re-run with 12 candidates to see how far down the passage ranked, which decides the fix.
3. **If the answer had the fact (in a passage or the tool data) and left it out,** it's a generation gap.
4. **For a guardrail action,** the trace holds each draft and the reviewer's verdict with the sentence it flagged.
5. **If the agent did what was expected,** the check or the run setup is at fault, not the agent.

Two categories were added to the five in tasks.md, because some failures fit none of them: **generation gap** (the fact was available and left out) and **eval setup** (the harness or a check, not the agent).

## Error-analysis table

| Case | Category | What happened | Root cause (evidence) | Fix | Priority |
|---|---|---|---|---|---|
| §3 #3 | **Guardrail** (false positive: over-block) | The user asked for a 12-month car plan and got only the generic "I can't promise a score" message | The G1 wording reviewer (`gpt-5-mini`) flagged "You're aiming for 720 by next year to buy a car", which **restates the user's own stored goal**. Both review calls agreed, so the draft was rewritten. The rewrite restated the goal again and was flagged again, so the answer was blocked. The review prompt exempts "the gap to the user's goal" but not the goal itself, which nearly every goal-aware answer restates. Earlier runs passed because their wording differed | Review prompt: restating the user's own goal, target or target date is not a prediction. Add #3's two drafts as regression cases | **1** |
| §3 #5 | Guardrail (follows from #3) | The goal was stored correctly (720, 2027, buy a car) | Its last check, "a later session uses the goal", is settled by #3, which was blocked | Same as #3 | **1** |
| §4 #9 | **Retrieval miss** | Gave the right drops (−9, −2, hard inquiries) but advised "hold off" rather than grouping the remaining applications in a short window | The "short window" advice is only in `planning-for-a-car-loan#02`, which isn't in the top 12 for this question. `factor-hard-inquiries#00` was at rank 5, outside the 3 kept. The question never says "inquiry"; that word is only in the user's score history ("Hard inquiry" in Aug and Sep) | **Data-aware retrieval:** also search on the factor labels in the user's own score history ("Hard inquiry" ranks `factor-hard-inquiries` 1st) | **2** |
| §4 #11 | **Retrieval miss** | Reported the −82 April drop and the recovery, but not the typical impact (−60 to −110, up to 7 years, fades in about 2 years) | Those figures are in `factor-payment-history#00` and `score-impact-reference#01`; neither is in the top 12 for "Why did my score crash in April…". "Late payment" is only in the tool data ("Late payment (30+ days)"), and searching on that label ranks `factor-payment-history#00` 1st | Data-aware retrieval, as #9 | **2** |
| §4 #27 | **Retrieval miss** | Put loan prepayment ahead of paying the card in full | "Pay the card in full first, because a carried balance costs interest" is in `minimum-due-and-interest`, ranked 8th for the question. The user's account data shows the carried card balance (₹66,000); searching on it ranks `minimum-due-and-interest#01` 1st | Data-aware retrieval: a carried card balance also searches the interest content | **2** |
| §4 #46 | **Fabricated figure** (a substitute) and guardrail miss | Correctly said January 2025 isn't on file, then offered "October 2025: 662" in its place | The tool returned `PERIOD_OUT_OF_RANGE` correctly. The system prompt's rule for that error says "give the months you do have", and the model went one step further and gave a month's score. G3 can't catch it, because 662 is real data, just not for the month asked | System prompt: give the range of months on file, never another month's figure in place of the one asked. Regression test on the rule | **3** |
| §4 #16 | **Generation gap** | Gave the overall paydown (₹14,750) but not that ACC-01 alone needs ₹36,500 | Both figures follow from the tool data (₹59,000 on ₹75,000; 30% is ₹22,500). The model answered "overall" literally and skipped the per-card view | System prompt: for a utilization target, also give the paydown for any single card over it | 4 |
| §4 #22 | Generation gap | "678 in March", without the change or the reason | The tool returned +5 and "On-time payments" for 2026-03; the model gave only the score | System prompt: a single month's score comes with its change and reason | 4 |
| §4 #23 ⚑ | Eval setup, and a generation gap | Didn't recall the car goal; also didn't name the two recent inquiries or say there are no late payments | The harness doesn't store this user's car goal before asking. The inquiries and the clean payment record are in the tool data, so leaving them out is a generation gap | Harness: seed the stored goal for the §4 memory queries (and report that change separately) | 5 |
| §4 #25 ⚑ | Eval setup, and a generation gap | Didn't call 70 points in 6 months "ambitious", or ask before changing the stored date | No goal was stored in this run, so there was no date to ask about. "Ambitious" follows from the data (650 → 720 in 6 months) | Harness: seed the goal. Prompt: say plainly when a timeline is tight | 5 |
| §4 #36 ⚑ | **Eval setup** | Didn't compare 841 with the 850 target | #35 stores that goal, but the harness runs each §4 query alone with empty memory | Harness: run #35 then #36 in two sessions, as §3 runs #5 then #3 | 5 |
| §4 #37 ⚑ | Eval setup | Didn't refer to the car goal | No goal stored in this run | Harness: seed the goal | 5 |
| §4 #38 ⚑ | Eval setup | Asked for a target date instead of keeping the stored one | No goal stored in this run, so there was no date to keep | Harness: seed the goal | 5 |
| §4 #41 | **Eval setup** (the check) | The check said "reporting cycle" was missing | The answer says scores recover "within a cycle" if you pay "before the statement date", which makes the point; the check only accepted exact phrases such as "next cycle". The judge passed it. *Side note:* it quotes the corpus's "typically 10–40 points" in reply to "how many points will I gain?". It is labelled typical, which G1 allows, but it is close to the line | Golden check: accept "cycle" and "statement date" | 5 |

⚑ = depends on a stored goal or an earlier turn that the baseline run doesn't set up.

## By category

| Category | Cases | Agent or eval? | Users affected |
|---|---|---|---|
| Retrieval miss | 3 (#9, #11, #27) | Agent | Answers miss the library's key fact: the typical impact, the shopping window, which debt to pay first |
| Guardrail false positive (over-block) | 2 (§3 #3, #5) | Agent | A goal-aware question gets a generic refusal and no plan. It also doubles the answer time (two GPT-5 calls) |
| Fabricated (substitute) figure | 1 (#46) | Agent | A figure for a month the user didn't ask about. Breaks requirements.md's "no nearby figure" |
| Generation gap | 2, plus parts of 2 (#16, #22; #23, #25) | Agent | Correct but incomplete: the figure was available and left out |
| Tool error | 0 | – | No tool failed in the baseline. The one injected failure (#45, a timeout) was handled gracefully and passed |
| Eval setup | 5 memory (#23, #25, #36, #37, #38) and 1 check (#41) | Eval | None: the harness or a check is at fault |
| Latency | 0 failing cases (latency isn't a pass/fail scorer), but the first tester's main complaint | Agent | See below |

Not a category but worth recording: **the judge itself varies**. Judging the same 50 answers twice changed 6 verdicts (Task 28), so a judge-only failure is weaker evidence than a failed automatic check. Eight of the 14 failures rest on the judge alone (#9, #16, #22, #23, #27, #36, #37, #38).

## Latency

Measured from the traces of the 50 baseline answers (cache off) and the Railway session:

| | Median | Notes |
|---|---|---|
| Whole answer (local) | 12.5 s | 4 of 50 over 20 s |
| GPT-5 calls | 9.2 s | **74 % of all answer time**; about 830 output tokens each, reasoning included |
| Small-model checks (wording review, cache confirmation) | 1.7 s | |
| Tools (MCP, Neon) | 1.2 s | |
| Retrieval | 0.1 s locally | about 2 s on Railway's CPU |
| Answers needing a second GPT-5 call | 25.7 s | Rewrites (and #3's block) double the time; 3 of the 4 answers over 20 s involved a rewrite or block |
| On Railway (the tester's 3 questions) | 39.5, 28.5, 19.7 s | The same questions locally: 28.3, 19.9, 17.2 s. The second needed a guardrail rewrite |

**Root cause:** the time is GPT-5 writing about 700–1,200 tokens, not the hosting. Railway adds about 2–10 s (retrieval on a slower CPU, and rewrites). **Fixes:**
- Fewer false-positive rewrites (fix 1 below) remove the worst cases.
- `REASONING_EFFORT=minimal` cut GPT-5's own time from 15–20 s to 9–12 s on the tester's questions, but one answer then needed a rewrite. It should be judged on the eval suite in Task 30, not switched blind. *(Judged in Task 30: 40 % faster but 4 fewer cases passing, so `low` stays; see [the trial](task-30-fixes-and-rerun.md#reasoning-effort-trial).)*

## Top 3 fixes for Task 30

| # | Fix | Cases | Why first |
|---|---|---|---|
| 1 | **G1 reviewer: restating the user's own goal is not a prediction** (review prompt, plus #3's drafts as regression cases) | §3 #3, #5 | The user sees a refusal instead of a plan, on the core goal-memory feature. It also adds a full GPT-5 call. One-line prompt change |
| 2 | **Data-aware retrieval:** besides the question, search on the factors in the user's own score history (and a carried card balance), and add the best new passage | #9, #11, #27 | The library has the right fact but the question doesn't name it. Probes show the factor label finds the right passage first each time. Raising `k` alone wouldn't: two of the passages aren't in the top 12 |
| 3 | **Out-of-range months: no substitute figure** (system prompt rule) | #46 | A hard-rule breach the guardrail layer can't catch. One-line prompt change |

**Also in Task 30, reported separately so the score change isn't inflated:** the eval-setup fixes (seed the stored goal for the §4 memory queries; accept "cycle" in #41's check). They change what is measured, not the agent. The before/after report will show the agent fixes and the measurement fixes as separate steps.

**Outcome (Task 30):** all three applied; 36 → 45 of 50, with the measurement fixes reported apart ([task-30-fixes-and-rerun.md](task-30-fixes-and-rerun.md)).

**Next candidates after the top 3:** the generation gaps (#16, #22: a single-figure answer comes with its change and reason; per-card paydowns), and a reasoning-effort trial for latency.

## Testers: what was observed, said and changed

The Week 4 Implementation plan asks for the app to be tested by people other than the builder, ideally Gen Z users who match the target user, and for what they did, what they said and every change made in response to be written down, as one build → feedback → improvement cycle.

**Session 1** (2026-10-27, a team member on the Railway build, as a new sign-up):

| Observed | Said | Root cause | Changed |
|---|---|---|---|
| Asked three questions about improving a score; each took 20–40 s | "Latency of each query is too high, nearly 30 seconds" | GPT-5 output length, plus a guardrail rewrite on one answer (above) | Measured and analyzed above. The rewrite share comes down with fix 1; reasoning effort is to be trialled on the eval suite in Task 30 |
| The three questions each missed the answer cache | "Semantically similar questions should be answered from the cache" | The three were different questions (similarity 0.776 and 0.717; the model check also said no to each), so serving one's answer for another would be wrong. But true rewordings under 0.90 never reached the model check | The model check now starts at 0.80: 13–14 of 15 rewordings hit instead of 11, still no wrong hit ([caching.md](../../caching.md) §3) |
| Traces from Railway never reached Langfuse | (found while checking the session) | Japan-region keys sent to the default EU host, which refuses them | `LANGFUSE_HOST` documented as required with the keys, and the app now logs a warning at startup when Langfuse refuses the keys |

**Collecting feedback from here on.** Each CreditCoach answer in the chat now has 👍 and 👎. A 👎 can carry a reason that maps onto the categories above: *Wrong or missing figure*, *Didn't answer my question*, *Too slow*, *Hard to follow*. The rating is attached to that answer's trace in Langfuse as `user.feedback` (with `user.feedback.reason`), so every rating opens onto the full record of what happened, and it is written to the app log. Real Gen Z testers are still to be recruited. Their sessions go into this table, and Task 30's re-run is where their feedback is checked against the fixes.

## Team sign-off

| Member | Reviewed | Date |
|---|---|---|
| Aman | [ ] | |
| Anil | [ ] | |
| Sudip | [ ] | |
