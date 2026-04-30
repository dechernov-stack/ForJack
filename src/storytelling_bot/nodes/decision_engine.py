"""DecisionEngine node — decision matrix from architecture.md."""
from __future__ import annotations

import datetime as dt
import logging

from storytelling_bot.schema import Flag, Layer, State

log = logging.getLogger(__name__)

_KEY_LAYERS = {Layer.FOUNDER_PERSONAL, Layer.FOUNDER_PROFESSIONAL, Layer.PRODUCT_BUSINESS}
_HIGH_CONF_CATS = {"hard:sanctions", "hard:criminal"}


def node_decision_engine(state: State) -> dict:
    kept_idxs = {s.fact_idx for s in state.fact_scores if s.keep}

    hard, soft = [], []
    for i, f in enumerate(state.facts):
        if i not in kept_idxs:
            continue
        if f.flag != Flag.RED or not f.red_flag_category:
            continue
        (hard if f.red_flag_category.startswith("hard:") else soft).append(f)

    green_in_key = sum(
        1 for i, f in enumerate(state.facts)
        if i in kept_idxs and f.flag == Flag.GREEN and f.layer in _KEY_LAYERS
    )

    high_conf_hard = [f for f in hard if f.confidence >= 0.85 and f.red_flag_category in _HIGH_CONF_CATS]

    if len(hard) >= 2:
        decision, rationale = "terminate", f">=2 hard red flags ({len(hard)})"
    elif high_conf_hard:
        decision, rationale = "terminate", f"hard sanctions/criminal conf>=0.85: {[f.red_flag_category for f in high_conf_hard]}"
    elif len(hard) == 1 or len(soft) >= 4:
        decision, rationale = "pause", f"hard={len(hard)}, soft={len(soft)}"
    elif len(hard) == 0 and len(soft) <= 1 and green_in_key >= 5:
        decision, rationale = "continue", f"0 hard, soft<={len(soft)}, green в ключевых={green_in_key}"
    else:
        decision = "watch"
        rationale = f"hard={len(hard)}, soft={len(soft)}, green в ключевых слоях={green_in_key}"

    result = {
        "recommendation": decision,
        "rationale": rationale,
        "hard_red_count": len(hard),
        "soft_red_count": len(soft),
        "green_in_key_layers": green_in_key,
        "evaluated_at": dt.datetime.now(dt.UTC).isoformat(),
        "human_approval_required": True,
    }
    log.info("Decision: %s (%s)", decision.upper(), rationale)
    return {"decision": result}
