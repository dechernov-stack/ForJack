# Архитектура (короткая выжимка)

> Полная версия — в `storytelling_bot_architecture.docx` рядом с этим репо. Этот файл — что нужно знать Claude Code, чтобы строить production-версию.

## 8-слойная модель сторителлинга

| № | Слой                                   | Подкатегории                                                                 |
|---|----------------------------------------|------------------------------------------------------------------------------|
| 1 | Founder Personal Story                 | Origin & Childhood · Values & Beliefs · Fears & Vulnerability · Dreams & Identity |
| 2 | Founder Professional Story             | Path to expertise · Founder role & motivation · Co-founder dynamics          |
| 3 | Community Culture, Values & Stories    | Attraction & Selection · Shared life · Investors & Partners                  |
| 4 | Community Professional Experience      | Expertise & Diversity · Growth & Transformation · Collective failure memory  |
| 5 | Clients Stories                        | Client's challenge & context · Moment of choice & trust · Conflict & honesty |
| 6 | Product & Business                     | Architecture · Philosophy of decisions · Evolution                           |
| 7 | Social Impact Vision                   | Vision of change · Contradictions & cost · Legacy                            |
| 8 | PEST Context                           | Historical moment · Market & technology · Policy & regulation                |

Каждый факт дополнительно классифицирован по 4 типам источников и одному из трёх флагов:

- **Источники:** `online_interview` · `offline_interview` · `online_research` · `archival`
- **Флаги:** 🟢 green (поддерживающий сигнал) · 🔴 red (тревожный сигнал) · ⚪ grey (информации нет)

## Граф агентов (LangGraph)

```
Orchestrator
  ├── InterviewCollector  (YouTube + Whisper, podcasts)
  ├── ResearchCollector   (Tavily, GDELT, SEC EDGAR, Crunchbase, X)
  ├── ArchivalCollector   (Wayback Machine, archive.org)
  └── OfflineIngest       (manual upload + OCR + Whisper)
        ↓
  LayerClassifier  +  EntityLinker
        ↓
  StorySynthesizer  +  TimelineBuilder
        ↓
  FlagDetector  (rules для hard, LLM-judge для soft)
        ↓
  DecisionEngine  →  continue | watch | pause | terminate
        ↓
  Reporter  (.docx, .pptx, HTML дашборд)

EventWatcher (RSS, GDELT live, X firehose) — резидентный, триггерит инкрементальные обновления
```

## Слои данных

| Слой        | Что лежит                                              | Технология                  |
|-------------|--------------------------------------------------------|------------------------------|
| **Bronze**  | Сырьё: HTML, аудио, PDF                                | MinIO/S3 + SHA-256 dedup     |
| **Silver**  | Нормализованные текстовые фрагменты + метаданные       | Postgres + jsonb             |
| **Gold**    | Классифицированные факты со связями                    | Postgres + Qdrant + Neo4j    |
| **Diamond** | Сторителлинг по 8 слоям + флаги + рекомендация         | Postgres + кэш HTML          |

## Red flags taxonomy

**Hard** (правила, low tolerance, триггер pause/terminate):
- `hard:sanctions` — OFAC / EU / UK / UN watchlists (OpenSanctions API)
- `hard:criminal` — уголовное преследование (PACER, court records)
- `hard:sec_enforcement` — SEC / FCA / ЦБ
- `hard:fraud` — подтверждённые случаи мошенничества, фиктивных банкротств
- `hard:data_breach_fine` — утечки с штрафом регулятора (GDPR, CCPA)

**Soft** (LLM-judge, требуют человеческой валидации):
- `soft:toxic_communication` — паттерны культа, угрозы сотрудникам
- `soft:exec_exodus` — ≥30% C-level ушло за 12 мес
- `soft:investor_lawsuit` — иски от предыдущих инвесторов
- `soft:deadpool_pattern` — серийный pivot без MVP
- `soft:reputation_crash` — Glassdoor/Trustpilot падение

## Decision matrix

| Решение         | Условие                                                                  |
|-----------------|--------------------------------------------------------------------------|
| 🟢 Continue     | 0 hard, ≤1 soft, ≥5 green в слоях 1, 2, 6                                |
| 🟡 Watch        | 0 hard, 2–3 soft ИЛИ <5 green в ключевых слоях                            |
| 🟠 Pause        | 1 hard ИЛИ ≥4 soft                                                        |
| 🔴 Terminate    | ≥2 hard ИЛИ 1 hard в sanctions/criminal с confidence ≥0.85                |

> **Бот выдаёт только рекомендацию.** Финальное решение принимает человек (старший аналитик; для terminate — обязательная юридическая валидация).

## Метрики качества (target)

- Coverage ≥85% (заполненные подкатегории)
- Freshness P50 ≤7 дн (слои 5–8), ≤30 дн (1–4)
- Flag precision ≥0.92 hard / ≥0.80 soft
- Recall ≥0.85
- Time-to-alert P95 ≤15 мин
- Citation rate = 100% (политика — никаких фактов без provenance)
- Hallucination rate ≤0.5% (audit-выборка)
