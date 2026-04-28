"""Centralised Langfuse wiring: validation, singleton, context propagation, prompt cache."""
from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import time

log = logging.getLogger(__name__)

# ── sentinel / singleton ──────────────────────────────────────────────────────

_SENTINEL = object()
_INSTANCE = _SENTINEL  # None → disabled, object → Langfuse client


class ConfigError(RuntimeError):
    """Raised when LANGFUSE_* keys are set but have wrong format."""


# ── context var: current trace ID (thread/task-local) ────────────────────────

_CURRENT_TRACE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "langfuse_trace_id", default=None
)


def set_trace_id(trace_id: str | None) -> None:
    _CURRENT_TRACE_ID.set(trace_id)


def get_trace_id() -> str | None:
    return _CURRENT_TRACE_ID.get()


# ── key validation ────────────────────────────────────────────────────────────


def _validate_keys() -> None:
    pub = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sec = os.environ.get("LANGFUSE_SECRET_KEY", "")
    if not pub and not sec:
        return  # Langfuse disabled — no validation needed
    if pub and not pub.startswith("pk-lf-"):
        raise ConfigError(
            f"LANGFUSE_PUBLIC_KEY must start with 'pk-lf-' (got '{pub[:12]}...'). "
            "Check your .env — copy the key directly from Langfuse UI."
        )
    if sec and not sec.startswith("sk-lf-"):
        raise ConfigError(
            f"LANGFUSE_SECRET_KEY must start with 'sk-lf-' (got '{sec[:12]}...'). "
            "Check your .env — copy the key directly from Langfuse UI."
        )


# ── singleton getter ──────────────────────────────────────────────────────────


def get_langfuse():
    """Return Langfuse client (validated, cached). Returns None if not configured."""
    global _INSTANCE
    if _INSTANCE is not _SENTINEL:
        return _INSTANCE

    _validate_keys()

    pub = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    if not pub:
        _INSTANCE = None
        return None

    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
    try:
        from langfuse import Langfuse
        _INSTANCE = Langfuse(
            public_key=pub,
            secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
            host=host,
        )
        log.info("Langfuse connected → %s", host)
    except Exception as exc:
        log.warning("Langfuse init failed (%s) — tracing disabled", exc)
        _INSTANCE = None
    return _INSTANCE


def _reset_for_tests() -> None:
    """Reset singleton so tests can inject different env vars."""
    global _INSTANCE
    _INSTANCE = _SENTINEL


# ── trace context manager ─────────────────────────────────────────────────────


@contextlib.contextmanager
def trace(name: str, entity_id: str):
    """Create a Langfuse trace for a pipeline run; set context var for child spans."""
    lf = get_langfuse()
    if not lf:
        set_trace_id(None)
        yield None
        return

    t = None
    try:
        t = lf.trace(name=name, input={"entity_id": entity_id})
        set_trace_id(t.id)
    except Exception:
        log.exception("Langfuse trace() failed — continuing without tracing")
        set_trace_id(None)

    try:
        yield t
    finally:
        set_trace_id(None)
        if t:
            try:
                lf.flush()
            except Exception:
                pass


@contextlib.contextmanager
def span(name: str, input_data: dict | None = None):
    """Create a span under the current trace. Noop if no active trace."""
    lf = get_langfuse()
    trace_id = get_trace_id()
    s = None
    if lf and trace_id:
        try:
            t = lf.trace(id=trace_id)
            s = t.span(name=name, input=input_data)
        except Exception:
            pass
    try:
        yield s
    finally:
        if s:
            try:
                s.end()
            except Exception:
                pass


# ── prompt management with cache ──────────────────────────────────────────────


class _PromptCache:
    def __init__(self, ttl: int = 300) -> None:
        self._cache: dict[str, tuple[str, float]] = {}
        self._ttl = ttl

    def get(self, name: str) -> str | None:
        entry = self._cache.get(name)
        if entry is None:
            return None
        text, ts = entry
        if time.monotonic() - ts > self._ttl:
            del self._cache[name]
            return None
        return text

    def set(self, name: str, text: str) -> None:
        self._cache[name] = (text, time.monotonic())

    def invalidate(self, name: str) -> None:
        self._cache.pop(name, None)


_PROMPT_CACHE = _PromptCache(ttl=300)


def get_prompt(name: str, fallback: str) -> str:
    """Fetch prompt from Langfuse Prompt Management (cached 5 min); fall back to literal."""
    cached = _PROMPT_CACHE.get(name)
    if cached is not None:
        return cached

    lf = get_langfuse()
    if lf:
        try:
            prompt_obj = lf.get_prompt(name, label="production", fallback=None)
            if prompt_obj and prompt_obj.prompt:
                text = prompt_obj.prompt
                _PROMPT_CACHE.set(name, text)
                log.debug("Loaded prompt '%s' from Langfuse Prompt Management", name)
                return text
        except Exception:
            log.debug("Prompt '%s' not found in Langfuse — using hardcoded fallback", name)

    _PROMPT_CACHE.set(name, fallback)
    return fallback
