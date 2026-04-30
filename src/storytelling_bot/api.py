"""FastAPI REST API — dossier, watchlist, pipeline trigger."""
from __future__ import annotations

import datetime
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .person_resolver import resolve_person
from .schema import Fact, Flag, Layer
from .storage.postgres import PostgresStore

log = logging.getLogger(__name__)

app = FastAPI(title="Storytelling Bot API", version="0.1.0")

_WATCHLIST_PATH = Path(os.environ.get("WATCHLIST_PATH", "data/watchlist.json"))
_UI_HTML = Path(__file__).parent / "templates" / "ui.html"
_watchlist_lock = threading.Lock()
_store_instance: PostgresStore | None = None
_runs: dict[str, str] = {}


@app.get("/")
def serve_ui() -> FileResponse:
    return FileResponse(_UI_HTML, media_type="text/html")


def _store() -> PostgresStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = PostgresStore()
    return _store_instance


def _read_watchlist() -> dict[str, Any]:
    if not _WATCHLIST_PATH.exists():
        return {"entities": []}
    return json.loads(_WATCHLIST_PATH.read_text(encoding="utf-8"))


def _write_watchlist(data: dict[str, Any]) -> None:
    _WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _WATCHLIST_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Watchlist ─────────────────────────────────────────────────────────────────

@app.get("/api/watchlist")
def get_watchlist() -> dict[str, Any]:
    return _read_watchlist()


class WatchlistEntry(BaseModel):
    id: str
    display_name: str = ""
    kind: str = "person"
    notes: str = ""


@app.post("/api/watchlist", status_code=201)
def add_to_watchlist(entry: WatchlistEntry) -> dict[str, Any]:
    with _watchlist_lock:
        data = _read_watchlist()
        entities = data.get("entities", [])
        if any(e["id"] == entry.id for e in entities):
            raise HTTPException(status_code=409, detail="Already in watchlist")
        entities.append({
            "id": entry.id,
            "kind": entry.kind,
            "display_name": entry.display_name or entry.id.replace("-", " ").title(),
            "added_at": datetime.date.today().isoformat(),
            "notes": entry.notes,
        })
        data["entities"] = entities
        _write_watchlist(data)
    return {"id": entry.id, "status": "added"}


@app.delete("/api/watchlist/{entity_id}", status_code=204)
def remove_from_watchlist(entity_id: str) -> None:
    with _watchlist_lock:
        data = _read_watchlist()
        entities = data.get("entities", [])
        filtered = [e for e in entities if e["id"] != entity_id]
        if len(filtered) == len(entities):
            raise HTTPException(status_code=404, detail="Not in watchlist")
        data["entities"] = filtered
        _write_watchlist(data)


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

    db_person_row = store.load_person(entity_id)
    if db_person_row:
        import json as _json
        nat_raw = db_person_row.get("nationalities", "[]")
        if isinstance(nat_raw, str):
            nat_raw = _json.loads(nat_raw)
        bd = db_person_row.get("birth_date")
        if isinstance(bd, str):
            try:
                import datetime as _dt
                bd = _dt.date.fromisoformat(bd)
            except ValueError:
                bd = None
        from .schema import PersonRole
        db_roles = []
        for r in db_person_row.get("roles", []):
            sd = r.get("start_date")
            if isinstance(sd, str):
                try:
                    import datetime as _dt
                    sd = _dt.date.fromisoformat(str(sd)[:10])
                except (ValueError, TypeError):
                    sd = None
            db_roles.append(PersonRole(
                entity_id=entity_id,
                company_name=r.get("company_name", ""),
                role=r.get("role", ""),
                start_date=sd,
                is_current=r.get("is_current", True),
            ))
        from .schema import Person
        person = Person(
            entity_id=entity_id,
            display_name=db_person_row.get("display_name") or entity_id.replace("-", " ").title(),
            birth_date=bd,
            nationalities=nat_raw,
            risk_level=db_person_row.get("risk_level", "unknown"),
            roles=db_roles,
        )
    else:
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

    seen_urls: set[str] = set()
    sources = []
    for f in facts:
        if f.source_url not in seen_urls and not f.source_url.startswith("internal://"):
            seen_urls.add(f.source_url)
            cap = f.captured_at.isoformat() if hasattr(f.captured_at, "isoformat") else str(f.captured_at)
            sources.append({"url": f.source_url, "source_type": str(f.source_type), "captured_at": cap})

    wl_ids = {e["id"] for e in _read_watchlist().get("entities", [])}

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
        "sources": sources,
        "decision": decision,
        "in_watchlist": entity_id in wl_ids,
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
