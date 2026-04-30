"""Tests for delta comparison between two Diamond-snapshot reports."""
from __future__ import annotations

from storytelling_bot.reports.delta import compare, render_digest


def _fact(text: str, url: str = "http://x.com", flag: str = "grey", layer: int = 2, sub: str = "") -> dict:
    return {"text": text, "source_url": url, "flag": flag, "layer": layer, "subcategory": sub}


def _report(facts: list[dict], decision: str = "watch") -> dict:
    return {"facts": facts, "decision": {"recommendation": decision}}


# ── new / removed facts ────────────────────────────────────────────────────────

def test_new_facts_detected():
    prev = _report([_fact("Old fact")])
    curr = _report([_fact("Old fact"), _fact("New fact")])
    delta = compare(prev, curr)
    assert len(delta["new_facts"]) == 1
    assert delta["new_facts"][0]["text"] == "New fact"


def test_removed_facts_detected():
    prev = _report([_fact("Fact A"), _fact("Fact B")])
    curr = _report([_fact("Fact A")])
    delta = compare(prev, curr)
    assert len(delta["removed_facts"]) == 1
    assert delta["removed_facts"][0]["text"] == "Fact B"


def test_unchanged_facts_not_in_new_or_removed():
    f = _fact("Same fact", url="http://same.com")
    prev = _report([f])
    curr = _report([f])
    delta = compare(prev, curr)
    assert delta["new_facts"] == []
    assert delta["removed_facts"] == []


# ── decision change ────────────────────────────────────────────────────────────

def test_decision_change_detected():
    prev = _report([], decision="watch")
    curr = _report([], decision="pause")
    delta = compare(prev, curr)
    assert delta["decision_change"] == ("watch", "pause")


def test_no_decision_change():
    prev = _report([], decision="watch")
    curr = _report([], decision="watch")
    delta = compare(prev, curr)
    assert delta["decision_change"] is None


# ── red flags ─────────────────────────────────────────────────────────────────

def test_new_red_flags_isolated():
    prev = _report([])
    curr = _report([
        _fact("Lawsuit filed", flag="red"),
        _fact("Normal fact", flag="grey"),
    ])
    delta = compare(prev, curr)
    assert len(delta["new_red_flags"]) == 1
    assert delta["new_red_flags"][0]["flag"] == "red"


def test_challenges_change_positive():
    prev = _report([_fact("Old red", flag="red")])
    curr = _report([_fact("Old red", flag="red"), _fact("New red", flag="red")])
    delta = compare(prev, curr)
    assert delta["challenges_change"] == 1


def test_challenges_change_negative():
    prev = _report([_fact("Red", url="http://a.com", flag="red"), _fact("Red 2", url="http://b.com", flag="red")])
    curr = _report([_fact("Red", url="http://a.com", flag="red")])
    delta = compare(prev, curr)
    assert delta["challenges_change"] == -1


# ── moved facts ───────────────────────────────────────────────────────────────

def test_moved_facts_detected():
    url = "http://same.com"
    text = "Same text"
    prev = _report([_fact(text, url=url, layer=2)])
    curr = _report([_fact(text, url=url, layer=6)])
    delta = compare(prev, curr)
    assert len(delta["moved_facts"]) == 1
    _moved_fact, from_layer, to_layer = delta["moved_facts"][0]
    assert from_layer == "2"
    assert to_layer == "6"


# ── subcategory diff ──────────────────────────────────────────────────────────

def test_subcategory_diff_counts_new():
    prev = _report([])
    curr = _report([_fact("Fact", layer=2, sub="Path to expertise")])
    delta = compare(prev, curr)
    assert "2|Path to expertise" in delta["subcategory_diff"]
    assert delta["subcategory_diff"]["2|Path to expertise"]["added"] == 1


# ── render_digest ─────────────────────────────────────────────────────────────

def test_render_digest_decision_change():
    prev = _report([], "watch")
    curr = _report([_fact("Red flag", flag="red")], "pause")
    delta = compare(prev, curr)
    text = render_digest(delta)
    assert "watch" in text
    assert "pause" in text
    assert "red" in text.lower()


def test_render_digest_no_changes():
    prev = _report([])
    curr = _report([])
    delta = compare(prev, curr)
    text = render_digest(delta)
    assert "0" in text
