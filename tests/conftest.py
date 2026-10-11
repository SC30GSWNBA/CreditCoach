"""Shared test setup: memory and the dataset always use the "files" backend, so no test touches the shared Neon
database, and the golden queries are checked against the committed data/*.csv."""

import pytest

from creditcoach import config

# Set at import too, not only per test: some test modules call the tools while pytest collects them.
config.DATA_BACKEND = "files"


@pytest.fixture(autouse=True)
def cache_off(monkeypatch):
    """The cache is off unless a test turns it on (tests/test_cache.py), so no test depends on an earlier one."""
    monkeypatch.setattr(config, "CACHE", "off")


@pytest.fixture(autouse=True)
def files_memory_backend(monkeypatch):
    monkeypatch.setattr(config, "MEMORY_BACKEND", "files")


@pytest.fixture(autouse=True)
def files_data_backend(monkeypatch):
    monkeypatch.setattr(config, "DATA_BACKEND", "files")


@pytest.fixture(autouse=True)
def no_live_guardrail_review(monkeypatch):
    """The guardrail layer's one model call never runs in tests: a test that needs it supplies its own."""
    from creditcoach.guardrails import checks

    def unstubbed(*args, **kwargs):
        raise AssertionError("checks.model_review was called without a stub")

    monkeypatch.setattr(checks, "model_review", unstubbed)
