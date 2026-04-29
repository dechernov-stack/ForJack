"""Data contracts: 8-layer model, Fact, State."""
from __future__ import annotations

import datetime as dt
from enum import Enum, StrEnum
from typing import Any

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


LAYER_LABEL: dict[Layer, str] = {
    Layer.FOUNDER_PERSONAL: "Founder Personal Story",
    Layer.FOUNDER_PROFESSIONAL: "Founder Professional Story",
    Layer.COMMUNITY_CULTURE: "Community Culture, Values & Stories",
    Layer.COMMUNITY_PRO_EXPERIENCE: "Community Professional Experience",
    Layer.CLIENTS_STORIES: "Clients Stories",
    Layer.PRODUCT_BUSINESS: "Product & Business",
    Layer.SOCIAL_IMPACT: "Social Impact Vision",
    Layer.PEST_CONTEXT: "Political, Economical, Social & Technological Context",
}

SUBCATEGORIES: dict[Layer, tuple[str, ...]] = {
    Layer.FOUNDER_PERSONAL: ("Origin & Childhood", "Values & Beliefs", "Fears & Vulnerability", "Dreams & Identity"),
    Layer.FOUNDER_PROFESSIONAL: ("Path to expertise", "Founder role & motivation", "Co-founder dynamics"),
    Layer.COMMUNITY_CULTURE: ("Attraction & Selection", "Shared life", "Investors & Partners"),
    Layer.COMMUNITY_PRO_EXPERIENCE: ("Expertise & Diversity", "Growth & Transformation", "Collective failure memory"),
    Layer.CLIENTS_STORIES: ("Client's challenge & context", "Moment of choice & trust", "Conflict & honesty"),
    Layer.PRODUCT_BUSINESS: ("Architecture of the solution", "Philosophy of decisions", "Evolution"),
    Layer.SOCIAL_IMPACT: ("Vision of change", "Contradictions & cost", "Legacy"),
    Layer.PEST_CONTEXT: ("Historical moment", "Market & technology", "Policy & regulation"),
}


class SourceType(StrEnum):
    ONLINE_INTERVIEW = "online_interview"
    OFFLINE_INTERVIEW = "offline_interview"
    ONLINE_RESEARCH = "online_research"
    ARCHIVAL = "archival"


class Flag(StrEnum):
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
    event_date: dt.date | None = None
    red_flag_category: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        d = self.model_dump()
        d["layer"] = self.layer.value
        d["source_type"] = self.source_type.value
        d["flag"] = self.flag.value
        d["captured_at"] = self.captured_at.isoformat()
        if self.event_date:
            d["event_date"] = self.event_date.isoformat()
        return d


class PersonRole(BaseModel):
    """A role held by a person at a company / entity."""
    entity_id: str
    company_name: str
    role: str
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    is_current: bool = True


class PersonConnection(BaseModel):
    """A relationship between a person and another person or entity."""
    related_person_entity_id: str | None = None
    related_entity_id: str | None = None
    relation_type: str
    strength: float = 0.5


class IdentifyingId(BaseModel):
    id_type: str
    id_value: str
    issuing_country: str | None = None


class Person(BaseModel):
    """Structured profile extracted from OSINT facts — powers the Dossier view."""
    entity_id: str
    display_name: str
    birth_date: dt.date | None = None
    nationalities: list[str] = Field(default_factory=list)
    photo_url: str | None = None
    risk_level: str = "unknown"
    name_variants: list[str] = Field(default_factory=list)
    identifying_ids: list[IdentifyingId] = Field(default_factory=list)
    roles: list[PersonRole] = Field(default_factory=list)
    connections: list[PersonConnection] = Field(default_factory=list)

    @property
    def aka_string(self) -> str:
        return ", ".join(self.name_variants) if self.name_variants else ""


class State(BaseModel):
    """Graph state passed between nodes."""
    entity_id: str
    raw_chunks: list[dict[str, Any]] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    story: dict[str, dict[str, str]] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)
    report_path: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    langfuse_trace_id: str | None = None

    model_config = {"arbitrary_types_allowed": True}
