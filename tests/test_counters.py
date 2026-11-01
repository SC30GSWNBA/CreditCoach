"""Usage counters (2026-11-01): questions answered and people signed up on the welcome page, and each signed-in
user's own count above the chat.

Memory uses the "files" backend in a temporary folder (tests/conftest.py), so nothing touches Neon.

Run:
    uv run pytest tests/test_counters.py -v
"""

from types import SimpleNamespace

import pytest

from creditcoach import config
from creditcoach.app import counters, main
from creditcoach.memory import store
from creditcoach.signup import store as signup


@pytest.fixture(autouse=True)
def memory(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEMORY_DIR", tmp_path / "memory")
    counters._cache.clear()
    main._answered.clear()
    main._sessions.clear()


def session(user_id, source="chat_ui", answers=1, errors=0):
    s = store.start_session(user_id, source=source)
    for i in range(answers):
        store.record(s, "user_message", f"question {i}")
        store.record(s, "assistant_message", f"answer {i}")
    for _ in range(errors):
        store.record(s, "error", "answer service failed")
    return s


def test_only_answers_the_chat_app_gave_are_counted():
    session("USR-001", answers=2, errors=1)  # a failed answer isn't an answer
    session("USR-001", answers=1)
    session("USR-002", answers=3)
    session("USR-002", source="eval", answers=5)  # eval, evidence and CLI runs never count
    session("USR-003", source="evidence", answers=4)
    everyone = store.answered()
    assert (everyone["answers"], everyone["sessions"]) == (6, 3) and everyone["since"]
    assert {k: v for k, v in store.answered("USR-001").items() if k != "since"} == {"answers": 3, "sessions": 2}
    assert store.answered("USR-003") == {"answers": 0, "sessions": 0, "since": None}


def test_the_welcome_page_shows_both_counters_and_keeps_them_briefly(monkeypatch):
    session("USR-001", answers=2)
    monkeypatch.setattr(signup, "signed_up", lambda: 7)
    page = counters.public_html()
    assert "Questions answered" in page and 'data-cc-count="2"' in page and "Live" in page
    assert "People signed up" in page and 'data-cc-count="7"' in page
    session("USR-001", answers=1)
    assert 'data-cc-count="2"' in counters.public_html()  # kept for CACHE_SECONDS
    counters._cache.clear()
    assert 'data-cc-count="3"' in counters.public_html()


def test_a_counter_that_cant_be_read_is_left_out_and_the_page_works(monkeypatch):
    monkeypatch.setattr(signup, "signed_up", lambda: (_ for _ in ()).throw(signup.SignupUnavailable()))
    assert "People signed up" not in counters.public_html() and "Questions answered" in counters.public_html()
    counters._cache.clear()
    monkeypatch.setattr(store, "answered", lambda user_id=None: 1 / 0)
    assert counters.public_html() == ""


def test_signed_up_needs_neon(monkeypatch):
    monkeypatch.setattr(config, "DATA_BACKEND", "files")
    with pytest.raises(signup.SignupUnavailable):
        signup.signed_up()


def test_the_users_own_counter_reads_like_a_sentence():
    assert "No questions answered for you yet" in counters.mine_html(0, 0, None)
    one = counters.mine_html(1, 1, "2026-10-14T09:00:00.000Z")
    assert "question answered for you so far" in one and "across 1 session since 14 Oct 2026" in one
    assert "questions answered" in counters.mine_html(5, 2, "2026-10-14T09:00:00.000Z")


def request(username, session_hash="page-1"):
    return SimpleNamespace(username=username, session_hash=session_hash)


def test_the_users_counter_counts_their_sessions_and_goes_up_with_each_answer():
    session("USR-001", answers=4)
    session("USR-002", answers=9)  # someone else's answers aren't theirs
    page = request("creditcoach_user1")
    assert 'data-cc-count="4"' in main.my_answers(page) and "across 1 session" in main.my_answers(page)
    main.count_answer(page, "USR-001")
    main.count_answer(page, "USR-001")
    shown = main.my_answers(page)
    assert 'data-cc-count="6"' in shown and "across 2 sessions" in shown  # this session counted once
    assert main.my_answers(request(None)) == "" and main.my_answers(request("nobody")) == ""


def test_the_users_counter_is_read_once_per_page_not_on_every_chat_update(monkeypatch):
    reads = []
    monkeypatch.setattr(store, "answered", lambda user_id=None: reads.append(user_id) or
                        {"answers": 1, "sessions": 1, "since": None})
    page = request("creditcoach_user1")
    for _ in range(5):
        main.my_answers(page)
    assert reads == ["USR-001"]
