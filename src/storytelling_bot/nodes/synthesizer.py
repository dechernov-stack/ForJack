"""StorySynthesizer node — narrative mode: thesis → evidence → caveats → appendix."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from storytelling_bot.schema import LAYER_LABEL, SUBCATEGORIES, Flag, Layer, State


def node_story_synthesizer(state: State) -> dict:
    profile = state.expert_profile
    fact_scores = {s.fact_idx: s for s in state.fact_scores}

    by_key: dict[tuple[Layer, str], tuple[list, list, list]] = defaultdict(lambda: ([], [], []))
    for i, f in enumerate(state.facts):
        kept_list, dropped_list, caveat_list = by_key[(f.layer, f.subcategory)]
        s = fact_scores.get(i)
        if s and s.keep:
            kept_list.append((i, f))
            if f.flag == Flag.GREY and not s.challenges_hypothesis:
                caveat_list.append(f)
        else:
            dropped_list.append((i, f))

    story: dict[str, dict[str, dict[str, Any]]] = {}
    for (layer, sub), (kept, dropped, caveats) in sorted(by_key.items(), key=lambda x: x[0][0].value):
        thesis = state.theses.get(f"{layer.value}|{sub}", "")
        evidence = []
        for i, f in kept:
            s = fact_scores.get(i)
            evidence.append({
                "text": f.text,
                "source": f.source_url,
                "source_type": f.source_type.value,
                "flag": f.flag.value,
                "challenges": bool(s and s.challenges_hypothesis),
                "expert_note": s.expert_note if s else "",
            })
        narrative_caveats = [
            {"text": f.text, "source": f.source_url, "reason": "серый сигнал, требует подтверждения"}
            for f in caveats
        ]
        appendix = []
        for i, f in dropped:
            s = fact_scores.get(i)
            appendix.append({
                "text": f.text,
                "source": f.source_url,
                "reason": s.expert_note if s else "не отобрано экспертом",
            })
        story.setdefault(LAYER_LABEL[layer], {})[sub] = {
            "thesis": thesis,
            "evidence": evidence,
            "caveats": narrative_caveats,
            "appendix": appendix,
        }

    cross_layer_overview = ""
    if profile:
        pieces = []
        for layer in profile.priority_layers:
            for sub in SUBCATEGORIES[layer]:
                t = state.theses.get(f"{layer.value}|{sub}")
                if t:
                    pieces.append(f"[{LAYER_LABEL[layer]} · {sub}] {t}")
                    break
        if pieces:
            cross_layer_overview = (
                f"Голос эксперта: {profile.voice}\n\n"
                f"Гипотеза: {profile.hypothesis}\n\n"
                "Сквозной нарратив (по приоритетам профиля):\n"
                + "\n".join(f"• {p}" for p in pieces)
            )

    return {"story": story, "cross_layer_overview": cross_layer_overview}
