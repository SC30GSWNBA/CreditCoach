# Task 8 evidence: all 45 chunks in the vector store

*Exported from the Chroma collection `creditcoach_corpus` in `.chroma` on 2026-10-02, in corpus order, by `uv run python scripts/task08_ingestion_report.py`. Text is exactly what was embedded (each chunk starts with its document title), shown in fenced blocks so its markdown isn't rendered.*

**45 chunks · 17 source files · 5,099 words.** "Queries" are the requirements.md queries (§3 #1–6 and §4 #7–50) the source file is tagged for.

## Index

| # | Chunk ID | File | Part | Category | Words / Tokens | Queries |
|---|---|---|---|---|---|---|
| 1 | [`credit-scores-in-india#00`](#1-credit-scores-in-india00) | `01-credit-scores-in-india.md` | 1/2 | scoring_factor | 159 / 209 | 1,3,6,13,20,26,43,50 |
| 2 | [`credit-scores-in-india#01`](#2-credit-scores-in-india01) | `01-credit-scores-in-india.md` | 2/2 | scoring_factor | 131 / 158 | 1,3,6,13,20,26,43,50 |
| 3 | [`factor-payment-history#00`](#3-factor-payment-history00) | `02-payment-history.md` | 1/2 | scoring_factor | 158 / 195 | 1,3,11,34,42 |
| 4 | [`factor-payment-history#01`](#4-factor-payment-history01) | `02-payment-history.md` | 2/2 | scoring_factor | 153 / 183 | 1,3,11,34,42 |
| 5 | [`factor-credit-utilization#00`](#5-factor-credit-utilization00) | `03-credit-utilization.md` | 1/3 | scoring_factor | 128 / 198 | 1,2,3,7,10,12,15,16,18,19,21,23,25,28,37,41 |
| 6 | [`factor-credit-utilization#01`](#6-factor-credit-utilization01) | `03-credit-utilization.md` | 2/3 | scoring_factor | 170 / 226 | 1,2,3,7,10,12,15,16,18,19,21,23,25,28,37,41 |
| 7 | [`factor-credit-utilization#02`](#7-factor-credit-utilization02) | `03-credit-utilization.md` | 3/3 | scoring_factor | 54 / 75 | 1,2,3,7,10,12,15,16,18,19,21,23,25,28,37,41 |
| 8 | [`factor-credit-history-length#00`](#8-factor-credit-history-length00) | `04-credit-history-length.md` | 1/2 | scoring_factor | 185 / 231 | 1,3,24 |
| 9 | [`factor-credit-history-length#01`](#9-factor-credit-history-length01) | `04-credit-history-length.md` | 2/2 | scoring_factor | 25 / 40 | 1,3,24 |
| 10 | [`factor-hard-inquiries#00`](#10-factor-hard-inquiries00) | `05-hard-inquiries.md` | 1/2 | scoring_factor | 138 / 184 | 1,3,7,8,9,12,23,33 |
| 11 | [`factor-hard-inquiries#01`](#11-factor-hard-inquiries01) | `05-hard-inquiries.md` | 2/2 | scoring_factor | 114 / 145 | 1,3,7,8,9,12,23,33 |
| 12 | [`factor-credit-mix#00`](#12-factor-credit-mix00) | `06-credit-mix.md` | 1/1 | scoring_factor | 133 / 154 | 3 |
| 13 | [`score-impact-reference#00`](#13-score-impact-reference00) | `07-score-impact-reference.md` | 1/3 | scoring_factor | 53 / 67 | 1,3,6,7,8,10,11,41,42 |
| 14 | [`score-impact-reference#01`](#14-score-impact-reference01) | `07-score-impact-reference.md` | 2/3 | scoring_factor | 141 / 184 | 1,3,6,7,8,10,11,41,42 |
| 15 | [`score-impact-reference#02`](#15-score-impact-reference02) | `07-score-impact-reference.md` | 3/3 | scoring_factor | 90 / 110 | 1,3,6,7,8,10,11,41,42 |
| 16 | [`why-scores-drop#00`](#16-why-scores-drop00) | `08-why-scores-drop.md` | 1/3 | scoring_factor | 51 / 69 | 1,7,8,9,10,12,13 |
| 17 | [`why-scores-drop#01`](#17-why-scores-drop01) | `08-why-scores-drop.md` | 2/3 | scoring_factor | 122 / 173 | 1,7,8,9,10,12,13 |
| 18 | [`why-scores-drop#02`](#18-why-scores-drop02) | `08-why-scores-drop.md` | 3/3 | scoring_factor | 170 / 230 | 1,7,8,9,10,12,13 |
| 19 | [`no-credit-history#00`](#19-no-credit-history00) | `09-no-credit-history.md` | 1/2 | financial_literacy | 175 / 233 | 3,14,20 |
| 20 | [`no-credit-history#01`](#20-no-credit-history01) | `09-no-credit-history.md` | 2/2 | financial_literacy | 91 / 122 | 3,14,20 |
| 21 | [`building-good-credit-habits#00`](#21-building-good-credit-habits00) | `10-building-good-credit-habits.md` | 1/3 | financial_literacy | 25 / 37 | 3,6,11,24,26,27,28,43 |
| 22 | [`building-good-credit-habits#01`](#22-building-good-credit-habits01) | `10-building-good-credit-habits.md` | 2/3 | financial_literacy | 155 / 216 | 3,6,11,24,26,27,28,43 |
| 23 | [`building-good-credit-habits#02`](#23-building-good-credit-habits02) | `10-building-good-credit-habits.md` | 3/3 | financial_literacy | 105 / 134 | 3,6,11,24,26,27,28,43 |
| 24 | [`minimum-due-and-interest#00`](#24-minimum-due-and-interest00) | `11-minimum-due-and-interest.md` | 1/3 | financial_literacy | 57 / 87 | 2,3,4,21,27,29 |
| 25 | [`minimum-due-and-interest#01`](#25-minimum-due-and-interest01) | `11-minimum-due-and-interest.md` | 2/3 | financial_literacy | 158 / 212 | 2,3,4,21,27,29 |
| 26 | [`minimum-due-and-interest#02`](#26-minimum-due-and-interest02) | `11-minimum-due-and-interest.md` | 3/3 | financial_literacy | 97 / 128 | 2,3,4,21,27,29 |
| 27 | [`planning-for-a-car-loan#00`](#27-planning-for-a-car-loan00) | `12-planning-for-a-car-loan.md` | 1/3 | financial_literacy | 64 / 92 | 3,5,9,23,24,25,26 |
| 28 | [`planning-for-a-car-loan#01`](#28-planning-for-a-car-loan01) | `12-planning-for-a-car-loan.md` | 2/3 | financial_literacy | 151 / 220 | 3,5,9,23,24,25,26 |
| 29 | [`planning-for-a-car-loan#02`](#29-planning-for-a-car-loan02) | `12-planning-for-a-car-loan.md` | 3/3 | financial_literacy | 120 / 158 | 3,5,9,23,24,25,26 |
| 30 | [`credit-goals-and-no-guarantees#00`](#30-credit-goals-and-no-guarantees00) | `13-credit-goals-and-no-guarantees.md` | 1/2 | financial_literacy | 158 / 205 | 3,5,6,11,25,28,35,36,37,38,39,40,41,42,43,44,50 |
| 31 | [`credit-goals-and-no-guarantees#01`](#31-credit-goals-and-no-guarantees01) | `13-credit-goals-and-no-guarantees.md` | 2/2 | financial_literacy | 157 / 213 | 3,5,6,11,25,28,35,36,37,38,39,40,41,42,43,44,50 |
| 32 | [`credit-report-and-disputes#00`](#32-credit-report-and-disputes00) | `14-credit-report-and-disputes.md` | 1/3 | financial_literacy | 76 / 109 | 1,6,24,30,34 |
| 33 | [`credit-report-and-disputes#01`](#33-credit-report-and-disputes01) | `14-credit-report-and-disputes.md` | 2/3 | financial_literacy | 146 / 223 | 1,6,24,30,34 |
| 34 | [`credit-report-and-disputes#02`](#34-credit-report-and-disputes02) | `14-credit-report-and-disputes.md` | 3/3 | financial_literacy | 83 / 123 | 1,6,24,30,34 |
| 35 | [`payday-loans-and-instant-loan-apps#00`](#35-payday-loans-and-instant-loan-apps00) | `15-payday-loans-and-instant-loan-apps.md` | 1/5 | product_risk | 70 / 112 | 4,12,29,31,32,44 |
| 36 | [`payday-loans-and-instant-loan-apps#01`](#36-payday-loans-and-instant-loan-apps01) | `15-payday-loans-and-instant-loan-apps.md` | 2/5 | product_risk | 150 / 220 | 4,12,29,31,32,44 |
| 37 | [`payday-loans-and-instant-loan-apps#02`](#37-payday-loans-and-instant-loan-apps02) | `15-payday-loans-and-instant-loan-apps.md` | 3/5 | product_risk | 85 / 130 | 4,12,29,31,32,44 |
| 38 | [`payday-loans-and-instant-loan-apps#03`](#38-payday-loans-and-instant-loan-apps03) | `15-payday-loans-and-instant-loan-apps.md` | 4/5 | product_risk | 108 / 157 | 4,12,29,31,32,44 |
| 39 | [`payday-loans-and-instant-loan-apps#04`](#39-payday-loans-and-instant-loan-apps04) | `15-payday-loans-and-instant-loan-apps.md` | 5/5 | product_risk | 52 / 100 | 4,12,29,31,32,44 |
| 40 | [`credit-repair-scams#00`](#40-credit-repair-scams00) | `16-credit-repair-scams.md` | 1/2 | product_risk | 122 / 169 | 4,6,12,30,34,44 |
| 41 | [`credit-repair-scams#01`](#41-credit-repair-scams01) | `16-credit-repair-scams.md` | 2/2 | product_risk | 141 / 190 | 4,6,12,30,34,44 |
| 42 | [`safer-alternatives#00`](#42-safer-alternatives00) | `17-safer-alternatives.md` | 1/4 | product_risk | 40 / 54 | 4,12,21,29,32,33,44 |
| 43 | [`safer-alternatives#01`](#43-safer-alternatives01) | `17-safer-alternatives.md` | 2/4 | product_risk | 160 / 222 | 4,12,21,29,32,33,44 |
| 44 | [`safer-alternatives#02`](#44-safer-alternatives02) | `17-safer-alternatives.md` | 3/4 | product_risk | 149 / 217 | 4,12,21,29,32,33,44 |
| 45 | [`safer-alternatives#03`](#45-safer-alternatives03) | `17-safer-alternatives.md` | 4/4 | product_risk | 29 / 59 | 4,12,21,29,32,33,44 |

## Chunks

### 1. credit-scores-in-india00

`credit-scores-in-india#00` · [01-credit-scores-in-india.md](../../../corpus/01-credit-scores-in-india.md) · part 1 of 2 · scoring_factor · 159 words / 209 tokens · queries 1,3,6,13,20,26,43,50  
Source: CreditCoach team (general education on the Indian credit system)

```text
How credit scores work in India

A credit score is a three-digit number that summarizes how you have handled credit in the past. Lenders use it to decide whether to approve a loan or card and on what terms, such as the interest rate.

In India, credit information is collected by credit information companies (also called credit bureaus) licensed by the Reserve Bank of India (RBI). There are four: TransUnion CIBIL, Experian, Equifax, and CRIF High Mark. Banks and lenders report your loans and cards to these bureaus every month, and each bureau calculates its own score from that data. This is why your score can differ slightly between bureaus or apps.

Most Indian credit scores run from 300 to 900. A higher score means lower risk to a lender. Many lenders treat a score of about 750 or above as strong, but each lender sets its own rules, and a score is only one part of a loan decision alongside income and existing debts.
```

### 2. credit-scores-in-india01

`credit-scores-in-india#01` · [01-credit-scores-in-india.md](../../../corpus/01-credit-scores-in-india.md) · part 2 of 2 · scoring_factor · 131 words / 158 tokens · queries 1,3,6,13,20,26,43,50  
Source: CreditCoach team (general education on the Indian credit system)

```text
How credit scores work in India

Your score is built from the same broad factors used by most scoring models worldwide: whether you pay on time, how much of your card limits you use, how long you have had credit, how often you apply for new credit, and the mix of credit you hold. Payment history and credit utilization usually matter most.

A score changes as new information is reported, usually once a month. Because lenders report on different dates, your score can move within a month even if you did nothing new. Small ups and downs of a few points are normal.

No one can calculate your exact future score, including CreditCoach. Scoring models are owned by the bureaus and are not public, so any change can only be described as typical or likely, never guaranteed.
```

### 3. factor-payment-history00

`factor-payment-history#00` · [02-payment-history.md](../../../corpus/02-payment-history.md) · part 1 of 2 · scoring_factor · 158 words / 195 tokens · queries 1,3,11,34,42  
Source: credit_score_factors_guide.pdf §1 and §7 (impact ranges); India terms added by CreditCoach team

```text
Payment history and late payments

Payment history, meaning whether you have paid past credit accounts on time, is typically the single largest factor in a credit score. It makes up roughly 35% of most scoring models.

A single payment more than 30 days late can cause a noticeable score drop. According to our reference guide, a payment 30 or more days late typically lowers a score by about 60 to 110 points. It can stay on a credit report for up to seven years, although its effect on the score fades over roughly two years.

In India, credit reports show late payments as "days past due" (DPD). DPD counts how many days a payment was overdue in a given month. A report showing 0 or "STD" (standard) means the account was paid on time. Numbers like 30, 60, or 90 DPD mean the payment was that many days late. The longer and more recent the delay, the bigger the effect on the score.
```

### 4. factor-payment-history01

`factor-payment-history#01` · [02-payment-history.md](../../../corpus/02-payment-history.md) · part 2 of 2 · scoring_factor · 153 words / 183 tokens · queries 1,3,11,34,42  
Source: credit_score_factors_guide.pdf §1 and §7 (impact ranges); India terms added by CreditCoach team

```text
Payment history and late payments

Paying only part of what is due can still count as late if you pay less than the minimum amount due. Paying at least the minimum by the due date keeps the account from being reported as past due, although interest is charged on any unpaid balance.

What helps after a late payment:
- Bring the account up to date as soon as possible. Every extra month overdue makes the record worse.
- Set up auto-pay for at least the minimum amount due so a busy month doesn't turn into a missed payment.
- Keep every account on time from now on. Recent on-time months gradually outweigh an older late payment.

A late payment cannot be removed from your report just because you ask or pay someone. If the late payment is a genuine error, you can dispute it with the credit bureau for free (see "Reading your credit report and fixing errors").
```

### 5. factor-credit-utilization00

`factor-credit-utilization#00` · [03-credit-utilization.md](../../../corpus/03-credit-utilization.md) · part 1 of 3 · scoring_factor · 128 words / 198 tokens · queries 1,2,3,7,10,12,15,16,18,19,21,23,25,28,37,41  
Source: credit_score_factors_guide.pdf §2 and §7 (impact ranges); worked example by CreditCoach team

```text
Credit utilization (how much of your card limits you use)

Credit utilization is the percentage of your available revolving credit (credit cards) that you are currently using. It is your balance divided by your limit. It makes up roughly 30% of most scoring models, second only to payment history.

**How to calculate it**
- Per card: card balance ÷ card limit × 100.
- Overall: add up all card balances, add up all card limits, then divide the total balance by the total limit × 100.
- Example: balances of ₹45,000, ₹15,000 and ₹12,000 on limits of ₹60,000, ₹80,000 and ₹40,000 give ₹72,000 ÷ ₹1,80,000 = 40% overall. The first card on its own is at 75%.
- Loans such as education, car, home, or personal loans have no credit limit, so they are not part of utilization.
```

### 6. factor-credit-utilization01

`factor-credit-utilization#01` · [03-credit-utilization.md](../../../corpus/03-credit-utilization.md) · part 2 of 3 · scoring_factor · 170 words / 226 tokens · queries 1,2,3,7,10,12,15,16,18,19,21,23,25,28,37,41  
Source: credit_score_factors_guide.pdf §2 and §7 (impact ranges); worked example by CreditCoach team

```text
Credit utilization (how much of your card limits you use)

**The 30% level.** Utilization above roughly 30% on any single card, or across all cards combined, is commonly associated with score drops. This applies even if you pay your bill in full every month. Lower is generally better; many people aim to keep it under 10% to 30%.

**Why paying in full doesn't always prevent it.** Utilization is usually based on the balance your card issuer reports to the credit bureaus, often around your statement date, not the balance after you pay. A large purchase reported before the statement closes can show up as a utilization spike even if you clear it a few days later.

**Typical impact.** A sudden utilization spike is one of the most common causes of a short-term score dip. According to our reference guide, a spike above 30% typically lowers a score by about 10 to 40 points. Unlike a late payment, the effect is short-lived: it typically fades about one reporting cycle after the balance is paid down and the lower balance is reported.
```

### 7. factor-credit-utilization02

`factor-credit-utilization#02` · [03-credit-utilization.md](../../../corpus/03-credit-utilization.md) · part 3 of 3 · scoring_factor · 54 words / 75 tokens · queries 1,2,3,7,10,12,15,16,18,19,21,23,25,28,37,41  
Source: credit_score_factors_guide.pdf §2 and §7 (impact ranges); worked example by CreditCoach team

```text
Credit utilization (how much of your card limits you use)

**What helps**
- Pay down the card with the highest utilization first.
- Make a payment before the statement date so a lower balance gets reported.
- Spread spending across cards or make more than one payment a month.
- Avoid closing unused cards, since that removes their limit and raises your overall utilization.
```

### 8. factor-credit-history-length00

`factor-credit-history-length#00` · [04-credit-history-length.md](../../../corpus/04-credit-history-length.md) · part 1 of 2 · scoring_factor · 185 words / 231 tokens · queries 1,3,24  
Source: credit_score_factors_guide.pdf §3 and §7 (impact ranges)

```text
Length of credit history and closing old cards

Length of credit history makes up roughly 15% of most scoring models. It considers the age of your oldest account, your newest account, and the average age of all your accounts. A longer, well-managed history generally helps.

This is why young borrowers often start with modest scores even when they have done nothing wrong. Their history is simply short, and it improves as accounts age.

**Closing your oldest card.** Closing your oldest card can shorten your average history length and may lower your score. According to our reference guide, closing the oldest open account typically lowers a score by about 5 to 20 points, and the effect recovers only gradually as newer accounts age. Closing a card also removes its credit limit, which can push up your overall utilization.

If an old card has no annual fee, keeping it open and using it lightly (for example, one small purchase paid off each month) usually helps your history and utilization. If a card charges a fee you don't want to pay, ask the issuer whether it can be converted to a no-fee version before closing it.
```

### 9. factor-credit-history-length01

`factor-credit-history-length#01` · [04-credit-history-length.md](../../../corpus/04-credit-history-length.md) · part 2 of 2 · scoring_factor · 25 words / 40 tokens · queries 1,3,24  
Source: credit_score_factors_guide.pdf §3 and §7 (impact ranges)

```text
Length of credit history and closing old cards

**Opening several new accounts at once** lowers the average age of your accounts and adds hard inquiries, so it can cause a small, temporary dip.
```

### 10. factor-hard-inquiries00

`factor-hard-inquiries#00` · [05-hard-inquiries.md](../../../corpus/05-hard-inquiries.md) · part 1 of 2 · scoring_factor · 138 words / 184 tokens · queries 1,3,7,8,9,12,23,33  
Source: credit_score_factors_guide.pdf §4 and §7 (impact ranges); soft vs hard inquiries by CreditCoach team

```text
New credit and hard inquiries

New credit makes up roughly 10% of most scoring models.

**Hard inquiries.** When you apply for a credit card or loan, the lender checks your credit report. This is recorded as a hard inquiry (sometimes called a hard enquiry or hard pull). A hard inquiry can cause a small, temporary score dip. According to our reference guide, it typically lowers a score by about 2 to 10 points. It stays on your report for about two years, but its effect on the score usually fades within about 12 months.

**Soft inquiries don't count.** Checking your own score, whether on a bureau website, a bank app, or a credit-score app, is a soft inquiry. So are pre-approved offers a lender generates without an application. Soft inquiries do not affect your score, so checking your own score regularly is safe.
```

### 11. factor-hard-inquiries01

`factor-hard-inquiries#01` · [05-hard-inquiries.md](../../../corpus/05-hard-inquiries.md) · part 2 of 2 · scoring_factor · 114 words / 145 tokens · queries 1,3,7,8,9,12,23,33  
Source: credit_score_factors_guide.pdf §4 and §7 (impact ranges); soft vs hard inquiries by CreditCoach team

```text
New credit and hard inquiries

**Several applications close together.** Each application usually adds its own hard inquiry. Applying for several cards or loans in a short period can add up to a bigger dip, and it can make lenders cautious because it looks like you urgently need credit.

**What helps**
- Apply only for credit you actually need.
- Before a big loan, such as a car or home loan, avoid other new applications for a few months.
- Use eligibility checks that say they don't affect your score before submitting a full application.
- If you see an inquiry you don't recognise, check your report and dispute it with the bureau. It may be a sign of fraud.
```

### 12. factor-credit-mix00

`factor-credit-mix#00` · [06-credit-mix.md](../../../corpus/06-credit-mix.md) · part 1 of 1 · scoring_factor · 133 words / 154 tokens · queries 3  
Source: credit_score_factors_guide.pdf §5

```text
Credit mix

Credit mix makes up roughly 10% of most scoring models. It looks at whether you hold different kinds of credit: revolving credit such as credit cards, and installment loans such as education, car, or home loans.

Having a mix of account types can modestly help a score, but it is a minor factor compared with payment history and credit utilization.

Taking on a loan you don't need just to improve your credit mix is generally not worth it. The new loan adds a hard inquiry, adds debt and interest, and adds another payment you must never miss. The better path is to handle the credit you already have well: pay on time and keep card utilization low. A healthy mix tends to build naturally over time as you take loans for real needs.
```

### 13. score-impact-reference00

`score-impact-reference#00` · [07-score-impact-reference.md](../../../corpus/07-score-impact-reference.md) · part 1 of 3 · scoring_factor · 53 words / 67 tokens · queries 1,3,6,7,8,10,11,41,42  
Source: credit_score_factors_guide.pdf §7 (Score Impact Reference Table)

```text
Score impact reference table

The table below summarizes the typical score impact of common credit events, how long each stays on a credit report, and roughly how long its scoring effect tends to last. Actual impact varies by scoring model and by each person's credit history. These are typical ranges for education, not predictions for any individual.
```

### 14. score-impact-reference01

`score-impact-reference#01` · [07-score-impact-reference.md](../../../corpus/07-score-impact-reference.md) · part 2 of 3 · scoring_factor · 141 words / 184 tokens · queries 1,3,6,7,8,10,11,41,42  
Source: credit_score_factors_guide.pdf §7 (Score Impact Reference Table)

```text
Score impact reference table

| Event | Typical score impact | Time on credit report | Scoring effect fades in |
|---|---|---|---|
| Payment 30+ days late | −60 to −110 points | Up to 7 years | About 2 years |
| Hard inquiry (new credit application) | −2 to −10 points | About 2 years | About 12 months |
| Utilization spike above 30% | −10 to −40 points | Until the next reporting cycle | 1 reporting cycle after paydown |
| Collections account | −50 to −100 points | Up to 7 years | About 2 years |
| Closing oldest open account | −5 to −20 points | Not applicable (history length effect) | Gradually, as newer accounts age |
| Bankruptcy | −130 to −240 points | 7 to 10 years | About 2 to 3 years |
```

### 15. score-impact-reference02

`score-impact-reference#02` · [07-score-impact-reference.md](../../../corpus/07-score-impact-reference.md) · part 3 of 3 · scoring_factor · 90 words / 110 tokens · queries 1,3,6,7,8,10,11,41,42  
Source: credit_score_factors_guide.pdf §7 (Score Impact Reference Table)

```text
Score impact reference table

How to read it:
- The biggest and longest-lasting drops come from missed payments, collections, and bankruptcy.
- Utilization spikes and hard inquiries cause smaller, temporary dips that recover on their own once the cause is fixed or time passes.
- Two events in the same month, such as a hard inquiry plus a utilization spike, can combine into a larger drop.
- These ranges come from general scoring models. Indian bureaus do not publish exact point impacts, so treat them as approximate guides on the 300 to 900 scale.
```

### 16. why-scores-drop00

`why-scores-drop#00` · [08-why-scores-drop.md](../../../corpus/08-why-scores-drop.md) · part 1 of 3 · scoring_factor · 51 words / 69 tokens · queries 1,7,8,9,10,12,13  
Source: CreditCoach team, summarizing credit_score_factors_guide.pdf §1–§4 and §7

```text
Why did my credit score drop? Common causes

A sudden drop is worrying, but most drops have an ordinary, explainable cause. The quickest way to find it is to compare what changed on your credit record in the month the score fell. The point ranges below are typical, not predictions: every scoring model and every credit history is different.
```

### 17. why-scores-drop01

`why-scores-drop#01` · [08-why-scores-drop.md](../../../corpus/08-why-scores-drop.md) · part 2 of 3 · scoring_factor · 122 words / 173 tokens · queries 1,7,8,9,10,12,13  
Source: CreditCoach team, summarizing credit_score_factors_guide.pdf §1–§4 and §7

```text
Why did my credit score drop? Common causes

**Most common causes of a short-term drop**
1. **A utilization spike.** A card balance rose above roughly 30% of its limit, often after a large purchase reported before the statement date. This is one of the most common causes of a short-term dip. Typical impact: about 10 to 40 points, fading about one reporting cycle after the balance is paid down.
2. **A new hard inquiry.** You applied for a card or loan. Typical impact: about 2 to 10 points, fading within about 12 months.
3. **Both at once.** A new card application in the same month as a high balance can combine into a larger drop. For example, a 20-point drop can come from a hard inquiry plus a utilization spike.
```

### 18. why-scores-drop02

`why-scores-drop#02` · [08-why-scores-drop.md](../../../corpus/08-why-scores-drop.md) · part 3 of 3 · scoring_factor · 170 words / 230 tokens · queries 1,7,8,9,10,12,13  
Source: CreditCoach team, summarizing credit_score_factors_guide.pdf §1–§4 and §7

```text
Why did my credit score drop? Common causes

**Causes of a larger or longer drop**
- **A payment 30 or more days late.** Typically 60 to 110 points, with the effect fading over about two years.
- **An account sent to collections.** Typically 50 to 100 points.
- **Closing your oldest card.** Typically 5 to 20 points, recovering gradually.

**Things that do not lower your score**
- Checking your own score (a soft inquiry).
- Your salary or income, which is not part of a credit score.
- Your age, and how many bank savings accounts you have.

**What to do next**
- Look at which factor changed in the month of the drop, and check your card balances against their limits.
- If a card is above 30%, paying it down before the next statement date is usually the fastest fix.
- If you applied for credit recently, avoid further applications for a while and let the inquiry age.
- Check your credit report for anything you don't recognise, and dispute errors with the bureau for free.
```

### 19. no-credit-history00

`no-credit-history#00` · [09-no-credit-history.md](../../../corpus/09-no-credit-history.md) · part 1 of 2 · financial_literacy · 175 words / 233 tokens · queries 3,14,20  
Source: CreditCoach team (general education)

```text
No credit history yet (new to credit)

If you have never had a credit card or loan, the credit bureaus may have no record of you, or too little to calculate a score. Lenders often call this being "new to credit" (NTC). It is not the same as having a bad score. There is simply nothing to score yet.

People with no credit history can still find it harder or costlier to get a loan, because the lender has no track record to judge. The goal is to start a small, well-managed history before you need a big loan.

**Common ways to start**
- **A secured credit card** issued against a fixed deposit. The limit is linked to your deposit, so banks can approve it without a credit history. Used lightly and paid on time, it builds a history like any other card.
- **A basic credit card from your salary-account bank**, which may already know your income and banking history.
- **An existing loan in your name**, such as an education loan, already builds history if payments are made on time.
```

### 20. no-credit-history01

`no-credit-history#01` · [09-no-credit-history.md](../../../corpus/09-no-credit-history.md) · part 2 of 2 · financial_literacy · 91 words / 122 tokens · queries 3,14,20  
Source: CreditCoach team (general education)

```text
No credit history yet (new to credit)

**Good first habits**
- Keep usage low, ideally well under 30% of the limit.
- Pay the full statement balance by the due date, or at least the minimum amount due. Auto-pay helps.
- Don't apply for several cards at once. Each application adds a hard inquiry.
- Check your score after a few months. A first score usually appears once an account has some months of history.

A history of a few months is a thin file. It becomes stronger over time as accounts age and on-time payments add up.
```

### 21. building-good-credit-habits00

`building-good-credit-habits#00` · [10-building-good-credit-habits.md](../../../corpus/10-building-good-credit-habits.md) · part 1 of 3 · financial_literacy · 25 words / 37 tokens · queries 3,6,11,24,26,27,28,43  
Source: CreditCoach team, based on credit_score_factors_guide.pdf §1–§5

```text
Habits that build a strong credit score

Credit scores reward steady, boring habits over time. There is no shortcut, but the habits below are the ones most commonly associated with steady improvement.
```

### 22. building-good-credit-habits01

`building-good-credit-habits#01` · [10-building-good-credit-habits.md](../../../corpus/10-building-good-credit-habits.md) · part 2 of 3 · financial_literacy · 155 words / 216 tokens · queries 3,6,11,24,26,27,28,43  
Source: CreditCoach team, based on credit_score_factors_guide.pdf §1–§5

```text
Habits that build a strong credit score

1. **Pay every bill on time.** Payment history is the biggest factor. Set up auto-pay for at least the minimum amount due on every card and loan EMI so nothing is missed.
2. **Keep card utilization low.** Aim to keep each card and your overall usage below about 30% of your limits, and lower if you can. Pay before the statement date if you have a large purchase.
3. **Pay the full statement balance when possible.** This avoids interest, which on credit cards is usually expensive.
4. **Apply for new credit only when you need it.** Each application adds a hard inquiry. Space out applications, especially before a big loan.
5. **Keep old accounts open** if they have no annual fee, so your credit history stays long and your total limit stays high.
6. **Check your credit report regularly.** Checking your own score does not lower it. Look for errors or accounts you don't recognise.
```

### 23. building-good-credit-habits02

`building-good-credit-habits#02` · [10-building-good-credit-habits.md](../../../corpus/10-building-good-credit-habits.md) · part 3 of 3 · financial_literacy · 105 words / 134 tokens · queries 3,6,11,24,26,27,28,43  
Source: CreditCoach team, based on credit_score_factors_guide.pdf §1–§5

```text
Habits that build a strong credit score

7. **Keep an emergency fund.** Even one to three months of expenses in savings reduces the chance that a surprise bill turns into a missed payment or a high-cost loan.

How long improvement takes depends on the starting point. Recovering from a utilization spike can take about one reporting cycle after the balance is paid down. Recovering from a late payment takes much longer, with its effect fading over about two years. In every case, recent on-time months count for more than older problems.

No one can promise a specific score by a specific date. These habits improve the odds; they don't guarantee a number.
```

### 24. minimum-due-and-interest00

`minimum-due-and-interest#00` · [11-minimum-due-and-interest.md](../../../corpus/11-minimum-due-and-interest.md) · part 1 of 3 · financial_literacy · 57 words / 87 tokens · queries 2,3,4,21,27,29  
Source: CreditCoach team (general education)

```text
Credit card bills, minimum amount due, and interest

Every credit card statement shows three important amounts and dates:
- **Total amount due**: everything you owe on the statement date.
- **Minimum amount due**: the smallest payment that keeps your account from being reported as late. It is usually a small percentage of the total.
- **Payment due date**: the date by which you must pay.
```

### 25. minimum-due-and-interest01

`minimum-due-and-interest#01` · [11-minimum-due-and-interest.md](../../../corpus/11-minimum-due-and-interest.md) · part 2 of 3 · financial_literacy · 158 words / 212 tokens · queries 2,3,4,21,27,29  
Source: CreditCoach team (general education)

```text
Credit card bills, minimum amount due, and interest

**What happens with each choice**
- **Pay the total amount due by the due date:** no interest is charged on purchases, and the account is reported as paid on time.
- **Pay at least the minimum but not the total:** the account stays on time, but interest is charged on the unpaid balance. Interest on Indian credit cards is usually charged monthly, and it adds up to a high annual rate. Many issuers also stop the interest-free period on new purchases while a balance is carried.
- **Pay less than the minimum, or pay late:** late fees and interest apply, and if the payment becomes 30 or more days past due it can seriously damage your score.

**The minimum-due trap.** Paying only the minimum every month keeps your record clean in the short term, but the balance shrinks very slowly while interest keeps building. A high carried balance also keeps your utilization high, which holds your score down.
```

### 26. minimum-due-and-interest02

`minimum-due-and-interest#02` · [11-minimum-due-and-interest.md](../../../corpus/11-minimum-due-and-interest.md) · part 3 of 3 · financial_literacy · 97 words / 128 tokens · queries 2,3,4,21,27,29  
Source: CreditCoach team (general education)

```text
Credit card bills, minimum amount due, and interest

**If you can't pay in full**
- Pay as much above the minimum as you can, and never less than the minimum.
- Ask your card issuer about converting the outstanding balance into EMIs. It usually costs less than carrying the balance at the card's standard interest rate, but check the interest rate and processing fee first.
- Stop adding new spending to the card until the balance is under control.
- Do not use an instant loan app or payday-style loan to pay a card bill. It usually replaces expensive debt with even more expensive debt.
```

### 27. planning-for-a-car-loan00

`planning-for-a-car-loan#00` · [12-planning-for-a-car-loan.md](../../../corpus/12-planning-for-a-car-loan.md) · part 1 of 3 · financial_literacy · 64 words / 92 tokens · queries 3,5,9,23,24,25,26  
Source: CreditCoach team, based on credit_score_factors_guide.pdf §1–§4

```text
Preparing your credit for a car loan (or any big loan)

If you plan to take a car loan (or a home or other large loan) within the next year or so, the months before you apply matter. Lenders look at your credit score and report, your income, and your existing EMIs. A stronger credit profile can mean a smoother approval and a better interest rate, though no lender's decision can be guaranteed in advance.
```

### 28. planning-for-a-car-loan01

`planning-for-a-car-loan#01` · [12-planning-for-a-car-loan.md](../../../corpus/12-planning-for-a-car-loan.md) · part 2 of 3 · financial_literacy · 151 words / 220 tokens · queries 3,5,9,23,24,25,26  
Source: CreditCoach team, based on credit_score_factors_guide.pdf §1–§4

```text
Preparing your credit for a car loan (or any big loan)

**A 12-month plan, in order of impact**
1. **Never miss a payment.** Payment history is the biggest factor, and a late payment in the months before you apply does the most damage. Put every card and EMI on auto-pay.
2. **Bring card utilization down.** Pay down the card with the highest utilization first, then keep each card and your total below about 30%, lower if possible. Utilization recovers quickly once lower balances are reported, so this is the fastest lever.
3. **Pause new credit applications.** Avoid new cards or loans for several months before the car loan. Each application adds a hard inquiry, which can dip the score and make lenders cautious.
4. **Check your credit report early.** Get your report a few months ahead so there is time to dispute any errors before a lender sees them.
5. **Keep old cards open** to protect your history length and total limit.
```

### 29. planning-for-a-car-loan02

`planning-for-a-car-loan#02` · [12-planning-for-a-car-loan.md](../../../corpus/12-planning-for-a-car-loan.md) · part 3 of 3 · financial_literacy · 120 words / 158 tokens · queries 3,5,9,23,24,25,26  
Source: CreditCoach team, based on credit_score_factors_guide.pdf §1–§4

```text
Preparing your credit for a car loan (or any big loan)

6. **Plan the EMI you can afford.** Lenders compare your total EMIs with your income. A car EMI that fits comfortably in your budget, alongside a down payment you have saved, lowers the risk of future missed payments.

**When you shop for the loan**
- Compare offers using eligibility checks that don't affect your score where possible.
- Submit full applications to a small number of lenders within a short window rather than spreading them out.

These steps are the habits most associated with a stronger credit profile. How much a score moves in 12 months depends on your starting point and on factors outside any plan, so treat any target as a goal to work toward, not a promise.
```

### 30. credit-goals-and-no-guarantees00

`credit-goals-and-no-guarantees#00` · [13-credit-goals-and-no-guarantees.md](../../../corpus/13-credit-goals-and-no-guarantees.md) · part 1 of 2 · financial_literacy · 158 words / 205 tokens · queries 3,5,6,11,25,28,35,36,37,38,39,40,41,42,43,44,50  
Source: CreditCoach team, based on credit_score_factors_guide.pdf §6–§7

```text
Setting a credit goal, and why no one can guarantee a score

**A good credit goal has three parts:** a target score, a target date, and a purpose. For example: "Reach 720 by next September so I can apply for a car loan." Writing down the purpose helps you make trade-offs, such as skipping a new card offer because it would add a hard inquiry before the car loan.

**Making the goal realistic.** Start from where you are and what is holding the score down:
- If the main issue is high card utilization, improvement can show up within a reporting cycle or two after balances come down.
- If the issue is a recent late payment, recovery is slower, because its effect fades over about two years.
- If your history is short, time itself is part of the plan, since accounts need to age.

A goal can be ambitious. If it is, plan the steps that give it the best chance and review progress every month or two.
```

### 31. credit-goals-and-no-guarantees01

`credit-goals-and-no-guarantees#01` · [13-credit-goals-and-no-guarantees.md](../../../corpus/13-credit-goals-and-no-guarantees.md) · part 2 of 2 · financial_literacy · 157 words / 213 tokens · queries 3,5,6,11,25,28,35,36,37,38,39,40,41,42,43,44,50  
Source: CreditCoach team, based on credit_score_factors_guide.pdf §6–§7

```text
Setting a credit goal, and why no one can guarantee a score

**Why no one can guarantee a score**
- Scores are calculated by the credit bureaus using models that are not public.
- Scores depend on information outside your plan: the dates lenders report, changes in how scores are calculated, and unexpected events that affect your finances.
- The same action can move two people's scores by different amounts, depending on their full history.

So any honest projection is educational: "this habit is commonly associated with improvement," not "you will reach 720." Be cautious of anyone, whether an app, an agent, or a "credit repair" company, who promises a specific score or a specific number of points by a date. Guaranteeing a point increase is a recognised red flag for a scam.

**What you can control:** paying on time, keeping utilization low, limiting new applications, keeping old accounts open, and checking your report for errors. Focusing on these consistently is the most reliable path toward any credit goal.
```

### 32. credit-report-and-disputes00

`credit-report-and-disputes#00` · [14-credit-report-and-disputes.md](../../../corpus/14-credit-report-and-disputes.md) · part 1 of 3 · financial_literacy · 76 words / 109 tokens · queries 1,6,24,30,34  
Source: CreditCoach team (general education on the Indian credit system)

```text
Reading your credit report and fixing errors

Your credit report is the record your score is calculated from. In India, each of the four credit bureaus (TransUnion CIBIL, Experian, Equifax, and CRIF High Mark) keeps its own report on you. RBI rules entitle you to one free full credit report a year from each bureau, which you can request on the bureau's website. Many banks and apps also show your score for free. Checking your own report or score does not lower it.
```

### 33. credit-report-and-disputes01

`credit-report-and-disputes#01` · [14-credit-report-and-disputes.md](../../../corpus/14-credit-report-and-disputes.md) · part 2 of 3 · financial_literacy · 146 words / 223 tokens · queries 1,6,24,30,34  
Source: CreditCoach team (general education on the Indian credit system)

```text
Reading your credit report and fixing errors

**What to look at**
- **Personal details:** name, date of birth, PAN, and addresses. Mistakes here can mix your record with someone else's.
- **Accounts:** every card and loan listed should be yours. Check balances, credit limits, and whether closed accounts are shown as closed.
- **Payment history (DPD):** each month should show 0, "000", or "STD" if you paid on time. Any days-past-due entry you don't recognise needs attention.
- **Enquiries:** each hard inquiry from a lender. An inquiry for credit you never applied for can be a sign of identity fraud.

**Fixing an error**
- Raise a dispute directly with the credit bureau on its website. Disputing is free.
- You can also contact the lender that reported the wrong information and ask it to correct its report to the bureau.
- Keep copies of statements or payment receipts that show the correct information.
```

### 34. credit-report-and-disputes02

`credit-report-and-disputes#02` · [14-credit-report-and-disputes.md](../../../corpus/14-credit-report-and-disputes.md) · part 3 of 3 · financial_literacy · 83 words / 123 tokens · queries 1,6,24,30,34  
Source: CreditCoach team (general education on the Indian credit system)

```text
Reading your credit report and fixing errors

**What can't be "fixed"**
Accurate negative information, such as a late payment that really happened, cannot be removed by a dispute or by paying a company. It fades with time as you build a record of on-time payments. Anyone who promises to delete accurate entries for a fee is making a false promise.

If a lender or bureau does not resolve your complaint, you can escalate to the lender's grievance officer and then to the RBI's Integrated Ombudsman through the RBI's complaint portal.
```

### 35. payday-loans-and-instant-loan-apps00

`payday-loans-and-instant-loan-apps#00` · [15-payday-loans-and-instant-loan-apps.md](../../../corpus/15-payday-loans-and-instant-loan-apps.md) · part 1 of 5 · product_risk · 70 words / 112 tokens · queries 4,12,29,31,32,44  
Source: credit_score_factors_guide.pdf §6; India digital-lending safeguards summarized by CreditCoach team

```text
Payday loans and instant loan apps — why they are high-risk

**What they are.** A payday loan is a small, short-term loan meant to be repaid from your next salary. In India, the most common form is an **instant loan app**: a mobile app offering a quick loan of a few thousand to tens of thousands of rupees, often approved in minutes with little paperwork. Cash-advance products, such as withdrawing cash on a credit card, work in a similar high-cost way.
```

### 36. payday-loans-and-instant-loan-apps01

`payday-loans-and-instant-loan-apps#01` · [15-payday-loans-and-instant-loan-apps.md](../../../corpus/15-payday-loans-and-instant-loan-apps.md) · part 2 of 5 · product_risk · 150 words / 220 tokens · queries 4,12,29,31,32,44  
Source: credit_score_factors_guide.pdf §6; India digital-lending safeguards summarized by CreditCoach team

```text
Payday loans and instant loan apps — why they are high-risk

**Why they are high-risk**
- **Very high cost.** Payday loans and cash-advance products often carry annual percentage rates far higher than standard credit. With instant loan apps, processing fees, "platform" fees, and short repayment periods can make the real annual cost extremely high, even when the advertised rate looks small.
- **They usually don't build your credit.** Many payday lenders don't report to the credit bureaus at all, so repaying on time may not help your score.
- **Missing a payment can hurt badly.** A missed payment can lead to collections activity, which damages a score. According to our reference guide, a collections account typically lowers a score by about 50 to 100 points and can stay on a report for up to seven years.
- **Debt spirals.** Borrowing from one app to repay another, or to pay a credit card bill, replaces one debt with a more expensive one.
```

### 37. payday-loans-and-instant-loan-apps02

`payday-loans-and-instant-loan-apps#02` · [15-payday-loans-and-instant-loan-apps.md](../../../corpus/15-payday-loans-and-instant-loan-apps.md) · part 3 of 5 · product_risk · 85 words / 130 tokens · queries 4,12,29,31,32,44  
Source: credit_score_factors_guide.pdf §6; India digital-lending safeguards summarized by CreditCoach team

```text
Payday loans and instant loan apps — why they are high-risk

- **Unregulated apps.** Some apps are not linked to any RBI-regulated lender. They have been associated with hidden charges, misuse of phone contacts and photos, and abusive recovery practices.

**Using a payday loan to pay a credit card bill** is almost always a bad trade. It swaps card interest for an even higher cost, adds a new debt that may not help your score, and risks collections if the short deadline is missed. Safer options are covered in "Safer alternatives when you're short of money."
```

### 38. payday-loans-and-instant-loan-apps03

`payday-loans-and-instant-loan-apps#03` · [15-payday-loans-and-instant-loan-apps.md](../../../corpus/15-payday-loans-and-instant-loan-apps.md) · part 4 of 5 · product_risk · 108 words / 157 tokens · queries 4,12,29,31,32,44  
Source: credit_score_factors_guide.pdf §6; India digital-lending safeguards summarized by CreditCoach team

```text
Payday loans and instant loan apps — why they are high-risk

**Safeguards in India.** Under RBI rules on digital lending:
- The actual lender must be a bank or an RBI-regulated NBFC, and the app must name it.
- The loan should be paid directly into your bank account, and repaid directly to the lender, not through a third party's account.
- You should receive a Key Fact Statement showing the all-in annual percentage rate (APR) and every fee before you sign.
- Digital loans come with a cooling-off period during which you can exit by repaying the principal and the proportionate cost, without a penalty.
- Apps should not demand access to your contacts, photos, or media files.
```

### 39. payday-loans-and-instant-loan-apps04

`payday-loans-and-instant-loan-apps#04` · [15-payday-loans-and-instant-loan-apps.md](../../../corpus/15-payday-loans-and-instant-loan-apps.md) · part 5 of 5 · product_risk · 52 words / 100 tokens · queries 4,12,29,31,32,44  
Source: credit_score_factors_guide.pdf §6; India digital-lending safeguards summarized by CreditCoach team

```text
Payday loans and instant loan apps — why they are high-risk

**Red flags:** no named RBI-regulated lender, fees deducted upfront, pressure to decide immediately, requests for access to contacts or gallery, or threats and harassment over repayment. Unauthorised lenders can be reported on the RBI's Sachet portal, and harassment or fraud can be reported to the national cyber crime helpline (1930) or cybercrime.gov.in.
```

### 40. credit-repair-scams00

`credit-repair-scams#00` · [16-credit-repair-scams.md](../../../corpus/16-credit-repair-scams.md) · part 1 of 2 · product_risk · 122 words / 169 tokens · queries 4,6,12,30,34,44  
Source: credit_score_factors_guide.pdf §6; CreditCoach team

```text
Credit repair services and score-guarantee scams

After a score drop, you may see advertisements offering to "fix" or "boost" your credit score fast. Some of these are scams, and even the honest ones cannot do anything you can't do yourself for free.

**Red flags.** Any company that guarantees it can raise your score by a specific number of points, or asks for payment before doing any work, is a red flag under general consumer-protection guidance. Other warning signs:
- Promises to remove accurate late payments, defaults, or collections from your report.
- Advice to create a "new credit identity" or to hide information from lenders.
- Pressure to pay quickly, or requests for your bank passwords, OTPs, or PAN and Aadhaar details beyond what a legitimate service needs.
```

### 41. credit-repair-scams01

`credit-repair-scams#01` · [16-credit-repair-scams.md](../../../corpus/16-credit-repair-scams.md) · part 2 of 2 · product_risk · 141 words / 190 tokens · queries 4,6,12,30,34,44  
Source: credit_score_factors_guide.pdf §6; CreditCoach team

```text
Credit repair services and score-guarantee scams

**What is true about fixing credit**
- Only the lender that reported the information, and the credit bureau, can correct your report. No outside company can change it directly.
- Genuine errors can be disputed with the credit bureau for free. You don't need to pay anyone to raise a dispute.
- Accurate negative information cannot be deleted early. It fades over time as you build a record of on-time payments.
- No one can guarantee a specific score or point increase, because scores are calculated by the bureaus using models that aren't public.

**Where to get legitimate help.** Free credit counselling is available in India, for example through financial literacy and credit counselling centres run by banks. They can help you understand your report, make a repayment plan, and talk to lenders, without an upfront fee or a guaranteed-outcome promise.
```

### 42. safer-alternatives00

`safer-alternatives#00` · [17-safer-alternatives.md](../../../corpus/17-safer-alternatives.md) · part 1 of 4 · product_risk · 40 words / 54 tokens · queries 4,12,21,29,32,33,44  
Source: CreditCoach team (general education)

```text
Safer alternatives when you're short of money

If you are struggling to pay a credit card bill or an EMI, it is tempting to reach for the fastest money available, such as an instant loan app. There are usually safer options. Try them in roughly this order.
```

### 43. safer-alternatives01

`safer-alternatives#01` · [17-safer-alternatives.md](../../../corpus/17-safer-alternatives.md) · part 2 of 4 · product_risk · 160 words / 222 tokens · queries 4,12,21,29,32,33,44  
Source: CreditCoach team (general education)

```text
Safer alternatives when you're short of money

1. **Pay at least the minimum amount due, on time.** This keeps the account from being reported as late, which protects your score while you sort out the rest. Interest is charged on the unpaid balance, so pay more whenever you can.
2. **Talk to your card issuer or lender early.** Before a payment is missed, ask about a payment plan, a revised due date, or converting the card's outstanding balance into EMIs. Converting to EMIs usually costs less than carrying the balance at the card's standard rate; check the interest rate and processing fee first.
3. **A balance transfer, if you qualify.** Some card issuers let you move an outstanding balance to another card at a lower interest rate for a set period. Check the fees, the rate after the offer ends, and whether applying for a new card adds a hard inquiry.
4. **Use your emergency fund**, or a planned withdrawal from savings, rather than new high-cost debt.
```

### 44. safer-alternatives02

`safer-alternatives#02` · [17-safer-alternatives.md](../../../corpus/17-safer-alternatives.md) · part 3 of 4 · product_risk · 149 words / 217 tokens · queries 4,12,21,29,32,33,44  
Source: CreditCoach team (general education)

```text
Safer alternatives when you're short of money

5. **Cut and pause.** Stop new spending on the card and review subscriptions and non-essential costs for a couple of months.
6. **A personal loan from a bank or RBI-regulated NBFC**, if you truly need to borrow. Compare the all-in annual cost (APR) on the Key Fact Statement, and borrow only what you can repay.
7. **Free credit counselling.** Financial literacy and credit counselling centres run by banks offer free guidance on budgeting, repayment plans, and talking to lenders.

**What to avoid**
- Payday loans and instant loan apps, especially to pay another debt.
- Borrowing from one app to repay another.
- Anyone promising to "settle" or "erase" your debt or credit record for an upfront fee.
- Settling a debt for less than you owe without understanding the consequences: a "settled" status on your report can hurt your score and may make future loans harder to get.
```

### 45. safer-alternatives03

`safer-alternatives#03` · [17-safer-alternatives.md](../../../corpus/17-safer-alternatives.md) · part 4 of 4 · product_risk · 29 words / 59 tokens · queries 4,12,21,29,32,33,44  
Source: CreditCoach team (general education)

```text
Safer alternatives when you're short of money

If a lender or recovery agent harasses you, note the details and complain to the lender's grievance officer. If that doesn't resolve it, escalate to the RBI's Integrated Ombudsman.
```
