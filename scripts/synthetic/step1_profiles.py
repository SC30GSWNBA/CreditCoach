"""Task 6, step 1 of 3: build one synthetic user profile per interviewee -> ``data/users.csv``.

Reads:
    user_interviews/CreditCoach_User_Profiles.xlsx   12 interview responses (dummy participants).
Writes:
    data/users.csv   13 users: USR-001 (Aravind, the requirements.md persona) plus USR-002..USR-013, one
                     per interview, in interview order (P1 -> USR-002, ..., P12 -> USR-013).

For each interviewee it keeps their answers (cards held, card usage, loans, savings, goals, and so on,
in the questionnaire's wording), scores their credit knowledge from 0 to 6 (questions 7-12), gives them a
fictional first name matching the recorded gender, and picks an age inside their age band that is
consistent with their years of work. For Aravind, fields the persona doesn't state are left blank.

Run:
    uv run python scripts/synthetic/step1_profiles.py

Next: step2_accounts_scores.py builds each user's accounts and score history from this file.
"""

import csv
import re

import pandas as pd

from creditcoach import config

INTERVIEWS = config.ROOT / "user_interviews" / "CreditCoach_User_Profiles.xlsx"
OUT = config.ROOT / "data" / "users.csv"

# Correct options for the knowledge questions (see docs/research/interview-questionnaire.md answer key).
KNOWLEDGE_KEY = {7: "b", 8: "b", 9: "b", 10: "b", 11: "c", 12: "c"}

FICTIONAL_NAMES = {"Male": ["Arjun", "Vikram", "Rahul", "Karthik", "Nikhil", "Sameer", "Aditya", "Manish"],
                   "Female": ["Ananya", "Kavya", "Neha", "Shruti"]}
AGES_IN_BAND = {"26 to 30": [27, 29, 26, 28, 30, 27, 29], "31 to 35": [32, 34, 33], "Above 35": [38, 41]}
MIN_YEARS = {"Less than 1 year": 0, "1 to 3 years": 1, "4 to 8 years": 4, "More than 8 years": 9}

ARAVIND = {
    "user_id": "USR-001", "first_name": "Aravind", "gender": "", "age": 22, "age_band": "21 to 25",
    "years_working": "Less than 1 year", "credit_cards": "2 to 3", "checks_score": "", "learns_from": "Search engines and blogs",
    "self_reported_score": "", "knowledge_score": "", "unexplained_drop": "Yes, and I never found out why",
    "pays_card": "", "card_usage": "", "knows_apr": "", "late_payments_12m": "",
    "loans": "Education / student loan; Car loan", "risky_product_exposure": "Considered it, but decided not to",
    "invests_in": "", "emergency_fund": "", "emi_pct": "", "invest_pct": "", "goals_2yr": "Buying a car",
    "source": "requirements.md persona + sample_data (blank = not stated)",
}


def clean(value) -> str:
    """Strip the option letter from a questionnaire answer and tidy it.

    Examples: "b) 26 to 30" -> "26 to 30"; multi-select "a) X;c) Y" -> "X; Y". Also fixes the "2‚Äì3"
    character-encoding glitch in the workbook. Blank cells become "".
    """
    if pd.isna(value):
        return ""
    text = str(value).replace("‚Äì", "–").replace("2–3", "2 to 3")  # fix mojibake "2‚Äì3"
    return "; ".join(re.sub(r"^[a-g]\)\s*", "", p.strip()) for p in text.split(";") if p.strip())


def letter(value) -> str:
    """Return the option letter of a questionnaire answer, e.g. "b) 26 to 30" -> "b" ("" if none)."""
    m = re.match(r"\s*([a-g])\)", str(value))
    return m.group(1) if m else ""


def main() -> None:
    """Read the interview workbook and write ``data/users.csv`` (Aravind first, then one row per interview)."""
    df = pd.read_excel(INTERVIEWS)
    q = {int(m.group(1)): c for c in df.columns if (m := re.match(r"(\d+)\.", c))}
    names = {g: iter(n) for g, n in FICTIONAL_NAMES.items()}
    ages = {b: iter(a) for b, a in AGES_IN_BAND.items()}

    rows = [ARAVIND]
    for i, r in df.reset_index(drop=True).iterrows():
        band = clean(r[q[1]])
        years = clean(r[q[2]])
        age = max(next(ages[band]), 21 + MIN_YEARS[years])  # keep age consistent with years worked
        rows.append({
            "user_id": f"USR-{i + 2:03d}",
            "first_name": next(names[r["Your Gender"]]),
            "gender": r["Your Gender"],
            "age": age,
            "age_band": band,
            "years_working": years,
            "credit_cards": "0" if clean(r[q[3]]) == "None" else clean(r[q[3]]),  # "None" reads as missing in pandas
            "checks_score": clean(r[q[4]]),
            "learns_from": clean(r[q[5]]),
            "self_reported_score": clean(r[q[6]]),
            "knowledge_score": sum(letter(r[q[n]]) == k for n, k in KNOWLEDGE_KEY.items()),
            "unexplained_drop": clean(r[q[13]]),
            "pays_card": clean(r[q[14]]),
            "card_usage": clean(r[q[15]]),
            "knows_apr": clean(r[q[16]]),
            "late_payments_12m": clean(r[q[17]]),
            "loans": clean(r[q[18]]),
            "risky_product_exposure": clean(r[q[19]]),
            "invests_in": clean(r[q[20]]),
            "emergency_fund": clean(r[q[21]]),
            "emi_pct": clean(r[q[22]]),
            "invest_pct": clean(r[q[24]]),
            "goals_2yr": clean(r[q[25]]),
            "source": f"Interview P{i + 1}",
        })

    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(ARAVIND.keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} profiles to {OUT.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
