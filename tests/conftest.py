"""Shared test setup: memory always uses the "files" backend, so no test writes to the shared Neon database."""

import pytest

from creditcoach import config


@pytest.fixture(autouse=True)
def files_memory_backend(monkeypatch):
    monkeypatch.setattr(config, "MEMORY_BACKEND", "files")
