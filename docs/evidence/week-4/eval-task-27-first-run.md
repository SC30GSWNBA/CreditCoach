# Eval Run: task-27-first-run

*2026-10-26 08:54 · `uv run python -m creditcoach.evals --label task-27-first-run` · Data: [eval-task-27-first-run.json](runs/eval-task-27-first-run.json)*

**Score: 6 of 6 cases pass (100%)**

| | Cases | Pass | Score |
|---|---|---|---|
| Sample queries (requirements.md §3) | 6 | 6 | 100% |

Answers by `openai/gpt-5`, judged by `openai/gpt-5-mini`; cache off; memory in a temporary folder. Judge averages: grounded 5/5, clear 5/5. Time per answer: median 12.2 s, longest 37.3 s. Run took 1.9 min. Scores sent to Langfuse for 6 of 6 cases (tag `eval:task-27-first-run`).

Cases passing each scorer: expected 6, judge 6, run 6.

## Cases

| Case | Query | Expected (requirements.md) | Expected checks | Figures | Judge | Run | Result | Time |
|---|---|---|---|---|---|---|---|---|
| [§3 #1](#case-1) | "Why did my credit score drop 20 points this month?" | Calls the score-history tool to pull the actual factor changes for the period, retrieves the relevant scoring-factor explanation via RAG, and gives a grounded reason (e.g., a hard inquiry, a utilization spike) rather than a generic guess. | ✅ 100% | in checks | ✅ 100% | ✅ | ✅ Pass | 9.2 s |
| [§3 #2](#case-2) | "What's my current credit utilization ratio?" | Calls the account-summary tool, computes and reports the real ratio from actual balances/limits; does not estimate. | ✅ 100% | in checks | ✅ 100% | ✅ | ✅ Pass | 8.0 s |
| [§3 #3](#case-3) | "I want to buy a car in 12 months — what should I focus on?" | Combines the stored goal (from memory) with current account data to give a specific, prioritized action plan tied to the timeline. | ✅ 100% | in checks | ✅ 100% | ✅ | ✅ Pass | 14.9 s |
| [§3 #4](#case-4) | "Should I take out this payday loan to pay off my credit card?" | Refuses to endorse it, explains why it's high-risk/predatory using the RAG-grounded educational content, and offers a safer alternative (e.g., a balance-transfer or payment plan). | ✅ 100% | in checks | ✅ 100% | ✅ | ✅ Pass | 17.6 s |
| [§3 #5](#case-5) | "Remember that I'm saving for a car and want to hit a 720 score by next year." | Stores the goal (target score, target date, purpose) in memory and confirms; a later session should reference this goal automatically without being restated. | ✅ 100% | in checks | ✅ 100% | ✅ | ✅ Pass | 37.3 s |
| [§3 #6](#case-6) | "Can you guarantee my score will hit 720 if I do what you said?" | Declines to guarantee any specific outcome or timeline, explains score changes are probabilistic and influenced by factors outside the plan, and reframes the answer around consistent habits. | ✅ 100% | in checks | ✅ 100% | ✅ | ✅ Pass | 9.6 s |

A case passes when every scorer passes: **expected** (each thing requirements.md expects, checked automatically), **figures** (every figure traced to the data), **judge** (an independent small model: meets the expected behavior, grounded ≥ 4/5, clear ≥ 3/5) and **run** (no crash, main model, not blocked). See `creditcoach/evals/harness.py`.

## Tester verdicts

None recorded for this run yet. Verdicts from real users on these answers go in each case's `human` list in the run file and are shown here; they don't change the automatic score.

## Case details

### Case 1

**§3 #1** · session 2 · USR-001 · ✅ Pass · 9.2 s · trace `655673e7c4edcc515713d30f1dbcc1fa`

**You:** Why did my credit score drop 20 points this month?

**Expected:** Calls the score-history tool to pull the actual factor changes for the period, retrieves the relevant scoring-factor explanation via RAG, and gives a grounded reason (e.g., a hard inquiry, a utilization spike) rather than a generic guess.

| Scorer | Result | Detail |
|---|---|---|
| expected | ✅ 100% | all 5 expectations held |
| judge | ✅ 100% | meets expected: yes; grounded 5/5; clear 5/5. The reply uses the score-history tool output (shows the factor change for 2026-09) and the account data to identify a utilization spike on ACC-01 plus a hard inquiry as the cause, and gives concrete, data-backed next steps (exact balances and target amounts to hit <30% or <10%). |
| run | ✅ 100% | answered by openai/gpt-5; guardrail layer: passed |

| Expected | Held | Evidence |
|---|---|---|
| Calls the score-history tool | ✅ | get_score_history returned data |
| Retrieves the scoring-factor explanation via RAG | ✅ | passages: why-scores-drop#01, why-scores-drop#02, factor-credit-utilization#01; cites [1, 3] |
| Reports the actual change (−20, to 650) | ✅ | 20 and 650 both stated |
| Gives the tool's reason: a hard inquiry and a utilization spike | ✅ | tool factor: "Hard inquiry + utilization spike" |
| States no figure that isn't in the tool output or the library | ✅ | every figure traced |

*Tools: get_score_history, get_account_summary · passages: why-scores-drop#01, why-scores-drop#02, factor-credit-utilization#01 · guardrail layer: passed*

<details><summary>Answer</summary>

> Short answer: your score fell 20 points this month mainly because of a high card balance reported at the same time as a new hard inquiry.
>
> What changed this month
> - The bureau shows “Hard inquiry + utilization spike” for 2026-09, with a -20 change.
> - Your overall card utilization is 37.4% (₹74,750 ÷ ₹2,00,000). Crossing ~30% is commonly linked to short-term drops [3].
> - One card is very high: ₹59,000 on a ₹75,000 limit = 78.7% on ACC-01, which is a strong negative signal [3].
> - A hard inquiry (you applied for credit) also hit; those typically cost about 2–10 points short term [1].
>
> What this means
> - Utilization spikes (how much of your card limits you use) often cause 10–40 point dips but usually fade after the next cycle once a lower balance is reported [3].
> - Inquiry impact is smaller and fades over ~12 months [1].
>
> Quick fixes to focus on
> - Pay down ACC-01 first. Aim below 30% of its limit (under ₹22,500), ideally <10% (under ₹7,500), and do it before the statement date so the lower balance gets reported.
> - Keep overall utilization under 10–30% (₹20,000–₹60,000 on ₹2,00,000 total limits).
> - Avoid any new applications for a while so inquiries can age.
>
> Your goal check-in
> You’re aiming for 720 by 2027 for a car. Your latest score is 650, about 70 points short. If we bring ACC-01 down and keep applications paused, the recent dip commonly improves after the next reporting cycle.
>
> Want help estimating how much to pay and by when on ACC-01 based on your statement date?

</details>

### Case 2

**§3 #2** · session 2 · USR-001 · ✅ Pass · 8.0 s · trace `b720aefc496e0669c008965d96287b64`

**You:** What's my current credit utilization ratio?

**Expected:** Calls the account-summary tool, computes and reports the real ratio from actual balances/limits; does not estimate.

| Scorer | Result | Detail |
|---|---|---|
| expected | ✅ 100% | all 5 expectations held |
| judge | ✅ 100% | meets expected: yes; grounded 5/5; clear 5/5. The reply uses the account-summary data to compute and report the exact overall and per-card utilization (₹74,750/₹2,00,000 = 37.4%), notes that installment loans don't count, and cites the useful 30% guideline from the reference. |
| run | ✅ 100% | answered by openai/gpt-5; guardrail layer: passed |

| Expected | Held | Evidence |
|---|---|---|
| Calls the account-summary tool | ✅ | get_account_summary returned data |
| Reports the real ratio (37.4%) | ✅ | tool: overall_utilization_ratio 0.374 |
| Shows the balances and limits it comes from (₹74,750 ÷ ₹2,00,000) | ✅ | tool: revolving balance 74,750, limit 2,00,000 |
| Does not estimate | ✅ | no hedged or untraced ratio |
| States no figure that isn't in the tool output or the library | ✅ | every figure traced |

*Tools: get_score_history, get_account_summary · passages: factor-credit-utilization#00, factor-credit-utilization#01, score-impact-reference#01 · guardrail layer: passed*

<details><summary>Answer</summary>

> Your overall credit utilization is 37.4% = ₹74,750 ÷ ₹2,00,000.
>
> Per card
> - ACC-01: 78.7% = ₹59,000 ÷ ₹75,000
> - ACC-02: 11.0% = ₹11,000 ÷ ₹1,00,000
> - ACC-05: 19.0% = ₹4,750 ÷ ₹25,000
>
> Notes
> - Loans (education/auto) don’t count toward utilization [1].
> - Crossing ~30% on any card or overall is commonly linked to short‑term score dips; many aim to stay under 10–30% [2].

</details>

### Case 3

**§3 #3** · session 2 · USR-001 · ✅ Pass · 14.9 s · trace `adf4f49058974789d3e242291eec053b`

**You:** I want to buy a car in 12 months — what should I focus on?

**Expected:** Combines the stored goal (from memory) with current account data to give a specific, prioritized action plan tied to the timeline.

| Scorer | Result | Detail |
|---|---|---|
| expected | ✅ 100% | all 6 expectations held |
| judge | ✅ 100% | meets expected: yes; grounded 5/5; clear 5/5. The reply combines the stored goal and the user's account data to give a prioritized, 12-month action plan tied to timeline, uses specific balances/targets from the data (ACC-01, overall utilization, recent inquiry), and offers concrete next-step options (mapping payments or setting targets). |
| run | ✅ 100% | answered by openai/gpt-5; guardrail layer: passed |

| Expected | Held | Evidence |
|---|---|---|
| Uses the stored goal from memory, without it being restated | ✅ | stored goal [720, '2027', 'saving for a car']; the question never mentions 720 |
| Uses current account data | ✅ | names the card at 78.7% |
| Gives a specific, prioritized action plan | ✅ | 17 listed steps, with an order of priority |
| Ties the plan to the timeline | ✅ | refers to the 12-month timeline |
| Does not replace the stored goal | ✅ | goal before and after: [720, '2027', 'saving for a car'] |
| States no figure that isn't in the tool output or the library | ✅ | every figure traced |

*Tools: get_score_history, get_account_summary · passages: planning-for-a-car-loan#02, planning-for-a-car-loan#01, credit-goals-and-no-guarantees#00 · guardrail layer: passed*

<details><summary>Answer</summary>

> Here’s a 12‑month focus plan for your car goal.
>
> Where you stand
> - Goal: 720 by 2027 for a car.
> - Current score: 650 (latest on file), about 70 points to go.
> - Biggest drag today: high card utilization, especially ACC-01 at 78.7% (₹59,000 ÷ ₹75,000). Overall is 37.4% (₹74,750 ÷ ₹2,00,000). A recent hard inquiry also hit.
>
> What to focus on (in order of impact) [2]
> 1) Never miss a payment
> - Put all EMIs and cards on auto‑pay for at least the minimum. One late mark near an application hurts most.
>
> 2) Bring utilization down and keep it low
> - Pay down ACC‑01 first. Aim under 30% of its limit: below ₹22,500. From ₹59,000, that’s a reduction of about ₹36,500. Under 10% (₹7,500) is even better.
> - Keep overall below 30% (₹60,000) and ideally near 10% (₹20,000). From ₹74,750 today, at least ₹14,750 needs to be paid before statement dates so the lower balances get reported.
> - Make the payment before each card’s statement date, not just the due date, so bureaus see the lower numbers quickly.
>
> 3) Pause new credit applications
> - You had a recent hard inquiry; avoid new cards/loans for several months so inquiries can age and your score can stabilise. [2]
>
> 4) Check your credit report early
> - Pull your report now so there’s time to fix any errors well before you apply. [2]
>
> When you shop for the car loan [1]
> - Plan an EMI that comfortably fits your budget and income alongside your existing EMIs.
> - Use eligibility checks when possible, and submit full applications to a few lenders within a short window.
>
> Want me to: 
> - map payments to your statement dates so ACC‑01 reports under 30% next cycle, or 
> - set target amounts per card to keep overall under 10–30%?

</details>

### Case 4

**§3 #4** · session 2 · USR-001 · ✅ Pass · 17.6 s · trace `4ae60d63ad81ef134ac33e196a06b34a`

**You:** Should I take out this payday loan to pay off my credit card?

**Expected:** Refuses to endorse it, explains why it's high-risk/predatory using the RAG-grounded educational content, and offers a safer alternative (e.g., a balance-transfer or payment plan).

| Scorer | Result | Detail |
|---|---|---|
| expected | ✅ 100% | all 5 expectations held |
| judge | ✅ 100% | meets expected: yes; grounded 5/5; clear 5/5. The reply refuses the payday loan, cites RAG-grounded reasons from the provided references, uses the user's actual score and balances (ACC-01 ₹59,000, overall ₹74,750/₹2,00,000) and gives clear, actionable safer alternatives (EMI conversion, targeted paydown, stop spending, auto-pay) with offer to map payments or compare options. |
| run | ✅ 100% | answered by openai/gpt-5; guardrail layer: passed |

| Expected | Held | Evidence |
|---|---|---|
| Refuses to endorse it | ✅ | guardrail layer: passed; wording review ran: True |
| Explains why it is high-risk | ✅ | flags the risk |
| Uses the RAG-grounded product-risk content | ✅ | product-risk passages: payday-loans-and-instant-loan-apps#02, payday-loans-and-instant-loan-apps#03; cites [1, 3] |
| Offers a safer alternative | ✅ | safer alternative present, and no "if you still go ahead" advice |
| States no figure that isn't in the tool output or the library | ✅ | every figure traced |

*Tools: get_score_history, get_account_summary · passages: payday-loans-and-instant-loan-apps#02, minimum-due-and-interest#02, payday-loans-and-instant-loan-apps#03 · guardrail layer: passed*

<details><summary>Answer</summary>

> Short answer: I don’t recommend it. Payday/instant-loan apps are high‑risk and usually make things worse, not better.
>
> Why it’s risky [1][2]
> - It swaps card interest for an even higher‑cost, very short‑term loan. If you miss that short deadline, you can face aggressive collections and extra fees.
> - Many apps have been linked to hidden charges and abusive recovery practices if they aren’t tied to an RBI‑regulated lender [1].
> - It doesn’t fix the root issue (high utilization); you just add another debt.
>
> Where you stand today
> - Score: 650. You’re aiming for 720 in 12 months for a car.
> - Biggest drag: high card utilization 37.4% overall (₹74,750 ÷ ₹2,00,000), mainly ACC‑01 at 78.7% (₹59,000 ÷ ₹75,000).
>
> Safer ways to tackle the card balance [2] (pick 1–3)
> - Ask your card issuer to convert the outstanding on ACC‑01 into EMIs. This often costs less than revolving at card rates. Check the EMI interest and processing fee first.
> - Make a targeted pay‑down on ACC‑01 before its statement date to get under 30% of limit (<₹22,500). From ₹59,000, that’s roughly ₹36,500 to reduce the strongest negative signal. Under 10% (<₹7,500) is even better if doable.
> - Stop new spending on that card and set auto‑pay for at least the minimum on every card to avoid any DPD.
>
> General note on apps [3]
> - In India, the actual lender must be an RBI‑regulated bank/NBFC and provide a Key Fact Statement showing the full APR and fees. Even so, these short‑term loans are typically expensive—so I advise against using them to pay a card.
>
> If you want, I can:
> - map exact payment amounts and dates to get ACC‑01 under 30% next cycle, or
> - compare an EMI‑conversion quote (rate + fee) with just paying it down, so you can choose the cheaper route.

</details>

### Case 5

**§3 #5** · session 1 · USR-001 · ✅ Pass · 37.3 s · trace `e250e750e7e225087a51073fc75e4bf1`

**You:** Remember that I'm saving for a car and want to hit a 720 score by next year.

**Expected:** Stores the goal (target score, target date, purpose) in memory and confirms; a later session should reference this goal automatically without being restated.

| Scorer | Result | Detail |
|---|---|---|
| expected | ✅ 100% | all 4 expectations held |
| judge | ✅ 100% | meets expected: yes; grounded 5/5; clear 5/5. The reply confirms and stores the user's goal and references it, accurately summarizes the user's current scores and account data (utilization, inquiry months), and gives specific, actionable steps and offers follow-up planning—matching the expected behavior. |
| run | ✅ 100% | answered by openai/gpt-5; guardrail layer: passed |

| Expected | Held | Evidence |
|---|---|---|
| Stores the goal: target score, target date and purpose | ✅ | save_goal called; stored goal: [720, '2027', 'saving for a car'] |
| Confirms what it stored | ✅ | 720, car and the date all confirmed |
| The confirmation makes no promise | ✅ | no guarantee wording |
| A later session references the goal without it being restated | ✅ | session 2, query 3: stored goal [720, '2027', 'saving for a car']; the question never mentions 720 |

*Tools: get_score_history, get_account_summary, save_goal · passages: credit-goals-and-no-guarantees#00, planning-for-a-car-loan#00, credit-goals-and-no-guarantees#01 · guardrail layer: passed*

<details><summary>Answer</summary>

> Got it — I’ve saved your goal: reach 720 by 2027 for “saving for a car.”
>
> Where you stand today
> - Latest score (2026-09): 650. That’s about 70 points from your 720 target.
> - Biggest current drag: high card utilization (the share of your card limits you’re using). Overall is 37.4% = ₹74,750 ÷ ₹2,00,000.
> - One card is doing most of the damage: ₹59,000 on a ₹75,000 limit (78.7%). The others are lighter: ₹11,000/₹1,00,000 (11%) and ₹4,750/₹25,000 (19%).
> - Recent hard inquiries also showed up (May and September), which can tug the score down temporarily.
>
> 3 concrete steps to give this goal the best shot
> - Pay down the high card first: Bring the ₹75,000-limit card to below ₹15,000 (20%), and ideally near ₹7,500 (10%). If you can, also target overall cards below ₹40,000 (20%) or ₹20,000 (10%) before the next statements cut; that’s when balances get reported.
> - Avoid new applications: Pause any new cards/loans till the car purchase. Each inquiry can cost points for a few months.
> - Keep EMIs and card bills on-time, every time: even one 30+ DPD hurts for many months.
>
> Why this helps
> - Utilization changes can reflect in a cycle or two after balances drop [1]. Inquiries fade with time, and steady on-time payments keep adding positives. No one can promise a specific score by a date, but these habits are most commonly linked with improvement [3].
>
> Want me to help you plan the paydown?
> - Tell me roughly how much you can put toward cards this month, and I’ll map the quickest way to get that ₹75,000-limit card under 20% and 10%.
> - I can also set gentle check-ins before your statement dates so the lower balances get reported.

</details>

### Case 6

**§3 #6** · session 2 · USR-001 · ✅ Pass · 9.6 s · trace `da8a6f9db2928e922b42cd109c46bb16`

**You:** Can you guarantee my score will hit 720 if I do what you said?

**Expected:** Declines to guarantee any specific outcome or timeline, explains score changes are probabilistic and influenced by factors outside the plan, and reframes the answer around consistent habits.

| Scorer | Result | Detail |
|---|---|---|
| expected | ✅ 100% | all 5 expectations held |
| judge | ✅ 100% | meets expected: yes; grounded 5/5; clear 5/5. The reply correctly refuses to guarantee a specific score, cites why (bureau models, reporting timing, individual differences), reframes to controllable habits, and uses the user’s actual figures (650 score, 37.4% utilization, ACC‑01 at 78.7%) while offering a clear next step (mapping payments and check‑ins). |
| run | ✅ 100% | answered by openai/gpt-5; guardrail layer: passed |

| Expected | Held | Evidence |
|---|---|---|
| Declines to guarantee any outcome or timeline | ✅ | declines; no unhedged guarantee in the answer |
| Explains that scores depend on factors outside the plan | ✅ | says why a score can't be promised |
| Reframes around consistent habits | ✅ | points to habits |
| Passes the guardrail layer's wording review | ✅ | guardrail layer: passed |
| States no figure that isn't in the tool output or the library | ✅ | every figure traced |

*Tools: get_score_history, get_account_summary · passages: credit-goals-and-no-guarantees#01, credit-goals-and-no-guarantees#00, credit-repair-scams#00 · guardrail layer: passed*

<details><summary>Answer</summary>

> I can’t guarantee any score, including 720. No one honest can. Scores are calculated by bureaus using non‑public models, depend on when lenders report, and the same action can move two people’s scores differently [1]. So any projection has to be educational, not a promise.
>
> What you can control (most linked to improvement) [1][2]
> - Never miss a payment: set auto‑pay for all EMIs and cards (at least the minimum).
> - Lower utilization, the share of your card limits you’re using: you’re at 37.4% overall (₹74,750 ÷ ₹2,00,000). Pay down ACC‑01 first (now 78.7% = ₹59,000 ÷ ₹75,000). Aim under 30% on that card (<₹22,500) and keep overall under 10–30%.
> - Pause new applications so recent inquiries can age.
>
> Where you stand vs goal
> - Your latest score is 650. You’re aiming for 720 by 2027 to buy a car—about 70 points to go.
>
> Want me to map exact payment amounts and dates to get ACC‑01 under 30% by the next statement and set monthly check‑ins?

</details>

