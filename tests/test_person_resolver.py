"""Tests for PersonResolver — person profile extraction from facts."""
from __future__ import annotations

import datetime as dt

from storytelling_bot.person_resolver import resolve_person
from storytelling_bot.schema import Fact, Layer, SourceType


def _make_fact(text: str, layer: Layer = Layer.FOUNDER_PROFESSIONAL) -> Fact:
    return Fact(
        entity_id="test-founder",
        layer=layer,
        subcategory="Path to expertise",
        source_type=SourceType.ONLINE_RESEARCH,
        text=text,
        source_url="https://example.com",
        captured_at=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    )


# ── display_name fallback ────────────────────────────────────────────────────

def test_display_name_from_entity_id():
    person = resolve_person("john-doe", facts=[])
    assert person.display_name == "John Doe"


def test_display_name_from_metadata():
    person = resolve_person("john-doe", facts=[], metadata={"display_name": "Jonathan P. Doe"})
    assert person.display_name == "Jonathan P. Doe"


# ── role extraction ──────────────────────────────────────────────────────────

def test_extracts_ceo_role():
    fact = _make_fact("He served as CEO at Acme Corp since 2015.")
    person = resolve_person("test-founder", facts=[fact])
    assert any(r.role == "Ceo" and r.company_name == "Acme Corp" for r in person.roles)


def test_extracts_founder_role():
    fact = _make_fact("She co-founded DataSync in 2018.")
    person = resolve_person("test-founder", facts=[fact])
    assert any("datasync" in r.company_name.lower() for r in person.roles)


def test_role_start_year_parsed():
    fact = _make_fact("CTO at NeuralBase since 2020.")
    person = resolve_person("test-founder", facts=[fact])
    role = next((r for r in person.roles if r.company_name == "NeuralBase"), None)
    assert role is not None
    assert role.start_date == dt.date(2020, 1, 1)


def test_role_deduplication():
    fact1 = _make_fact("CEO at Stripe since 2015.")
    fact2 = _make_fact("He is CEO at Stripe, leading global payments.")
    person = resolve_person("test-founder", facts=[fact1, fact2])
    stripe_roles = [r for r in person.roles if "stripe" in r.company_name.lower()]
    assert len(stripe_roles) == 1


# ── nationality extraction ───────────────────────────────────────────────────

def test_extracts_nationality():
    fact = _make_fact("The founder is American and studied at MIT.", Layer.FOUNDER_PERSONAL)
    person = resolve_person("test-founder", facts=[fact])
    assert "US" in person.nationalities


def test_multiple_nationalities():
    fact = _make_fact("Born British, later became Swiss citizen.", Layer.FOUNDER_PERSONAL)
    person = resolve_person("test-founder", facts=[fact])
    assert "GB" in person.nationalities
    assert "CH" in person.nationalities


def test_no_nationality_if_not_mentioned():
    fact = _make_fact("Raised $50M in Series B funding.")
    person = resolve_person("test-founder", facts=[fact])
    assert person.nationalities == []


# ── metadata passthrough ─────────────────────────────────────────────────────

def test_metadata_risk_level():
    person = resolve_person("x", facts=[], metadata={"risk_level": "high_risk"})
    assert person.risk_level == "high_risk"


def test_metadata_name_variants():
    person = resolve_person("x", facts=[], metadata={"name_variants": ["J. Doe", "Johnny"]})
    assert "J. Doe" in person.name_variants


def test_metadata_nationalities_preserved():
    person = resolve_person("x", facts=[], metadata={"nationalities": ["US", "IL"]})
    assert "US" in person.nationalities
    assert "IL" in person.nationalities


# ── person_to_db_row ─────────────────────────────────────────────────────────

def test_person_to_db_row_contains_required_fields():
    from storytelling_bot.person_resolver import person_to_db_row
    person = resolve_person("stripe", facts=[], metadata={"display_name": "Stripe Inc."})
    row = person_to_db_row(person)
    assert row["entity_id"] == "stripe"
    assert row["display_name"] == "Stripe Inc."
    assert isinstance(row["nationalities"], str)  # JSON-serialized


# ── schema model ────────────────────────────────────────────────────────────

def test_person_aka_string_empty():
    from storytelling_bot.schema import Person
    p = Person(entity_id="x", display_name="Test")
    assert p.aka_string == ""


def test_person_aka_string_populated():
    from storytelling_bot.schema import Person
    p = Person(entity_id="x", display_name="Test", name_variants=["T.", "Testy"])
    assert p.aka_string == "T., Testy"
