"""Tests for the FastAPI REST API."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from storytelling_bot.api import app

client = TestClient(app)


def _mock_store(facts=None, decision=None):
    m = MagicMock()
    m.load_facts.return_value = facts or []
    m.load_latest_decision.return_value = decision
    return m


# ── watchlist ─────────────────────────────────────────────────────────────────

def test_watchlist_missing_file(tmp_path, monkeypatch):
    import storytelling_bot.api as api_mod
    monkeypatch.setattr(api_mod, "_WATCHLIST_PATH", tmp_path / "missing.json")
    resp = client.get("/api/watchlist")
    assert resp.status_code == 200
    assert resp.json() == {"entities": []}


def test_watchlist_returns_data(tmp_path, monkeypatch):
    import storytelling_bot.api as api_mod
    wl = tmp_path / "watchlist.json"
    wl.write_text(json.dumps({"entities": [{"id": "stripe", "display_name": "Stripe"}]}))
    monkeypatch.setattr(api_mod, "_WATCHLIST_PATH", wl)
    resp = client.get("/api/watchlist")
    assert resp.status_code == 200
    assert resp.json()["entities"][0]["id"] == "stripe"


# ── dossier ───────────────────────────────────────────────────────────────────

def test_dossier_empty_entity():
    with patch("storytelling_bot.api._store", return_value=_mock_store()):
        resp = client.get("/api/entities/john-doe/dossier")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == "john-doe"
    assert data["display_name"] == "John Doe"
    assert data["facts_count"] == 0
    assert data["decision"] is None
    assert data["red_flags"] == []


def test_dossier_with_decision():
    decision = {
        "recommendation": "continue",
        "rationale": "No red flags found",
        "hard_flag_count": 0,
        "soft_flag_count": 0,
        "green_count": 3,
        "created_at": "2026-04-29T10:00:00",
    }
    with patch("storytelling_bot.api._store", return_value=_mock_store(decision=decision)):
        resp = client.get("/api/entities/stripe/dossier")
    assert resp.status_code == 200
    assert resp.json()["decision"]["recommendation"] == "continue"


def test_dossier_risk_level_defaults_unknown():
    with patch("storytelling_bot.api._store", return_value=_mock_store()):
        resp = client.get("/api/entities/acme/dossier")
    assert resp.json()["risk_level"] == "unknown"


def test_dossier_nationalities_empty_by_default():
    with patch("storytelling_bot.api._store", return_value=_mock_store()):
        resp = client.get("/api/entities/founder-x/dossier")
    assert resp.json()["nationalities"] == []


# ── pipeline run ──────────────────────────────────────────────────────────────

def test_trigger_run_returns_202():
    with patch("storytelling_bot.api._run_pipeline"):
        resp = client.post("/api/entities/stripe/run")
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"


def test_trigger_run_job_ids_are_unique():
    with patch("storytelling_bot.api._run_pipeline"):
        r1 = client.post("/api/entities/a/run").json()
        r2 = client.post("/api/entities/a/run").json()
    assert r1["job_id"] != r2["job_id"]


def test_get_run_status_not_found():
    resp = client.get("/api/runs/nonexistent-job-xyz-999")
    assert resp.status_code == 404


def test_get_run_status_known():
    import storytelling_bot.api as api_mod
    api_mod._runs["test-known-job-42"] = "done"
    resp = client.get("/api/runs/test-known-job-42")
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"
