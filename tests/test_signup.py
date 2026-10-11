"""Sign-up, sign-in sessions and the weekly question allowance.

No database, API key or mail server needed: Neon is never touched (the dataset backend is "files" in every test, so
there are no sign-up logins), and the pieces that would write to it are replaced with stand-ins.

Run:
    uv run pytest tests/test_signup.py -v
"""

import random
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from creditcoach import auth, config, dataset
from creditcoach.app import limits, sessions, welcome
from creditcoach.signup import generate, mailer, questions, store

REQUIRED = {"age_band": "26 to 30", "years_working": "1 to 3 years", "credit_cards": "1",
            "self_reported_score": "Good", "pays_card": "More than the minimum, but not the full amount",
            "card_usage": "31 to 70%", "late_payments_12m": "Once", "loans": ["Education / student loan"],
            "risky_product_exposure": "Never considered one", "goals_2yr": ["Buying a car"]}
MONTHS = generate.months_ending("2026-09-01")


def form(**changes) -> list:
    """The form's values in field order: the required answers above, everything optional blank."""
    answers = {**REQUIRED, **changes}
    return [answers.get(column, [] if kind == questions.MULTI else None)
            for column, kind, *_ in questions.FIELDS]


def build(user_id="USR-016", **changes):
    user = generate.user_row(user_id, questions.clean("Asha", None, form(**changes)))
    counter = iter(range(29, 999))
    accounts = generate.build_accounts(user, lambda: f"ACC-{next(counter):02d}")
    scenario, scores = generate.build_scores(user, accounts, MONTHS)
    return user, accounts, scenario, scores


# ---- The form ----

def test_the_form_has_ten_required_questions_and_the_dataset_columns():
    required = [q[0] for q in questions.FIELDS if q[4]]
    assert required == list(REQUIRED)
    columns = {q[0] for q in questions.FIELDS} - set(generate.KNOWLEDGE_KEY)
    assert columns <= set(dataset.USER_COLUMNS)
    for q, right in generate.KNOWLEDGE_KEY.items():  # the quiz key names real options
        assert right in next(f[3] for f in questions.FIELDS if f[0] == q)


def test_nothing_answered_lists_every_required_question():
    blank = questions.clean("", None, [None] * len(questions.FIELDS))
    assert len(questions.missing(blank)) == 10


@pytest.mark.parametrize("column", list(REQUIRED))
def test_each_required_question_blocks_sign_up_on_its_own(column):
    empty = [] if isinstance(REQUIRED[column], list) else None
    missing = questions.missing(questions.clean("", None, form(**{column: empty})))
    assert missing == [next(f[2] for f in questions.FIELDS if f[0] == column)]


def test_no_cards_answers_the_two_card_questions_for_you():
    answers = questions.clean("", None, form(credit_cards="0", pays_card=None, card_usage=None))
    assert questions.missing(answers) == []
    assert (answers["pays_card"], answers["card_usage"]) == tuple(questions.NO_CARD_ANSWERS.values())


def test_values_the_form_never_offers_count_as_unanswered():
    answers = questions.clean("  A   very long name that goes past thirty characters ", "Robot",
                              form(age_band="99", loans=["A yacht loan"]))
    assert answers["gender"] == "" and len(answers["first_name"]) == 30
    assert len(questions.missing(answers)) == 2


# ---- The password ----

def test_passwords_are_16_characters_with_every_kind():
    seen = set()
    for _ in range(3000):
        p = generate.new_password()
        seen.add(p)
        assert len(p) == 16
        assert re.search("[a-z]", p) and re.search("[A-Z]", p) and re.search("[0-9]", p)
        assert any(c in generate.SPECIALS for c in p)
    assert len(seen) == 3000


# ---- The generated profile ----

def test_months_end_at_the_dataset_latest_month():
    scores = dataset.read_files()[2]
    assert MONTHS == sorted(scores.date.unique()) and len(MONTHS) == 12
    assert generate.months_ending("2026-02-01", 3) == ["2025-12-01", "2026-01-01", "2026-02-01"]


def test_a_sign_up_becomes_a_user_row_accounts_and_twelve_scores():
    user, accounts, scenario, scores = build()
    assert list(user) == dataset.USER_COLUMNS and all(isinstance(v, str) for v in user.values())
    assert user["source"] == dataset.SIGNUP_SOURCE and user["first_name"] == "Asha" and 26 <= int(user["age"]) <= 30
    assert [a["account_type"] for a in accounts] == ["Credit Card", "Education Loan"]
    assert list(accounts[0]) == dataset.ACCOUNT_COLUMNS and list(scores[0]) == dataset.SCORE_COLUMNS
    assert 0.35 <= accounts[0]["utilization_ratio"] <= 0.65 and accounts[1]["credit_limit_inr"] is None
    assert [s["date"] for s in scores] == MONTHS and scores[0]["primary_factor_change"] == "Baseline"
    assert scenario == "Utilization spike + late payment"
    assert sum(s["primary_factor_change"] == "Late payment (30+ days)" for s in scores) == 1
    assert generate.problems(user, accounts, scores) == []
    assert build() == build()  # the same answers for the same user id give the same data


def test_no_cards_and_no_loans_is_a_user_with_no_credit_file():
    user, accounts, scenario, scores = build(credit_cards="0", loans=["No loans"], pays_card=None, card_usage=None,
                                             late_payments_12m="Never")
    assert (accounts, scores, scenario) == ([], [], "No credit file") and user["loans"] == "No loans"


def test_special_answers_get_their_accounts():
    _, accounts, _, _ = build(credit_cards="4 or more", risky_product_exposure="Yes, I've used one",
                              loans=["Buy-now-pay-later plan", "Home loan"])
    kinds = [a["account_type"] for a in accounts]
    assert kinds == ["Credit Card"] * 4 + ["Home Loan", "Buy Now Pay Later", "Instant Loan App"]
    _, accounts, _, _ = build(loans=["Payday loan or instant cash app loan"],
                              risky_product_exposure="Yes, I've used one")
    assert [a["account_type"] for a in accounts].count("Instant Loan App") == 1  # not doubled


def test_the_latest_score_lands_in_the_self_reported_band_when_nothing_went_wrong():
    for report, (lo, hi) in generate.LATEST_BY_SELF_REPORT.items():
        _, _, _, scores = build(self_reported_score=report, late_payments_12m="Never", card_usage="Less than 10%",
                                pays_card="The full amount, every month")
        assert lo <= scores[-1]["score"] <= hi, report


def test_every_combination_of_answers_passes_the_dataset_rules():
    rng = random.Random(7)
    options = {f[0]: f[3] for f in questions.FIELDS}
    for i in range(1500):
        changes = {c: rng.choice(options[c]) for c in REQUIRED if c not in ("loans", "goals_2yr")}
        changes["loans"] = rng.sample(options["loans"], rng.randint(1, 3))
        user, accounts, _, scores = build(f"USR-{16 + i % 900:03d}", **changes)
        assert generate.problems(user, accounts, scores) == [], changes
        assert len(scores) == (12 if accounts else 0)


def test_problems_catches_bad_data():
    user, accounts, _, scores = build()
    scores[5]["score"] += 60
    assert any("out of range" in p for p in generate.problems(user, accounts, scores))
    assert generate.problems(user, accounts[1:], []) == ["card count doesn't match the answer"]


# ---- Where sign-ups live ----

def test_drift_ignores_sign_up_rows():
    users, accounts, scores = dataset.read_files()
    user, new_accounts, _, new_scores = build()
    with_signup = (pd.concat([users, pd.DataFrame([user])], ignore_index=True),
                   pd.concat([accounts, pd.DataFrame(new_accounts)], ignore_index=True),
                   pd.concat([scores, pd.DataFrame(new_scores)], ignore_index=True))
    kept = dataset.without_signups(with_signup)
    assert [len(f) for f in kept] == [15, 28, 156]
    assert kept[0].equals(users) and list(kept[2].score) == list(scores.score)
    assert dataset.without_signups((users, accounts, scores))[0] is users


def test_sign_up_needs_neon_and_never_writes_the_committed_files(monkeypatch):
    assert not store.available() and store.logins() == {}
    with pytest.raises(store.SignupUnavailable):
        store.create_account(questions.clean("", None, form()))
    assert auth.signup_logins() == {}


def test_logins_come_from_the_file_and_from_sign_ups(monkeypatch):
    entry = auth.make_entry("USR-016", "S3cret!pass-word")
    monkeypatch.setattr(auth, "signup_logins", lambda reload=False: {"creditcoach_user16": entry})
    assert auth.user_id_for("creditcoach_user16") == "USR-016" and auth.user_id_for("creditcoach_user1") == "USR-001"
    assert auth.check_login("creditcoach_user16", "S3cret!pass-word")
    assert not auth.check_login("creditcoach_user16", "wrong") and not auth.check_login("creditcoach_user99", "x")
    assert auth.is_team("creditcoach_user1") and not auth.is_team("creditcoach_user16")
    assert "creditcoach_user16" not in auth.logins()  # the committed file's logins are unchanged
    assert limits.applies("creditcoach_user16") and not limits.applies("creditcoach_user1")
    assert not limits.applies(None) and not limits.applies("nobody")


def test_a_login_created_by_another_copy_of_the_app_reloads_the_dataset(monkeypatch):
    """Someone signs up on another running copy: the first time this one sees their login, it re-reads the dataset."""
    entry = lambda n: auth.make_entry(f"USR-{n:03d}", "S3cret!pass-word")  # noqa: E731
    in_neon = {"creditcoach_user16": entry(16)}
    dropped = []
    monkeypatch.setattr(config, "DATA_BACKEND", "postgres")
    monkeypatch.setattr(store, "logins", lambda: dict(in_neon))
    monkeypatch.setattr(auth, "forget_dataset", lambda: dropped.append(1))
    monkeypatch.setattr(auth, "_signups", {"entries": {}, "read": 0.0})
    monkeypatch.setattr(auth, "SIGNUP_RELOAD_SECONDS", 0)

    assert auth.user_id_for("creditcoach_user16") == "USR-016" and len(dropped) == 1  # first read
    assert auth.user_id_for("creditcoach_user16") == "USR-016" and len(dropped) == 1  # known: nothing re-read
    assert auth.user_id_for("creditcoach_user17") is None and len(dropped) == 1       # unknown name, nothing new
    in_neon["creditcoach_user17"] = entry(17)                                         # signed up elsewhere
    assert auth.user_id_for("creditcoach_user17") == "USR-017" and len(dropped) == 2
    monkeypatch.setattr(store, "logins", lambda: 1 / 0)                               # Neon unreachable
    assert auth.user_id_for("creditcoach_user18") is None and len(dropped) == 2
    assert auth.user_id_for("creditcoach_user17") == "USR-017"                        # last known logins still work


def test_forget_dataset_makes_the_next_read_load_again():
    from creditcoach import user_data
    from creditcoach.tools import common

    common.tables(), user_data.user_ids()
    assert common.tables.cache_info().currsize == 1 and user_data._tables.cache_info().currsize == 1
    auth.forget_dataset()
    assert common.tables.cache_info().currsize == 0 and user_data._tables.cache_info().currsize == 0
    assert len(user_data.user_ids()) == 15


# ---- Sessions ----

def test_a_session_cookie_names_its_user_until_it_expires_or_is_altered():
    value = sessions.cookie_for("creditcoach_user1", now=1000)
    assert sessions.username_in(value, now=1000 + sessions.SESSION_SECONDS - 1) == "creditcoach_user1"
    assert sessions.username_in(value, now=1000 + sessions.SESSION_SECONDS + 1) is None
    assert sessions.username_in(value.replace("user1", "user2")) is None
    assert sessions.username_in(sessions.cookie_for("creditcoach_user99")) is None  # no such login
    for junk in (None, "", "a|b", "creditcoach_user1|soon|abc"):
        assert sessions.username_in(junk) is None
    request = SimpleNamespace(cookies={sessions.COOKIE: sessions.cookie_for("creditcoach_user3")})
    assert sessions.current_user(request) == "creditcoach_user3"


def test_a_ticket_works_once():
    ticket = sessions.issue_ticket("creditcoach_user1")
    assert sessions.redeem_ticket(ticket) == "creditcoach_user1"
    assert sessions.redeem_ticket(ticket) is None and sessions.redeem_ticket("made-up") is None


def test_log_in_gives_a_ticket_only_for_the_right_password(monkeypatch):
    monkeypatch.setattr(sessions, "_failures", {})
    monkeypatch.setattr(auth, "check_login", lambda u, p: (u, p) == ("creditcoach_user1", "right"))
    note, ticket = welcome.log_in(" creditcoach_user1 ", "right")
    assert sessions.redeem_ticket(ticket) == "creditcoach_user1" and "Signed in" in note
    for _ in range(sessions.MAX_FAILURES):
        note, ticket = welcome.log_in("creditcoach_user1", "wrong")
        assert ticket == "" and "don't match" in note
    note, ticket = welcome.log_in("creditcoach_user1", "right")  # locked for a while, even with the right one
    assert ticket == "" and "Too many attempts" in note


# ---- The sign-up handler ----

@pytest.fixture
def accounts_made(monkeypatch):
    made = []

    def create_account(answers):
        made.append(answers)
        return {"username": "creditcoach_user16", "user_id": "USR-016", "password": "Aa1!" * 4}

    monkeypatch.setattr(store, "create_account", create_account)
    return made


def test_sign_up_creates_nothing_until_the_form_is_complete(accounts_made, monkeypatch):
    note, *rest = welcome.sign_up("", None, "", True, *form(age_band=None, loans=[]))
    assert "Which age group" in note and "Which of these do you currently have" in note and not accounts_made
    note, *rest = welcome.sign_up("", None, "", False, *form())
    assert "tick the box" in note and not accounts_made
    monkeypatch.setattr(config, "INVITE_CODE", "friends-2026")
    note, *rest = welcome.sign_up("", None, "guess", True, *form())
    assert "invite code" in note and not accounts_made
    note, modal, username, password = welcome.sign_up("Asha", "Female", "friends-2026", True, *form())
    assert (note, username, password) == ("", "creditcoach_user16", "Aa1!" * 4) and modal["visible"] is True
    assert len(accounts_made) == 1 and accounts_made[0]["first_name"] == "Asha"


def test_sign_up_says_so_when_it_is_full_or_fails(monkeypatch):
    def closed(answers):
        raise store.SignupClosed("50 sign-ups")

    monkeypatch.setattr(store, "create_account", closed)
    assert "full for now" in welcome.sign_up("", None, "", True, *form())[0]
    monkeypatch.setattr(store, "create_account", lambda answers: 1 / 0)
    assert "Nothing was saved" in welcome.sign_up("", None, "", True, *form())[0]


def test_the_email_backup_needs_a_mail_account_and_a_real_address(monkeypatch):
    assert not mailer.configured()
    with pytest.raises(RuntimeError):
        mailer.send_login("me@example.com", "creditcoach_user16", "pw")
    assert mailer.valid("me@example.com") and not mailer.valid("me@example") and not mailer.valid("a b@c.de")
    sent = []
    monkeypatch.setattr(mailer, "send_login", lambda *args: sent.append(args))
    assert "doesn't look like" in welcome.email_login("nope", "creditcoach_user16", "pw")
    assert "Sent" in welcome.email_login(" me@example.com ", "creditcoach_user16", "pw")
    assert sent == [("me@example.com", "creditcoach_user16", "pw")]


def test_the_welcome_page_builds_with_and_without_sign_up(monkeypatch):
    welcome.build()
    monkeypatch.setattr(store, "available", lambda: True)
    monkeypatch.setattr(config, "INVITE_CODE", "x")
    welcome.build()


# ---- The weekly allowance in the chat ----

class Allowance:
    """A stand-in for ``app.limits`` storage: ``limit`` questions, then none."""

    def __init__(self, limit=2):
        self.limit, self.asked, self.resets = limit, 0, datetime.now(timezone.utc) + timedelta(days=7)

    def take(self, user_id):
        if self.asked >= self.limit:
            return limits.Grant(False, 0, self.resets)
        self.asked += 1
        return limits.Grant(True, self.limit - self.asked, self.resets)

    def give_back(self, user_id):
        self.asked -= 1


@pytest.fixture
def chat(monkeypatch, tmp_path):
    from creditcoach.app import main as app

    allowance = Allowance()
    monkeypatch.setattr(config, "MEMORY_DIR", tmp_path)
    monkeypatch.setattr(config, "WEEKLY_QUESTIONS", allowance.limit)
    monkeypatch.setattr(app, "_sessions", {})
    monkeypatch.setattr(app.auth, "user_id_for", lambda username: "USR-002")
    monkeypatch.setattr(limits, "applies", lambda username: username == "creditcoach_user16")
    monkeypatch.setattr(limits, "take", allowance.take)
    monkeypatch.setattr(limits, "give_back", allowance.give_back)
    reply = SimpleNamespace(text="Your score is 838.", model="m", passages=[], tool_calls=[],
                            retrieval_seconds=0.1, generation_seconds=0.2)
    monkeypatch.setattr(app, "answer", lambda q, user_id, **kw: reply)
    return app, allowance


def test_a_signed_up_user_gets_the_weekly_allowance(chat):
    app, allowance = chat
    request = SimpleNamespace(username="creditcoach_user16", session_hash="w1")
    first = app.final_reply("What is my score?", [], request)
    assert "Your score is 838." in first and "Questions left this week: **1 of 2**" in first
    assert "**0 of 2**" in app.final_reply("And my utilization?", [], request)
    third = app.final_reply("One more?", [], request)
    assert third.startswith("You've used all 2 questions for this week") and allowance.asked == 2
    assert app.final_reply("   ", [], request) == "Please type a question about your credit."  # not counted


def test_a_failed_answer_is_not_counted(chat, monkeypatch):
    app, allowance = chat
    monkeypatch.setattr(app, "answer", lambda q, user_id, **kw: 1 / 0)
    request = SimpleNamespace(username="creditcoach_user16", session_hash="w2")
    assert app.final_reply("What is my score?", [], request) == app.APOLOGY and allowance.asked == 0


def test_no_answer_when_the_allowance_cannot_be_checked(chat, monkeypatch):
    app, allowance = chat
    monkeypatch.setattr(limits, "take", lambda user_id: 1 / 0)
    request = SimpleNamespace(username="creditcoach_user16", session_hash="w3")
    assert app.final_reply("What is my score?", [], request) == limits.UNAVAILABLE


def test_the_team_logins_have_no_limit(chat):
    app, allowance = chat
    request = SimpleNamespace(username="creditcoach_user2", session_hash="w4")
    replies = [app.final_reply("What is my score?", [], request) for _ in range(4)]
    assert all("Your score is 838." in r and "Questions left" not in r for r in replies) and allowance.asked == 0
