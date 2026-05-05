"""Shared pytest fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_opensanctions_circuit_breaker():
    """Reset the module-level circuit breaker before every test.

    _OPENSANCTIONS_DISABLED persists across tests in the same session because it
    is a module global.  A 401/429 in one test would silently disable all
    subsequent API calls, causing unrelated tests to return None.
    """
    import storytelling_bot.sanctions.checker as checker
    checker._OPENSANCTIONS_DISABLED = False
    yield
    checker._OPENSANCTIONS_DISABLED = False
