"""Unit tests must not write synthetic traces into the developer's trace history."""

import pytest


@pytest.fixture(autouse=True)
def isolated_observability(monkeypatch):
    monkeypatch.setenv('EMPORIO_TRACE_ENABLED', 'false')
    # Keep responses independent of the wall clock; hours tests inject their own clock.
    monkeypatch.setenv('EMPORIO_BUSINESS_HOURS_NOTICE', 'false')
