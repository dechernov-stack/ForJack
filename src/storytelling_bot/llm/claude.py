"""AnthropicClient — real Claude LLM calls with few-shot from DE.pdf."""
from __future__ import annotations

import json
import logging
import os
import re

from storytelling_bot.schema import SUBCATEGORIES, Fact, Layer

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Few-shot examples extracted from DE.pdf (one per layer)
# ---------------------------------------------------------------------------
_FEW_SHOT_EXAMPLES = [
    # Layer 1 — Founder Personal
    {
        "text": "Оскар Хартманн родился 14 мая 1982 года в Казахстане в семье инженера. В 8 лет переехал в Германию, с 11 лет работал — разносил газеты, работал на складах.",
        "layer": 1, "subcategory": "Origin & Childhood", "confidence": 0.95,
    },
    {
        "text": "Главный страх Дэйва Вайзера — осознание того, что основатель может владеть 80% компании стоимостью $100M, но жить на скромную зарплату, не имея финансовой гибкости.",
        "layer": 1, "subcategory": "Fears & Vulnerability", "confidence": 0.92,
    },
    {
        "text": "Дэйв Вайзер мечтает объединить 12 000 основателей крупнейших частных компаний, влияющих на 5 миллиардов человек, в одну глобальную сеть взаимопомощи — Founders OS.",
        "layer": 1, "subcategory": "Dreams & Identity", "confidence": 0.91,
    },
    # Layer 2 — Founder Professional
    {
        "text": "Дэйв Вайзер масштабировал Gett до 1500 городов, обслуживая Fortune 500. Привлёк более $1B инвестиций за 20+ лет лидерства в стартап-экосистемах Кремниевой долины и Израиля.",
        "layer": 2, "subcategory": "Path to expertise", "confidence": 0.94,
    },
    {
        "text": "Оскар Хартманн признаёт ошибку на $300M при инвестициях в Ozon. Этот опыт лёг в основу его роли в Angels Fund II — защищать ангелов от подобных потрясений.",
        "layer": 2, "subcategory": "Founder role & motivation", "confidence": 0.90,
    },
    # Layer 3 — Community Culture
    {
        "text": "Accumulator работает по invite-only принципу. Критерии: оценка >$100M, раунд в 2024+ году, runway >18 месяцев или прибыльность. Только аккредитованные инвесторы.",
        "layer": 3, "subcategory": "Attraction & Selection", "confidence": 0.93,
    },
    {
        "text": "В декабре 2024 года Accumulator получил $46M инвестиций от Авишая Абраами (Wix), Филипа Дамеса (Zalando), NFX и FJ Labs. Стратегический партнёр — Founders Forum Group.",
        "layer": 3, "subcategory": "Investors & Partners", "confidence": 0.92,
    },
    # Layer 4 — Community Professional Experience
    {
        "text": "Сообщество объединяет экспертизу: от SpaceX и Discord до Perplexity и Qonto. Дэйв — опыт 6 компаний в США, Израиле и Великобритании. Оскар — 100+ инвестиций в 10+ стран.",
        "layer": 4, "subcategory": "Expertise & Diversity", "confidence": 0.89,
    },
    {
        "text": "Команда пережила коллективные провалы: $170M потеряно из-за закрытия окна IPO Gett, Fab.com обесценилась с $1.5B до нуля за полгода, Vigoda была deadpooled.",
        "layer": 4, "subcategory": "Collective failure memory", "confidence": 0.91,
    },
    # Layer 5 — Clients Stories
    {
        "text": "Типичный клиент — основатель 'единорога', владеющий 60–80% компании стоимостью $100M+, но получающий скромную зарплату и живущий в финансовом стрессе.",
        "layer": 5, "subcategory": "Client's challenge & context", "confidence": 0.90,
    },
    {
        "text": "Момент выбора: либо нести концентрированный риск, либо продать с дисконтом 10–20% на secondary. Accumulator предлагает третий путь — equity pooling по оценке последнего раунда.",
        "layer": 5, "subcategory": "Moment of choice & trust", "confidence": 0.89,
    },
    # Layer 6 — Product & Business
    {
        "text": "Accumulator Fund I зарегистрирован в SEC под Rule 506(b) и Section 3(c)(1). AUM по трём фондам (Founders Fund I, Angels Fund II, Index Fund III) — более $60M.",
        "layer": 6, "subcategory": "Architecture of the solution", "confidence": 0.95,
    },
    {
        "text": "Продукт эволюционировал из stealth-режима до оценки $140M, запустив три специализированных фонда с AUM >$60M. Ключевые инвесторы — лидеры из Wix и Zalando.",
        "layer": 6, "subcategory": "Evolution", "confidence": 0.91,
    },
    # Layer 7 — Social Impact
    {
        "text": "Accumulator стремится создать финансовые 'рельсы' для частного рынка стоимостью $6 трлн, делая частные акции ликвидными задолго до IPO — трансформируя 'бумажное богатство' в реальное.",
        "layer": 7, "subcategory": "Vision of change", "confidence": 0.90,
    },
    {
        "text": "Наследие: поколение предпринимателей, которые строят вдолгую без парализующего финансового давления. Сеть 12 000 фаундеров с совокупным доходом $1 трлн.",
        "layer": 7, "subcategory": "Legacy", "confidence": 0.88,
    },
    # Layer 8 — PEST Context
    {
        "text": "С 1996 года число публичных компаний в США сократилось вдвое — с >7000 до <4000. NSMIA и JOBS Act изменили правила игры. Объём вторичного рынка достиг $110B в H1 2025.",
        "layer": 8, "subcategory": "Market & technology", "confidence": 0.93,
    },
    {
        "text": "SEC регулирует Accumulator как фонд акций под Rule 506(b) и NSMIA. Геополитический кризис (война) закрыл окно IPO для Gett — классический макро-риск для late-stage стартапов.",
        "layer": 8, "subcategory": "Policy & regulation", "confidence": 0.92,
    },
]

_CLASSIFY_FEW_SHOT = "\n".join([
    f'Text: "{ex["text"]}"\n→ layer={ex["layer"]}, subcategory="{ex["subcategory"]}", confidence={ex["confidence"]}'
    for ex in _FEW_SHOT_EXAMPLES
])

_CLASSIFY_SYSTEM = f"""You are a storytelling-layer classifier for an investor data lake.
Classify each text fragment into one of 8 layers and the best-matching subcategory.

Layers and subcategories:
1. Founder Personal Story: Origin & Childhood | Values & Beliefs | Fears & Vulnerability | Dreams & Identity
2. Founder Professional Story: Path to expertise | Founder role & motivation | Co-founder dynamics
3. Community Culture, Values & Stories: Attraction & Selection | Shared life | Investors & Partners
4. Community Professional Experience: Expertise & Diversity | Growth & Transformation | Collective failure memory
5. Clients Stories: Client's challenge & context | Moment of choice & trust | Conflict & honesty
6. Product & Business: Architecture of the solution | Philosophy of decisions | Evolution
7. Social Impact Vision: Vision of change | Contradictions & cost | Legacy
8. PEST Context: Historical moment | Market & technology | Policy & regulation

Few-shot examples:
{_CLASSIFY_FEW_SHOT}

Return ONLY valid JSON:
{{"layer": <1-8>, "subcategory": "<exact name>", "confidence": <0.0-1.0>}}
No explanation. No markdown. Just JSON."""

_SYNTHESIZE_SYSTEM = """You are a storytelling analyst synthesizing facts into a coherent narrative paragraph.

CRITICAL RULES — violations are unacceptable:
1. NEVER add facts, interpretations, evaluations or conclusions not present in the provided list.
2. NEVER say things like "this demonstrates", "which shows", "indicating that" — no meta-commentary.
3. If information is absent — write exactly "(нет данных)".
4. Every word must be directly traceable to a provided fact (names, numbers, dates, quotes).
5. Keep the narrative concise (2-3 sentences max). Just report, do not interpret.
6. Respond in the same language as the facts."""

_JUDGE_SYSTEM = """You are a risk analyst evaluating text for red flags in founder/company due diligence.

Hard flags (high certainty, rule-based triggers):
- hard:sanctions — OFAC, EU, UK, UN watchlists, embargo mentions
- hard:criminal — criminal indictment, fraud conviction, мошенничество, уголовное преследование
- hard:sec_enforcement — SEC/FCA/ЦБ enforcement action, regulatory fine
- hard:fraud — confirmed fraud, fictitious bankruptcy, Ponzi
- hard:data_breach_fine — GDPR/CCPA/ICO fine for data breach

Soft flags (LLM judgment, require human validation):
- soft:toxic_communication — cult leader patterns, harassment, threats to employees
- soft:exec_exodus — ≥30% C-level departures in 12 months
- soft:investor_lawsuit — lawsuit from previous investors
- soft:deadpool_pattern — serial pivot without MVP
- soft:reputation_crash — Glassdoor/Trustpilot sudden drop

Rules:
- For hard flags: confidence ≥ 0.85 required. If evidence is weak → downgrade to soft.
- Return null if no red flag detected.
- Return ONLY valid JSON: {"category": "<hard:X or soft:X>", "confidence": <0.0-1.0>}
  OR the literal string: null
No explanation. No markdown."""


class AnthropicClient:
    def __init__(self) -> None:
        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self._client = None

    def _anthropic(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return self._client

    def _call(self, system: str, user: str, trace_name: str, max_tokens: int = 256) -> str:
        """Make an API call, recording a Langfuse generation under the current trace."""
        from storytelling_bot import langfuse_ctx
        lf = langfuse_ctx.get_langfuse()
        trace_id = langfuse_ctx.get_trace_id()

        client = self._anthropic()
        resp = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        result = resp.content[0].text.strip()

        if lf:
            try:
                parent = lf.trace(id=trace_id) if trace_id else lf.trace(name=trace_name)
                parent.generation(
                    name=trace_name,
                    model=self._model,
                    input=user[:500],
                    output=result,
                    usage={
                        "input_tokens": resp.usage.input_tokens,
                        "output_tokens": resp.usage.output_tokens,
                    },
                )
            except Exception:
                pass

        return result

    def classify_fact(self, text: str) -> tuple[Layer, str, float]:
        from storytelling_bot import langfuse_ctx
        system = langfuse_ctx.get_prompt("classify_fact", _CLASSIFY_SYSTEM)
        raw = self._call(system, f'Classify this text:\n"{text}"', "classify_fact")
        try:
            # Strip markdown fences if present
            clean = re.sub(r"```[a-z]*\n?", "", raw).strip().rstrip("`").strip()
            data = json.loads(clean)
            layer = Layer(int(data["layer"]))
            subcat = str(data["subcategory"])
            # Validate subcategory exists
            valid_subs = SUBCATEGORIES.get(layer, ())
            if subcat not in valid_subs:
                subcat = valid_subs[0] if valid_subs else subcat
            confidence = float(data.get("confidence", 0.7))
            return layer, subcat, confidence
        except Exception as e:
            log.warning("classify_fact parse error: %s — raw: %s", e, raw[:100])
            # Fallback to mock
            from storytelling_bot.llm.mock import MockClient
            return MockClient().classify_fact(text)

    def synthesize_layer(self, layer: Layer, facts: list[Fact]) -> str:
        if not facts:
            return "(нет данных)"
        from storytelling_bot import langfuse_ctx
        from storytelling_bot.schema import LAYER_LABEL
        system = langfuse_ctx.get_prompt("synthesize_layer", _SYNTHESIZE_SYSTEM)
        facts_text = "\n".join(f"- [{f.flag.value}] {f.text} [src: {f.source_url}]" for f in facts)
        prompt = f"Layer: {LAYER_LABEL[layer]}\n\nFacts:\n{facts_text}\n\nSynthesize a narrative paragraph."
        return self._call(system, prompt, "synthesize_layer", max_tokens=512)

    def judge_red_flag(self, text: str) -> tuple[str, float] | None:
        from storytelling_bot import langfuse_ctx
        system = langfuse_ctx.get_prompt("judge_red_flag", _JUDGE_SYSTEM)
        raw = self._call(system, f'Evaluate for red flags:\n"{text}"', "judge_red_flag")
        if raw.strip().lower() in ("null", "none", "{}"):
            return None
        try:
            clean = re.sub(r"```[a-z]*\n?", "", raw).strip().rstrip("`").strip()
            if clean.lower() == "null":
                return None
            data = json.loads(clean)
            cat = str(data["category"])
            conf = float(data.get("confidence", 0.8))
            # Enforce: hard needs ≥0.85, else downgrade to soft
            if cat.startswith("hard:") and conf < 0.85:
                soft_name = cat[5:]  # strip "hard:"
                cat = f"soft:{soft_name}"
            return cat, conf
        except Exception as e:
            log.warning("judge_red_flag parse error: %s — raw: %s", e, raw[:100])
            return None

    def classify_green(self, text: str) -> bool:
        # Use mock heuristic for green classification (less critical path)
        from storytelling_bot.llm.mock import MockClient
        return MockClient().classify_green(text)

    def embed(self, texts: list[str]) -> list[list[float]]:
        voyage_key = os.environ.get("VOYAGE_API_KEY")
        if voyage_key:
            try:
                import voyageai
                vc = voyageai.Client(api_key=voyage_key)
                result = vc.embed(texts, model="voyage-3", input_type="document")
                return result.embeddings
            except Exception as e:
                log.warning("voyage-ai embed failed: %s — using hash fallback", e)
        from storytelling_bot.llm.mock import MockClient
        return MockClient().embed(texts)
