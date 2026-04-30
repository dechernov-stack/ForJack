"""2-of-3 consensus reconciler for EntityCard from multiple providers."""
from __future__ import annotations

import os
import re
from collections import Counter
from typing import Any

from storytelling_bot.schema import Anchor, EntityCard, NameVariant

_RU_MONTHS = {
    "января": "01", "февраля": "02", "марта": "03", "апреля": "04",
    "мая": "05", "июня": "06", "июля": "07", "августа": "08",
    "сентября": "09", "октября": "10", "ноября": "11", "декабря": "12",
}

_FIRSTNAME_ALIASES = {
    "davd": "david", "david": "david", "davi": "david",
    "daniel": "daniil", "daniil": "daniil", "danil": "daniil", "dani": "daniil",
}

_MIN_CONSENSUS = float(os.environ.get("RESOLVER_MIN_CONSENSUS", "0.6"))


def _norm_lastname(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-zа-я]", "", s)
    table = str.maketrans({
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
        "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
        "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
        "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    })
    s = s.translate(table)
    return s.replace("nn", "n").replace("ie", "i")


def _norm_firstname(s: str) -> str:
    s = _norm_lastname(s)
    return _FIRSTNAME_ALIASES.get(s[:5], _FIRSTNAME_ALIASES.get(s[:4], s[:5]))


def _norm_anchor_value(v: str) -> str:
    raw = v.strip().lower()
    m = re.search(r"\b(19|20)\d{2}\b", raw)
    if m and len(raw) < 60:
        for ru_m, mn in _RU_MONTHS.items():
            if ru_m in raw:
                day_m = re.search(r"\b(\d{1,2})\s+" + ru_m, raw)
                if day_m:
                    return f"{m.group(0)}-{mn}-{int(day_m.group(1)):02d}"
        iso = re.search(r"\b(19|20)\d{2}-\d{2}-\d{2}\b", raw)
        if iso:
            return iso.group(0)
        if re.fullmatch(r"(19|20)\d{2}", raw.strip()):
            return m.group(0)
    raw = raw.replace("ё", "е")
    raw = re.sub(r"москв[аеу]", "moscow", raw)
    raw = re.sub(r",\s*(ussr|россия|russia|russian federation)", "", raw)
    return re.sub(r"\s+", " ", raw)[:80]


def _entity_key(ent: dict[str, Any]) -> str:
    name = (ent.get("canonical_name") or "").strip()
    if not name:
        return "?"
    parts = name.split()
    last = parts[-1] if parts else "?"
    first = parts[0] if parts else "?"
    return f"{_norm_lastname(last)}|{_norm_firstname(first)}"


def _e_summary(e: dict[str, Any]) -> str:
    return f"name={e.get('canonical_name', '')}; anchors={len(e.get('anchors') or [])}"


def _merge_group(group: list[tuple[str, dict[str, Any]]], total_providers: int) -> EntityCard:
    providers = [p for p, _ in group]

    name_counter: Counter = Counter(g[1].get("canonical_name", "") for g in group)
    canonical = name_counter.most_common(1)[0][0]
    canonical_lang = next((g[1].get("canonical_lang") for g in group if g[1].get("canonical_lang")), "en")

    seen_var: set = set()
    variants: list[NameVariant] = []
    for _, e in group:
        for v in e.get("name_variants") or []:
            key = (v.get("lang"), v.get("spelling"))
            if key in seen_var:
                continue
            seen_var.add(key)
            variants.append(NameVariant(lang=v.get("lang", ""), spelling=v.get("spelling", ""), note=v.get("note", "")))

    anchor_map: dict[tuple[str, str], Anchor] = {}
    for provider, e in group:
        for a in e.get("anchors") or []:
            norm_val = _norm_anchor_value(a.get("value", ""))
            key = (a.get("type", ""), norm_val)
            if not key[0] or not key[1]:
                continue
            if key not in anchor_map:
                anchor_map[key] = Anchor(type=key[0], value=a.get("value", ""), sources=[], confidence=0.0)
            ar = anchor_map[key]
            if provider not in ar.sources:
                ar.sources.append(provider)
            ar.confidence = max(ar.confidence, float(a.get("confidence", 0.6)))
    anchors = sorted(anchor_map.values(), key=lambda a: (-len(a.sources), a.type))

    signals: list[float] = [name_counter.most_common(1)[0][1] / total_providers]
    for typ in ("dob", "birthplace"):
        votes = max((len(a.sources) for a in anchors if a.type == typ), default=0)
        if votes:
            signals.append(votes / total_providers)
    company_votes = max((len(a.sources) for a in anchors if a.type == "company"), default=0)
    if company_votes:
        signals.append(min(1.0, company_votes / total_providers))
    consensus = round(sum(signals) / max(1, len(signals)), 3)

    negatives: list[str] = []
    for _, e in group:
        for n in e.get("negatives") or []:
            if n and n not in negatives:
                negatives.append(n)

    related: list[dict[str, str]] = []
    for _, e in group:
        for r in e.get("related_entities") or []:
            if r not in related:
                related.append(r)

    disagreed: list[dict[str, str]] = []
    if len(set(name_counter)) > 1:
        disagreed.append({
            "field": "canonical_name",
            "values": " | ".join(f"{c} ({n}×)" for c, n in name_counter.most_common()),
        })
    dob_set: Counter = Counter()
    for _, e in group:
        for a in e.get("anchors") or []:
            if a.get("type") == "dob":
                dob_set[a.get("value", "")] += 1
    if len(dob_set) > 1:
        disagreed.append({"field": "dob", "values": " | ".join(dob_set.keys())})

    raw = {p: _e_summary(e) for p, e in group}

    return EntityCard(
        canonical_name=canonical,
        canonical_lang=canonical_lang,
        role_hint=next((g[1].get("role_hint", "") for g in group if g[1].get("role_hint")), ""),
        name_variants=variants,
        anchors=anchors,
        negatives=negatives,
        related_entities=related,
        consensus_score=consensus,
        providers_agreed=providers,
        providers_disagreed=disagreed,
        raw_provider_answers=raw,
        uncertain=consensus < _MIN_CONSENSUS,
    )


def reconcile(provider_outputs: dict[str, dict[str, Any]]) -> list[EntityCard]:
    """2-of-3 consensus → list[EntityCard]."""
    by_key: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for provider, out in provider_outputs.items():
        for ent in out.get("entities") or []:
            key = _entity_key(ent)
            by_key.setdefault(key, []).append((provider, ent))

    cards = [_merge_group(group, len(provider_outputs)) for group in by_key.values()]
    cards.sort(key=lambda c: c.canonical_name)
    return cards
