"""Unit tests must not write synthetic traces into the developer's trace history."""

import pytest


@pytest.fixture(autouse=True)
def isolated_observability(monkeypatch):
    monkeypatch.setenv('EMPORIO_TRACE_ENABLED', 'false')
