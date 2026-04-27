"""OfflineIngest — manual fact upload (offline_interview)."""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from storytelling_bot.collectors.base import DEMO_CORPUS
from storytelling_bot.schema import SourceType

log = logging.getLogger(__name__)
_OVERLAY_PATH = Path("offline_overlay.json")


class OfflineIngest:
    source_type = SourceType.OFFLINE_INTERVIEW

    def collect(self, entity_id: str) -> List[Dict[str, Any]]:
        corpus = DEMO_CORPUS.get(entity_id, [])
        base = [c for c in corpus if c["source_type"] == self.source_type]
        if _OVERLAY_PATH.exists():
            try:
                overlay = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
                base += [
                    {
                        "source_type": SourceType.OFFLINE_INTERVIEW,
                        "url": r.get("url", "internal://manual"),
                        "captured_at": r.get("added_at", dt.date.today().isoformat())[:10],
                        "text": r["text"],
                        "entity_focus": r.get("entity", entity_id),
                    }
                    for r in overlay
                    if r.get("entity") == entity_id
                ]
            except Exception:
                pass
        return base

    def add_fact(self, entity_id: str, text: str, source_url: str) -> None:
        overlay: List[Dict[str, Any]] = []
        if _OVERLAY_PATH.exists():
            try:
                overlay = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        overlay.append({
            "entity": entity_id,
            "text": text,
            "source_type": SourceType.OFFLINE_INTERVIEW.value,
            "url": source_url,
            "added_at": dt.datetime.now(dt.UTC).isoformat(),
        })
        _OVERLAY_PATH.write_text(json.dumps(overlay, ensure_ascii=False, indent=2), encoding="utf-8")
        DEMO_CORPUS.setdefault(entity_id, []).append({
            "source_type": SourceType.OFFLINE_INTERVIEW,
            "url": source_url,
            "captured_at": dt.date.today().isoformat(),
            "text": text,
            "entity_focus": entity_id,
        })
        log.info("Offline fact added for %s", entity_id)
