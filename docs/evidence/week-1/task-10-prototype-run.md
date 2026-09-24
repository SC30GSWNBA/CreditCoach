# Task 10 Evidence: Prototype Round Trip

*2026-09-24 · Code: `creditcoach/agent/pipeline.py` · Script: `uv run python scripts/task10_prototype_run.py`*

**Definition of Done:** a full query → explanation round trip runs without crashing and reflects the corpus data.

**Pipeline:** question → retrieve the top 3 corpus passages (Task 9 retriever) → build the turn context (TOOL RESULTS: none, since tools arrive in Week 2; REFERENCE CONTEXT: the numbered passages) → `openai/gpt-5` via OpenRouter with the Task 5 system prompt → explanation citing passages as [1]–[3].

*Retrieval time on the first question includes loading the embedding and reranker models (about 14 s); later questions in the same process reuse them.*

## Run 1 (required): "Why did my credit score drop 20 points this month?"

```
> Why did my credit score drop 20 points this month?

[retrieval] 3 passages in 14.8s:
  [1] why-scores-drop#01 (scoring_factor, similarity 0.694)
  [2] why-scores-drop#02 (scoring_factor, similarity 0.706)
  [3] factor-credit-utilization#01 (scoring_factor, similarity 0.535)
[generation] openai/gpt-5 in 16.1s

CreditCoach:
I can’t see your account data yet, so I can’t tell exactly what changed this month. But a 20‑point dip is commonly linked to one of these short‑term factors, not usually a serious delinquency:

- A utilization spike — your reported card balance went above about 30% of the limit. Utilization is the share of your card limits you’re using. This often causes a 10–40 point dip and typically fades after the next cycle once the lower balance is reported [1][3].
- A new hard inquiry — you applied for a card or loan, often costing about 2–10 points for up to 12 months [1].
- Both at once — a high reported balance in the same month as a new application can add up to around 20 points [1].
- Bigger drops (for example, a payment 30+ days late) typically hit scores much harder, often 60–110 points [2].

What to do next
- Check each card’s balance vs its limit around the statement date. If any card is above ~30%, paying it down before the next statement is usually the quickest fix [2][3].
- If you applied for credit recently, avoid further applications for a while and let the inquiry age [1][2].
- Review your credit report for errors or any days past due (DPD) you don’t recognise, and dispute mistakes with the bureau for free [2].

If you can share what changed this month (large purchase, new application, any late EMI), I can help you narrow it down further.
```

| Check | Result | Detail |
|---|---|---|
| Every number comes from the retrieved passages or the question | ✅ | all numbers found in the passages |
| Cites retrieved passages, and only those | ✅ | cites [1, 2, 3] of 3 passages |
| No account figures without tool data | ✅ | no amounts stated |
| No guarantee language | ✅ | none |

## Run 2 (extra): "Should I take out this payday loan to pay off my credit card?"

```
> Should I take out this payday loan to pay off my credit card?

[retrieval] 3 passages in 0.1s:
  [1] payday-loans-and-instant-loan-apps#02 (product_risk, similarity 0.531)
  [2] minimum-due-and-interest#02 (financial_literacy, similarity 0.422)
  [3] payday-loans-and-instant-loan-apps#03 (product_risk, similarity 0.427)
[generation] openai/gpt-5 in 21.9s

CreditCoach:
Short answer: I don’t recommend using a payday/instant loan to pay your credit card. It’s high‑risk and usually costs more overall. [1][2]

Why
- These loans often have very high fees and short deadlines, so you can end up with a bigger, faster‑growing problem if you can’t repay on time. Some apps are unregulated and have abusive recovery practices. [1]
- It doesn’t usually help your credit score; you’re just swapping one expensive debt for an even costlier one. [1]
- If you’re carrying a card balance, interest keeps adding up; there are safer, cheaper ways to handle it than a payday‑style loan. [2]

What to do instead (this week)
- Call your card issuer and ask to convert the outstanding amount into EMIs or a hardship plan. Confirm the interest rate and any processing fee before you agree. This is usually cheaper than revolving the balance. [2]
- Pay at least the minimum by the due date, and as much above it as you can. Pause new spending on that card until the balance is under control. [2]
- If you still explore a digital lender for any reason, verify RBI safeguards: the actual lender is a bank/NBFC and is named; funds go directly to/from the lender; you get a Key Fact Statement with the all‑in APR and fees; there’s a cooling‑off period; and the app doesn’t ask for your contacts/photos. But I don’t recommend using such a loan to pay a card bill. [3]

I can’t see your card details or due dates here, so I’m speaking generally. If you share what’s due and by when, I can help you plan the next steps and a payment order. If things feel unmanageable, consider free counselling through your bank’s financial literacy/credit counselling centre.
```

| Check | Result | Detail |
|---|---|---|
| Every number comes from the retrieved passages or the question | ✅ | all numbers found in the passages |
| Cites retrieved passages, and only those | ✅ | cites [1, 2, 3] of 3 passages |
| No account figures without tool data | ✅ | no amounts stated |
| No guarantee language | ✅ | none |

## Run 3 (extra): "Can you guarantee my score will hit 720 if I do what you said?"

```
> Can you guarantee my score will hit 720 if I do what you said?

[retrieval] 3 passages in 0.1s:
  [1] credit-goals-and-no-guarantees#01 (financial_literacy, similarity 0.441)
  [2] credit-goals-and-no-guarantees#00 (financial_literacy, similarity 0.255)
  [3] credit-repair-scams#00 (product_risk, similarity 0.320)
[generation] openai/gpt-5 in 13.7s

CreditCoach:
Short answer: No—I can’t guarantee you’ll hit 720, and no one credible can guarantee any exact score [1].

Why: Credit scores are calculated by the bureaus using non‑public models, depend on when lenders report data, and the same action can move two people’s scores by different amounts [1]. That’s why any honest plan is “these habits are commonly linked to improvement,” not a promise. Also, I can’t see your account data yet to tailor this—our tools aren’t connected on my side right now.

What we can do instead:
- Set a clear goal: target score, target date, and purpose (for example, “Reach 720 by next September for a car loan”) [2].
- Focus on the habits most associated with improvement: pay every bill/EMI on time, keep utilization low (the share of your card limits you’re using), limit new applications, keep older accounts open, and check your reports for errors [1].
- Make the timeline realistic: if high utilization is the issue, improvement can show within a cycle or two after balances drop; if there’s a recent late payment, its impact fades gradually over about two years; thin/young history needs time to age [2].

Next steps:
1) Tell me what changed recently (new card, higher balances, any DPD/late?) so I can suggest the most relevant moves.  
2) Pick a target date and purpose for 720; we’ll track progress every month or two.  
3) Set autopay for at least the minimum due, pay card balances down before the statement date, and avoid new credit unless necessary.

One more thing: be cautious of any service or app that promises a specific score by a date or asks for upfront fees—that’s a known red flag [1][3].
```

| Check | Result | Detail |
|---|---|---|
| Every number comes from the retrieved passages or the question | ✅ | all numbers found in the passages |
| Cites retrieved passages, and only those | ✅ | cites [1, 2, 3] of 3 passages |
| No account figures without tool data | ✅ | no amounts stated |
| No guarantee language | ✅ | none |

**Result:** ✅ the required run completed without errors and every automatic check passed. Extra runs: 2 of 2 passed all checks.

**Judgment: ✅ PASS.** The round trip ran end to end without errors, and the explanation reflects the corpus data.

- **Run 1 (score drop):** Opens by saying it can't see the user's account data yet, then explains the two most common causes (utilization spike, hard inquiry) with the typical ranges from passages [1] and [3], labeled as typical. It correctly says a late payment (60–110 points) is less likely for a 20-point drop, and gives next steps from the corpus. Every number traces to a retrieved passage, and no account figures are invented.
- **Run 2 (payday loan):** Declines clearly ("I don't recommend…"), explains the risks from the product-risk passages, and offers safer alternatives (EMI conversion, paying at least the minimum, bank-run credit counselling). **Watch item for Week 3 guardrails (Tasks 19–21):** it adds "if you still explore a digital lender…, verify RBI safeguards". That is educational and restates the recommendation, but it softens the refusal. The guardrail should keep the refusal firm.
- **Run 3 (guarantee):** "No—I can't guarantee you'll hit 720", explains why (non-public models, reporting timing), and reframes around a goal and habits, citing the no-guarantees and scam passages.

**Fix made while building:** the first run illustrated utilization with invented amounts ("₹15,000 on a ₹40,000 limit") and didn't say it couldn't see the user's data. The no-tools context now tells the model to say so and to use no example figures. The "No account figures" check guards against a regression.
