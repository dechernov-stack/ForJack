"""Data contracts: 8-layer model, Fact, State."""
from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class Layer(int, Enum):
    FOUNDER_PERSONAL = 1
    FOUNDER_PROFESSIONAL = 2
    COMMUNITY_CULTURE = 3
    COMMUNITY_PRO_EXPERIENCE = 4
    CLIENTS_STORIES = 5
    PRODUCT_BUSINESS = 6
    SOCIAL_IMPACT = 7
    PEST_CONTEXT = 8


LAYER_LABEL: Dict[Layer, str] = {
    Layer.FOUNDER_PERSONAL: "Founder Personal Story",
    Layer.FOUNDER_PROFESSIONAL: "Founder Professional Story",
    Layer.COMMUNITY_CULTURE: "Community Culture, Values & Stories",
    Layer.COMMUNITY_PRO_EXPERIENCE: "Community Professional Experience",
    Layer.CLIENTS_STORIES: "Clients Stories",
    Layer.PRODUCT_BUSINESS: "Product & Business",
    Layer.SOCIAL_IMPACT: "Social Impact Vision",
    Layer.PEST_CONTEXT: "Political, Economical, Social & Technological Context",
}

SUBCATEGORIES: Dict[Layer, Tuple[str, ...]] = {
    Layer.FOUNDER_PERSONAL: ("Origin & Childhood", "Values & Beliefs", "Fears & Vulnerability", "Dreams & Identity"),
    Layer.FOUNDER_PROFESSIONAL: ("Path to expertise", "Founder role & motivation", "Co-founder dynamics"),
    Layer.COMMUNITY_CULTURE: ("Attraction & Selection", "Shared life", "Investors & Partners"),
    Layer.COMMUNITY_PRO_EXPERIENCE: ("Expertise & Diversity", "Growth & Transformation", "Collective failure memory"),
    Layer.CLIENTS_STORIES: ("Client's challenge & context", "Moment of choice & trust", "Conflict & honesty"),
    Layer.PRODUCT_BUSINESS: ("Architecture of the solution", "Philosophy of decisions", "Evolution"),
    Layer.SOCIAL_IMPACT: ("Vision of change", "Contradictions & cost", "Legacy"),
    Layer.PEST_CONTEXT: ("Historical moment", "Market & technology", "Policy & regulation"),
}


class SourceType(str, Enum):
    ONLINE_INTERVIEW = "online_interview"
    OFFLINE_INTERVIEW = "offline_interview"
    ONLINE_RESEARCH = "online_research"
    ARCHIVAL = "archival"


class Flag(str, Enum):
    GREEN = "green"
    RED = "red"
    GREY = "grey"


class Fact(BaseModel):
    """Atomic unit of the data lake (Diamond layer)."""
    entity_id: str
    layer: Layer
    subcategory: str
    source_type: SourceType
    text: str
    source_url: str
    captured_at: dt.datetime
    flag: Flag = Flag.GREY
    confidence: float = 0.5
    event_date: Optional[dt.date] = None
    red_flag_category: Optional[str] = None

    def to_jsonable(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["layer"] = self.layer.value
        d["source_type"] = self.source_type.value
        d["flag"] = self.flag.value
        d["captured_at"] = self.captured_at.isoformat()
        if self.event_date:
            d["event_date"] = self.event_date.isoformat()
        return d


class State(BaseModel):
    """Graph state passed between nodes."""
    entity_id: str
    raw_chunks: List[Dict[str, Any]] = Field(default_factory=list)
    facts: List[Fact] = Field(default_factory=list)
    timeline: List[Dict[str, Any]] = Field(default_factory=list)
    story: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    decision: Dict[str, Any] = Field(default_factory=dict)
    report_path: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
