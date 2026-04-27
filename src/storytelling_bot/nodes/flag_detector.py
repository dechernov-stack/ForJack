"""FlagDetector node — deterministic sanctions rules → LLM-judge → green."""
from __future__ import annotations

import logging
from collections import defaultdict

from storytelling_bot.llm import get_llm_client
from storytelling_bot.sanctions import check_sanctions
from storytelling_bot.schema import Fact, Flag, State

log = logging.getLogger(__name__)


def node_flag_detector(state: State) -> dict:
    llm = get_llm_client()
    facts: list[Fact] = []

    for fact in state.facts:
        f = fact.model_copy()

        # ── Step 1: deterministic sanctions/keyword hard rules (no LLM call) ──
        hard = check_sanctions(f.text, entity_name=state.entity_id)
        if hard:
            cat, conf = hard
            f.flag = Flag.RED
            f.red_flag_category = cat
            f.confidence = conf
            facts.append(f)
            continue

        # ── Step 2: LLM-judge for remaining soft/hard flags ──────────────────
        red = llm.judge_red_flag(f.text)
        if red:
            cat, conf = red
            f.flag = Flag.RED
            f.red_flag_category = cat
            f.confidence = conf
        elif llm.classify_green(f.text):
            f.flag = Flag.GREEN
            f.confidence = max(f.confidence, 0.8)
        else:
            f.flag = Flag.GREY

        facts.append(f)

    counts: dict = defaultdict(int)
    for f in facts:
        counts[f.flag.value] += 1
    log.info("Flag distribution: %s", dict(counts))
    return {"facts": facts}
