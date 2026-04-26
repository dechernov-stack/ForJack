# План работ для Claude Code

> **Аудитория этого документа — Claude Code**, запущенный на внешней машине, в этой папке.  
> Прочитай этот файл целиком, потом начни выполнять задачи строго по порядку.  
> После каждой задачи — `git add . && git commit -m "<task-N>: <subject>"`.  
> Если задача неоднозначна — задай ОДИН уточняющий вопрос аналитику и подожди ответа.

---

## Контекст

В этой папке лежит рабочий прототип `storytelling_bot.py` (монофайл, моки вместо API). Цель — превратить его в production-репо: модульная структура, реальные источники, тесты, Docker, прогон на новой компании. Архитектура — в `architecture.md`. Не отступай от 8-слойной модели и red-flags taxonomy без согласования.

**Принципы, которые нельзя нарушать:**

- **Provenance 100%.** Каждый факт в Diamond-слое должен иметь `source_url` + `source_hash` + `captured_at`. Никогда не генерируй факты без подкрепления цитатой в Silver.
- **Human-in-the-loop.** `decision = "terminate"` никогда не уходит в action автоматически. Отдельный флаг `human_approval_required = True`.
- **Hard vs soft flags.** Hard — детерминированные правила (sanctions/criminal/SEC), soft — LLM-judge с обязательной двойной валидацией.
- **Vendor-agnostic LLM.** LLM-вызовы в одном модуле `src/storytelling_bot/llm/`, через интерфейс `LLMClient`. Дефолт — Claude (`anthropic`), но переключение на другой провайдер — одной env-переменной.

---

## Задачи

### Task 1 — Bootstrap репозитория и среды

1. Запусти `git init`, добавь `.gitignore` (уже есть). Сделай первый коммит из текущего состояния: `chore: bootstrap from prototype`.
2. Создай `.env` из `.env.example`, попроси пользователя заполнить как минимум `ANTHROPIC_API_KEY` и `TAVILY_API_KEY` (остальные опционально).
3. Создай виртуальное окружение и установи зависимости:
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -U pip
   pip install -r requirements.txt
   python -m playwright install chromium
   ```
4. Проверь, что прототип запускается: `python storytelling_bot.py --entity accumulator --output reports/demo.json --export-html reports/demo.html`.
5. Прогон тестов: `pytest tests/ -v`. Все 10 должны быть зелёными.
6. Коммит: `chore: env bootstrapped, baseline tests green`.

**DoD:** прототип работает в новой среде, тесты зелёные, `.env` сконфигурирован.

---

### Task 2 — Разнести монофайл на модули

Переноси код из `storytelling_bot.py` в модульную структуру `src/storytelling_bot/`. Не меняй поведение — только декомпозируй.

```
src/storytelling_bot/
├── __init__.py
├── __main__.py            # CLI (typer вместо argparse)
├── schema.py              # Layer, Fact, State, SourceType, Flag, SUBCATEGORIES
├── graph.py               # build_graph()
├── llm/
│   ├── __init__.py
│   ├── base.py            # LLMClient (Protocol)
│   ├── claude.py          # AnthropicClient
│   └── mock.py            # MockClient (детерминированная эвристика — текущая)
├── collectors/
│   ├── __init__.py
│   ├── base.py            # Collector (Protocol)
│   ├── interview.py
│   ├── research.py
│   ├── archival.py
│   └── offline.py
├── nodes/
│   ├── __init__.py
│   ├── classifier.py
│   ├── flag_detector.py
│   ├── synthesizer.py
│   ├── timeline.py
│   ├── decision_engine.py
│   ├── metrics.py
│   └── reporter.py
├── storage/
│   ├── __init__.py
│   ├── memory.py          # in-memory store для тестов
│   └── postgres.py        # production store
└── dashboard.py           # генерация HTML
```

**Указания:**
- LangGraph: используй `from langgraph.graph import StateGraph, END`. State — `pydantic.BaseModel` (а не dataclass).
- `__main__.py` строит CLI на typer с теми же командами: `run`, `list`, `add-fact`, `diff`, `watch`, `export-html`. Сохраняй обратную совместимость флагов.
- Корневой `storytelling_bot.py` оставь как тонкий shim, который импортирует из `src/storytelling_bot/__main__.py` (для существующих тестов).
- Перепиши тесты под новые импорты, добавь `tests/test_classifier.py`, `tests/test_collectors_mock.py`.

**DoD:** `pytest tests/ -v` зелёный, `python -m storytelling_bot run --entity accumulator` работает, граф рендерится из LangGraph.

Коммит: `refactor: modularize into src/storytelling_bot/`.

---

### Task 3 — Заменить mock-LLM на Claude

В `src/storytelling_bot/llm/claude.py` реализуй `AnthropicClient` с тремя методами (соответствуют сигнатурам в `mock.py`):

```python
class AnthropicClient(LLMClient):
    async def classify_fact(self, text: str) -> tuple[Layer, str, float]: ...
    async def synthesize_layer(self, layer: Layer, facts: list[Fact]) -> str: ...
    async def judge_red_flag(self, text: str) -> Optional[tuple[str, float]]: ...
```

**Жёсткие требования:**

1. Используй `anthropic` SDK с моделью `claude-sonnet-4-6` (env: `ANTHROPIC_MODEL`).
2. Few-shot для `classify_fact` строй из `architecture.md` + 3-5 примеров каждого слоя из исходного `DE.pdf` (попроси пользователя положить `DE.pdf` рядом с репо).
3. `synthesize_layer` — строгая инструкция: «никогда не добавлять факты, не присутствующие в переданном списке. Если факта нет — пиши `(нет данных)`».
4. `judge_red_flag` — system prompt задаёт hard/soft taxonomy из `architecture.md`. Возвращает либо `("hard:<cat>", confidence)`, либо `("soft:<cat>", confidence)`, либо `None`. Confidence ≥0.85 для hard, иначе понизь до soft.
5. Все вызовы оборачивай в `langfuse` трейсинг (если `LANGFUSE_PUBLIC_KEY` задан).
6. Добавь faithfulness-eval: тест, который для случайной выборки 5 синтезов проверяет, что каждое утверждение покрыто хотя бы одной цитатой.

**DoD:** `LLM_PROVIDER=anthropic python -m storytelling_bot run --entity accumulator` отрабатывает без ошибок, faithfulness-test зелёный, токены логируются.

Коммит: `feat(llm): real Claude classifier, synthesizer, red-flag judge`.

---

### Task 4 — ResearchCollector на Tavily + GDELT + SEC EDGAR

В `src/storytelling_bot/collectors/research.py`:

1. **Tavily.** Использовать `tavily-python`. Запрос — имя сущности + alias-список. Для каждой компании автоматически собирать alias из Crunchbase fallback (если ключ есть), иначе — дёрнуть Wikipedia API.
2. **GDELT.** REST API `gdeltproject.org/api/v2/doc/doc?query=...&format=json`. Брать последние 30 дней по дефолту, передавать tone-метаданные в Silver (для будущих soft-флагов).
3. **SEC EDGAR.** `sec-edgar-downloader` для тикеров/CIK. Парсить `13F`, `D`, `10-K`, `8-K` для регуляторного следа. Для частных компаний — пропускать.
4. **Дедупликация** на уровне Bronze: сохранять только если SHA-256 сырья не встречался.
5. **Rate-limit** через `tenacity` retry-with-backoff.
6. Каждый коллектор пишет в `data/bronze/<entity>/<source>/<sha256>.json` + Silver-запись.

**Тесты:** `respx`-моки на httpx, проверяющие что:
- Tavily-ответ нормализуется в `Fact` со всеми полями.
- При 429 повторяется с backoff.
- Дубль-сырьё не пишется.

**DoD:** `python -m storytelling_bot run --entity stripe --provider anthropic` собирает реальные факты по Stripe, в Silver появляется ≥30 записей.

Коммит: `feat(collectors): research collector via Tavily/GDELT/SEC`.

---

### Task 5 — InterviewCollector через YouTube + Whisper

1. `yt-dlp` качает аудио по поисковому запросу `<entity_name> founder interview`. Брать топ-5 за последний год, длительность 10–90 минут.
2. `faster-whisper` (`base` или `small` модель) транскрибирует. Если `WHISPER_DEVICE=cuda`, использовать GPU.
3. Опционально `pyannote.audio` для диаризации — нарезать на реплики и оставлять только реплики, где спикер совпадает с фаундером (по голосовому отпечатку из ≥3 эталонных интервью, если доступны).
4. Транскрипт нарезать на параграфы по 200–400 слов и каждый параграф — отдельный сырьевой фрагмент.

**Установка faster-whisper отдельная** (CPU достаточно для прототипа):
```bash
pip install faster-whisper
```

**DoD:** `python -m storytelling_bot collect-interviews --entity stripe --limit 3` сохраняет ≥3 транскриптов в `data/bronze/stripe/online_interview/`.

Коммит: `feat(collectors): YouTube + Whisper interview collector`.

---

### Task 6 — ArchivalCollector через Wayback Machine

`waybackpack` или прямой запрос к `https://archive.org/wayback/available`. Для каждой сущности — снапшоты сайта компании за 5 опорных дат (год основания, +1, +3, +5, current). Diff-сравнение между снапшотами идёт в `Silver` как метаданные «эволюция продукта/команды».

**DoD:** для Stripe (founded 2010) собрано ≥5 снапшотов; в Silver появляется запись `evolution_diff_2010_to_2015`.

Коммит: `feat(collectors): archival via Wayback Machine`.

---

### Task 7 — FlagDetector: hard-rules через OpenSanctions

`src/storytelling_bot/nodes/flag_detector.py`:

1. Перед LLM-judge делается детерминированная проверка:
   - **OpenSanctions** REST: `https://api.opensanctions.org/match/default` (без ключа, freemium).
   - **OFAC SDN** через CSV (https://www.treasury.gov/ofac/downloads/sdn.csv).
   - **EU consolidated list**.
2. Если матч ≥0.85 — `flag = RED`, `red_flag_category = "hard:sanctions"`, `confidence = матч-скор`.
3. Только если hard-rules не сработали — отправляется в LLM-judge для soft-флагов.

**DoD:** тест с подставной персоной из тестового SDN-списка → `terminate`. Реальный прогон по Anthropic → 0 hard, 0 soft.

Коммит: `feat(flag-detector): OpenSanctions + OFAC integration`.

---

### Task 8 — Хранилища: Postgres + MinIO + Qdrant

1. SQLAlchemy + Alembic-миграции в `src/storytelling_bot/storage/postgres.py`. Схема:
   - `entities (id, kind, name, watchlist_added_at)`
   - `bronze_chunks (id, entity_id, source_type, sha256, captured_at, raw_data jsonb)`
   - `silver_chunks (id, bronze_id, normalized_text, source_url, language, tone)`
   - `gold_facts (id, silver_id, entity_id, layer, subcategory, flag, red_flag_category, confidence, event_date)`
   - `decisions (id, entity_id, recommendation, rationale, evaluated_at, hard_count, soft_count, green_in_key)`
2. MinIO/S3 — Bronze raw blobs (HTML, audio).
3. Qdrant — векторный индекс fact'ов по `gold_facts.normalized_text`, метаданные `entity_id, layer, flag`. Embeddings — `voyage-2` или `text-embedding-3-large`.
4. Запустить `docker compose up -d postgres minio qdrant`, прогнать миграции, перенаправить storage-слой с in-memory на Postgres.

**DoD:** `python -m storytelling_bot run --entity stripe` пишет в Postgres + MinIO + Qdrant; повторный запуск не дублирует факты (idempotency).

Коммит: `feat(storage): Postgres + MinIO + Qdrant production store`.

---

### Task 9 — EventWatcher с алертами в Slack

`src/storytelling_bot/nodes/event_watcher.py`:

1. Цикл 5 минут (или Temporal task) опрашивает RSS активных сущностей + GDELT live + (если ключ) X firehose.
2. Найденные новые упоминания идут только в слои 5–8 (incremental).
3. Если у сущности `decision` изменился (например `watch → pause`) — push в Slack по `SLACK_WEBHOOK_URL` с разметкой:
   ```
   ⚠ STRIPE: decision watch → pause
   причина: 1 hard:sec_enforcement (confidence 0.91)
   источник: <link>
   ```
4. Для red-flag c hard-категорией — алерт сразу, без ожидания пересчёта decision.

**Тест:** мок RSS-фид с заранее подставленным sanctions-кейсом → проверка что webhook вызвался.

**DoD:** `python -m storytelling_bot watch --entity stripe --interval 300` стабильно работает 30 минут без сбоев, на тестовом подложенном «инциденте» алерт уходит в Slack за <30 сек.

Коммит: `feat(event-watcher): RSS/GDELT live + Slack alerts`.

---

### Task 10 — Прогон на новой реальной компании

Цель — продемонстрировать end-to-end на компании, которой не было в моках. **Используй один из вариантов** (выбери по ситуации с ключами):

**Вариант A — Anthropic (своя компания пользователя):** `python -m storytelling_bot run --entity anthropic --output reports/anthropic.json --export-html reports/anthropic.html`

**Вариант B — Stripe (классический unicorn):** `python -m storytelling_bot run --entity stripe --output reports/stripe.json --export-html reports/stripe.html`

**Вариант C — Theranos (для проверки red-flags pipeline):** должен прийти к решению `terminate` благодаря hard:fraud в архивах.

Перед прогоном:
1. Добавь сущность в `data/watchlist.json`.
2. Подложи известные алиасы (Anthropic ↔ "Anthropic PBC").
3. Запусти полный пайплайн.
4. Открой dashboard.html, проверь:
   - Coverage ≥40% (для известных компаний это нормальный таргет на realtime-сборе).
   - У всех фактов есть `source_url`.
   - Decision выглядит правдоподобно.
5. Сделай audit-выборку: 20 случайных фактов → проверь что каждый соответствует своему source_url (sanity-check).

**DoD:** есть `reports/<entity>.json`, `reports/<entity>.html`, `audit/<entity>_sample.csv` с пометками pass/fail аналитика; все 20 фактов из аудита pass.

Коммит: `chore: e2e run on <entity>, audit attached`.

---

### Task 11 — CI и git push

1. Добавь `.github/workflows/test.yml`: ruff lint + pytest на каждом push/PR.
2. README — обнови раздел Quickstart под новую структуру (`python -m storytelling_bot run`).
3. `git remote add origin <url-от-пользователя>`, `git push -u origin main`.
4. Если репо приватный — попроси у пользователя GitHub-токен или GH CLI auth.

**DoD:** репо в GitHub, CI зелёный, ссылка отдана пользователю.

Коммит: `ci: add ruff + pytest workflow`.

---

### Task 12 — Что отдать аналитику (handoff)

Сгенерируй `HANDOFF.md` с разделами:

- Что работает (короткий список фич).
- Известные ограничения (например, LinkedIn не подключён — нужен Sales Navigator API).
- Стоимость одного прогона по компании в токенах Claude (среднее по 5 прогонам).
- 3 наиболее тонких места, где нужна человеческая валидация.
- Куда смотреть при инциденте (Langfuse-трейсы, postgres `decisions` table).

---

## Условия остановки и эскалации

- Если LLM возвращает невалидный JSON ≥3 раз подряд — switch на `mock` LLM client и эскалировать аналитику.
- Если стоимость прогона по компании превышает $5 — pause и сообщить.
- Если в Slack ушёл alert типа `terminate` — никаких дополнительных действий не делать; только убедиться, что человек получил уведомление.
- Любой merge в main без зелёного CI — запрещён.

## Полезные команды (cheatsheet)

```bash
# полный прогон + дашборд
python -m storytelling_bot run --entity stripe --output reports/stripe.json --export-html reports/stripe.html

# offline-факт со встречи
python -m storytelling_bot add-fact --entity stripe \
    --text "Со встречи 2026-04-26: …" \
    --source offline_interview \
    --url internal://meet/2026-04-26

# diff между двумя прогонами
python -m storytelling_bot diff reports/stripe-prev.json reports/stripe.json

# watch-режим
python -m storytelling_bot watch --entity stripe --interval 300

# тесты
pytest tests/ -v

# lint
ruff check src/ tests/
```
