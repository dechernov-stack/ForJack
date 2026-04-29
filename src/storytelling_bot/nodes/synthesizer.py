"""StorySynthesizer node."""
from __future__ import annotations

from collections import defaultdict

from storytelling_bot.schema import LAYER_LABEL, Flag, Layer, State


def node_story_synthesizer(state: State) -> dict:
    by_key: dict[tuple[Layer, str], list] = defaultdict(list)
    for f in state.facts:
        by_key[(f.layer, f.subcategory)].append(f)

    story: dict[str, dict[str, str]] = defaultdict(dict)
    for (layer, sub), facts in sorted(by_key.items(), key=lambda x: x[0][0].value):
        green = [f for f in facts if f.flag == Flag.GREEN]
        red = [f for f in facts if f.flag == Flag.RED]
        grey = [f for f in facts if f.flag == Flag.GREY]
        parts = []
        if green:
            parts.append("ЗЕЛЁНЫЙ:\n" + "\n".join(f"  · {f.text} [src: {f.source_url}]" for f in green))
        if red:
            parts.append("КРАСНЫЙ:\n" + "\n".join(f"  · {f.text} (категория: {f.red_flag_category}) [src: {f.source_url}]" for f in red))
        if grey:
            parts.append("СЕРЫЙ (требует доуточнения):\n" + "\n".join(f"  · {f.text} [src: {f.source_url}]" for f in grey))
        story[LAYER_LABEL[layer]][sub] = "\n\n".join(parts) if parts else "(пусто)"
    return {"story": dict(story)}
