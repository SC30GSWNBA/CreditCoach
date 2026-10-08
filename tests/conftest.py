"""Shared test setup: memory and the dataset always use the "files" backend, so no test touches the shared Neon
database, and the golden queries are checked against the committed data/*.csv."""

import pytest

from creditcoach import config

# Set at import too, not only per test: some test modules call the tools while pytest collects them.
config.DATA_BACKEND = "files"


@pytest.fixture(autouse=True)
def files_memory_backend(monkeypatch):
    monkeypatch.setattr(config, "MEMORY_BACKEND", "files")


@pytest.fixture(autouse=True)
def files_data_backend(monkeypatch):
    monkeypatch.setattr(config, "DATA_BACKEND", "files")
