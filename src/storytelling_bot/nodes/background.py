"""BackgroundFill node — Claude fills baseline profile from training knowledge."""
from __future__ import annotations

import datetime as dt
import json
import logging
import re

from storytelling_bot.llm import get_llm_client
from storytelling_bot.schema import State

log = logging.getLogger(__name__)

_SYSTEM = """\
You are an OSINT research analyst. Given a person or company identifier, \
provide comprehensive background information from your knowledge.

Return ONLY valid JSON (no markdown fences) with this exact structure:
{
  "display_name": "Full Name in English",
  "birth_date": "YYYY-MM-DD or null",
  "nationalities": ["US"],
  "roles": [
    {"company": "Tesla", "title": "CEO", "start_year": 2008, "is_current": true}
  ],
  "risk_level": "unknown",
  "facts": [
    {"text": "...", "layer": 1, "subcategory": "Origin & Childhood", "flag": "green"}
  ]
}

Layers:
1 = Founder Personal Story (origin, childhood, values, beliefs, identity)
2 = Founder Professional Story (career path, company history, motivation)
3 = Community Culture (team culture, values, key hires, investors)
4 = Community Professional Experience (team expertise, backgrounds)
5 = Client Stories (clients, key partnerships, deals)
6 = Product & Business (products, business model, revenue, financials)
7 = Social Impact (vision, controversies, public statements, scandals)
8 = Political/Economic Context (regulatory, geopolitical, sanctions, legal)

risk_level: one of "unknown", "low_risk", "watch", "high_risk"
flag: "green" for positive/verified facts, "red" for serious concerns or \
controversies, "grey" for neutral/informational

Generate 20-30 substantive facts spanning multiple layers. Include known \
controversies and regulatory issues as red flags.
If entity is completely unknown to you, return {"display_name": null, "facts": []}.\
"""


def node_fill_background(state: State) -> dict:
    llm = get_llm_client()
    entity_name = state.entity_id.replace("-", " ").replace("_", " ")

    try:
        raw = llm._call(_SYSTEM, f'Entity: "{entity_name}"', "background_fill", max_tokens=3000)
        clean = re.sub(r"```[a-z]*\n?", "", raw).strip().rstrip("`").strip()
        data = json.loads(clean)
    except Exception as exc:
        log.warning("Background fill failed for %s: %s", state.entity_id, exc)
        return {}

    if not data.get("display_name"):
        log.info("Background fill: unknown entity %s", state.entity_id)
        return {}

    now = dt.datetime.now(dt.UTC).isoformat()
    chunks = []
    for f in data.get("facts", []):
        text = f.get("text", "").strip()
        if not text:
            continue
        chunks.append({
            "text": text,
            "url": "internal://claude-knowledge",
            "source_type": "online_research",
            "captured_at": now,
            "entity_focus": state.entity_id,
            "_layer_hint": f.get("layer"),
            "_subcategory_hint": f.get("subcategory"),
            "_flag_hint": f.get("flag"),
        })

    person_meta = {
        "display_name": data.get("display_name"),
        "birth_date": data.get("birth_date"),
        "nationalities": data.get("nationalities", []),
        "roles": data.get("roles", []),
        "risk_level": data.get("risk_level", "unknown"),
    }

    log.info(
        "Background fill: %d knowledge facts for '%s' (display_name=%s)",
        len(chunks), state.entity_id, person_meta["display_name"],
    )
    return {
        "raw_chunks": state.raw_chunks + chunks,
        "person_meta": person_meta,
    }
