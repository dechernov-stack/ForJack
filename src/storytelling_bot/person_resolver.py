"""PersonResolver — extract structured Person profile from OSINT facts.

Uses regex + heuristic matching against Layer.FOUNDER_PROFESSIONAL and
Layer.FOUNDER_PERSONAL facts to populate PersonRole and PersonConnection
records.  When LLM extraction is needed, call resolve_with_llm() instead.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .schema import (
    Fact,
    IdentifyingId,
    Layer,
    Person,
    PersonRole,
)

log = logging.getLogger(__name__)

# ── role extraction patterns ──────────────────────────────────────────────────

_ROLE_PATTERNS = [
    # "CEO at Stripe since 2010" / "served as CTO at NeuralBase"
    re.compile(
        r"(?P<role>CEO|CTO|CFO|COO|co-founder|founder|chairman|president|"
        r"managing director|board member|director|partner|VP)"
        r"[\s,]+(?:at|of|@)\s+"
        r"(?P<company>[\w][\w\s\-&.]*?)"
        r"(?=\s+(?:since|from|in|as of|\d{4})|[,;.!?]|$)",
        re.IGNORECASE,
    ),
    # "founded / co-founded Stripe in 2010"
    re.compile(
        r"(?:founded|co-founded|started|launched)\s+"
        r"(?P<company>[\w][\w\s\-&.]*?)"
        r"(?=\s+in\s+\d{4}|\s+(?:in|during)\b|[,;.!?]|$)",
        re.IGNORECASE,
    ),
]

_YEAR_PATTERN = re.compile(r"(?:since|from|in)\s+(?P<year>\d{4})", re.IGNORECASE)

_NATIONALITY_PATTERN = re.compile(
    r"\b(american|british|russian|german|french|chinese|indian|canadian|"
    r"australian|israeli|emirati|swiss)\b",
    re.IGNORECASE,
)

_NATIONALITY_MAP = {
    "american": "US", "british": "GB", "russian": "RU", "german": "DE",
    "french": "FR", "chinese": "CN", "indian": "IN", "canadian": "CA",
    "australian": "AU", "israeli": "IL", "emirati": "AE", "swiss": "CH",
}

_ID_PATTERNS = [
    re.compile(r"\bpassport\s+(?:no\.?|number)?\s*([A-Z0-9]{6,12})\b", re.IGNORECASE),
    re.compile(r"\btax\s+id\s*[:=]?\s*([0-9\-]{8,15})\b", re.IGNORECASE),
]


# ── public API ────────────────────────────────────────────────────────────────

def resolve_person(entity_id: str, facts: list[Fact], metadata: dict[str, Any] | None = None) -> Person:
    """Build a Person profile from facts.  metadata can supply display_name, photo_url, etc."""
    meta = metadata or {}
    display_name = meta.get("display_name") or _name_from_entity_id(entity_id)

    person = Person(
        entity_id=entity_id,
        display_name=display_name,
        birth_date=meta.get("birth_date"),
        nationalities=list(meta.get("nationalities", [])),
        photo_url=meta.get("photo_url"),
        risk_level=meta.get("risk_level", "unknown"),
        name_variants=list(meta.get("name_variants", [])),
    )

    for fact in facts:
        _apply_fact(person, fact, entity_id)

    _dedupe(person)
    return person


# ── internal helpers ──────────────────────────────────────────────────────────

def _name_from_entity_id(entity_id: str) -> str:
    return entity_id.replace("-", " ").replace("_", " ").title()


def _apply_fact(person: Person, fact: Fact, entity_id: str) -> None:
    text = fact.text

    if fact.layer in (Layer.FOUNDER_PROFESSIONAL, Layer.FOUNDER_PERSONAL):
        _extract_roles(person, text, entity_id, fact)
        _extract_nationalities(person, text)
        _extract_ids(person, text)


def _extract_roles(person: Person, text: str, entity_id: str, fact: Fact) -> None:
    import datetime as dt
    for pattern in _ROLE_PATTERNS:
        for m in pattern.finditer(text):
            groups = m.groupdict()
            role_title = (groups.get("role") or "Founder").strip()
            company = (groups.get("company") or "").strip().rstrip("., ")
            if not company or len(company) > 60:
                continue
            # extract year from the context after the match
            context = text[m.start():]
            year_m = _YEAR_PATTERN.search(context[:80])
            start = None
            if year_m:
                try:
                    start = dt.date(int(year_m.group("year")), 1, 1)
                except ValueError:
                    pass

            person.roles.append(
                PersonRole(
                    entity_id=entity_id,
                    company_name=company,
                    role=role_title.title(),
                    start_date=start,
                    is_current=True,
                )
            )


def _extract_nationalities(person: Person, text: str) -> None:
    for m in _NATIONALITY_PATTERN.finditer(text):
        iso = _NATIONALITY_MAP.get(m.group(0).lower())
        if iso and iso not in person.nationalities:
            person.nationalities.append(iso)


def _extract_ids(person: Person, text: str) -> None:
    for i, pattern in enumerate(_ID_PATTERNS):
        id_type = ["passport", "tax_id"][i]
        for m in pattern.finditer(text):
            person.identifying_ids.append(
                IdentifyingId(id_type=id_type, id_value=m.group(1))
            )


def _dedupe(person: Person) -> None:
    seen_roles: set[tuple[str, str]] = set()
    unique_roles = []
    for r in person.roles:
        key = (r.company_name.lower(), r.role.lower())
        if key not in seen_roles:
            seen_roles.add(key)
            unique_roles.append(r)
    person.roles = unique_roles

    seen_ids: set[tuple[str, str]] = set()
    unique_ids = []
    for pid in person.identifying_ids:
        key = (pid.id_type, pid.id_value)
        if key not in seen_ids:
            seen_ids.add(key)
            unique_ids.append(pid)
    person.identifying_ids = unique_ids


def person_to_db_row(person: Person) -> dict[str, Any]:
    """Serialize Person to a dict suitable for INSERT INTO persons."""
    return {
        "entity_id": person.entity_id,
        "display_name": person.display_name,
        "birth_date": person.birth_date,
        "nationalities": json.dumps(person.nationalities),
        "photo_url": person.photo_url,
        "risk_level": person.risk_level,
    }
