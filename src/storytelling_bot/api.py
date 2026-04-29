"""FastAPI REST API — dossier, watchlist, pipeline trigger."""
from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException

from .person_resolver import resolve_person
from .schema import Fact, Flag, Layer
from .storage.postgres import PostgresStore

log = logging.getLogger(__name__)

app = FastAPI(title="Storytelling Bot API", version="0.1.0")

_WATCHLIST_PATH = Path(os.environ.get("WATCHLIST_PATH", "data/watchlist.json"))
_store_instance: PostgresStore | None = None
_runs: dict[str, str] = {}


def _store() -> PostgresStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = PostgresStore()
    return _store_instance


# ── Watchlist ─────────────────────────────────────────────────────────────────

@app.get("/api/watchlist")
def get_watchlist() -> dict[str, Any]:
    if not _WATCHLIST_PATH.exists():
        return {"entities": []}
    return json.loads(_WATCHLIST_PATH.read_text(encoding="utf-8"))


# ── Dossier ───────────────────────────────────────────────────────────────────

@app.get("/api/entities/{entity_id}/dossier")
def get_dossier(entity_id: str) -> dict[str, Any]:
    store = _store()
    raw_rows = store.load_facts(entity_id)

    facts: list[Fact] = []
    for r in raw_rows:
        try:
            facts.append(
                Fact(
                    entity_id=r["entity_id"],
                    layer=Layer(int(r["layer"])),
                    subcategory=r["subcategory"],
                    source_type=r["source_type"],
                    text=r["text"],
                    source_url=r["source_url"],
                    captured_at=r["captured_at"],
                    flag=r.get("flag", "grey"),
                    confidence=float(r.get("confidence", 0.5)),
                    red_flag_category=r.get("red_flag_category"),
                )
            )
        except Exception:
            continue

    person = resolve_person(entity_id, facts)
    decision = store.load_latest_decision(entity_id)
    red_flags = [
        {
            "category": f.red_flag_category or "GENERAL",
            "text": f.text[:200],
            "confidence": f.confidence,
        }
        for f in facts
        if f.flag == Flag.RED
    ]

    return {
        "entity_id": person.entity_id,
        "display_name": person.display_name,
        "birth_date": person.birth_date.isoformat() if person.birth_date else None,
        "nationalities": person.nationalities,
        "aka_string": person.aka_string,
        "photo_url": person.photo_url,
        "risk_level": person.risk_level,
        "roles": [r.model_dump() for r in person.roles],
        "facts_count": len(facts),
        "red_flags": red_flags,
        "decision": decision,
    }


# ── Pipeline run ──────────────────────────────────────────────────────────────

def _run_pipeline(entity_id: str, job_id: str) -> None:
    from .graph import build_graph
    from .schema import State

    _runs[job_id] = "running"
    try:
        state = State(entity_id=entity_id)
        build_graph().run(state)
        _runs[job_id] = "done"
    except Exception as exc:
        log.exception("Pipeline failed for %s", entity_id)
        _runs[job_id] = f"error: {exc}"


@app.post("/api/entities/{entity_id}/run", status_code=202)
def trigger_run(entity_id: str, background_tasks: BackgroundTasks) -> dict[str, str]:
    job_id = str(uuid.uuid4())
    _runs[job_id] = "queued"
    background_tasks.add_task(_run_pipeline, entity_id, job_id)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/runs/{job_id}")
def get_run_status(job_id: str) -> dict[str, str]:
    status = _runs.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "status": status}
