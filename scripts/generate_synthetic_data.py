"""Task 6: generate the synthetic CreditCoach dataset in data/.

USR-001 (Aravind) is copied unchanged from sample_data/credit_profile_sample.xlsx. USR-002 to USR-006
are authored scenarios whose habits and bands are drawn from the 12 user interviews (aggregates in
data/README.md). Every monthly score change is checked against the factor ranges in
credit_score_factors_guide.pdf, so the data never contradicts the RAG corpus.

    uv run python scripts/generate_synthetic_data.py
"""

import csv
from datetime import date

import pandas as pd

from creditcoach import config

DATA_DIR = config.ROOT / "data"
EVIDENCE = config.ROOT / "docs" / "evidence" / "week-1" / "task-06-dataset-summary.md"

# Allowed monthly score change per factor label. Negative ranges are from the guide's Score Impact
# Reference Table; positive ranges and "Utilization increase" (a rise that stays below the 30% level)
# are our own conservative assumptions for synthetic data.
FACTOR_RANGES = {
    "On-time payments": (2, 8),
    "Account age increase": (2, 6),
    "Utilization decreased": (5, 15),
    "Utilization increase": (-10, -1),
    "Utilization spike": (-40, -10),  # guide: spike above 30%
    "Hard inquiry": (-10, -2),  # guide
    "Late payment (30+ days)": (-110, -60),  # guide
}

# Month-by-month score events: (factor_change label, score delta). The first entry is the baseline score.
START = date(2025, 10, 1)  # same 12-month window as the USR-001 sample (Oct 2025 to Sep 2026)

USERS = [
    {
        "user_id": "USR-002", "first_name": "Meera", "age": 24, "years_working": "1 to 3 years",
        "scenario": "Thin file",
        "persona": "Opened her first and only credit card in May 2026, so her credit file is only a few months old. "
                   "Checks her score rarely and isn't sure what counts.",
        "emi_pct_band": "0%, no loans", "invest_pct_band": "21 to 35%", "emergency_fund_band": "4 to 6 months",
        "interview_basis": "3 of 12 interviewees had no credit card; 3 of 12 didn't know their score.",
        "start": date(2026, 6, 1), "baseline": 648,
        "events": [("On-time payments", 4), ("Account age increase", 3), ("On-time payments", 5)],
        "accounts": [("ACC-06", "Credit Card", 80, 1000)],
    },
    {
        "user_id": "USR-003", "first_name": "Rohan", "age": 28, "years_working": "4 to 8 years",
        "scenario": "Steady improver",
        "persona": "Pays his one card in full every month and keeps usage low while repaying an education loan. "
                   "Invests through monthly SIPs.",
        "emi_pct_band": "1 to 10%", "invest_pct_band": "21 to 35%", "emergency_fund_band": "More than 6 months",
        "interview_basis": "Most common interview pattern: 1 card, paid in full, under 30% usage, education loan, "
                           "never late, invests in mutual funds.",
        "start": START, "baseline": 702,
        "events": [("On-time payments", 5), ("On-time payments", 4), ("Utilization increase", -4),
                   ("Utilization decreased", 6), ("On-time payments", 5), ("Account age increase", 3),
                   ("On-time payments", 4), ("On-time payments", 6), ("On-time payments", 3),
                   ("Account age increase", 4), ("On-time payments", 5)],
        "accounts": [("ACC-07", "Credit Card", 240, 3000), ("ACC-08", "Student Loan", 5200, None)],
    },
    {
        "user_id": "USR-004", "first_name": "Priya", "age": 30, "years_working": "4 to 8 years",
        "scenario": "Hard inquiries",
        "persona": "Planning to buy a car. Applied for a new credit card in August and pre-applied for a car loan in "
                   "September, and saw two small dips in a row.",
        "emi_pct_band": "1 to 10%", "invest_pct_band": "11 to 20%", "emergency_fund_band": "1 to 3 months",
        "interview_basis": "Car purchase was a stated goal for 2 of 12 interviewees; 6 of 12 knew a new application "
                           "causes a small, temporary dip, but 6 of 12 did not.",
        "start": START, "baseline": 694,
        "events": [("On-time payments", 4), ("On-time payments", 3), ("On-time payments", 5),
                   ("Account age increase", 3), ("On-time payments", 4), ("On-time payments", 6),
                   ("On-time payments", 3), ("Utilization decreased", 5), ("On-time payments", 4),
                   ("Hard inquiry", -7), ("Hard inquiry", -5)],
        "accounts": [("ACC-09", "Credit Card", 610, 4000), ("ACC-10", "Credit Card", 150, 2500),
                     ("ACC-11", "Student Loan", 3100, None)],
    },
    {
        "user_id": "USR-005", "first_name": "Kabir", "age": 33, "years_working": "More than 8 years",
        "scenario": "Late payment recovery",
        "persona": "Missed a card payment by more than 30 days in March 2026 while travelling, and has paid on time "
                   "every month since. Also repaying a home loan.",
        "emi_pct_band": "21 to 35%", "invest_pct_band": "11 to 20%", "emergency_fund_band": "1 to 3 months",
        "interview_basis": "3 of 12 interviewees had a home loan. No interviewee reported a late payment (11 never, "
                           "1 preferred not to say), so this profile exists for coverage of the guide's biggest factor.",
        "start": START, "baseline": 741,
        "events": [("On-time payments", 3), ("On-time payments", 4), ("On-time payments", 2),
                   ("On-time payments", 3), ("Late payment (30+ days)", -86), ("On-time payments", 6),
                   ("On-time payments", 5), ("On-time payments", 7), ("On-time payments", 6),
                   ("Account age increase", 4), ("On-time payments", 6)],
        "accounts": [("ACC-12", "Credit Card", 1100, 5000), ("ACC-13", "Home Loan", 142000, None)],
    },
    {
        "user_id": "USR-006", "first_name": "Dev", "age": 36, "years_working": "More than 8 years",
        "scenario": "High utilization and debt stress",
        "persona": "Carries a balance above 70% of his card limit, pays more than the minimum but not in full, and "
                   "took a personal loan and an instant cash app loan to cover expenses. Has little emergency savings.",
        "emi_pct_band": "More than 35%", "invest_pct_band": "1 to 10%", "emergency_fund_band": "Less than 1 month",
        "interview_basis": "Based on one interviewee pattern: over 70% card usage, home plus personal loan, more than "
                           "35% of pay on repayments, no regular investing, and prior use of an instant cash loan.",
        "start": START, "baseline": 688,
        "events": [("On-time payments", 3), ("Utilization increase", -6), ("Utilization increase", -5),
                   ("On-time payments", 2), ("Hard inquiry", -8), ("Utilization spike", -14),
                   ("On-time payments", 3), ("Utilization increase", -4), ("Utilization spike", -12),
                   ("Utilization increase", -3), ("Utilization spike", -11)],
        "accounts": [("ACC-14", "Credit Card", 4450, 6000), ("ACC-15", "Personal Loan", 9800, None),
                     ("ACC-16", "Instant Cash Loan", 400, None)],
    },
]

USR_001_META = {
    "user_id": "USR-001", "first_name": "Aravind", "age": 22, "years_working": "Less than 1 year",
    "scenario": "Utilization spike + hard inquiry",
    "persona": "requirements.md persona. First full-time job; score dropped 20 points this month.",
    "emi_pct_band": "11 to 20%", "invest_pct_band": "1 to 10%", "emergency_fund_band": "1 to 3 months",
    "interview_basis": "Seed profile from sample_data (unchanged). Salary bands are our assumption.",
}


def factor_in_range(label: str, delta: int) -> bool:
    parts = [p.strip() for p in label.replace("(new card)", "").split(" + ")]
    lo = hi = 0
    for p in parts:
        key = next((k for k in FACTOR_RANGES if k.lower() == p.lower()), None)
        if key is None:
            return False
        lo, hi = lo + FACTOR_RANGES[key][0], hi + FACTOR_RANGES[key][1]
    return lo <= delta <= hi


def month_seq(start: date, n: int) -> list[date]:
    out, y, m = [], start.year, start.month
    for _ in range(n):
        out.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def build() -> tuple[list[dict], list[dict], list[dict]]:
    sample_scores = pd.read_excel(config.SAMPLE_DATA, sheet_name="ScoreHistory")
    sample_accounts = pd.read_excel(config.SAMPLE_DATA, sheet_name="Accounts")

    users = [USR_001_META]
    scores = [{"user_id": r.user_id, "date": str(r.date)[:10], "score": int(r.score),
               "primary_factor_change": r.primary_factor_change} for r in sample_scores.itertuples()]
    accounts = [{"account_id": r.account_id, "user_id": r.user_id, "account_type": r.account_type,
                 "balance_usd": int(r.balance_usd),
                 "credit_limit_usd": "" if pd.isna(r.credit_limit_usd) else int(r.credit_limit_usd),
                 "utilization_ratio": "" if pd.isna(r.utilization_ratio) else float(r.utilization_ratio)}
                for r in sample_accounts.itertuples()]

    for u in USERS:
        users.append({k: v for k, v in u.items() if k not in ("start", "baseline", "events", "accounts")})
        dates = month_seq(u["start"], len(u["events"]) + 1)
        score = u["baseline"]
        scores.append({"user_id": u["user_id"], "date": dates[0].isoformat(), "score": score,
                       "primary_factor_change": "Baseline"})
        for d, (label, delta) in zip(dates[1:], u["events"]):
            score += delta
            scores.append({"user_id": u["user_id"], "date": d.isoformat(), "score": score,
                           "primary_factor_change": label})
        for acc_id, acc_type, bal, limit in u["accounts"]:
            accounts.append({"account_id": acc_id, "user_id": u["user_id"], "account_type": acc_type,
                             "balance_usd": bal, "credit_limit_usd": limit or "",
                             "utilization_ratio": round(bal / limit, 2) if limit else ""})
    return users, scores, accounts


def validate(users, scores, accounts) -> list[str]:
    errors = []
    df = pd.DataFrame(scores)
    for uid, g in df.groupby("user_id"):
        g = g.sort_values("date")
        if not g.score.between(300, 850).all():
            errors.append(f"{uid}: score outside 300-850")
        months = pd.to_datetime(g.date).dt.to_period("M")
        if not (months.diff().dropna().apply(lambda x: x.n) == 1).all():
            errors.append(f"{uid}: months not contiguous")
        for prev, row in zip(g.itertuples(), list(g.itertuples())[1:]):
            if not factor_in_range(row.primary_factor_change, row.score - prev.score):
                errors.append(f"{uid} {row.date}: '{row.primary_factor_change}' delta {row.score - prev.score:+d} out of range")
    for a in accounts:
        if a["credit_limit_usd"] != "" and a["utilization_ratio"] != round(a["balance_usd"] / a["credit_limit_usd"], 2):
            errors.append(f"{a['account_id']}: utilization_ratio mismatch")
    sample = pd.read_excel(config.SAMPLE_DATA, sheet_name="ScoreHistory")
    ours = df[df.user_id == "USR-001"].reset_index(drop=True)
    if list(ours.score) != list(sample.score) or list(ours.primary_factor_change) != list(sample.primary_factor_change):
        errors.append("USR-001 differs from sample_data")
    return errors


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def summary(users, scores, accounts) -> str:
    df = pd.DataFrame(scores)
    acc = pd.DataFrame(accounts)
    lines = ["# Task 6 Evidence: Synthetic Dataset Summary\n",
             "*Generated by `uv run python scripts/generate_synthetic_data.py`. Files: `data/users.csv`, "
             "`data/score_history.csv`, `data/accounts.csv`.*\n",
             f"**{len(users)} user profiles · {len(df)} monthly score records · {len(acc)} accounts**\n",
             "| User | Name | Scenario | Months of history | Period | Score first → latest | Latest factor change | Accounts | Revolving utilization |",
             "|---|---|---|---|---|---|---|---|---|"]
    for u in users:
        g = df[df.user_id == u["user_id"]].sort_values("date")
        a = acc[acc.user_id == u["user_id"]]
        rev = a[a.credit_limit_usd != ""]
        util = rev.balance_usd.sum() / rev.credit_limit_usd.astype(float).sum() if len(rev) else float("nan")
        lines.append(f"| {u['user_id']} | {u['first_name']} | {u['scenario']} | {len(g)} | "
                     f"{g.date.iloc[0][:7]} to {g.date.iloc[-1][:7]} | {g.score.iloc[0]} → {g.score.iloc[-1]} | "
                     f"{g.primary_factor_change.iloc[-1]} | {len(a)} ({', '.join(a.account_type)}) | "
                     f"${rev.balance_usd.sum():,} / ${rev.credit_limit_usd.astype(float).sum():,.0f} = {util:.1%} |")
    lines += ["", f"**Validation:** all checks passed (scores within 300–850, months contiguous, every monthly "
                  f"change within its factor range, utilization ratios match balance ÷ limit, USR-001 identical to "
                  f"`sample_data`)."]
    return "\n".join(lines) + "\n"


def main() -> None:
    users, scores, accounts = build()
    errors = validate(users, scores, accounts)
    if errors:
        raise SystemExit("Validation failed:\n" + "\n".join(errors))
    DATA_DIR.mkdir(exist_ok=True)
    write_csv(DATA_DIR / "users.csv", users)
    write_csv(DATA_DIR / "score_history.csv", scores)
    write_csv(DATA_DIR / "accounts.csv", accounts)
    text = summary(users, scores, accounts)
    EVIDENCE.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
