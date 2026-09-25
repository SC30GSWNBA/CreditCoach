"""Task 6, step 2 of 3: generate each user's accounts and 12-month score history -> ``data/accounts.csv``, ``data/score_history.csv``.

Reads:
    data/users.csv                            The 13 profiles from step 1.
    sample_data/credit_profile_sample.xlsx    Aravind's (USR-001) original data, in USD.
Writes:
    data/accounts.csv         One row per card or loan: balance and limit in INR, and card utilization.
    data/score_history.csv    One row per user per month (Oct 2025 to Sep 2026): score and what changed.

Indian consumer context: amounts in INR, scores on the 300-900 range used by Indian credit bureaus,
and Indian loan types (education, car, home, personal, instant loan app).

How the data follows each profile:
    Accounts  Exactly the cards and loans the person reported. Card limits scale with years worked, and
              balances fall inside their stated card-usage band. People with no cards and no loans get no
              accounts and no score history (no credit file).
    Scores    A starting score from their self-reported score, then a month-by-month story that fits their
              scenario (steady improver, hard inquiries, late payment, utilization spike, ...; see
              ``SCENARIOS``). Every monthly change must fall within the range allowed for its factor
              (``FACTOR_RANGES``), whose negative ranges come from credit_score_factors_guide.pdf.
    USR-001   Scores copied unchanged from the sample; amounts scaled x50 into INR, so every ratio is
              identical (79% on the main card, 37.4% overall).

The output is deterministic (each user has a fixed random seed), and nothing is written unless every
validation check passes (see ``validate``).

Run:
    uv run python scripts/synthetic/step2_accounts_scores.py
"""

import csv
import random

import pandas as pd

from creditcoach import config

DATA = config.ROOT / "data"
MONTHS = [f"{y}-{m:02d}-01" for y, m in [(2025, 10), (2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 10)]]

# Allowed monthly score change per factor. Negative ranges: guide's Score Impact Reference Table.
# Positive ranges, "Utilization increase" (stays under 30%) and "Stable": our assumptions for synthetic data.
FACTOR_RANGES = {
    "Stable (no major change)": (-2, 2),
    "On-time payments": (2, 8),
    "Account age increase": (2, 6),
    "Utilization decreased": (5, 15),
    "Utilization increase": (-10, -1),
    "Utilization spike": (-40, -10),
    "Hard inquiry": (-10, -2),
    "Late payment (30+ days)": (-110, -60),
}

SCORE_MIN, SCORE_MAX = 300, 900  # Indian bureau (CIBIL-style) range
SAMPLE_TO_INR = 50  # fixed scale for USR-001's USD sample amounts: keeps every ratio identical
SAMPLE_TYPE_TO_INDIA = {"Student Loan": "Education Loan", "Auto Loan": "Car Loan", "Retail Card": "Credit Card"}

CARD_LIMIT_BY_YEARS = {"Less than 1 year": (30000, 75000), "1 to 3 years": (75000, 150000),
                       "4 to 8 years": (150000, 300000), "More than 8 years": (300000, 500000)}
USAGE_RANGE = {"Less than 10%": (0.03, 0.09), "10 to 30%": (0.12, 0.28), "31 to 70%": (0.35, 0.65),
               "More than 70%": (0.72, 0.85)}
UNKNOWN_USAGE = (0.35, 0.50)  # has a card but "I don't know" its usage: model an unnoticed high balance
LOANS = {"Education / student loan": ("Education Loan", 300000, 1500000),
         "Home loan": ("Home Loan", 2000000, 7500000),
         "Car loan": ("Car Loan", 300000, 800000),
         "Personal loan": ("Personal Loan", 100000, 500000)}
BASELINE_BY_SELF_REPORT = {"Excellent": (790, 815), "Good": (730, 760), "Average / fair": (650, 690)}

# Score-story scenario per user (see data/README.md). Everyone else is a steady improver.
SCENARIOS = {
    "USR-003": "Hard inquiries (car loan shopping)",
    "USR-005": "Loan-only file (no credit card)",
    "USR-004": "No credit file",
    "USR-007": "No credit file",
    "USR-009": "Late payment recovery",
    "USR-011": "Unnoticed utilization spike",
    "USR-012": "High utilization and debt stress",
}


def n_cards(value: str) -> int:
    """Convert the "credit_cards" answer to a number of cards: "0" -> 0, "1" -> 1, "2 to 3" -> 2."""
    return {"0": 0, "1": 1, "2 to 3": 2}.get(value, 0)


def build_accounts(u: dict, rng: random.Random, next_id) -> list[dict]:
    """Create one user's credit cards and loans from their profile.

    Args:
        u: A row from users.csv.
        rng: The user's seeded random generator (for limits and balances within the allowed bands).
        next_id: Function that returns the next free account id, e.g. "ACC-06".

    Returns:
        Account rows for accounts.csv. Loans have no limit or utilization.
    """
    rows = []
    cards = n_cards(u["credit_cards"])
    lo, hi = USAGE_RANGE.get(u["card_usage"], UNKNOWN_USAGE)
    for _ in range(cards):
        limit = rng.randrange(*CARD_LIMIT_BY_YEARS[u["years_working"]], 5000)
        balance = round(limit * rng.uniform(lo, hi) / 100) * 100
        rows.append(("Credit Card", balance, limit))
    for loan in [x.strip() for x in u["loans"].split(";")]:
        if loan in LOANS:
            kind, lo_bal, hi_bal = LOANS[loan]
            rows.append((kind, rng.randrange(lo_bal, hi_bal, 5000), None))
    if u["risky_product_exposure"] == "Yes, I've used one":
        rows.append(("Instant Loan App", rng.randrange(5000, 25000, 1000), None))
    return [{"account_id": next_id(), "user_id": u["user_id"], "account_type": t, "balance_inr": b,
             "credit_limit_inr": lim or "", "utilization_ratio": round(b / lim, 2) if lim else ""}
            for t, b, lim in rows]


def story(uid: str, u: dict, rng: random.Random) -> list[str]:
    """Choose what changes each month for a user, based on their scenario.

    Args:
        uid: The user id, used to look up their scenario in ``SCENARIOS`` (default "Steady improver").
        u: The user's row from users.csv (used to vary steady improvers, e.g. "Excellent" scores hold).
        rng: The user's random generator (not used for the labels, which are fixed per scenario).

    Returns:
        11 factor labels, one for each month from Nov 2025 to Sep 2026 (Oct 2025 is the baseline).
    """
    scenario = SCENARIOS.get(uid, "Steady improver")
    base = ["On-time payments"] * 11
    base[5] = "Account age increase"  # Apr 2026
    if scenario == "Steady improver":
        if u["self_reported_score"] == "Excellent":  # near the top of the scale, scores mostly hold
            base = ["Stable (no major change)" if i % 2 else "On-time payments" for i in range(11)]
        if u["card_usage"] in ("10 to 30%", "") or u["pays_card"].startswith("More than the minimum"):
            base[2], base[3] = "Utilization increase", "Utilization decreased"  # Jan dip, Feb recovery
    elif scenario == "Hard inquiries (car loan shopping)":
        base[9], base[10] = "Hard inquiry", "Hard inquiry"  # Aug and Sep applications
    elif scenario == "Loan-only file (no credit card)":
        base = ["On-time payments" if i % 3 == 0 else "Stable (no major change)" for i in range(11)]
    elif scenario == "Late payment recovery":
        base[5] = "Late payment (30+ days)"  # Apr 2026
    elif scenario == "Unnoticed utilization spike":
        base[8], base[9], base[10] = "Utilization increase", "Utilization spike", "Stable (no major change)"
    elif scenario == "High utilization and debt stress":
        base = ["On-time payments", "Utilization increase", "Utilization increase", "Stable (no major change)",
                "Hard inquiry", "Utilization spike", "On-time payments", "Utilization increase",
                "Utilization spike", "Stable (no major change)", "Utilization spike"]
    return base


def build_scores(u: dict, rng: random.Random) -> list[dict]:
    """Create one user's 12 monthly score records: a baseline in Oct 2025, then one change per month.

    Args:
        u: A row from users.csv.
        rng: The user's seeded random generator (for the exact change within each factor's range).

    Returns:
        Score rows for score_history.csv, or an empty list for users with no credit file.
    """
    uid = u["user_id"]
    if SCENARIOS.get(uid) == "No credit file":
        return []
    lo, hi = BASELINE_BY_SELF_REPORT.get(u["self_reported_score"], (690, 715))
    score = rng.randint(lo, hi)
    rows = [{"user_id": uid, "date": MONTHS[0], "score": score, "primary_factor_change": "Baseline"}]
    for month, label in zip(MONTHS[1:], story(uid, u, rng)):
        f_lo, f_hi = FACTOR_RANGES[label]
        if label == "Late payment (30+ days)":
            f_lo, f_hi = -95, -70  # middle of the guide's range
        score = min(SCORE_MAX, max(SCORE_MIN, score + rng.randint(f_lo, f_hi)))
        rows.append({"user_id": uid, "date": month, "score": score, "primary_factor_change": label})
    return rows


def sample_rows() -> tuple[list[dict], list[dict]]:
    """Load Aravind's (USR-001) data from the sample workbook, converted to INR and Indian account types.

    Returns:
        ``(score_rows, account_rows)``. Scores are unchanged; amounts are multiplied by ``SAMPLE_TO_INR``.
    """
    s = pd.read_excel(config.SAMPLE_DATA, sheet_name="ScoreHistory")
    a = pd.read_excel(config.SAMPLE_DATA, sheet_name="Accounts")
    scores = [{"user_id": r.user_id, "date": str(r.date)[:10], "score": int(r.score),
               "primary_factor_change": r.primary_factor_change} for r in s.itertuples()]
    accounts = [{"account_id": r.account_id, "user_id": r.user_id,
                 "account_type": SAMPLE_TYPE_TO_INDIA.get(r.account_type, r.account_type),
                 "balance_inr": int(r.balance_usd) * SAMPLE_TO_INR,
                 "credit_limit_inr": "" if pd.isna(r.credit_limit_usd) else int(r.credit_limit_usd) * SAMPLE_TO_INR,
                 "utilization_ratio": "" if pd.isna(r.utilization_ratio) else float(r.utilization_ratio)}
                for r in a.itertuples()]
    return scores, accounts


def in_range(label: str, delta: int) -> bool:
    """Check that a monthly score change is allowed for its factor label.

    Combined labels such as "Hard inquiry + utilization spike" allow the sum of their parts' ranges.

    Args:
        label: The ``primary_factor_change`` text, e.g. "Utilization spike".
        delta: The score change from the previous month.

    Returns:
        True if the label is known and the change falls within its range.
    """
    lo = hi = 0
    for part in label.replace("(new card)", "").split(" + "):
        key = next((k for k in FACTOR_RANGES if k.lower() == part.strip().lower()), None)
        if key is None:
            return False
        lo, hi = lo + FACTOR_RANGES[key][0], hi + FACTOR_RANGES[key][1]
    return lo <= delta <= hi


def validate(users: list[dict], scores: list[dict], accounts: list[dict]) -> list[str]:
    """Check the generated data for consistency before anything is written.

    Checks: accounts and scores belong to known users; card counts match each interview answer; scores stay
    within 300-900; every monthly change is within its factor's range; anyone above 30% utilization shows a
    utilization change in their last 3 months; utilization ratios equal balance / limit; and USR-001's scores
    and ratios match the sample.

    Returns:
        A list of problems. Empty means the data is valid.
    """
    errors = []
    ids = {u["user_id"] for u in users}
    s, a = pd.DataFrame(scores), pd.DataFrame(accounts)
    errors += [f"{x}: account for unknown user" for x in set(a.user_id) - ids]
    errors += [f"{x}: score for unknown user" for x in set(s.user_id) - ids]
    if a.account_id.duplicated().any():
        errors.append("duplicate account_id")
    for u in users:
        uid = u["user_id"]
        g = s[s.user_id == uid].sort_values("date") if len(s) else s
        acc = a[a.user_id == uid]
        if uid != "USR-001" and (acc.account_type == "Credit Card").sum() != n_cards(u["credit_cards"]):
            errors.append(f"{uid}: card count doesn't match interview answer")
        if len(acc) == 0 and len(g):
            errors.append(f"{uid}: score history without any accounts")
        if not g.score.between(SCORE_MIN, SCORE_MAX).all():
            errors.append(f"{uid}: score outside {SCORE_MIN}-{SCORE_MAX}")
        for prev, row in zip(g.itertuples(), list(g.itertuples())[1:]):
            if not in_range(row.primary_factor_change, row.score - prev.score):
                errors.append(f"{uid} {row.date}: '{row.primary_factor_change}' {row.score - prev.score:+d} out of range")
        rev = acc[acc.credit_limit_inr != ""]
        if len(rev) and len(g):
            util = rev.balance_inr.sum() / rev.credit_limit_inr.astype(float).sum()
            recent = " ".join(g.primary_factor_change.tail(3)).lower()
            if util > 0.30 and "utilization" not in recent:
                errors.append(f"{uid}: utilization {util:.0%} but no utilization change in the last 3 months")
    for r in accounts:
        if r["credit_limit_inr"] != "" and r["utilization_ratio"] != round(r["balance_inr"] / r["credit_limit_inr"], 2):
            errors.append(f"{r['account_id']}: utilization_ratio mismatch")
    sample = pd.read_excel(config.SAMPLE_DATA, sheet_name="ScoreHistory")
    if list(s[s.user_id == "USR-001"].score) != list(sample.score):
        errors.append("USR-001 scores differ from sample_data")
    sample_util = pd.read_excel(config.SAMPLE_DATA, sheet_name="Accounts").utilization_ratio.dropna().tolist()
    if a[(a.user_id == "USR-001") & (a.utilization_ratio != "")].utilization_ratio.astype(float).tolist() != sample_util:
        errors.append("USR-001 utilization ratios differ from sample_data")
    return errors


def write_csv(path, rows, fields):
    """Write ``rows`` (dicts) to a CSV file at ``path`` with the given column order."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    """Generate, validate, and write accounts.csv and score_history.csv.

    Raises:
        SystemExit: With the list of problems if validation fails (nothing is written in that case).
    """
    users = pd.read_csv(DATA / "users.csv", dtype=str, keep_default_na=False).to_dict("records")
    scores, accounts = sample_rows()
    counter = iter(range(len(accounts) + 1, 1000))

    for u in users:
        if u["user_id"] == "USR-001":
            continue
        rng = random.Random(u["user_id"])
        accounts += build_accounts(u, rng, lambda: f"ACC-{next(counter):02d}")
        scores += build_scores(u, rng)

    errors = validate(users, scores, accounts)
    if errors:
        raise SystemExit("Validation failed:\n  " + "\n  ".join(errors))
    write_csv(DATA / "accounts.csv", accounts, list(accounts[0].keys()))
    write_csv(DATA / "score_history.csv", scores, list(scores[0].keys()))
    print(f"Validation passed. Wrote {len(accounts)} accounts and {len(scores)} score records "
          f"for {len({s['user_id'] for s in scores})} users with history ({len(users)} users total).")


if __name__ == "__main__":
    main()
