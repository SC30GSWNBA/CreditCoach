"""The dataset loader (``creditcoach.dataset``): backend choice and failures, without a database.

The Neon copy itself is checked against the CSVs by ``scripts/data_import.py`` and ``creditcoach.check``.

Run:
    uv run pytest tests/test_dataset.py -v
"""

import io

import pandas as pd
import pytest

from creditcoach import config, dataset
from creditcoach.agent import mcp_host
from creditcoach.memory import pg
from creditcoach.tools import common
from creditcoach.tools.score_history import get_score_history


def test_files_backend_reads_the_csvs():
    users, accounts, scores = dataset.load()
    assert (len(users), len(accounts), len(scores)) == (15, 28, 156)
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
    def down():
        raise ConnectionError("Neon is down")

    monkeypatch.setattr(config, "DATA_BACKEND", "postgres")
    monkeypatch.setattr(pg, "pool", down)
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
