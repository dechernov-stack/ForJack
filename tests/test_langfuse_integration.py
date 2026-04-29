"""Langfuse integration tests.

Unit tests (always run): key validation, prompt cache, context var.
Integration test (skipped if LANGFUSE_PUBLIC_KEY not set): real API call.
"""
from __future__ import annotations

import os

import pytest

# ── helper: reset singleton between tests ────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_langfuse_singleton():
    from storytelling_bot import langfuse_ctx
    langfuse_ctx._reset_for_tests()
    langfuse_ctx.set_trace_id(None)
    langfuse_ctx._PROMPT_CACHE._cache.clear()
    yield
    langfuse_ctx._reset_for_tests()
    langfuse_ctx.set_trace_id(None)
    langfuse_ctx._PROMPT_CACHE._cache.clear()


# ── ConfigError on bad key format ────────────────────────────────────────────

def test_bad_public_key_raises_config_error(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "wrong-format-key")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-valid")
    from storytelling_bot.langfuse_ctx import ConfigError, get_langfuse
    with pytest.raises(ConfigError, match="pk-lf-"):
        get_langfuse()


def test_bad_secret_key_raises_config_error(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-valid")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "wrong-format")
    from storytelling_bot.langfuse_ctx import ConfigError, get_langfuse
    with pytest.raises(ConfigError, match="sk-lf-"):
        get_langfuse()


def test_no_keys_returns_none(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    from storytelling_bot.langfuse_ctx import get_langfuse
    assert get_langfuse() is None


def test_correct_key_format_does_not_raise(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-abc123")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-xyz789")
    from storytelling_bot.langfuse_ctx import ConfigError, _validate_keys
    # Test only the key-format validation (no Langfuse import or network call needed).
    try:
        _validate_keys()
    except ConfigError:
        pytest.fail("Valid pk-lf-/sk-lf- prefix should not raise ConfigError")


# ── context var propagation ──────────────────────────────────────────────────

def test_set_get_trace_id():
    from storytelling_bot.langfuse_ctx import get_trace_id, set_trace_id
    assert get_trace_id() is None
    set_trace_id("abc-123")
    assert get_trace_id() == "abc-123"
    set_trace_id(None)
    assert get_trace_id() is None


def test_trace_context_manager_sets_id(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    from storytelling_bot.langfuse_ctx import get_trace_id, trace
    with trace("pipeline_run", "test_entity") as t:
        assert t is None  # no Langfuse client
        assert get_trace_id() is None  # still None when disabled
    assert get_trace_id() is None


# ── prompt cache ─────────────────────────────────────────────────────────────

def test_get_prompt_returns_fallback_when_no_langfuse(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    from storytelling_bot.langfuse_ctx import get_prompt
    result = get_prompt("classify_fact", "FALLBACK_PROMPT")
    assert result == "FALLBACK_PROMPT"


def test_get_prompt_cached_second_call_skips_langfuse(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    from storytelling_bot import langfuse_ctx
    langfuse_ctx._PROMPT_CACHE.set("my_prompt", "CACHED_VALUE")
    result = langfuse_ctx.get_prompt("my_prompt", "FALLBACK")
    assert result == "CACHED_VALUE"


def test_get_prompt_cache_ttl_expired():
    import time

    from storytelling_bot import langfuse_ctx
    langfuse_ctx._PROMPT_CACHE._cache["old"] = ("STALE", time.monotonic() - 400)
    result = langfuse_ctx.get_prompt("old", "FRESH_FALLBACK")
    assert result == "FRESH_FALLBACK"


# ── span noop when no trace active ───────────────────────────────────────────

def test_span_noop_when_no_langfuse(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    from storytelling_bot.langfuse_ctx import span
    with span("collector.research.tavily") as s:
        assert s is None  # noop


# ── integration test (real Langfuse) ─────────────────────────────────────────

@pytest.mark.skipif(
    not os.environ.get("LANGFUSE_PUBLIC_KEY"),
    reason="LANGFUSE_PUBLIC_KEY not set",
)
def test_trace_created_in_langfuse():
    """Create a trace and verify it's flushed without error."""
    from storytelling_bot.langfuse_ctx import get_langfuse, trace
    with trace("test_pipeline_run", "test_entity") as t:
        assert t is not None, "Langfuse trace must be created when keys are valid"
    lf = get_langfuse()
    assert lf is not None
    lf.flush()  # should not raise
