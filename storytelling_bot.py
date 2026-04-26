"""
storytelling_bot.py — Прототип Storytelling Data Lake Bot
=========================================================

Скелет мульти-агентной системы для автоматического наполнения
8-слойного data lake по компаниям и их фаундерам в логике DE.pdf.

Архитектура (см. storytelling_bot_architecture.docx):

    Orchestrator
      → InterviewCollector | ResearchCollector | ArchivalCollector | OfflineIngest  (параллельно)
      → LayerClassifier + EntityLinker
      → StorySynthesizer + TimelineBuilder
      → FlagDetector
      → DecisionEngine
      → Reporter

В production:
- `Graph` ниже заменяется на `from langgraph.graph import StateGraph`
- LLM-вызовы (`llm_classify`, `llm_synthesize`, `llm_judge`) идут в Claude / GPT / vLLM
- Коллекторы ходят в реальные API (Tavily, GDELT, SEC EDGAR, YouTube + Whisper, ...)
- Сохранение состояния — в Postgres + MinIO + Qdrant + Neo4j

CLI для аналитика:
    python storytelling_bot.py --list                     # список сущностей в watchlist
    python storytelling_bot.py --entity accumulator       # запустить пересбор и показать summary
    python storytelling_bot.py --entity accumulator \
        --output report.json --export-html dashboard.html # JSON + интерактивный дашборд
    python storytelling_bot.py --entity accumulator \
        --add-fact "Внутренняя встреча 2026-04-25: ..." \
        --add-fact-source offline_interview               # offline ingest — факт из встречи
    python storytelling_bot.py --diff prev.json curr.json # что изменилось между запусками
    python storytelling_bot.py --watch --entity accumulator \
        --interval 60                                     # daemon-режим (демо event watcher)

Прототип написан так, чтобы запускаться без внешних зависимостей —
коллекторы возвращают канонические факты по Accumulator из DE.pdf,
а LLM-функции замоканы детерминированной эвристикой.

В реальной системе:
- кнопки в дашборде (Re-run, Add fact) дёргают этот же CLI через REST-обёртку (Flask/FastAPI)
- offline-факты складываются в Postgres + MinIO (а не в локальный JSON)
- watch-режим работает поверх Temporal/Redis Streams, не sleep-цикла
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import logging
import re
import sys
import textwrap
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s · %(levelname)s · %(name)s · %(message)s",
)
log = logging.getLogger("storytelling_bot")


# =============================================================================
# 1. Контракт данных: 8 слоёв, флаги, факт
# =============================================================================

class Layer(int, Enum):
    FOUNDER_PERSONAL = 1
    FOUNDER_PROFESSIONAL = 2
    COMMUNITY_CULTURE = 3
    COMMUNITY_PRO_EXPERIENCE = 4
    CLIENTS_STORIES = 5
    PRODUCT_BUSINESS = 6
    SOCIAL_IMPACT = 7
    PEST_CONTEXT = 8


LAYER_LABEL = {
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


@dataclass
class Fact:
    """Атомарная единица data lake (Diamond layer)."""
    entity_id: str            # accumulator | dave-waiser | oscar-hartmann
    layer: Layer
    subcategory: str
    source_type: SourceType
    text: str                 # ≤500 символов, нормализованная цитата
    source_url: str
    captured_at: dt.datetime
    flag: Flag = Flag.GREY
    confidence: float = 0.5
    event_date: Optional[dt.date] = None
    red_flag_category: Optional[str] = None  # если flag=RED — какая категория

    def to_jsonable(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["layer"] = self.layer.value
        d["source_type"] = self.source_type.value
        d["flag"] = self.flag.value
        d["captured_at"] = self.captured_at.isoformat()
        if self.event_date:
            d["event_date"] = self.event_date.isoformat()
        return d


# =============================================================================
# 2. Минимальный Graph runtime (LangGraph-совместимый API)
# =============================================================================

@dataclass
class State:
    """Состояние, которое передаётся между нодами графа."""
    entity_id: str
    raw_chunks: List[Dict[str, Any]] = field(default_factory=list)
    facts: List[Fact] = field(default_factory=list)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    story: Dict[str, Dict[str, str]] = field(default_factory=dict)
    decision: Dict[str, Any] = field(default_factory=dict)
    report_path: Optional[str] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class Graph:
    """
    Урезанная реализация графа узлов в стиле LangGraph.StateGraph.

    Замена в production:
        from langgraph.graph import StateGraph, END
        g = StateGraph(State)
        g.add_node("collect", collect_node)
        g.add_edge("collect", "classify")
        g.set_entry_point("collect")
        graph = g.compile()
    """
    END = "__end__"

    def __init__(self) -> None:
        self.nodes: Dict[str, Callable[[State], State]] = {}
        self.edges: Dict[str, str] = {}
        self.parallel: Dict[str, List[str]] = {}
        self.entry: Optional[str] = None

    def add_node(self, name: str, fn: Callable[[State], State]) -> None:
        self.nodes[name] = fn

    def add_edge(self, src: str, dst: str) -> None:
        self.edges[src] = dst

    def add_parallel(self, name: str, branches: List[str], join_to: str) -> None:
        """name — виртуальный fanout-узел, выполняет ветки параллельно (sequentially в этом proto)."""
        self.parallel[name] = branches
        self.edges[name] = join_to

    def set_entry(self, name: str) -> None:
        self.entry = name

    def run(self, state: State) -> State:
        assert self.entry, "Entry node not set"
        node = self.entry
        while node != self.END:
            log.info("→ running node: %s", node)
            if node in self.parallel:
                for br in self.parallel[node]:
                    state = self.nodes[br](state)
            else:
                state = self.nodes[node](state)
            node = self.edges.get(node, self.END)
        return state


# =============================================================================
# 3. Коллекторы (моки на основе DE.pdf для Accumulator)
# =============================================================================

# В production коллекторы дёргают Tavily, YouTube+Whisper, SEC EDGAR и т.д.
# Здесь — каноничные фрагменты, отражающие 4 типа источников.

DEMO_CORPUS: Dict[str, List[Dict[str, Any]]] = {
    "accumulator": [
        # === ONLINE_INTERVIEW ===
        {
            "source_type": SourceType.ONLINE_INTERVIEW,
            "url": "https://youtube.com/watch?v=demo-waiser-podcast",
            "captured_at": "2025-11-10",
            "text": "Дэйв Вайзер: «Я владел значительной долей Gett, готовился к IPO. Началась война — окно закрылось, мои 170 миллионов превратились в цифру в таблице. Я понял, что это нельзя пускать на самотёк».",
            "entity_focus": "dave-waiser",
        },
        {
            "source_type": SourceType.ONLINE_INTERVIEW,
            "url": "https://podcast.example/oscar-hartmann-ep42",
            "captured_at": "2026-01-15",
            "text": "Оскар Хартманн: «Моя ошибка с Ozon стоила инвесторам 300 миллионов. Сейчас я строю Angels Fund II, чтобы один такой кейс не уничтожал капитал».",
            "entity_focus": "oscar-hartmann",
        },
        # === ONLINE_RESEARCH ===
        {
            "source_type": SourceType.ONLINE_RESEARCH,
            "url": "https://www.sec.gov/edgar/accumulator-fund-i",
            "captured_at": "2026-02-01",
            "text": "Accumulator Fund I зарегистрирован в SEC под Rule 506(b) и Section 3(c)(1). AUM по трём фондам — более $60M. Управляющим выступает Максим Темчук.",
            "entity_focus": "accumulator",
        },
        {
            "source_type": SourceType.ONLINE_RESEARCH,
            "url": "https://crunchbase.com/organization/accumulator",
            "captured_at": "2026-03-12",
            "text": "В декабре 2024 года Accumulator привлёк $46M при оценке $140M. Среди инвесторов — Авишай Абраами (Wix), Филип Дамес (Zalando), NFX, FJ Labs.",
            "entity_focus": "accumulator",
        },
        {
            "source_type": SourceType.ONLINE_RESEARCH,
            "url": "https://techcrunch.example/accumulator-launch",
            "captured_at": "2026-03-20",
            "text": "Accumulator работает по invite-only принципу. Критерии входа: оценка >$100M, последний раунд в 2024 году или позже, runway >18 месяцев или прибыльность.",
            "entity_focus": "accumulator",
        },
        {
            "source_type": SourceType.ONLINE_RESEARCH,
            "url": "https://news.example/private-market-stay-private",
            "captured_at": "2026-02-25",
            "text": "С 1996 года число публичных компаний в США сократилось почти вдвое — с >7000 до <4000. Средний возраст IPO вырос до 9–11 лет. Объём вторичного рынка достиг $110B в H1 2025.",
            "entity_focus": "accumulator",
        },
        # === ARCHIVAL ===
        {
            "source_type": SourceType.ARCHIVAL,
            "url": "https://web.archive.org/2014/gett-launch",
            "captured_at": "2025-12-01",
            "text": "Gett под руководством Дэйва Вайзера масштабировался до 1500 городов, обслуживая компании из Fortune 500. Привлечено более $1B инвестиций.",
            "entity_focus": "dave-waiser",
            "event_date": "2014-06-01",
        },
        {
            "source_type": SourceType.ARCHIVAL,
            "url": "https://web.archive.org/2010/kupivip",
            "captured_at": "2025-12-02",
            "text": "KupiVIP под руководством Оскара Хартманна вышла в лидеры рынка с продажами $250M за пять лет.",
            "entity_focus": "oscar-hartmann",
            "event_date": "2010-09-01",
        },
        # === OFFLINE_INTERVIEW (Manual ingest) ===
        {
            "source_type": SourceType.OFFLINE_INTERVIEW,
            "url": "internal://meetings/2026-04-12-accumulator-call",
            "captured_at": "2026-04-12",
            "text": "Внутренняя встреча: фаундер открыто признаёт, что у Accumulator нет публично известного CTO; технологическая команда формируется через нетворк Founders Forum.",
            "entity_focus": "accumulator",
        },
    ],
}


def collector_factory(source_type: SourceType) -> Callable[[State], State]:
    """Возвращает узел графа, фильтрующий корпус по типу источника."""

    def _node(state: State) -> State:
        corpus = DEMO_CORPUS.get(state.entity_id, [])
        filtered = [c for c in corpus if c["source_type"] == source_type]
        log.info("[%s] собрано %d фрагментов", source_type.value, len(filtered))
        state.raw_chunks.extend(filtered)
        return state

    return _node


# =============================================================================
# 4. LLM-функции (замоканы детерминированными эвристиками)
# =============================================================================

# Сигнатуры в production:
#   llm_classify(text) -> (Layer, subcategory, confidence)
#   llm_synthesize(facts_for_subcat) -> рассказанный нарратив
#   llm_judge(text, taxonomy) -> Optional[red_flag_category]

LAYER_KEYWORDS = {
    Layer.FOUNDER_PERSONAL: ["детств", "семь", "родил", "ценност", "страх", "мечт", "вера", "переломн", "the turning point"],
    Layer.FOUNDER_PROFESSIONAL: ["gett", "kupivip", "carprice", "опыт", "руководил", "масштаб", "ipo", "$1b", "$1 b", "млрд", "карьер"],
    Layer.COMMUNITY_CULTURE: ["invite-only", "сообщество", "клуб", "доверие", "founders forum", "нетворк", "ангел", "wix", "zalando"],
    Layer.COMMUNITY_PRO_EXPERIENCE: ["команда", "cxo", "ангелов", "управляющ", "advisory", "темчук", "хартманн"],
    Layer.CLIENTS_STORIES: ["клиент", "spacex", "discord", "vercel", "perplexity", "n26", "monzo", "qonto", "акционер"],
    Layer.PRODUCT_BUSINESS: ["equity pooling", "fund i", "fund ii", "fund iii", "secondary", "rule 506", "section 3(c)", "aum", "valuation", "оценк", "$46m", "$140m", "$60m"],
    Layer.SOCIAL_IMPACT: ["миссия", "защит", "ликвидност", "founders os", "наследие", "5 миллиард", "12 000"],
    Layer.PEST_CONTEXT: ["sec", "регулятор", "1996", "nsmia", "jobs act", "stay private", "макро", "ставк", "кризис", "война"],
}

SUBCAT_KEYWORDS = {
    Layer.FOUNDER_PERSONAL: {
        "Origin & Childhood": ["детств", "родил", "семь", "казахстан"],
        "Values & Beliefs": ["верит", "ценност", "вера", "убежден"],
        "Fears & Vulnerability": ["страх", "уязвим", "уроk", "ошибк", "the turning point", "переломн"],
        "Dreams & Identity": ["мечт", "идентичност", "founders os"],
    },
    Layer.FOUNDER_PROFESSIONAL: {
        "Path to expertise": ["gett", "kupivip", "carprice", "масштаб", "руководил", "$1b", "млрд"],
        "Founder role & motivation": ["мотивац", "роль", "архитект"],
        "Co-founder dynamics": ["темчук", "хартманн", "со-основа", "сооснова"],
    },
    Layer.PRODUCT_BUSINESS: {
        "Architecture of the solution": ["equity pooling", "fund i", "fund ii", "fund iii", "rule 506", "section 3(c)"],
        "Philosophy of decisions": ["philosophy", "founders os", "взаимн", "интерес"],
        "Evolution": ["evolution", "$46m", "$140m", "оценк", "стелс"],
    },
}


def llm_classify(text: str) -> Tuple[Layer, str, float]:
    """Грубая эвристика для демо. В production — LLM с few-shot из DE.pdf."""
    t = text.lower()
    best_layer, best_score = Layer.PRODUCT_BUSINESS, 0
    for layer, keys in LAYER_KEYWORDS.items():
        score = sum(1 for k in keys if k in t)
        if score > best_score:
            best_layer, best_score = layer, score
    # подкатегория
    subs = SUBCAT_KEYWORDS.get(best_layer, {})
    best_sub, best_sub_score = SUBCATEGORIES[best_layer][0], 0
    for sub, keys in subs.items():
        score = sum(1 for k in keys if k in t)
        if score > best_sub_score:
            best_sub, best_sub_score = sub, score
    confidence = min(0.6 + 0.1 * best_score, 0.95)
    return best_layer, best_sub, confidence


def llm_judge_red_flag(text: str) -> Optional[Tuple[str, float]]:
    """Демо-сигнатуры hard и soft red flags."""
    t = text.lower()
    hard = {
        "sanctions": ["sanction", "ofac", "санкц", "embargo"],
        "criminal": ["обвин", "indict", "уголовн", "fraud", "мошенниче"],
        "sec_enforcement": ["sec enforcement", "fcа fine", "fca fine", "регулятор", "штраф"],
        "data_breach_fine": ["data breach", "gdpr fine", "ico fine", "утечк"],
    }
    soft = {
        "toxic_communication": ["унизил", "угрожал", "культ личности", "оскорбил", "harass"],
        "exec_exodus": ["массовый исход", "ушли все", "увольнен", "exodus"],
        "investor_lawsuit": ["суд от инвесторов", "иск инвесторов", "investor lawsuit"],
        "deadpool_pattern": ["закрыли", "deadpool", "обанкротил"],
    }
    for cat, kws in hard.items():
        if any(k in t for k in kws):
            return f"hard:{cat}", 0.92
    for cat, kws in soft.items():
        if any(k in t for k in kws):
            return f"soft:{cat}", 0.78
    return None


def llm_classify_green(text: str) -> bool:
    """Простой green-сигнал: упоминание track record, доверия, инвестиций."""
    t = text.lower()
    green_signals = [
        "$1b", "$1 b", "млрд", "масштаб", "лидер рынка", "fortune 500",
        "advisory", "founders forum", "wix", "zalando", "регулиру",
        "track record", "довери", "честность", "признаёт", "признаёт ошибк",
        "опыт", "опытом", "ipo", "стелс-режим",
    ]
    return any(s in t for s in green_signals)


# =============================================================================
# 5. Узлы графа: classify, flag, synthesize, timeline, decide, report
# =============================================================================

def node_layer_classifier(state: State) -> State:
    """Превращает raw_chunks в Fact'ы с layer/subcategory."""
    facts: List[Fact] = []
    for chunk in state.raw_chunks:
        layer, sub, conf = llm_classify(chunk["text"])
        event_date = None
        if chunk.get("event_date"):
            event_date = dt.date.fromisoformat(chunk["event_date"])
        facts.append(Fact(
            entity_id=chunk.get("entity_focus", state.entity_id),
            layer=layer,
            subcategory=sub,
            source_type=SourceType(chunk["source_type"]),
            text=chunk["text"][:500],
            source_url=chunk["url"],
            captured_at=dt.datetime.fromisoformat(chunk["captured_at"]),
            confidence=conf,
            event_date=event_date,
        ))
    state.facts = facts
    log.info("Classified %d facts across %d layers",
             len(facts), len({f.layer for f in facts}))
    return state


def node_flag_detector(state: State) -> State:
    """Размечает 🟢/🔴/⚪. Hard-флаги — правила, soft — LLM-judge."""
    for fact in state.facts:
        red = llm_judge_red_flag(fact.text)
        if red:
            cat, conf = red
            fact.flag = Flag.RED
            fact.red_flag_category = cat
            fact.confidence = conf
        elif llm_classify_green(fact.text):
            fact.flag = Flag.GREEN
            fact.confidence = max(fact.confidence, 0.8)
        else:
            # Если факт информативный, но без зелёного/красного сигнала — оставим серым
            fact.flag = Flag.GREY
    counts = defaultdict(int)
    for f in state.facts:
        counts[f.flag.value] += 1
    log.info("Flag distribution: %s", dict(counts))
    return state


def node_timeline_builder(state: State) -> State:
    events = []
    for f in state.facts:
        if f.event_date:
            events.append({
                "date": f.event_date.isoformat(),
                "entity": f.entity_id,
                "layer": LAYER_LABEL[f.layer],
                "text": f.text,
                "source": f.source_url,
            })
    events.sort(key=lambda e: e["date"])
    state.timeline = events
    log.info("Timeline: %d datable events", len(events))
    return state


def node_story_synthesizer(state: State) -> State:
    """
    Группирует факты по слою/подкатегории и формирует storytelling-нарратив.
    В production вместо конкатенации — LLM с инструкцией «не выдумывать».
    """
    by_key: Dict[Tuple[Layer, str], List[Fact]] = defaultdict(list)
    for f in state.facts:
        by_key[(f.layer, f.subcategory)].append(f)

    story: Dict[str, Dict[str, str]] = defaultdict(dict)
    for (layer, sub), facts in sorted(by_key.items(), key=lambda x: x[0][0].value):
        green = [f for f in facts if f.flag == Flag.GREEN]
        red = [f for f in facts if f.flag == Flag.RED]
        grey = [f for f in facts if f.flag == Flag.GREY]
        narrative_parts = []
        if green:
            narrative_parts.append("ЗЕЛЁНЫЙ:\n" + "\n".join(f"  · {f.text} [src: {f.source_url}]" for f in green))
        if red:
            narrative_parts.append("КРАСНЫЙ:\n" + "\n".join(f"  · {f.text} (категория: {f.red_flag_category}) [src: {f.source_url}]" for f in red))
        if grey:
            narrative_parts.append("СЕРЫЙ (требует доуточнения):\n" + "\n".join(f"  · {f.text} [src: {f.source_url}]" for f in grey))
        story[LAYER_LABEL[layer]][sub] = "\n\n".join(narrative_parts) if narrative_parts else "(пусто)"
    state.story = dict(story)
    return state


def node_decision_engine(state: State) -> State:
    """
    Decision matrix из архитектурного документа:
      🟢 Continue   — 0 hard, ≤1 soft, ≥5 green в слоях 1, 2, 6
      🟡 Watch      — 0 hard, 2–3 soft ИЛИ <5 green
      🟠 Pause      — 1 hard ИЛИ ≥4 soft
      🔴 Terminate  — ≥2 hard ИЛИ 1 hard sanctions/criminal с conf ≥0.85
    """
    hard, soft = [], []
    for f in state.facts:
        if f.flag != Flag.RED or not f.red_flag_category:
            continue
        if f.red_flag_category.startswith("hard:"):
            hard.append(f)
        else:
            soft.append(f)
    key_layers = {Layer.FOUNDER_PERSONAL, Layer.FOUNDER_PROFESSIONAL, Layer.PRODUCT_BUSINESS}
    green_in_key = sum(1 for f in state.facts if f.flag == Flag.GREEN and f.layer in key_layers)

    # правила
    decision = "watch"
    rationale = []
    high_conf_hard = [f for f in hard if f.confidence >= 0.85
                      and f.red_flag_category in ("hard:sanctions", "hard:criminal")]
    if len(hard) >= 2:
        decision = "terminate"
        rationale.append(f">=2 hard red flags ({len(hard)})")
    elif high_conf_hard:
        decision = "terminate"
        rationale.append(f"hard sanctions/criminal с confidence>=0.85: {[f.red_flag_category for f in high_conf_hard]}")
    elif len(hard) == 1 or len(soft) >= 4:
        decision = "pause"
        rationale.append(f"hard={len(hard)}, soft={len(soft)}")
    elif len(hard) == 0 and len(soft) <= 1 and green_in_key >= 5:
        decision = "continue"
        rationale.append(f"0 hard, soft<=1, green в ключевых слоях={green_in_key}")
    else:
        decision = "watch"
        rationale.append(f"hard={len(hard)}, soft={len(soft)}, green в ключевых слоях={green_in_key}")

    state.decision = {
        "recommendation": decision,
        "rationale": "; ".join(rationale),
        "hard_red_count": len(hard),
        "soft_red_count": len(soft),
        "green_in_key_layers": green_in_key,
        "evaluated_at": dt.datetime.utcnow().isoformat(),
        "human_approval_required": True,
    }
    log.info("Decision: %s (%s)", decision.upper(), state.decision["rationale"])
    return state


def node_metrics(state: State) -> State:
    """Coverage = доля заполненных подкатегорий по 8 слоям."""
    total_subcats = sum(len(v) for v in SUBCATEGORIES.values())
    covered_subcats = len({(f.layer, f.subcategory) for f in state.facts})
    state.metrics = {
        "coverage_pct": round(100 * covered_subcats / total_subcats, 1),
        "fact_count": len(state.facts),
        "green_count": sum(1 for f in state.facts if f.flag == Flag.GREEN),
        "red_count": sum(1 for f in state.facts if f.flag == Flag.RED),
        "grey_count": sum(1 for f in state.facts if f.flag == Flag.GREY),
        "freshness_days_p50": _median([(dt.datetime.utcnow() - f.captured_at).days for f in state.facts]) if state.facts else None,
    }
    log.info("Metrics: %s", state.metrics)
    return state


def _median(xs: List[float]) -> Optional[float]:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return float(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2)


def node_reporter(state: State) -> State:
    """Сериализует Diamond-слой в JSON. В production — генерация .docx/.pptx."""
    payload = {
        "entity_id": state.entity_id,
        "generated_at": dt.datetime.utcnow().isoformat(),
        "metrics": state.metrics,
        "decision": state.decision,
        "timeline": state.timeline,
        "story": state.story,
        "facts": [f.to_jsonable() for f in state.facts],
    }
    if state.report_path:
        with open(state.report_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        log.info("Report saved → %s", state.report_path)
    state._payload = payload  # type: ignore[attr-defined]
    return state


# =============================================================================
# 6. Сборка графа
# =============================================================================

def build_graph() -> Graph:
    g = Graph()

    # collectors (параллельно — в production это langgraph.parallel или asyncio.gather)
    g.add_node("collect_interview", collector_factory(SourceType.ONLINE_INTERVIEW))
    g.add_node("collect_research", collector_factory(SourceType.ONLINE_RESEARCH))
    g.add_node("collect_archival", collector_factory(SourceType.ARCHIVAL))
    g.add_node("collect_offline", collector_factory(SourceType.OFFLINE_INTERVIEW))
    g.add_parallel("collect", [
        "collect_interview", "collect_research", "collect_archival", "collect_offline",
    ], join_to="classify")

    g.add_node("classify", node_layer_classifier)
    g.add_edge("classify", "flag")

    g.add_node("flag", node_flag_detector)
    g.add_edge("flag", "timeline")

    g.add_node("timeline", node_timeline_builder)
    g.add_edge("timeline", "synthesize")

    g.add_node("synthesize", node_story_synthesizer)
    g.add_edge("synthesize", "decide")

    g.add_node("decide", node_decision_engine)
    g.add_edge("decide", "metrics")

    g.add_node("metrics", node_metrics)
    g.add_edge("metrics", "report")

    g.add_node("report", node_reporter)
    g.add_edge("report", Graph.END)

    g.set_entry("collect")
    return g


# =============================================================================
# 7. CLI / Demo
# =============================================================================

def render_summary(state: State) -> str:
    lines = []
    lines.append("=" * 78)
    lines.append(f"STORYTELLING DATA LAKE — {state.entity_id.upper()}")
    lines.append("=" * 78)
    lines.append(f"Coverage: {state.metrics.get('coverage_pct')}% · "
                 f"Facts: {state.metrics.get('fact_count')} "
                 f"(green={state.metrics.get('green_count')}, "
                 f"red={state.metrics.get('red_count')}, "
                 f"grey={state.metrics.get('grey_count')})")
    lines.append(f"Freshness P50: {state.metrics.get('freshness_days_p50')} дн.")
    lines.append("")
    lines.append(f"DECISION: {state.decision.get('recommendation', '?').upper()}")
    lines.append(f"  rationale: {state.decision.get('rationale', '')}")
    lines.append(f"  human_approval_required: {state.decision.get('human_approval_required')}")
    lines.append("")
    lines.append("--- TIMELINE ---")
    for ev in state.timeline:
        lines.append(f"  {ev['date']} · {ev['entity']} · {ev['layer']}")
        lines.append(f"      {textwrap.shorten(ev['text'], 110)}")
    lines.append("")
    lines.append("--- STORY (по слоям) ---")
    for layer_name, subs in state.story.items():
        lines.append(f"\n■ {layer_name}")
        for sub, narrative in subs.items():
            lines.append(f"  ▸ {sub}")
            for ln in narrative.splitlines():
                lines.append(f"    {ln}")
    return "\n".join(lines)


def cmd_list_entities() -> int:
    print("Сущности в watchlist:")
    for ent in DEMO_CORPUS:
        n = len(DEMO_CORPUS[ent])
        print(f"  · {ent}  ({n} сырых фрагментов в корпусе)")
    return 0


def cmd_add_fact(entity: str, text: str, source_type: str, source_url: str) -> int:
    """Offline ingest: добавляет новый сырьевой фрагмент в локальный корпус."""
    if entity not in DEMO_CORPUS:
        log.error("Неизвестная сущность %r", entity)
        return 2
    DEMO_CORPUS[entity].append({
        "source_type": SourceType(source_type),
        "url": source_url,
        "captured_at": dt.date.today().isoformat(),
        "text": text,
        "entity_focus": entity,
    })
    # сохраняем локальный «оверлей» рядом со скриптом — в production это БД
    overlay_path = "offline_overlay.json"
    overlay = []
    try:
        with open(overlay_path, "r", encoding="utf-8") as fh:
            overlay = json.load(fh)
    except FileNotFoundError:
        pass
    overlay.append({
        "entity": entity, "text": text,
        "source_type": source_type, "url": source_url,
        "added_at": dt.datetime.utcnow().isoformat(),
    })
    with open(overlay_path, "w", encoding="utf-8") as fh:
        json.dump(overlay, fh, ensure_ascii=False, indent=2)
    log.info("Факт добавлен в корпус (entity=%s); сохранён в %s", entity, overlay_path)
    return 0


def cmd_diff(prev_path: str, curr_path: str) -> int:
    with open(prev_path, "r", encoding="utf-8") as fh:
        prev = json.load(fh)
    with open(curr_path, "r", encoding="utf-8") as fh:
        curr = json.load(fh)

    def _key(f: Dict[str, Any]) -> str:
        return f"{f['source_url']}::{hash(f['text'])}"

    prev_keys = {_key(f) for f in prev.get("facts", [])}
    curr_keys = {_key(f) for f in curr.get("facts", [])}
    added = [f for f in curr["facts"] if _key(f) not in prev_keys]
    removed = [f for f in prev["facts"] if _key(f) not in curr_keys]

    print(f"=== DIFF {prev_path} → {curr_path} ===")
    print(f"Decision: {prev['decision'].get('recommendation')} → {curr['decision'].get('recommendation')}")
    print(f"+ {len(added)} новых фактов, − {len(removed)} убрано")
    for f in added[:10]:
        print(f"  + [{f['flag']}] {textwrap.shorten(f['text'], 100)}")
    for f in removed[:10]:
        print(f"  − [{f['flag']}] {textwrap.shorten(f['text'], 100)}")
    return 0


def cmd_watch(entity: str, interval: int, max_iterations: int = 3) -> int:
    """Демо event-watcher. В production — слушает RSS/GDELT live, а не sleep-цикл."""
    import time
    log.info("WATCH режим: проверяю обновления каждые %d сек (max %d циклов)", interval, max_iterations)
    last_fact_count = 0
    for i in range(max_iterations):
        state = State(entity_id=entity)
        final = build_graph().run(state)
        n = len(final.facts)
        delta = n - last_fact_count
        recommend = final.decision.get("recommendation", "?").upper()
        log.info("[tick %d] фактов=%d (Δ=%+d), решение=%s", i + 1, n, delta, recommend)
        if delta > 0 and i > 0:
            log.warning("⚠ ALERT (mock): новые %d факт(ов) для %s — push в Slack/Telegram", delta, entity)
        last_fact_count = n
        if i < max_iterations - 1:
            time.sleep(interval)
    return 0


# ----- HTML-дашборд -----

DASHBOARD_HTML_TEMPLATE = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Storytelling Data Lake — __ENTITY__</title>
<style>
  :root {
    --navy: #1E2761;
    --ice: #CADCFC;
    --accent: #F96167;
    --green: #2C9F5F;
    --amber: #B58A00;
    --grey: #94A3B8;
    --bg: #F5F7FA;
    --card: #FFFFFF;
    --text: #0F172A;
    --muted: #475569;
    --border: #E2E8F0;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.5;
  }
  header {
    background: var(--navy); color: white; padding: 24px 32px;
    display: grid; grid-template-columns: 1fr auto; gap: 16px; align-items: center;
  }
  header .eyebrow {
    font-size: 11px; letter-spacing: 4px; text-transform: uppercase; color: var(--ice); margin-bottom: 4px;
  }
  header h1 { margin: 0; font-size: 28px; font-weight: 700; }
  header .meta { font-size: 13px; color: var(--ice); margin-top: 6px; }
  .decision-badge {
    padding: 14px 20px; border-radius: 8px; min-width: 220px; text-align: center;
    font-weight: 700; letter-spacing: 1px;
  }
  .decision-badge.continue { background: var(--green); color: white; }
  .decision-badge.watch    { background: var(--amber); color: white; }
  .decision-badge.pause    { background: #C2410C; color: white; }
  .decision-badge.terminate{ background: var(--accent); color: white; }
  .decision-badge .label { font-size: 11px; opacity: 0.8; letter-spacing: 3px; }
  .decision-badge .name  { font-size: 22px; margin-top: 4px; text-transform: uppercase; }
  .decision-badge .why   { font-size: 11px; opacity: 0.85; margin-top: 6px; font-weight: 400; letter-spacing: 0; }

  main { max-width: 1280px; margin: 24px auto; padding: 0 24px; }

  .toolbar {
    display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
    margin-bottom: 20px; padding: 14px 18px;
    background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  }
  .toolbar input[type=search] {
    flex: 1; min-width: 220px; padding: 8px 12px; border: 1px solid var(--border);
    border-radius: 6px; font-size: 14px;
  }
  .toolbar select, .toolbar button {
    padding: 7px 12px; border: 1px solid var(--border); border-radius: 6px;
    background: white; font-size: 13px; cursor: pointer;
  }
  .toolbar button.primary { background: var(--navy); color: white; border-color: var(--navy); }
  .toolbar button.primary:hover { background: #2a3a8c; }

  .kpis {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px; margin-bottom: 24px;
  }
  .kpi {
    background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    padding: 16px; border-left: 3px solid var(--navy);
  }
  .kpi .v { font-size: 26px; font-weight: 700; color: var(--navy); }
  .kpi .l { font-size: 11px; letter-spacing: 1px; text-transform: uppercase; color: var(--muted); margin-top: 4px; }

  .tabs { display: flex; gap: 4px; border-bottom: 2px solid var(--border); margin-bottom: 16px; }
  .tab {
    padding: 10px 18px; cursor: pointer; font-size: 14px; font-weight: 600; color: var(--muted);
    border-bottom: 2px solid transparent; margin-bottom: -2px;
  }
  .tab.active { color: var(--navy); border-bottom-color: var(--accent); }

  .panel { display: none; }
  .panel.active { display: block; }

  .layer-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    margin-bottom: 12px; overflow: hidden;
  }
  .layer-head {
    padding: 14px 18px; display: flex; align-items: center; gap: 12px; cursor: pointer;
    user-select: none;
  }
  .layer-head:hover { background: #FBFCFD; }
  .layer-num {
    width: 32px; height: 32px; border-radius: 16px; background: var(--navy); color: white;
    display: grid; place-items: center; font-weight: 700; font-size: 14px; flex-shrink: 0;
  }
  .layer-title { flex: 1; font-weight: 600; font-size: 15px; }
  .layer-stats { font-size: 12px; color: var(--muted); display: flex; gap: 10px; }
  .pill { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
  .pill.green { background: #E6F5EE; color: var(--green); }
  .pill.red   { background: #FDE7E8; color: var(--accent); }
  .pill.grey  { background: #ECEFF3; color: var(--muted); }
  .layer-body { padding: 0 18px 18px 62px; display: none; }
  .layer-card.open .layer-body { display: block; }
  .layer-card.open .arrow { transform: rotate(90deg); }
  .arrow { width: 0; height: 0; border-style: solid; border-width: 5px 0 5px 7px;
           border-color: transparent transparent transparent var(--muted); transition: transform 0.15s; }

  .subcat { margin-bottom: 14px; }
  .subcat-name { font-size: 13px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
  .fact {
    border-left: 3px solid var(--grey); padding: 8px 12px; margin-bottom: 6px;
    background: #FAFBFD; border-radius: 0 4px 4px 0; font-size: 13px;
  }
  .fact.green { border-left-color: var(--green); background: #F4FAF7; }
  .fact.red   { border-left-color: var(--accent); background: #FEF6F6; }
  .fact .src { font-size: 11px; color: var(--muted); margin-top: 4px; }
  .fact .src a { color: var(--navy); text-decoration: none; }
  .fact .src a:hover { text-decoration: underline; }
  .fact .meta { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .red-cat { color: var(--accent); font-weight: 600; }

  /* Timeline */
  .timeline { position: relative; padding-left: 24px; }
  .timeline::before { content: ""; position: absolute; left: 7px; top: 0; bottom: 0; width: 2px; background: var(--border); }
  .tl-item { position: relative; padding-bottom: 18px; }
  .tl-item::before { content: ""; position: absolute; left: -22px; top: 4px; width: 12px; height: 12px;
                     border-radius: 6px; background: var(--navy); border: 2px solid white; box-shadow: 0 0 0 1px var(--border); }
  .tl-date { font-size: 12px; color: var(--accent); font-weight: 700; letter-spacing: 1px; }
  .tl-text { font-size: 14px; margin-top: 2px; }
  .tl-meta { font-size: 11px; color: var(--muted); margin-top: 3px; }

  /* Facts table */
  table.facts { width: 100%; border-collapse: collapse; background: var(--card); border-radius: 8px; overflow: hidden;
                border: 1px solid var(--border); font-size: 13px; }
  table.facts th { background: var(--navy); color: white; text-align: left; padding: 10px 12px;
                   font-size: 11px; letter-spacing: 1px; text-transform: uppercase; font-weight: 600; }
  table.facts td { padding: 10px 12px; border-top: 1px solid var(--border); vertical-align: top; }
  table.facts tr.hidden { display: none; }
  table.facts tr:hover td { background: #FBFCFD; }

  footer {
    margin-top: 32px; padding: 16px 24px; text-align: center; font-size: 12px; color: var(--muted);
  }
  code.cmd {
    display: inline-block; padding: 2px 8px; background: #ECEFF3; border-radius: 4px;
    font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 12px; color: var(--navy);
  }
</style>
</head>
<body>
<header>
  <div>
    <div class="eyebrow">Storytelling Data Lake · v0.1</div>
    <h1>__ENTITY_TITLE__</h1>
    <div class="meta">Сгенерировано: __GENERATED_AT__</div>
  </div>
  <div class="decision-badge __DECISION__" title="__RATIONALE__">
    <div class="label">Recommendation</div>
    <div class="name">__DECISION__</div>
    <div class="why">__RATIONALE__</div>
  </div>
</header>
<main>
  <div class="kpis">
    <div class="kpi"><div class="v">__COVERAGE__%</div><div class="l">Coverage</div></div>
    <div class="kpi"><div class="v">__FACT_COUNT__</div><div class="l">Facts</div></div>
    <div class="kpi" style="border-left-color: var(--green)"><div class="v">__GREEN_COUNT__</div><div class="l">Green flags</div></div>
    <div class="kpi" style="border-left-color: var(--accent)"><div class="v">__RED_COUNT__</div><div class="l">Red flags</div></div>
    <div class="kpi" style="border-left-color: var(--grey)"><div class="v">__GREY_COUNT__</div><div class="l">Grey (требуют доуточнения)</div></div>
    <div class="kpi"><div class="v">__FRESHNESS__ дн.</div><div class="l">Freshness P50</div></div>
  </div>

  <div class="tabs">
    <div class="tab active" data-panel="story">Storytelling по слоям</div>
    <div class="tab" data-panel="timeline">Таймлайн</div>
    <div class="tab" data-panel="facts">Все факты</div>
    <div class="tab" data-panel="actions">Действия</div>
  </div>

  <div class="panel active" id="panel-story">
    <div class="toolbar">
      <input type="search" id="story-search" placeholder="Поиск по фактам и цитатам…">
      <select id="story-flag-filter">
        <option value="">Все флаги</option>
        <option value="green">🟢 Только Green</option>
        <option value="red">🔴 Только Red</option>
        <option value="grey">⚪ Только Grey</option>
      </select>
    </div>
    <div id="story-container"></div>
  </div>

  <div class="panel" id="panel-timeline">
    <div class="toolbar">
      <input type="search" id="tl-search" placeholder="Поиск по событиям…">
      <select id="tl-sort">
        <option value="asc">Старые сверху</option>
        <option value="desc">Новые сверху</option>
      </select>
    </div>
    <div class="timeline" id="timeline-container"></div>
  </div>

  <div class="panel" id="panel-facts">
    <div class="toolbar">
      <input type="search" id="facts-search" placeholder="Поиск по фактам…">
      <select id="facts-layer-filter"><option value="">Все слои</option></select>
      <select id="facts-flag-filter">
        <option value="">Все флаги</option>
        <option value="green">Green</option>
        <option value="red">Red</option>
        <option value="grey">Grey</option>
      </select>
      <select id="facts-source-filter">
        <option value="">Все источники</option>
        <option value="online_interview">online_interview</option>
        <option value="offline_interview">offline_interview</option>
        <option value="online_research">online_research</option>
        <option value="archival">archival</option>
      </select>
    </div>
    <table class="facts" id="facts-table">
      <thead><tr>
        <th>Слой</th><th>Подкатегория</th><th>Источник</th><th>Флаг</th><th>Текст</th><th>URL</th>
      </tr></thead>
      <tbody id="facts-tbody"></tbody>
    </table>
  </div>

  <div class="panel" id="panel-actions">
    <div style="background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 24px;">
      <h3 style="margin-top: 0; color: var(--navy);">Что аналитик может сделать дальше</h3>
      <p style="color: var(--muted);">В production эти кнопки делают POST в backend. Сейчас прототип — CLI; ниже команды, которые можно скопировать.</p>

      <div style="display: grid; gap: 14px; margin-top: 16px;">
        <div>
          <div style="font-weight: 600; margin-bottom: 4px;">▸ Перезапустить сбор</div>
          <code class="cmd">python storytelling_bot.py --entity __ENTITY__ --output report.json --export-html dashboard.html</code>
        </div>
        <div>
          <div style="font-weight: 600; margin-bottom: 4px;">▸ Добавить факт от руки (offline ingest со встречи)</div>
          <code class="cmd">python storytelling_bot.py --entity __ENTITY__ --add-fact "Расшифровка встречи: фаундер подтвердил план B…" --add-fact-source offline_interview --add-fact-url internal://meeting/2026-04-26</code>
        </div>
        <div>
          <div style="font-weight: 600; margin-bottom: 4px;">▸ Сравнить с предыдущим запуском</div>
          <code class="cmd">python storytelling_bot.py --diff prev_report.json report.json</code>
        </div>
        <div>
          <div style="font-weight: 600; margin-bottom: 4px;">▸ Запустить watch-режим (мок event watcher)</div>
          <code class="cmd">python storytelling_bot.py --watch --entity __ENTITY__ --interval 60</code>
        </div>
        <div>
          <div style="font-weight: 600; margin-bottom: 4px;">▸ Список доступных сущностей</div>
          <code class="cmd">python storytelling_bot.py --list</code>
        </div>
      </div>

      <hr style="margin: 24px 0; border: 0; border-top: 1px solid var(--border);">
      <h4 style="margin-top: 0; color: var(--navy);">Decision rationale</h4>
      <p id="rationale-detail" style="font-size: 14px;"></p>
      <div style="font-size: 12px; color: var(--muted);">
        ⚠ Бот выдаёт только рекомендацию. Финальное решение всегда утверждает человек —
        старший аналитик и (при terminate) юрист.
      </div>
    </div>
  </div>
</main>

<footer>
  Источник данных: <code style="font-family: monospace;">demo_report.json</code> ·
  Последнее обновление: __GENERATED_AT__
</footer>

<script>
const PAYLOAD = __PAYLOAD_JSON__;

// ---- helpers ----
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));

const LAYER_NUM = (() => {
  const list = Object.keys(PAYLOAD.story);
  const m = {};
  list.forEach((name, idx) => m[name] = idx + 1);
  return m;
})();

// ---- tabs ----
$$(".tab").forEach(t => t.addEventListener("click", () => {
  $$(".tab").forEach(x => x.classList.remove("active"));
  $$(".panel").forEach(x => x.classList.remove("active"));
  t.classList.add("active");
  $("#panel-" + t.dataset.panel).classList.add("active");
}));

// ---- story panel ----
function renderStory() {
  const cont = $("#story-container");
  cont.innerHTML = "";
  const facts_by_layer_sub = {};
  PAYLOAD.facts.forEach(f => {
    const layer = Object.keys(PAYLOAD.story).find(n => true && Object.keys(PAYLOAD.story[n]).includes(f.subcategory));
    const layerName = layer || `Layer ${f.layer}`;
    facts_by_layer_sub[layerName] = facts_by_layer_sub[layerName] || {};
    facts_by_layer_sub[layerName][f.subcategory] = facts_by_layer_sub[layerName][f.subcategory] || [];
    facts_by_layer_sub[layerName][f.subcategory].push(f);
  });

  Object.keys(PAYLOAD.story).forEach(layerName => {
    const subs = PAYLOAD.story[layerName];
    let totalFacts = 0, green = 0, red = 0, grey = 0;
    Object.values(facts_by_layer_sub[layerName] || {}).forEach(arr => {
      arr.forEach(f => {
        totalFacts++;
        if (f.flag === "green") green++;
        else if (f.flag === "red") red++;
        else grey++;
      });
    });

    const card = document.createElement("div");
    card.className = "layer-card";
    card.dataset.layerName = layerName;
    card.innerHTML = `
      <div class="layer-head">
        <div class="arrow"></div>
        <div class="layer-num">${LAYER_NUM[layerName] || "?"}</div>
        <div class="layer-title">${layerName}</div>
        <div class="layer-stats">
          <span class="pill green">🟢 ${green}</span>
          <span class="pill red">🔴 ${red}</span>
          <span class="pill grey">⚪ ${grey}</span>
        </div>
      </div>
      <div class="layer-body"></div>
    `;
    const body = card.querySelector(".layer-body");
    Object.keys(subs).forEach(subName => {
      const subDiv = document.createElement("div");
      subDiv.className = "subcat";
      subDiv.innerHTML = `<div class="subcat-name">${subName}</div>`;
      const arr = (facts_by_layer_sub[layerName] || {})[subName] || [];
      if (arr.length === 0) {
        subDiv.innerHTML += `<div class="fact grey"><em style="color: var(--muted)">(нет фактов в этой подкатегории — серое поле)</em></div>`;
      } else {
        arr.forEach(f => {
          const factEl = document.createElement("div");
          factEl.className = "fact " + f.flag;
          factEl.dataset.flag = f.flag;
          factEl.dataset.text = (f.text || "").toLowerCase();
          factEl.innerHTML = `
            <div>${f.text}</div>
            <div class="meta">
              <strong>${f.source_type}</strong> · confidence ${(f.confidence || 0).toFixed(2)}
              ${f.red_flag_category ? ' · <span class="red-cat">' + f.red_flag_category + "</span>" : ""}
            </div>
            <div class="src"><a href="${f.source_url}" target="_blank">${f.source_url}</a></div>
          `;
          subDiv.appendChild(factEl);
        });
      }
      body.appendChild(subDiv);
    });

    card.querySelector(".layer-head").addEventListener("click", () => card.classList.toggle("open"));
    cont.appendChild(card);
  });
  // open first by default
  cont.querySelector(".layer-card")?.classList.add("open");
}

function applyStoryFilters() {
  const q = $("#story-search").value.toLowerCase().trim();
  const flag = $("#story-flag-filter").value;
  $$(".fact").forEach(el => {
    const matchQ = !q || (el.dataset.text || "").includes(q);
    const matchF = !flag || el.dataset.flag === flag;
    el.style.display = (matchQ && matchF) ? "" : "none";
  });
}
$("#story-search").addEventListener("input", applyStoryFilters);
$("#story-flag-filter").addEventListener("change", applyStoryFilters);

// ---- timeline ----
function renderTimeline() {
  const cont = $("#timeline-container");
  cont.innerHTML = "";
  let items = [...PAYLOAD.timeline];
  const order = $("#tl-sort").value;
  items.sort((a, b) => order === "asc" ? a.date.localeCompare(b.date) : b.date.localeCompare(a.date));
  const q = $("#tl-search").value.toLowerCase().trim();
  items.filter(e => !q || e.text.toLowerCase().includes(q) || e.layer.toLowerCase().includes(q))
       .forEach(e => {
    const d = document.createElement("div");
    d.className = "tl-item";
    d.innerHTML = `
      <div class="tl-date">${e.date}</div>
      <div class="tl-text">${e.text}</div>
      <div class="tl-meta">${e.layer} · ${e.entity} · <a href="${e.source}" target="_blank">источник</a></div>
    `;
    cont.appendChild(d);
  });
  if (items.length === 0) {
    cont.innerHTML = '<div style="color: var(--muted); padding: 16px;">Датируемых событий пока нет.</div>';
  }
}
$("#tl-search").addEventListener("input", renderTimeline);
$("#tl-sort").addEventListener("change", renderTimeline);

// ---- facts table ----
function renderFactsTable() {
  const tbody = $("#facts-tbody");
  tbody.innerHTML = "";
  const layerSel = $("#facts-layer-filter");
  const layers = Object.keys(PAYLOAD.story);
  if (layerSel.options.length <= 1) {
    layers.forEach(l => {
      const o = document.createElement("option"); o.value = l; o.text = l;
      layerSel.appendChild(o);
    });
  }
  PAYLOAD.facts.forEach(f => {
    const tr = document.createElement("tr");
    const layerName = layers.find(n => Object.keys(PAYLOAD.story[n]).includes(f.subcategory)) || `Layer ${f.layer}`;
    tr.dataset.layer = layerName;
    tr.dataset.flag = f.flag;
    tr.dataset.source = f.source_type;
    tr.dataset.text = (f.text || "").toLowerCase();
    tr.innerHTML = `
      <td>${LAYER_NUM[layerName] || "?"}. ${layerName}</td>
      <td>${f.subcategory}</td>
      <td><code style="font-size: 11px;">${f.source_type}</code></td>
      <td><span class="pill ${f.flag}">${f.flag}</span>${f.red_flag_category ? '<br><small class="red-cat">' + f.red_flag_category + "</small>" : ""}</td>
      <td>${f.text}</td>
      <td><a href="${f.source_url}" target="_blank">↗</a></td>
    `;
    tbody.appendChild(tr);
  });
}
function applyFactsFilters() {
  const q = $("#facts-search").value.toLowerCase().trim();
  const layer = $("#facts-layer-filter").value;
  const flag = $("#facts-flag-filter").value;
  const source = $("#facts-source-filter").value;
  $$("#facts-tbody tr").forEach(tr => {
    const ok = (!q || tr.dataset.text.includes(q))
            && (!layer || tr.dataset.layer === layer)
            && (!flag || tr.dataset.flag === flag)
            && (!source || tr.dataset.source === source);
    tr.classList.toggle("hidden", !ok);
  });
}
["#facts-search", "#facts-layer-filter", "#facts-flag-filter", "#facts-source-filter"].forEach(s =>
  $(s).addEventListener("input", applyFactsFilters));

// ---- rationale ----
$("#rationale-detail").innerHTML = `
  <strong>${(PAYLOAD.decision.recommendation || "?").toUpperCase()}</strong>:
  ${PAYLOAD.decision.rationale || "(no rationale)"}
  <br><small style="color: var(--muted);">
    Hard red: ${PAYLOAD.decision.hard_red_count} ·
    Soft red: ${PAYLOAD.decision.soft_red_count} ·
    Green в ключевых слоях (1, 2, 6): ${PAYLOAD.decision.green_in_key_layers}
  </small>
`;

// initial render
renderStory();
renderTimeline();
renderFactsTable();
</script>
</body>
</html>
"""


def cmd_export_html(state: State, out_path: str) -> None:
    """Генерирует self-contained HTML-дашборд с встроенным JSON."""
    payload = getattr(state, "_payload", None)
    if payload is None:
        # на случай прямого вызова
        payload = {
            "entity_id": state.entity_id,
            "generated_at": dt.datetime.utcnow().isoformat(),
            "metrics": state.metrics,
            "decision": state.decision,
            "timeline": state.timeline,
            "story": state.story,
            "facts": [f.to_jsonable() for f in state.facts],
        }
    decision = payload["decision"].get("recommendation", "watch")
    rationale = payload["decision"].get("rationale", "").replace('"', "&quot;")
    metrics = payload["metrics"]

    html = (DASHBOARD_HTML_TEMPLATE
            .replace("__ENTITY__", state.entity_id)
            .replace("__ENTITY_TITLE__", state.entity_id.replace("-", " ").title())
            .replace("__GENERATED_AT__", payload["generated_at"][:19].replace("T", " "))
            .replace("__DECISION__", decision)
            .replace("__RATIONALE__", rationale)
            .replace("__COVERAGE__", str(metrics.get("coverage_pct", 0)))
            .replace("__FACT_COUNT__", str(metrics.get("fact_count", 0)))
            .replace("__GREEN_COUNT__", str(metrics.get("green_count", 0)))
            .replace("__RED_COUNT__", str(metrics.get("red_count", 0)))
            .replace("__GREY_COUNT__", str(metrics.get("grey_count", 0)))
            .replace("__FRESHNESS__", str(metrics.get("freshness_days_p50", "—")))
            .replace("__PAYLOAD_JSON__", json.dumps(payload, ensure_ascii=False)))

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    log.info("Дашборд сохранён → %s (открой в браузере)", out_path)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Storytelling Data Lake Bot — прототип",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("CLI для аналитика:")[1].split("Прототип написан")[0]
        if "CLI для аналитика:" in (__doc__ or "") else "",
    )
    p.add_argument("--entity", default="accumulator", help="ID сущности (компания/фаундер)")
    p.add_argument("--output", help="Путь для сохранения JSON-отчёта")
    p.add_argument("--export-html", dest="export_html", help="Путь для генерации интерактивного дашборда")
    p.add_argument("--quiet", action="store_true", help="Не печатать summary в stdout")
    p.add_argument("--list", dest="list_entities", action="store_true",
                   help="Показать список сущностей в watchlist")
    p.add_argument("--add-fact", dest="add_fact", help="Добавить факт от руки (offline ingest)")
    p.add_argument("--add-fact-source", default="offline_interview",
                   choices=[s.value for s in SourceType], help="Тип источника для --add-fact")
    p.add_argument("--add-fact-url", default="internal://manual",
                   help="URL источника для --add-fact (например internal://meeting/2026-04-26)")
    p.add_argument("--diff", nargs=2, metavar=("PREV", "CURR"),
                   help="Сравнить два JSON-отчёта (что изменилось)")
    p.add_argument("--watch", action="store_true", help="Daemon-режим: периодический пересбор + alert на изменения")
    p.add_argument("--interval", type=int, default=30, help="Интервал watch-режима (сек)")
    args = p.parse_args(argv)

    # ----- standalone subcommands -----
    if args.list_entities:
        return cmd_list_entities()
    if args.diff:
        return cmd_diff(args.diff[0], args.diff[1])
    if args.add_fact:
        return cmd_add_fact(args.entity, args.add_fact, args.add_fact_source, args.add_fact_url)
    if args.watch:
        return cmd_watch(args.entity, args.interval)

    # ----- main run -----
    if args.entity not in DEMO_CORPUS:
        log.error("В демо-корпусе нет сущности %r. Доступно: %s",
                  args.entity, list(DEMO_CORPUS))
        return 2

    state = State(entity_id=args.entity, report_path=args.output)
    graph = build_graph()
    final = graph.run(state)

    if args.export_html:
        cmd_export_html(final, args.export_html)

    if not args.quiet:
        print(render_summary(final))
    return 0


if __name__ == "__main__":
    sys.exit(main())
