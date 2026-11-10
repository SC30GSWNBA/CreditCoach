"""The admin login and its pages: sign-in, a changed or reset password, the admin cookie, and the routes.

No database or mail account needed: the admin login is kept in memory (as it is without Neon), and email is
replaced by a stand-in that records what would have been sent.

Run:
    uv run pytest tests/test_admin.py -v
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from creditcoach import admin, config
from creditcoach.app import admin_page, sessions, welcome
from creditcoach.signup import mailer

FIRST = "the-first-admin-password"
NEW = "a-brand-new-password"


@pytest.fixture(autouse=True)
def fresh_admin(monkeypatch):
    """Every test starts from the first password, with no reset link, no failed sign-ins and no sent email."""
    monkeypatch.setattr(config, "ADMIN_PASSWORD", FIRST)
    admin._memory.clear()
    admin._resets.clear()
    admin._epoch.update(value=None, read=0.0)
    sessions._failures.clear()
    yield
    admin._memory.clear()
    admin._epoch.update(value=None, read=0.0)


@pytest.fixture
def mail(monkeypatch):
    """Email that is recorded instead of sent: (subject, to, body) each."""
    sent = []
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "_send", lambda to, subject, body: sent.append((subject, to, body)))
    return sent


def request(username=None, query=None, cookies=None):
    return SimpleNamespace(username=username, query_params=query or {}, cookies=cookies or {})


# ---------------------------------------------------------------- the login

def test_the_admin_signs_in_with_the_admin_email_in_any_case_and_the_password():
    assert admin.check(config.ADMIN_EMAIL, FIRST)
    assert admin.check(f"  {config.ADMIN_EMAIL.upper()} ", FIRST)
    assert not admin.check(config.ADMIN_EMAIL, "wrong")
    assert not admin.check("someone@example.com", FIRST)


def test_without_a_password_set_there_is_no_admin_sign_in(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    assert not admin.configured() and not admin.check(config.ADMIN_EMAIL, "")
    assert admin_page.NOT_SET_UP in admin_page.sign_in(config.ADMIN_EMAIL, "")[0]


def test_only_a_hash_of_the_password_is_kept():
    admin.check(config.ADMIN_EMAIL, FIRST)
    assert FIRST not in str(admin._memory) and len(admin._memory["hash"]) == 64


@pytest.mark.parametrize("current, new, confirm, says", [
    ("wrong", NEW, NEW, "current password isn't right"),
    (FIRST, "short", "short", f"at least {admin.MIN_LENGTH} characters"),
    (FIRST, NEW, NEW + "x", "don't match"),
    (FIRST, FIRST, FIRST, "same as the current one"),
])
def test_a_new_password_is_refused_with_what_to_fix(current, new, confirm, says):
    with pytest.raises(admin.AdminError, match=says):
        admin.change(current, new, confirm)
    assert admin.check(config.ADMIN_EMAIL, FIRST)


def test_a_changed_password_replaces_the_first_one_and_moves_the_epoch():
    before = admin.epoch()
    admin.change(FIRST, NEW, NEW)
    assert admin.check(config.ADMIN_EMAIL, NEW) and not admin.check(config.ADMIN_EMAIL, FIRST)
    assert admin.epoch() != before


def test_the_stored_password_wins_over_the_setting_after_a_change(monkeypatch):
    """A redeploy keeps the first password in the setting; the password changed in the app must still work."""
    admin.change(FIRST, NEW, NEW)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", FIRST)
    assert admin.check(config.ADMIN_EMAIL, NEW) and not admin.check(config.ADMIN_EMAIL, FIRST)


# ---------------------------------------------------------------- the reset link

def test_a_reset_link_works_once():
    token = admin.start_reset()
    assert admin.reset_valid(token) and not admin.reset_valid("not-the-token")
    admin.finish_reset(token, NEW, NEW)
    assert admin.check(config.ADMIN_EMAIL, NEW)
    with pytest.raises(admin.AdminError, match="expired or was already used"):
        admin.finish_reset(token, NEW + "2", NEW + "2")


def test_a_reset_link_expires_and_a_new_one_replaces_it(monkeypatch):
    first = admin.start_reset()
    second = admin.start_reset()
    assert not admin.reset_valid(first) and admin.reset_valid(second)
    admin._memory["reset_expires"] = datetime.now(UTC) - timedelta(seconds=1)
    assert not admin.reset_valid(second)


def test_only_a_hash_of_the_reset_link_is_kept():
    token = admin.start_reset()
    assert token not in str(admin._memory)


def test_reset_links_are_limited_to_three_an_hour():
    for _ in range(admin.MAX_RESETS):
        admin.start_reset()
    with pytest.raises(admin.AdminError, match="wait an hour"):
        admin.start_reset()


# ---------------------------------------------------------------- the admin cookie and tickets

def test_the_admin_cookie_opens_the_admin_page_and_nothing_else_does():
    cookie = sessions.admin_cookie()
    assert sessions.admin_in(cookie)
    assert sessions.current_admin(request(cookies={sessions.ADMIN_COOKIE: cookie})) == sessions.ADMIN
    assert not sessions.admin_in(cookie.replace("admin|", "admi|", 1))
    assert not sessions.admin_in(cookie[:-1] + ("0" if cookie[-1] != "0" else "1"))
    assert not sessions.admin_in(sessions.cookie_for("creditcoach_user1"))  # a user's cookie
    assert not sessions.admin_in(sessions.admin_cookie(now=1_000_000))  # expired (made in 1970)
    assert sessions.username_in(cookie) is None  # and the admin's cookie isn't a user's


def test_a_new_password_signs_out_every_earlier_admin_session():
    cookie = sessions.admin_cookie()
    admin.change(FIRST, NEW, NEW)
    assert not sessions.admin_in(cookie) and sessions.admin_in(sessions.admin_cookie())


def test_a_ticket_only_works_where_its_kind_is_redeemed():
    user, admin_ticket = sessions.issue_ticket("creditcoach_user1"), sessions.issue_ticket(sessions.ADMIN, "admin")
    assert sessions.redeem_ticket(admin_ticket) is None and sessions.redeem_ticket(user, "admin") is None
    assert sessions.redeem_ticket(admin_ticket, "admin") == sessions.ADMIN
    assert sessions.redeem_ticket(admin_ticket, "admin") is None  # once
    assert sessions.redeem_ticket(user) == "creditcoach_user1"


# ---------------------------------------------------------------- the pages

def test_five_wrong_tries_pause_the_admin_sign_in():
    for left in (4, 3, 2, 1):
        note, ticket = admin_page.sign_in(config.ADMIN_EMAIL, "wrong")
        assert ticket == "" and f"{left} {'try' if left == 1 else 'tries'} left" in note
    admin_page.sign_in(config.ADMIN_EMAIL, "wrong")
    note, ticket = admin_page.sign_in(config.ADMIN_EMAIL, FIRST)  # even the right password waits now
    assert ticket == "" and "wait 15 minutes" in note


def test_a_right_sign_in_gives_an_admin_ticket():
    note, ticket = admin_page.sign_in(config.ADMIN_EMAIL, FIRST)
    assert "Signed in" in note and sessions.redeem_ticket(ticket, "admin") == sessions.ADMIN


def test_forgot_password_emails_a_link_to_the_admin_address_on_the_apps_own_address(mail, monkeypatch):
    """The link's address comes from the setting, never from the request, whose Host header a stranger could forge."""
    monkeypatch.setattr(config, "PUBLIC_URL", "https://creditcoach.example")
    note = admin_page.forgot()
    (subject, to, body), = mail
    assert to == config.ADMIN_EMAIL and "Reset" in subject and "30 minutes" in note
    token = body.split("https://creditcoach.example/admin/?reset=")[1].split()[0]
    assert admin.reset_valid(token)


def test_forgot_password_says_so_when_email_isnt_set_up():
    assert "Email isn't set up" in admin_page.forgot() and not admin._memory.get("reset_hash")


def test_the_reset_link_opens_the_new_password_form_and_a_stale_one_says_so():
    token = admin.start_reset()
    signin, reset, kept, note = admin_page.opened(request(query={"reset": token}))
    assert reset["visible"] is True and signin["visible"] is False and kept == token
    signin, reset, kept, note = admin_page.opened(request(query={"reset": "old"}))
    assert signin["visible"] is True and kept == "" and "expired" in note
    signin, reset, kept, note = admin_page.opened(request())
    assert signin["visible"] is True and note == ""


def test_a_new_password_from_the_reset_link_is_emailed_and_signs_in(mail):
    token = admin.start_reset()
    note, ticket, emailed = admin_page.set_new(token, NEW, NEW)
    assert emailed == "sent" and sessions.redeem_ticket(ticket, "admin") == sessions.ADMIN
    (subject, to, body), = mail
    assert to == config.ADMIN_EMAIL and f"New password: {NEW}" in body and "IST" in body


def test_changing_the_password_on_the_dashboard_emails_it_to_the_admin_address_only(mail):
    note, ticket, emailed = admin_page.change(FIRST, NEW, NEW, request(sessions.ADMIN))
    assert emailed == "sent" and ticket and admin.check(config.ADMIN_EMAIL, NEW)
    assert [to for _, to, _ in mail] == [config.ADMIN_EMAIL]
    assert "emailed the new password" in admin_page.NOTES["sent"][1]


def test_a_failed_email_still_changes_the_password_and_says_so(monkeypatch):
    monkeypatch.setattr(mailer, "_send", lambda *a: (_ for _ in ()).throw(OSError("no route")))
    monkeypatch.setattr(mailer, "configured", lambda: True)
    note, ticket, emailed = admin_page.change(FIRST, NEW, NEW, request(sessions.ADMIN))
    assert emailed == "unsent" and admin.check(config.ADMIN_EMAIL, NEW)
    assert "couldn't be sent" in admin_page.NOTES["unsent"][1]


def test_only_the_admin_can_change_the_password():
    note, ticket, _ = admin_page.change(FIRST, NEW, NEW, request("creditcoach_user1"))
    assert ticket == "" and "sign in again" in note and admin.check(config.ADMIN_EMAIL, FIRST)


def test_the_welcome_page_links_to_the_admin_sign_in_under_the_log_in_form():
    page = welcome.build()
    html = [str(b.value) for b in page.blocks.values() if getattr(b, "value", None) and "Admin sign-in" in str(b.value)]
    assert html == [welcome.ADMIN_LINK] and 'href="/admin/"' in welcome.ADMIN_LINK


# ---------------------------------------------------------------- the routes

@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from creditcoach.app import main, server

    return TestClient(server.create(main.build(), ""))


def test_the_admin_dashboard_needs_the_admin_cookie(client):
    assert client.get("/admin/dashboard/", follow_redirects=False).headers["location"] == "/admin/"
    client.cookies.set(sessions.COOKIE, sessions.cookie_for("creditcoach_user1"))  # signed in as a user
    assert client.get("/admin/dashboard/", follow_redirects=False).headers["location"] == "/admin/"


def test_an_admin_ticket_signs_in_and_opens_the_dashboard(client):
    _, ticket = admin_page.sign_in(config.ADMIN_EMAIL, FIRST)
    r = client.get(f"/admin/enter?t={ticket}&note=sent", follow_redirects=False)
    assert r.headers["location"] == "/admin/dashboard/?note=sent"
    assert "Path=/admin" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]
    assert client.get("/admin/dashboard/", follow_redirects=False).status_code == 200
    assert client.get("/admin/", follow_redirects=False).headers["location"] == "/admin/dashboard/"
    assert client.get("/admin/?reset=x", follow_redirects=False).status_code == 200  # a reset link still opens
    assert client.get("/app/", follow_redirects=False).headers["location"] == "/welcome/"  # not the chat


def test_a_used_or_user_ticket_doesnt_open_the_admin_dashboard(client):
    _, ticket = admin_page.sign_in(config.ADMIN_EMAIL, FIRST)
    client.get(f"/admin/enter?t={ticket}", follow_redirects=False)
    client.cookies.clear()
    assert client.get(f"/admin/enter?t={ticket}", follow_redirects=False).headers["location"] == "/admin/"
    user = sessions.issue_ticket("creditcoach_user1")
    assert client.get(f"/admin/enter?t={user}", follow_redirects=False).headers["location"] == "/admin/"


def test_admin_log_out_clears_the_admin_cookie(client):
    r = client.get("/admin/logout", follow_redirects=False)
    assert r.headers["location"] == "/welcome/" and 'creditcoach_admin=""' in r.headers["set-cookie"]
