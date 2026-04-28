"""Graph builder using LangGraph StateGraph."""
from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from storytelling_bot.collectors import (
    ArchivalCollector,
    InterviewCollector,
    OfflineIngest,
    ResearchCollector,
)
from storytelling_bot.nodes import (
    embed_facts,
    node_decision_engine,
    node_flag_detector,
    node_layer_classifier,
    node_metrics,
    node_reporter,
    node_story_synthesizer,
    node_timeline_builder,
)
from storytelling_bot.schema import State

log = logging.getLogger(__name__)


def _collect_all(state: State) -> dict[str, Any]:
    collectors = [
        InterviewCollector(),
        ResearchCollector(),
        ArchivalCollector(),
        OfflineIngest(),
    ]
    chunks = []
    for c in collectors:
        result = c.collect(state.entity_id)
        log.info("[%s] collected %d chunks", c.source_type.value, len(result))
        chunks.extend(result)
    return {"raw_chunks": chunks}


class GraphWrapper:
    """Thin wrapper so callers can do graph.run(state) -> State."""

    def __init__(self, compiled) -> None:
        self._compiled = compiled

    def run(self, state: State) -> State:
        result = self._compiled.invoke(state)
        if isinstance(result, State):
            return result
        if isinstance(result, dict):
            return State(**{k: v for k, v in result.items() if k in State.model_fields})
        return state


def build_graph() -> GraphWrapper:
    g = StateGraph(State)

    g.add_node("collect", _collect_all)
    g.add_node("classify", node_layer_classifier)
    g.add_node("flag", node_flag_detector)
    g.add_node("embed", embed_facts)
    g.add_node("timeline", node_timeline_builder)
    g.add_node("synthesize", node_story_synthesizer)
    g.add_node("decide", node_decision_engine)
    g.add_node("metrics", node_metrics)
    g.add_node("report", node_reporter)

    g.set_entry_point("collect")
    g.add_edge("collect", "classify")
    g.add_edge("classify", "flag")
    g.add_edge("flag", "embed")
    g.add_edge("embed", "timeline")
    g.add_edge("timeline", "synthesize")
    g.add_edge("synthesize", "decide")
    g.add_edge("decide", "metrics")
    g.add_edge("metrics", "report")
    g.add_edge("report", END)

    return GraphWrapper(g.compile())
