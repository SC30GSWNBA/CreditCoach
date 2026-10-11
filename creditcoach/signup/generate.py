"""Turn sign-up answers into a users row, the accounts the person reported, and a 12-month score history.

It follows ``scripts/synthetic/step2_accounts_scores.py``, which built the 15 original users: the same factor
labels and allowed monthly changes, the same card-limit and loan bands, and the same months as the rest of the
dataset, so the tools' "latest month" doesn't move when someone signs up. Three things differ, because a sign-up
can give answers the 14 interviews never did:

    Story     Chosen from the answers (late payments, card usage, cards and loans held), not from a per-user table.
    Scores    The self-reported score describes the person's score now, so the history is anchored to end in that
              band (step 2 anchors the first month). Late payments can still pull the latest month below the band.
    Options   "4 or more" cards, "Below average / poor", a buy-now-pay-later plan and a current payday loan.

Everything is deterministic for a given user id and set of answers, except the password. ``problems`` applies
step 2's validation rules to one new user; ``store`` refuses to save data that fails them.

Example:
    >>> u = user_row("USR-016", answers)
    >>> accounts = build_accounts(u, lambda: "ACC-29")
    >>> scenario, scores = build_scores(u, accounts, months_ending("2026-09-01"))
    >>> problems(u, accounts, scores)
    []
"""

import random
import secrets
import string

from creditcoach.dataset import SIGNUP_SOURCE

# Allowed monthly score change per factor: data/README.md > How Score Changes Are Bounded
FACTOR_RANGES = {
    "Stable (no major change)": (-2, 2),
    "On-time payments": (2, 8),
    "Account age increase": (2, 6),
    "Utilization decreased": (5, 15),
    "Utilization increase": (-10, -1),
    "Utilization spike": (-40, -10),
    "Hard inquiry": (-10, -2),
    "Late payment (30+ days)": (-95, -70),  # middle of the guide's -110 to -60, as in step 2
}
SCORE_MIN, SCORE_MAX = 300, 900
CARD_LIMIT_BY_YEARS = {"Less than 1 year": (30000, 75000), "1 to 3 years": (75000, 150000),
                       "4 to 8 years": (150000, 300000), "More than 8 years": (300000, 500000)}
USAGE_RANGE = {"Less than 10%": (0.03, 0.09), "10 to 30%": (0.12, 0.28), "31 to 70%": (0.35, 0.65),
               "More than 70%": (0.72, 0.85)}
UNKNOWN_USAGE = (0.35, 0.50)  # has a card but doesn't know its usage: an unnoticed high balance, as in step 2
LOANS = {"Education / student loan": ("Education Loan", 300000, 1500000),
         "Home loan": ("Home Loan", 2000000, 7500000),
         "Car loan": ("Auto Loan", 300000, 800000),
         "Personal loan": ("Personal Loan", 100000, 500000),
         "Buy-now-pay-later plan": ("Buy Now Pay Later", 2000, 30000),
         "Payday loan or instant cash app loan": ("Instant Loan App", 5000, 25000)}
LATEST_BY_SELF_REPORT = {"Excellent": (800, 845), "Good": (740, 790), "Average / fair": (660, 720),
                         "Below average / poor": (560, 640)}
UNKNOWN_LATEST = (690, 740)
AGE_BANDS = {"21 to 25": (21, 25), "26 to 30": (26, 30), "31 to 35": (31, 35), "Above 35": (36, 42)}
MIN_YEARS = {"Less than 1 year": 0, "1 to 3 years": 1, "4 to 8 years": 4, "More than 8 years": 9}
N_CARDS = {"0": 0, "1": 1, "2 to 3": 2, "4 or more": 4}
# Correct answers to the credit quiz (docs/research/interview-questionnaire.md, answer key)
KNOWLEDGE_KEY = {"q7": "Paying bills on time",
                 "q8": "The share of your credit card limit you're currently using",
                 "q9": "Above 30%",
                 "q10": "A small, temporary dip",
                 "q11": "Your score may go down because your credit history looks shorter",
                 "q12": "A red flag for a possible scam"}

PASSWORD_LENGTH = 16
SPECIALS = "!@#$%^&*-_=+?"


def new_password() -> str:
    """A random 16-character password with at least one lowercase, uppercase, digit and special character."""
    pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, SPECIALS]
    chars = [secrets.choice(p) for p in pools]
    chars += [secrets.choice("".join(pools)) for _ in range(PASSWORD_LENGTH - len(pools))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def months_ending(latest: str, count: int = 12) -> list[str]:
    """The ``count`` months ending at ``latest`` (``YYYY-MM-01``), oldest first."""
    year, month = int(latest[:4]), int(latest[5:7])
    months = []
    for _ in range(count):
        months.append(f"{year}-{month:02d}-01")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return months[::-1]


def user_row(user_id: str, a: dict) -> dict:
    """One ``users`` row (the dataset's columns and wording) from cleaned sign-up answers.

    Args:
        user_id: The new user's id, e.g. ``"USR-016"``.
        a: Answers from ``questions.clean``, with every required question answered.

    Returns:
        A dict with exactly ``dataset.USER_COLUMNS``; every value is text and blank means "not stated".
    """
    rng = random.Random(user_id + ":age")
    lo, hi = AGE_BANDS[a["age_band"]]
    answered_quiz = any(a.get(q) for q in KNOWLEDGE_KEY)
    loans = [x for x in a.get("loans") or [] if x != "No loans"] or ["No loans"]
    return {
        "user_id": user_id, "first_name": a.get("first_name") or "",
        "gender": a.get("gender") if a.get("gender") in ("Male", "Female") else "",
        "age": str(max(rng.randint(lo, hi), 21 + MIN_YEARS[a["years_working"]])),  # consistent with years worked
        "age_band": a["age_band"], "years_working": a["years_working"], "credit_cards": a["credit_cards"],
        "checks_score": a.get("checks_score") or "", "learns_from": "; ".join(a.get("learns_from") or []),
        "self_reported_score": a["self_reported_score"],
        "knowledge_score": str(sum(a.get(q) == k for q, k in KNOWLEDGE_KEY.items())) if answered_quiz else "",
        "unexplained_drop": a.get("unexplained_drop") or "", "pays_card": a["pays_card"],
        "card_usage": a["card_usage"], "knows_apr": a.get("knows_apr") or "",
        "late_payments_12m": a["late_payments_12m"], "loans": "; ".join(loans),
        "risky_product_exposure": a["risky_product_exposure"], "invests_in": "; ".join(a.get("invests_in") or []),
        "emergency_fund": a.get("emergency_fund") or "", "emi_pct": a.get("emi_pct") or "",
        "invest_pct": a.get("invest_pct") or "", "goals_2yr": "; ".join(a.get("goals_2yr") or []),
        "source": SIGNUP_SOURCE,
    }


def build_accounts(u: dict, next_id) -> list[dict]:
    """The cards and loans the person reported, sized the way step 2 sizes them.

    Args:
        u: The row from ``user_row``.
        next_id: Function that returns the next free account id, e.g. ``"ACC-29"``.

    Returns:
        Account rows with ``dataset.ACCOUNT_COLUMNS``. Loans have ``None`` for limit and utilization.
    """
    rng = random.Random(u["user_id"])
    rows = []
    lo, hi = USAGE_RANGE.get(u["card_usage"], UNKNOWN_USAGE)
    for _ in range(N_CARDS[u["credit_cards"]]):
        limit = rng.randrange(*CARD_LIMIT_BY_YEARS[u["years_working"]], 5000)
        rows.append(("Credit Card", round(limit * rng.uniform(lo, hi) / 100) * 100, limit))
    held = [x.strip() for x in u["loans"].split(";")]
    for loan in held:
        if loan in LOANS:
            kind, lo_bal, hi_bal = LOANS[loan]
            rows.append((kind, rng.randrange(lo_bal, hi_bal, 1000 if hi_bal <= 30000 else 5000), None))
    if u["risky_product_exposure"] == "Yes, I've used one" and "Payday loan or instant cash app loan" not in held:
        rows.append(("Instant Loan App", rng.randrange(5000, 25000, 1000), None))
    return [{"account_id": next_id(), "user_id": u["user_id"], "account_type": kind, "balance_inr": balance,
             "credit_limit_inr": limit, "utilization_ratio": round(balance / limit, 2) if limit else None}
            for kind, balance, limit in rows]


def utilization(accounts: list[dict]) -> float:
    """Total card balance / total card limit, or 0 for someone with no card."""
    cards = [a for a in accounts if a["credit_limit_inr"]]
    return sum(a["balance_inr"] for a in cards) / sum(a["credit_limit_inr"] for a in cards) if cards else 0.0


def story(u: dict, accounts: list[dict]) -> tuple[str, list[str]]:
    """The scenario name and the 11 monthly factor labels (months 2 to 12) that fit the person's answers."""
    util = utilization(accounts)
    late = {"Once": 1, "2 or more times": 2}.get(u["late_payments_12m"], 0)
    if not late and u["pays_card"] == "I sometimes miss or pay late":
        late = 1
    labels = ["On-time payments"] * 11
    labels[5] = "Account age increase"
    name = "Steady improver"
    if not any(a["credit_limit_inr"] for a in accounts):
        name = "Loan-only file (no credit card)"
        labels = ["On-time payments" if i % 3 == 0 else "Stable (no major change)" for i in range(11)]
    elif util > 0.70:
        name = "High utilization and debt stress"
        labels = ["On-time payments", "Utilization increase", "Utilization increase", "Stable (no major change)",
                  "On-time payments", "Utilization spike", "On-time payments", "Utilization increase",
                  "Utilization spike", "Stable (no major change)", "Utilization increase"]
    elif util > 0.30:
        name = "Utilization spike"
        labels[8], labels[9], labels[10] = "Utilization increase", "Utilization spike", "Stable (no major change)"
    else:
        if u["self_reported_score"] == "Excellent":  # near the top of the scale, scores mostly hold
            labels = ["Stable (no major change)" if i % 2 else "On-time payments" for i in range(11)]
        if u["card_usage"] == "10 to 30%" or u["pays_card"].startswith("More than the minimum"):
            labels[2], labels[3] = "Utilization increase", "Utilization decreased"
    if late:
        plain = name in ("Steady improver", "Loan-only file (no credit card)")
        name = "Late payment recovery" if plain else name + " + late payment"
        for i in ([4], [1, 6])[late - 1]:  # never the last 3 months, which carry the utilization story
            labels[i] = "Late payment (30+ days)"
    return name, labels


def build_scores(u: dict, accounts: list[dict], months: list[str]) -> tuple[str, list[dict]]:
    """Twelve monthly scores ending in the person's self-reported band, or none for someone with no accounts.

    Args:
        u: The row from ``user_row``.
        accounts: The rows from ``build_accounts``.
        months: The 12 months to fill, oldest first (``months_ending``).

    Returns:
        ``(scenario, rows)``. ``rows`` have ``dataset.SCORE_COLUMNS``; the first is the ``Baseline``.
    """
    if not accounts:
        return "No credit file", []
    rng = random.Random(u["user_id"] + ":scores")
    name, labels = story(u, accounts)
    deltas = [rng.randint(*FACTOR_RANGES[label]) for label in labels]
    target = rng.randint(*LATEST_BY_SELF_REPORT.get(u["self_reported_score"], UNKNOWN_LATEST))
    running = low = high = 0
    for d in deltas:
        running += d
        low, high = min(low, running), max(high, running)
    # Start where the path ends in the band, moved only as far as needed to keep every month inside 300-900
    score = min(max(target - running, SCORE_MIN - low), SCORE_MAX - high)
    rows = [{"user_id": u["user_id"], "date": months[0], "score": score, "primary_factor_change": "Baseline"}]
    for month, label, d in zip(months[1:], labels, deltas):
        score += d
        rows.append({"user_id": u["user_id"], "date": month, "score": score, "primary_factor_change": label})
    return name, rows


def problems(u: dict, accounts: list[dict], scores: list[dict]) -> list[str]:
    """Step 2's validation rules, applied to one new user. Empty means the data is consistent."""
    errors = []
    if sum(a["account_type"] == "Credit Card" for a in accounts) != N_CARDS[u["credit_cards"]]:
        errors.append("card count doesn't match the answer")
    if scores and not accounts:
        errors.append("score history without accounts")
    if len(scores) not in (0, 12):
        errors.append("score history isn't 12 months")
    for prev, row in zip(scores, scores[1:]):
        lo, hi = FACTOR_RANGES[row["primary_factor_change"]]
        if not lo <= row["score"] - prev["score"] <= hi:
            errors.append(f"{row['date']}: change out of range for {row['primary_factor_change']}")
    if any(not SCORE_MIN <= r["score"] <= SCORE_MAX for r in scores):
        errors.append(f"score outside {SCORE_MIN}-{SCORE_MAX}")
    if scores and utilization(accounts) > 0.30:
        if "utilization" not in " ".join(r["primary_factor_change"] for r in scores[-3:]).lower():
            errors.append("utilization above 30% but no utilization change in the last 3 months")
    for a in accounts:
        if a["credit_limit_inr"] and a["utilization_ratio"] != round(a["balance_inr"] / a["credit_limit_inr"], 2):
            errors.append(f"{a['account_id']}: utilization_ratio mismatch")
    return errors
