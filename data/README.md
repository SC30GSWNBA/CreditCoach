# CreditCoach Synthetic Dataset

All data here is **synthetic**, set in an **Indian consumer context**: amounts are in ₹ (INR), scores use the **300–900 range** of Indian credit bureaus (TransUnion CIBIL, Experian, Equifax, CRIF High Mark), and loans use Indian types (education, car, home, personal, instant loan apps). Every name is fictional. USR-001 (Aravind) is the requirements.md persona. Its scores are copied unchanged from `sample_data/credit_profile_sample.xlsx`. Its USD amounts are scaled ×50 into ₹, a fixed scale rather than an exchange rate, so every utilization ratio stays identical: 79% on the main card and 37.4% overall. Its account types are renamed to Indian terms: Student Loan → Education Loan, Auto Loan → Car Loan, Retail Card → Credit Card. USR-002 to USR-013 are **one synthetic user per interviewee** (interviews P1–P12). Their habits, cards, loans, savings and goals come from that person's answers, and the balances, limits and scores are generated to fit those answers.

The data is built in three steps:

```bash
uv run python scripts/synthetic/step1_profiles.py         # users.csv from user_interviews/CreditCoach_User_Profiles.xlsx
uv run python scripts/synthetic/step2_accounts_scores.py  # accounts.csv + score_history.csv from users.csv, validated
uv run python scripts/synthetic/step3_summary.py          # evidence summary
```

All three steps run on a fresh clone. Generation is deterministic: each user has a fixed random seed.

Step 2 refuses to write data unless all of these hold:
- Accounts and scores belong to known users.
- Card counts match each interview answer.
- Scores stay within 300–900.
- Every monthly change falls within its factor's range.
- Anyone above 30% utilization shows a utilization change in their last 3 months.
- Utilization ratios equal balance ÷ limit.
- USR-001's scores and utilization ratios match the sample exactly.

## Files

| File | One row per | Columns |
|---|---|---|
| `users.csv` | user (13) | `user_id`, `first_name`, `gender`, `age`, `age_band`, `years_working`, `credit_cards`, `checks_score`, `learns_from`, `self_reported_score`, `knowledge_score` (0–6, Q7–Q12), `unexplained_drop`, `pays_card`, `card_usage`, `knows_apr`, `late_payments_12m`, `loans`, `risky_product_exposure`, `invests_in`, `emergency_fund`, `emi_pct`, `invest_pct`, `goals_2yr`, `source` |
| `accounts.csv` | account (25) | `account_id`, `user_id`, `account_type`, `balance_inr`, `credit_limit_inr` (blank for installment loans), `utilization_ratio` (blank for installment loans) |
| `score_history.csv` | user × month (132) | `user_id`, `date` (1st of month, Oct 2025 to Sep 2026), `score`, `primary_factor_change` |

`accounts.csv` and `score_history.csv` follow the sample workbook's columns, with amounts in ₹ (`_inr` instead of `_usd`). The Week 2 tools (`get_score_history`, `get_account_summary`) will serve them. The `users.csv` answers use the questionnaire's wording. For USR-001, fields the persona doesn't state are left blank.

## How Interview Answers Become Accounts and Scores

| Interview answer | Generated data |
|---|---|
| Number of credit cards (Q3) | That many `Credit Card` accounts. The limit depends on years worked: under 1 year ₹30,000–75,000, 1–3 years ₹75,000–1.5 lakh, 4–8 years ₹1.5–3 lakh, over 8 years ₹3–5 lakh. |
| Card usage (Q15) | Balance ÷ limit inside the stated band. A person who has a card but said "I don't know" gets 35–50%, modeling an unnoticed high balance. |
| Loans (Q18) | Education loan ₹3–15 lakh · Car loan ₹3–8 lakh · Personal loan ₹1–5 lakh · Home loan ₹20–75 lakh |
| Used a payday/instant-cash loan (Q19) | An `Instant Loan App` account (₹5,000–25,000), the Indian equivalent of a payday loan |
| Self-reported score (Q6) | Starting score in Oct 2025 (300–900 range): Excellent 790–815, Good 730–760, Average/fair 650–690, don't know 690–715 |
| No cards and no loans | No accounts and **no score history** (no credit file) |

## Profiles and Score Scenarios

| User | Source | Scenario | What happens | Sample query it exercises |
|---|---|---|---|---|
| USR-001 Aravind | Persona | Utilization spike + hard inquiry | 690 → 670 → 650; card at 79% | #1–#6 (the main demo user) |
| USR-003 Vikram | P2 | Hard inquiries (car loan shopping) | Two inquiry dips in Aug and Sep; wants a car | #1 with a different cause; #3 car plan |
| USR-009 Nikhil | P8 ("prefer not to say" on late payments) | Late payment recovery | Payment 30+ days past due in Apr 2026 (811 → 729), recovering since | The guide's biggest factor |
| USR-011 Sameer | P10 | Unnoticed utilization spike | Card creeps to 48%; Aug drop of 33 points (724 → 691) he didn't notice | #1 and #2 for a user who never checks |
| USR-012 Aditya | P11 | High utilization and debt stress | 83% card usage, personal loan, **Instant Loan App**; 746 → 684 | #2 high utilization; #4 predatory-product guardrail |
| USR-005 Kavya | P4 | Loan-only file (no credit card) | Scored from a student loan only; small steady gains | Advice for someone with no card |
| USR-004 Ananya, USR-007 Karthik | P3, P6 | No credit file | No accounts, no scores | Tools must say "no credit history yet", not error or invent |
| USR-002, 006, 008, 010, 013 | P1, P5, P7, P9, P12 | Steady improver | On-time payments with small dips; "Excellent" users level off in the 830s–840s | Scores that *rose*; no false alarm |

## How Score Changes Are Bounded

Each monthly change must fall within the range for its `primary_factor_change` label. Combined labels like `Hard inquiry + utilization spike` add their ranges together.

| Factor change | Allowed monthly change | Source |
|---|---|---|
| Late payment (30+ days) | −110 to −60 | Factors guide, Score Impact Reference Table |
| Utilization spike (above 30%) | −40 to −10 | Factors guide |
| Hard inquiry | −10 to −2 | Factors guide |
| Utilization increase (stays below 30%) | −10 to −1 | Our assumption |
| Stable (no major change) | −2 to +2 | Our assumption |
| Utilization decreased | +5 to +15 | Our assumption |
| On-time payments | +2 to +8 | Our assumption |
| Account age increase | +2 to +6 | Our assumption |

This keeps the data consistent with the RAG corpus. When CreditCoach quotes a typical range, the user's own history won't contradict it. The guide's point ranges come from US-style scoring models. Indian bureaus don't publish point impacts, so we use the same ranges as approximate bounds on the 300–900 scale. The Task #7 corpus should add India-specific content: the CIBIL score range, what "days past due" (DPD) means, and RBI rules on digital lending apps.

## What the User Interviews Told Us

We interviewed **12 people** (8 men, 4 women), aged mostly 26–30 (7), with 3 aged 31–35 and 2 over 35, working in different industries. The responses (dummy participants) are in `user_interviews/CreditCoach_User_Profiles.xlsx`, and the counts below summarize them. Questions follow [docs/research/interview-questionnaire.md](../docs/research/interview-questionnaire.md). The raw file doesn't include Q23 (% of pay on card bills).

**Credit habits: these shaped the profiles**
- **Cards:** 8 have one card, 3 have none, 1 has two or three.
- **Paying the bill:** 6 pay in full, 2 pay more than the minimum, 3 have no card, and 1 left it blank.
- **Card usage:** 3 use under 10% of their limit, 4 use 10–30%, 1 uses over 70%, and 4 don't know or have no card.
- **Late payments:** 11 have never paid late, and 1 preferred not to say.
- **Loans:** 4 have an education loan, 3 a home loan, 1 a car loan and 1 a personal loan. 4 have no loans.
- **Loan repayments:** 5 put 0% of pay toward them, 4 put 1–10%, and 1 each is in the 11–20%, 21–35% and over-35% bands.
- **Investing:** 8 invest in mutual funds or SIPs and 6 use savings or fixed deposits. 2 don't invest regularly.
- **Emergency fund:** 5 have more than 6 months of expenses saved, 3 have 4–6 months, 3 have 1–3 months, and 1 has less than a month.

**Credit knowledge (Q7–Q12): these shape the RAG corpus (Task #7)**
- **Only 1 of 12 knew that scores commonly drop above roughly 30% utilization.** 2 said 10%, 3 said 70%, 2 said 100%, and 4 didn't know. This is the biggest gap, and it bears directly on sample query #1.
- 5 of 12 didn't know what closing their oldest card does, and 3 gave a wrong answer.
- 6 of 12 knew a new application causes a small, temporary dip. 2 thought nothing happens, 1 thought it raises the score, and 3 didn't know.
- 8 of 12 correctly said payment history has the biggest effect. 2 thought it was salary.
- 11 of 12 recognized the "+100 points for an upfront fee" offer as a scam.

**Risk and goals: these shape the guardrails and memory**
- 4 of 12 weren't sure what payday loans, instant cash apps or credit-repair services are. 1 had used one.
- 5 of 12 had never checked their score closely enough to notice a drop, and 3 never check it at all.
- Top 2-year goals (more than one allowed): paying off debt (7), a wedding, travel or other big expense (7), a car (2), a home (2). Goal memory (Task #16) needs to support more than a car.
