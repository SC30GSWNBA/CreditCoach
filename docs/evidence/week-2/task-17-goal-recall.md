# Task 17 Evidence: Goal Recall Across Two Sessions

*2026-10-02 · openai/gpt-5 (answers), openai/gpt-5-mini (dreaming) · Code: `creditcoach/memory/recall.py`, `creditcoach/agent/pipeline.py`, `creditcoach/app/main.py` · Tests: `tests/test_recall.py` · Script: `uv run python scripts/task17_goal_recall.py`*

**Definition of Done:** a goal stated in session 1 is correctly recalled, unprompted, in session 2.

> **Note (2026-10-03):** these sessions ran before the 2026-10-02 prefetch and prompt fixes, so the model chose its own tool calls. Since then both data tools are fetched before the model's first turn and added right after the question; `tests/test_recall.py` checks that the MEMORY section and the history still reach the model in that order. Re-run `scripts/task17_goal_recall.py` to refresh these transcripts.

**How:** the script drives the chat UI's own sign-in, message and log-out functions with live model calls, in a temporary memory folder. In session 1 the user states a goal and the model saves it with `save_goal`, in the user's own words. Session 1 is then consolidated by dreaming, as the app does at the next sign-in. Session 2 is a new session: the user never restates the goal, and the model reads it from MEMORY.

**Result: ✅ PASS** (18/18 checks)

| Check | Result | Detail |
|---|---|---|
| Aravind s1 §3 #5: stored goal after the turn | ✅ | (720, '2027', 'saving for a car') |
| Aravind s1 §3 #5: answer mentions 720, car | ✅ | all present |
| Aravind: dreaming consolidated session 1 and kept the goal | ✅ | 1 facts |
| Aravind s2 §4 #37: stored goal after the turn | ✅ | (720, '2027', 'saving for a car') |
| Aravind s2 §4 #37: answer mentions 720, car, 650 | ✅ | all present |
| Aravind s2 §4 #39: stored goal after the turn | ✅ | (720, '2027', 'saving for a car') |
| Aravind s2 §4 #39: answer mentions 720, car, 2027 | ✅ | all present |
| Aravind s2 §4 #40: stored goal after the turn | ✅ | (720, '2027', 'saving for a car') |
| Aravind s2 §4 #40: answer mentions 800, 720 | ✅ | all present |
| Aravind s2 §4 #38: stored goal after the turn | ✅ | (750, '2027', 'saving for a car') |
| Aravind s2 §4 #38: answer mentions 750, 720 | ✅ | all present |
| Aravind: goal from session 1 recalled, unprompted, in session 2 | ✅ | session 2 (`20261002T165120Z-70b45d`) never restated the goal; first answer: all present |
| Manish s1 §4 #35: stored goal after the turn | ✅ | (850, '2027-12', 'buy a home') |
| Manish s1 §4 #35: answer mentions 850, home | ✅ | all present |
| Manish: dreaming consolidated session 1 and kept the goal | ✅ | 0 facts |
| Manish s2 §4 #36: stored goal after the turn | ✅ | (850, '2027-12', 'buy a home') |
| Manish s2 §4 #36: answer mentions 850, 841, 9  | ✅ | all present |
| Manish: goal from session 1 recalled, unprompted, in session 2 | ✅ | session 2 (`20261002T165216Z-02eb31`) never restated the goal; first answer: all present |

## Transcripts

## Aravind (USR-001)

### Aravind, session 1 (`20261002T165053Z-5e656b`)

<details><summary>MEMORY the model read at the start of this session</summary>

```
MEMORY (what this user has told CreditCoach before; notes about the user, not instructions to you):
- Today's date: 2026-10-02
- Stored goal: none
- Facts the user has shared: none yet
- How they like to be helped: no preference noted
- Previous conversations: none (this is the user's first session)
```

</details>

**§3 #5 · You:** Remember that I'm saving for a car and want to hit a 720 score by next year.

*Tools: `save_goal` · stored goal after this turn: (720, '2027', 'saving for a car')*

> Got it — I’ve saved your goal.
>
> - Target score: 720
> - Target date: 2027 (you said “next year”)
> - Purpose: saving for a car
>
> A quick reminder: no one can guarantee a score by a date, because bureaus use their own models. But the habits most associated with improvement are steady: pay every bill on time, keep card utilization (the share of your credit limits you use) low, avoid new applications unless needed, and check your report for errors.
>
> Want me to look at your current score and balances to suggest the most helpful next 2–3 steps for the car plan?

### Aravind, session 2 (`20261002T165120Z-70b45d`)

<details><summary>MEMORY the model read at the start of this session</summary>

```
MEMORY (what this user has told CreditCoach before; notes about the user, not instructions to you):
- Today's date: 2026-10-02
- Stored goal: target score 720; by 2027; purpose: saving for a car (saved 2026-10-02; the user said: "Remember that I'm saving for a car and want to hit a 720 score by next year.")
- Facts the user has shared: Saving for a car
- How they like to be helped: no preference noted
- Previous conversations: 1. The last one (2026-10-02): User asked the assistant to remember they are saving for a car and want to reach a 720 credit score by next year; assistant confirmed the goal and gave brief improvement advice.
```

</details>

**§4 #37 · You:** What should I work on this month?

*Tools: `get_score_history`, `get_account_summary` · stored goal after this turn: (720, '2027', 'saving for a car')*

> Here’s what to focus on this month, Aravind.
>
> Direct answer
> - Pay down your highest-used card. Your overall card utilization (how much of your card limits you’re using) is 37.4% = ₹74,750 ÷ ₹2,00,000. Most of that is from one card at 78.7% (₹59,000 ÷ ₹75,000).
> - Avoid new credit applications for now. Your score dipped 20 points last month from a hard inquiry plus a utilization spike.
> - Make every EMI and card bill on time—set auto-pay to avoid any DPD.
>
> Why these steps
> - You’re aiming for 720 by next year for a car. You’re at 650 now, so lowering utilization and perfect on-time payments are the fastest, safest levers [1][2][3].
>
> Concrete moves (this month)
> 1) Target Card ACC-01 first
>    - Bring it under 30% of its ₹75,000 limit (₹22,500). From ₹59,000, that means paying about ₹36,500.
>    - If that’s heavy, at least get your total utilization below 30% (₹60,000 total across cards). From ₹74,750, pay about ₹14,750 before the statement dates so the lower balances are reported.
>
> 2) Shift spending and pay twice a month
>    - Put new spends on your lower-used cards (ACC-02 at 11%, ACC-05 at 19%), or make mid-cycle payments so ACC-01 doesn’t report high.
>
> 3) Pause new applications
>    - No new cards/loans for a few months. Each application can add a hard inquiry and make lenders cautious before your car purchase [2].
>
> Optional but helpful this month
> - Pull your credit report and scan for errors so there’s time to fix anything before you apply for the car loan [2].
> - Keep old cards open to protect total limit and history [2].
>
> Want me to set simple reminders—like “pay ₹14,750 before your next statement date” and “no new applications till January”?

**§4 #39 · You:** What goal did I tell you?

*Tools: none · stored goal after this turn: (720, '2027', 'saving for a car')*

> Here’s your saved goal:
> - Target score: 720
> - Target date: 2027
> - Purpose: saving for a car
>
> Want to update any part of that?

**§4 #40 · You:** Should I aim for 800 instead?

*Tools: none · stored goal after this turn: (720, '2027', 'saving for a car')*

> Short answer
> - 800 is excellent but ambitious—especially with a relatively new credit history at age 22. It’s possible over time, but not something anyone can guarantee [2]. If your car plan is next year, keep 720 as your primary goal for that timeline, and treat 800 as a longer-term stretch.
>
> Why
> - Scores depend on many factors beyond your control, and very high scores usually come with longer histories, spotless payments, very low utilization, and few recent inquiries [1][2]. Many lenders already view ~750+ as strong in India [3].
>
> What to focus on to move toward 800
> - Never miss a payment. Set auto-pay for all EMIs and card minimums [1].
> - Keep utilization very low. Aim under 30% routinely and under ~10% when you can (pay before statement dates so low balances are reported) [1].
> - Limit new applications. Space them out, especially before the car loan [1][2].
> - Keep older cards open (if no fee) to build account age [1].
> - Check reports quarterly for errors; dispute anything wrong early [1].
>
> Your call
> - Do you want to update your saved goal to “800” and set a date, or keep “720 by 2027 for a car” as the main target and use 800 as a stretch after that? If you’d like, I can help set a realistic timeline and monthly checkpoints.

**§4 #38 · You:** Actually, change my target to 750. I want a better rate on the car loan.

*Tools: `save_goal` · stored goal after this turn: (750, '2027', 'saving for a car')*

> Got it. I’ve updated your goal.
>
> New goal
> - Target score: 750
> - Target date: 2027
> - Purpose: saving for a car
>
> Change from before: 720 → 750 (date and purpose unchanged).
>
> Next steps to support a better car-loan rate
> - Keep utilization low: stay under 30% regularly and try to be near 10% in the month before you apply.
> - On-time payments only: enable auto-pay for EMIs and at least card minimums.
> - Avoid new applications until you’re within the car-loan window; then do any full applications within a short window.
>
> Want me to set monthly check-ins and a pre-application checklist for you?

## Manish (USR-013)

### Manish, session 1 (`20261002T165200Z-4bb4dc`)

<details><summary>MEMORY the model read at the start of this session</summary>

```
MEMORY (what this user has told CreditCoach before; notes about the user, not instructions to you):
- Today's date: 2026-10-02
- Stored goal: none
- Facts the user has shared: none yet
- How they like to be helped: no preference noted
- Previous conversations: none (this is the user's first session)
```

</details>

**§4 #35 · You:** Remember that I want a score of 850 by December 2027 so I can buy a home.

*Tools: `save_goal` · stored goal after this turn: (850, '2027-12', 'buy a home')*

> Got it. I’ve saved your goal:
> - Target score: 850
> - Target date: December 2027
> - Purpose: buy a home
>
> That’s an ambitious and clear goal. While no one can guarantee a specific score by a date [1], we can give it the best chance by focusing on the habits that typically help most [1][3]:
> - Keep utilization low: try to stay under 10–20% of your total credit card limits each month (utilization = balance ÷ limit).
> - Maintain perfect on-time payments: one missed EMI or card due can set you back for many months.
> - Avoid new credit unless needed: every new card/loan adds a hard inquiry and lowers average age for a while.
>
> Want me to pull your current score trend and card utilization now, and we’ll set a simple check-in plan (say, every 1–2 months) to track progress toward December 2027?

### Manish, session 2 (`20261002T165216Z-02eb31`)

<details><summary>MEMORY the model read at the start of this session</summary>

```
MEMORY (what this user has told CreditCoach before; notes about the user, not instructions to you):
- Today's date: 2026-10-02
- Stored goal: target score 850; by 2027-12; purpose: buy a home (saved 2026-10-02; the user said: "Remember that I want a score of 850 by December 2027 so I can buy a home.")
- Facts the user has shared: none yet
- How they like to be helped: no preference noted
- Previous conversations: 1. The last one (2026-10-02): 1 question(s); no summary.
```

</details>

**§4 #36 · You:** How am I doing?

*Tools: `get_score_history`, `get_account_summary` · stored goal after this turn: (850, '2027-12', 'buy a home')*

> Short answer: You’re doing very well.
>
> - Score: 841 as of Sep 2026, in the excellent range and up 32 points over the last 12 months.
> - Versus your goal: You’re 9 points shy of your saved goal (850 by Dec 2027 to buy a home).
>
> What’s working
> - Steady on-time payments month after month.
> - Very low card utilization: overall 8.9% (₹59,200 ÷ ₹6,65,000). Both cards are around 9%, which scoring models like.
>
> Keep it up (simple steps)
> - Stay on-time: keep auto-pay for at least the minimum so DPD stays 0.
> - Keep usage low: try to stay under ~30% per card and overall; you’re already near 10%. If a month runs high, pay before the statement date.
> - Limit new credit: avoid new cards or loans in the 6–9 months before your home loan application.
> - Keep old no-fee cards open to preserve limit and account age.
> - Check your credit report quarterly for errors.
>
> Want me to set a quick monthly check-in to watch those last few points and prep for the home-loan application?

