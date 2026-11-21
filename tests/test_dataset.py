"""The dataset loader (``creditcoach.dataset``): backend choice and failures, without a database.

The Neon copy itself is checked against the CSVs by ``scripts/data_import.py`` and ``creditcoach.check``.

Run:
    uv run pytest tests/test_dataset.py -v
"""

import io

import pandas as pd
import psycopg
import pytest

from creditcoach import config, dataset
from creditcoach.agent import mcp_host
from creditcoach.tools import common
from creditcoach.tools.score_history import get_score_history


def test_files_backend_reads_the_csvs():
    users, accounts, scores = dataset.load()
    assert (len(users), len(accounts), len(scores)) == (15, 28, 169)
    assert users.equals(pd.read_csv(config.DATA_DIR / "users.csv", dtype=str, keep_default_na=False))


def test_columns_match_the_csv_headers():
    for table in dataset.TABLES:
        header = (config.DATA_DIR / f"{table}.csv").read_text(encoding="utf-8").splitlines()[0]
        assert header.split(",") == dataset.COLUMNS[table], table


def test_csv_text_parses_the_same_as_the_file():
    """Neon's rows arrive as CSV text (COPY TO STDOUT); parsed with the same options they equal the file's."""
    for table, frame in zip(dataset.TABLES, dataset.read_files()):
        text = (config.DATA_DIR / f"{table}.csv").read_bytes()
        assert dataset.parse(table, io.BytesIO(text)).equals(frame), table


def test_unknown_backend_is_refused(monkeypatch):
    monkeypatch.setattr(config, "DATA_BACKEND", "sqlite")
    with pytest.raises(ValueError, match="unknown data backend"):
        dataset.load()


def test_unreachable_neon_is_data_unavailable(monkeypatch):
    def down(*args, **kwargs):
        raise ConnectionError("Neon is down")

    monkeypatch.setattr(config, "DATA_BACKEND", "postgres")
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://u:p@example.neon.tech/db")
    monkeypatch.setattr(psycopg, "connect", down)
    common.tables.cache_clear()
    try:
        r = get_score_history("USR-001", "latest")
        assert r["error"]["code"] == "DATA_UNAVAILABLE" and r["error"]["retryable"] is True
        assert "ConnectionError" in r["error"]["message"]
    finally:
        common.tables.cache_clear()  # later tests read the real files again


def test_tool_server_gets_this_processs_backend(monkeypatch):
    monkeypatch.setattr(config, "DATA_BACKEND", "files")
    assert mcp_host.server_params().env["CREDITCOACH_DATA_BACKEND"] == "files"
    monkeypatch.setattr(config, "DATA_BACKEND", "postgres")
    assert mcp_host.server_params().env["CREDITCOACH_DATA_BACKEND"] == "postgres"


def test_tool_server_gets_the_database_url_from_this_process(monkeypatch):
    """Found deploying to Railway: with no .env file, the tool server never saw DATABASE_URL and every call failed."""
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://u:p@example.neon.tech/db")
    assert mcp_host.server_params().env["DATABASE_URL"] == "postgresql://u:p@example.neon.tech/db"
    monkeypatch.setattr(config, "DATABASE_URL", "")
    assert "DATABASE_URL" not in mcp_host.server_params().env


def test_tool_server_runs_its_numeric_libraries_on_one_thread():
    """Found load-testing Railway: each server started 48 threads, and 50 servers at once ran the app out of them."""
    env = mcp_host.server_params().env
    assert env["OMP_NUM_THREADS"] == env["OPENBLAS_NUM_THREADS"] == env["MKL_NUM_THREADS"] == "1"


def test_one_users_read_has_only_their_rows_and_the_datasets_latest_month():
    """Each answer's tool server reads one user's rows (2026-11-21), but "now" stays the whole dataset's last month."""
    everyone = dataset.load()
    users, accounts, scores = dataset.load("USR-001")
    assert set(users.user_id) == set(accounts.user_id) == set(scores.user_id) == {"USR-001"}
    assert len(scores) == (everyone[2].user_id == "USR-001").sum()
    assert dataset.latest_month(scores) == dataset.latest_month(everyone[2])


def test_a_tool_server_for_one_user_finds_no_other_user(monkeypatch):
    monkeypatch.setenv(common.SERVER_USER, "USR-001")
    common.tables.cache_clear()
    try:
        assert get_score_history("USR-001", "latest")["ok"] is True
        assert get_score_history("USR-002", "latest")["error"]["code"] == "UNKNOWN_USER"
    finally:
        common.tables.cache_clear()


def test_the_tool_server_is_told_its_user():
    assert mcp_host.server_params("USR-040").env[common.SERVER_USER] == "USR-040"
    assert common.SERVER_USER not in mcp_host.server_params().env


def test_user_ids_may_have_four_digits():
    """Sign-ups past the 999th are USR-1000 and on (2026-11-21); a fifth digit is still refused."""
    from creditcoach.guardrails import checks
    from creditcoach.memory import store

    for pattern in (common.USER_ID, store.USER_ID):
        assert pattern.fullmatch("USR-1000") and pattern.fullmatch("USR-001") and not pattern.fullmatch("USR-10000")
    assert checks.USER_ID.search("my id is USR-1000") and not checks.USER_ID.search("USR-10000")
