"""Delta comparison between two Diamond-snapshot reports."""
from __future__ import annotations

from typing import Any


def _fact_key(f: dict[str, Any]) -> str:
    return f"{f.get('source_url', '')}::{hash(f.get('text', ''))}"


def compare(prev: dict[str, Any], curr: dict[str, Any]) -> dict[str, Any]:
    """Compare two JSON report dicts; return structured delta."""
    prev_facts: list[dict] = prev.get("facts", [])
    curr_facts: list[dict] = curr.get("facts", [])

    prev_by_key = {_fact_key(f): f for f in prev_facts}
    curr_by_key = {_fact_key(f): f for f in curr_facts}

    new_facts = [f for f in curr_facts if _fact_key(f) not in prev_by_key]
    removed_facts = [f for f in prev_facts if _fact_key(f) not in curr_by_key]

    moved_facts: list[tuple[dict, str, str]] = []
    for key, f in curr_by_key.items():
        if key in prev_by_key:
            prev_layer = prev_by_key[key].get("layer")
            curr_layer = f.get("layer")
            if prev_layer != curr_layer:
                moved_facts.append((f, str(prev_layer), str(curr_layer)))

    prev_decision = prev.get("decision", {}).get("recommendation")
    curr_decision = curr.get("decision", {}).get("recommendation")
    decision_change = (prev_decision, curr_decision) if prev_decision != curr_decision else None

    prev_challenges = sum(1 for f in prev_facts if f.get("flag") == "red")
    curr_challenges = sum(1 for f in curr_facts if f.get("flag") == "red")
    challenges_change = curr_challenges - prev_challenges

    new_red_flags = [f for f in new_facts if f.get("flag") == "red"]

    subcat_diff: dict[str, dict[str, int]] = {}
    for f in new_facts:
        k = f"{f.get('layer')}|{f.get('subcategory', '')}"
        subcat_diff.setdefault(k, {"added": 0, "removed": 0})
        subcat_diff[k]["added"] += 1
    for f in removed_facts:
        k = f"{f.get('layer')}|{f.get('subcategory', '')}"
        subcat_diff.setdefault(k, {"added": 0, "removed": 0})
        subcat_diff[k]["removed"] += 1

    return {
        "new_facts": new_facts,
        "moved_facts": moved_facts,
        "removed_facts": removed_facts,
        "decision_change": decision_change,
        "challenges_change": challenges_change,
        "new_red_flags": new_red_flags,
        "subcategory_diff": subcat_diff,
    }


def render_digest(delta: dict[str, Any], fmt: str = "markdown") -> str:
    lines = []
    if delta.get("decision_change"):
        prev, curr = delta["decision_change"]
        lines.append(f"**Decision changed**: {prev} → {curr}")
    if delta.get("new_red_flags"):
        lines.append(f"**New red flags**: {len(delta['new_red_flags'])}")
        for f in delta["new_red_flags"][:5]:
            lines.append(f"  - [{f.get('flag','?')}] {f.get('text','')[:100]}")
    lines.append(f"**New facts**: {len(delta['new_facts'])}  |  **Removed**: {len(delta['removed_facts'])}")
    if delta.get("challenges_change"):
        sign = "+" if delta["challenges_change"] > 0 else ""
        lines.append(f"**Red-flag delta**: {sign}{delta['challenges_change']}")
    return "\n".join(lines)
