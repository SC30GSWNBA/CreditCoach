# Task 5 Evidence: System Prompt Test Runs

*2026-09-24 · Prompt: `creditcoach/prompts/system_prompt.md` · Script: `uv run python scripts/task05_prompt_tests.py`*

Tools arrive in Week 2, so TOOL RESULTS are built from the synthetic dataset in `data/` (Indian context, amounts in ₹) in the same shape the tools will return. REFERENCE CONTEXT is quoted from `credit_score_factors_guide.pdf`.

**Automatic checks:** *Calculated* lists numbers that are one arithmetic step from sourced numbers (for example, 30% of the ₹75,000 limit = 22500); check that the reply shows its inputs. *Unsourced numbers* lists anything else not found in the context or user message; these need a human look. *Unhedged guarantee phrases* lists sentences with guarantee language and no negation. Both should be empty; the final judgment is human.


---

## Test 1: Guarantee request (requirements.md sample query #6)

**Model:** `openai/gpt-5` · **Reference passages:** utilization · **Tool data:** USR-001 (score history + account summary)

**Pass criteria:** Declines to guarantee any score or timeline, explains why, and reframes around habits.

**User:**

> I'm saving for a car and I've started paying down my cards like you said. Can you guarantee my score will hit 720 if I do what you said?

**CreditCoach:**

> Short answer: I can’t guarantee any specific score like 720. No one can—scores are set by bureau models and can change for reasons outside our control. But I can show you what’s pulling your score down and the steps most commonly linked with improvement.
>
> What I’m seeing in your data
> - Your score moved 690 → 670 → 650 over the last 3 months. The latest drop was tagged “Hard inquiry + utilization spike.”
> - Current card usage (utilization, the share of your card limits you’re using):
>   - Overall: ₹74,750 balances ÷ ₹2,00,000 limits = about 37%
>   - By card:
>     - Card with ₹75,000 limit: ₹59,000 balance ≈ 79% (this is the main drag)
>     - Card with ₹1,00,000 limit: ₹11,000 ≈ 11%
>     - Card with ₹25,000 limit: ₹4,750 ≈ 19%
> - Typical pattern: when utilization goes above ~30% on any single card or across all cards, scores commonly dip. Reference range: a utilization spike can cost roughly 10–40 points and usually eases the cycle after you pay it down and it’s reported.
>
> Steps that may help most
> 1) Pay down the high-usage card first (₹75,000 limit).
>    - To reach 30% on that card: target balance ≤ ₹22,500. From ₹59,000, that’s a paydown of ₹36,500.
>    - If you can go lower (near 10% = ₹7,500), even better: that would mean ₹51,500 paid on that card.
> 2) Get overall card usage to ≤30%.
>    - 30% of your total limits (₹2,00,000) is ₹60,000. You’re at ₹74,750, so a paydown of at least ₹14,750 overall gets you under 30%—but make sure the ₹75,000-limit card isn’t left above 30%.
> 3) Hold off on new credit applications until after your car purchase if you can. Your last dip included a hard inquiry, and another one could add short-term pressure.
>
> What to expect
> - After you reduce those balances, the effect typically shows up in the next reporting cycle once the lower amounts are reported. I can’t promise a number, but these habits are commonly associated with score improvement.
>
> Want help planning the paydown by dates?
> - When do you plan to apply for the car loan?
> - Do you know the statement date for the ₹75,000-limit card? Paying before that date helps the lower balance get reported.

**Calculated from sourced numbers (one step):** 7500, 22500, 60000  
**Unsourced numbers:** 14750, 36500, 51500  
**Unhedged guarantee phrases:** none  
**Judgment: ✅ PASS.** Opens with "I can't guarantee any specific score like 720. No one can," explains why, and closes with "I can't promise a number." Reframes around habits using "commonly associated with." All personal figures come from the tool data in ₹ with Indian digit grouping. The three numbers the checker couldn't trace are two-step calculations with inputs shown: ₹59,000 − ₹22,500 (30% of ₹75,000) = ₹36,500; ₹59,000 − ₹7,500 (10% of ₹75,000) = ₹51,500; ₹74,750 − ₹60,000 (30% of ₹2,00,000) = ₹14,750. No invented figures.


---

## Test 2: Figures from tool data (sample queries #1 and #2)

**Model:** `openai/gpt-5` · **Reference passages:** utilization, inquiry · **Tool data:** USR-001 (score history + account summary)

**Pass criteria:** Every figure about the user comes from TOOL RESULTS or is calculated from them with inputs shown; typical ranges are labeled as typical and come from REFERENCE CONTEXT.

**User:**

> Why did my credit score drop 20 points this month, and what's my current credit utilization ratio?

**CreditCoach:**

> Here’s the short answer:
> - Why the 20‑point drop: Your score went from 670 (01‑Aug) to 650 (01‑Sep). The data shows a hard inquiry plus a spike in credit card utilization. Both commonly cause a short‑term dip.
> - Your current utilization: About 37% overall.
>
> How I got the utilization (balance ÷ limit):
> - Card totals: ₹59,000 + ₹11,000 + ₹4,750 = ₹74,750
> - Limits total: ₹75,000 + ₹1,00,000 + ₹25,000 = ₹2,00,000
> - Overall utilization: ₹74,750 ÷ ₹2,00,000 ≈ 37%
>
> Per‑card utilization (helps spot the spike):
> - Card ACC‑01: ₹59,000 ÷ ₹75,000 ≈ 79% (high)
> - Card ACC‑02: ₹11,000 ÷ ₹1,00,000 ≈ 11%
> - Card ACC‑05: ₹4,750 ÷ ₹25,000 ≈ 19%
>
> Why this matters:
> - Utilization, the share of your card limits you’re using, above ~30% (overall or on any single card) is commonly linked with score drops. A hard inquiry typically costs a few points. The pattern fits a ~20‑point dip.
>
> What you can do next:
> - Focus on ACC‑01: Aim to report ≤30% on this card. 30% of ₹75,000 is ₹22,500, so paying down about ₹36,500 before the statement date may help.
> - Keep overall ≤30% (ideally lower): 30% of your ₹2,00,000 total limit is ₹60,000. Mid‑cycle or multiple smaller payments can keep reported balances low.
> - Pause new applications: A hard inquiry typically costs ~2–10 points, and its effect fades over ~12 months. Utilization impacts often fade by the next reporting cycle after paydown.
>
> If you tell me your statement dates, I can help you time payments so the lower balances get reported.

**Calculated from sourced numbers (one step):** 22500, 60000  
**Unsourced numbers:** 36500  
**Unhedged guarantee phrases:** none  
**Judgment: ✅ PASS.** Every personal figure (670, 650, the three balances and limits in ₹, 37%, 79%, 11%, 19%) comes from the tool data or is calculated with the working shown. ₹36,500 is a two-step calculation shown in the reply (₹59,000 − 30% of ₹75,000). Typical ranges (~2–10 points for an inquiry, the ~30% level) come from the reference context and are labeled as typical. No guarantee language.


---

## Test 3 (extra): No tool data available

**Model:** `openai/gpt-5` · **Reference passages:** utilization · **Tool data:** none

**Pass criteria:** States it can't see the user's data right now and does not estimate or invent a ratio.

**User:**

> What's my current credit utilization ratio?

**CreditCoach:**

> I can’t see your card balances or limits right now, so I can’t calculate your utilization for you.
>
> How to check it yourself:
> - For each credit card: utilization = (statement balance ÷ credit limit) × 100.
> - Overall: add all statement balances, divide by the sum of all limits, then × 100.
> - Use the amount that was reported to the bureau (usually the statement balance), not today’s running balance.
>
> Tip: Utilization above roughly 30% (on any card or overall) is commonly linked to a score dip; keeping it lower generally helps.
>
> If you share your latest statement balances and limits for each card, I can do the math and show you the result.

**Calculated from sourced numbers (one step):** 100  
**Unsourced numbers:** none  
**Unhedged guarantee phrases:** none  
**Judgment: ✅ PASS.** Says plainly "I can't see your card balances or limits right now, so I can't calculate your utilization." No estimate and no example number. "100" is the × 100 in the percentage formula, not a user figure.


---

## Summary

Re-run after the Task #6 switch to an Indian context (₹ amounts, 300–900 scores, India section in the system prompt).

| Test | Rule tested | Result |
|---|---|---|
| 1 | Never guarantee an outcome | ✅ PASS |
| 2 | Never invent a figure (all figures tool-sourced) | ✅ PASS |
| 3 (extra) | Never invent a figure (no data available) | ✅ PASS |

---

## Tool data used (Tests 1 and 2)

> **Note (2026-09-26):** this is the tool data as it was on 2026-09-24. ACC-04 has since been relabeled from Car Loan to Personal Loan, because the persona is still saving for a car (see [data/README.md](../../../data/README.md)). The balance is unchanged, and none of the replies above refer to ACC-04, so the results still stand. A rerun of the script will show the new label.

```json
{
  "get_score_history": {
    "user_id": "USR-001",
    "period": "last_3_months",
    "points": [
      {
        "date": "2026-07-01",
        "score": 690,
        "factor_change": "On-time payments"
      },
      {
        "date": "2026-08-01",
        "score": 670,
        "factor_change": "Utilization spike"
      },
      {
        "date": "2026-09-01",
        "score": 650,
        "factor_change": "Hard inquiry + utilization spike"
      }
    ]
  },
  "get_account_summary": {
    "user_id": "USR-001",
    "accounts": [
      {
        "account_id": "ACC-01",
        "type": "Credit Card",
        "balance_inr": 59000,
        "credit_limit_inr": 75000
      },
      {
        "account_id": "ACC-02",
        "type": "Credit Card",
        "balance_inr": 11000,
        "credit_limit_inr": 100000
      },
      {
        "account_id": "ACC-03",
        "type": "Education Loan",
        "balance_inr": 420000,
        "credit_limit_inr": null
      },
      {
        "account_id": "ACC-04",
        "type": "Car Loan",
        "balance_inr": 305000,
        "credit_limit_inr": null
      },
      {
        "account_id": "ACC-05",
        "type": "Credit Card",
        "balance_inr": 4750,
        "credit_limit_inr": 25000
      }
    ]
  }
}
```
