"""FlagDetector node — hard rules then LLM-judge."""
from __future__ import annotations

import logging
from collections import defaultdict

from storytelling_bot.llm import get_llm_client
from storytelling_bot.schema import Fact, Flag, State

log = logging.getLogger(__name__)


def node_flag_detector(state: State) -> dict:
    llm = get_llm_client()
    facts: list[Fact] = []
    for fact in state.facts:
        f = fact.model_copy()
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
