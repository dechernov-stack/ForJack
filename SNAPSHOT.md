# Storytelling-Bot — State Snapshot
> Generated: 2026-04-28. Read-only inspection: git, docker compose ps, grep, cat.

---

## 1. Статус 12 задач

| # | Статус | Коммит |
|---|---|---|
| 1 | **done** — схема `Layer/Fact/State`, `StrEnum Flag/SourceType`, `SUBCATEGORIES` | `efe56f3` refactor: modularise |
| 2 | **done** — `LLMClient` Protocol + `AnthropicClient` (3 метода + Langfuse trace) + `MockClient` | `a7b4c77` feat(llm) |
| 3 | **done** — LangGraph 8-node pipeline, `build_graph()`, `GraphWrapper` | `a7b4c77` |
| 4 | **done** — Tavily + GDELT + SEC EDGAR, Bronze/Silver FS + MinIO mirror, tenacity retry | `9d082da` |
| 5 | **done** — YouTube yt-dlp + faster-whisper CPU/int8, transcript chunking | `80a1a5e` |
| 6 | **done** — Wayback Machine CDX API, snapshot text extraction | `40a6ef1` |
| 7 | **done** — 5 hard-flag regex паттернов + OpenSanctions REST API | `ebf5081` |
| 8 | **done** — `PostgresStore`, `MinIOStore`, `VectorStore`, Langfuse в docker-compose | `053af38` |
| 9 | **done** — `EventWatcher` RSS + GDELT + Slack webhook, dedup по SHA | `70d5455` |
| 10 | **done** — E2E тесты: anthropic (watch), theranos (terminate / 16 hard flags) | `7ca2f08` |
| 11 | **done** — CI GitHub Actions (py3.11+3.13), ruff clean, deploy job | `bdc4bed` |
| 12 | **done** — HANDOFF.md | `0206e8e` |

---

## 2. Структура репо

```
src/storytelling_bot/
├── schema.py            # Layer, Fact, State, Flag, SourceType
├── graph.py             # LangGraph 8-node pipeline
├── __main__.py          # Typer CLI: run / list / add-fact / diff / watch / export-html
├── dashboard.py         # Rich terminal dashboard
├── llm/                 # base.py (Protocol), claude.py, mock.py
├── collectors/          # research.py, interview.py, archival.py, offline.py, base.py, lake.py
├── nodes/               # classifier, flag_detector, decision_engine, synthesizer,
│                        #   timeline, metrics, reporter
├── sanctions/           # checker.py (keyword rules + OpenSanctions)
├── storage/             # postgres.py, minio_store.py, vector_store.py, memory.py
└── watcher/             # event_watcher.py

tests/                   # 11 файлов, 96 тестов — все passing (mock LLM)
```

---

## 3. Инфраструктура

**Локально (Mac):** все сервисы подняты через docker-compose.
**VPS (185.207.66.186):** поднято вручную, nginx работает (порты 8080/8081).

| Сервис | Статус | Порты |
|---|---|---|
| postgres | healthy | 5432 |
| langfuse-db | healthy | 5433 |
| langfuse | up (v2, pinned) | 3000 |
| minio | healthy | 9000 / 9001 |
| qdrant | up (healthcheck unhealthy) | 6333 / 6334 |
| nginx | up | 8080 (Langfuse) / 8081 (MinIO) |

**Postgres:** таблицы `facts` и `decisions` — auto-DDL при первом запуске. Alembic отсутствует.

**MinIO:** бакеты `bronze` и `silver` созданы. На VPS заполнены после прогона stripe (GDELT, SEC, Wayback).

**Langfuse:** UI доступен, трейсы пусты — `LANGFUSE_HOST=http://localhost:3000` не работает из процесса вне Docker; нужно `http://langfuse:3000` или внешний хост.

**Qdrant:** коллекция `facts` создаётся лениво. Вектора не пишутся — нет embedding-ноды в графе.

**Neo4j, Redis:** не реализованы, только в requirements.txt.

---

## 4. .env — ключи (без значений)

| Ключ | Статус |
|---|---|
| `ANTHROPIC_API_KEY` | **set** |
| `ANTHROPIC_MODEL` | **set** (claude-sonnet-4-6) |
| `LLM_PROVIDER` | **unset** (дефолт: anthropic) |
| `TAVILY_API_KEY` | **set** |
| `CRUNCHBASE_API_KEY` | **unset** |
| `OPENSANCTIONS_API_KEY` | **unset** (API работает без ключа, но /entities/ возвращает 401) |
| `LANGFUSE_PUBLIC_KEY` | **set** (pk-lf-local-dev) |
| `LANGFUSE_SECRET_KEY` | **set** (на VPS — без pk-/sk- префикса, баг) |
| `LANGFUSE_HOST` | **set** (localhost:3000 — не работает из CLI) |
| `MINIO_ENDPOINT` | **unset** (дефолт: localhost:9000) |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | **unset** (дефолт: minioadmin) |
| `DATABASE_URL` | **set** |
| `QDRANT_URL` | **set** |
| `SLACK_WEBHOOK_URL` | **unset** |
| `WHISPER_DEVICE` / `WHISPER_MODEL` | **unset** (дефолт: CPU / tiny) |

---

## 5. LLM-слой

- **Провайдер по умолчанию:** `anthropic` — `get_llm_client()` читает `LLM_PROVIDER`
- **AnthropicClient** — 3 метода:
  - `classify_fact` — JSON-ответ с few-shot (16 примеров из DE.pdf), fallback на MockClient при парс-ошибке ✓
  - `synthesize_layer` — faithfulness system-промпт, max_tokens=512 ✓
  - `judge_red_flag` — hard/soft категории, conf≥0.85 для hard, иначе downgrade в soft ✓
  - `classify_green` — **делегирует в MockClient** (не реализован в AnthropicClient) ⚠️
- **Langfuse:** обёрнуты только вызовы `AnthropicClient._call()`. Collectors и storage — не трейсятся
- **Faithfulness-тест:** `tests/test_faithfulness.py` — запускается только на main-push с реальным ключом

---

## 6. Коллекторы

| Коллектор | Статус | Примечание |
|---|---|---|
| `ResearchCollector` | **реальный** | Tavily (если ключ), GDELT ✓, SEC EDGAR ✓. 14 тестов passing |
| `ArchivalCollector` | **реальный** | Wayback Machine CDX + snapshot fetch ✓ |
| `InterviewCollector` | **частичный** | yt-dlp + faster-whisper реализованы; `yt_dlp` не установлен на VPS → 0 chunks |
| `OfflineIngest` | **stub** | Читает `offline_overlay.json` + DEMO_CORPUS. Нет OCR, нет PDF |

DEMO_CORPUS заполнен для: `accumulator`, `stripe`, `theranos`.

---

## 7. FlagDetector

- **OpenSanctions:** подключён. Без API-ключа `/entities/` возвращает 401. Graceful деградация — None
- **OFAC SDN CSV:** не загружается — только keyword regex (5 паттернов)
- **Hard-паттерны:** sanctions, criminal, sec_enforcement, fraud, data_breach_fine
- **LLM-judge soft-флаги:** работает через `AnthropicClient.judge_red_flag()`
- **Тесты:** 15 шт. в `test_sanctions_checker.py` — все passing

---

## 8. Storage

**PostgresStore:**
- Таблицы: `facts`, `decisions` — auto-DDL, Alembic отсутствует
- `ON CONFLICT DO NOTHING` без уникального индекса — dedup фактически не работает ⚠️
- **Не вызывается из графа** — `node_reporter` пишет только JSON-файл ⚠️

**MinIOStore:**
- Работает — bronze/silver через `collectors/lake.py` (lazy singleton)
- Bronze = сырой JSON с SHA-256 dedup на уровне файловой системы

**VectorStore (Qdrant):**
- Реализован — `upsert_fact`, `search`, `count`
- **Не вызывается нигде в графе** — нет embedding-ноды, Qdrant пустой ⚠️

---

## 9. EventWatcher

- Реализован: RSS (feedparser) + GDELT polling, dedup по SHA256(url+date)
- Slack webhook: mock когда `SLACK_WEBHOOK_URL` не задан
- `feedparser` не установлен на VPS → RSS не работает, GDELT работает
- Тесты: mocked, passing

---

## 10. Реальные прогоны

| Entity | Decision | Facts | Метрики |
|---|---|---|---|
| `anthropic` | **watch** | 20 | coverage 16%, 0 green, 0 red, p50 freshness 392 дн. |
| `theranos` | **terminate** | 35 | coverage 24%, 19 red (16 hard), p50=0 |
| `stripe` | **watch** | ~41 | только VPS, без `--output` → не сохранён |

- Все прогоны с **mock LLM** (theranos — DEMO_CORPUS с hardcoded fraud-фактами)
- Стоимость в токенах: не измерялась (Langfuse не получает трейсы)
- `data/watchlist.json`: **не создан**

---

## 11. CI / Git

```
2811449 feat(deploy): auto-deploy to VPS on push to main via GitHub Actions SSH
588f940 feat(deploy): VPS deployment — nginx + systemd timer
0ecdc01 feat: wire MinIO uploads into all collectors via lake.py
a0c6e75 fix: pin langfuse to v2
47226a3 fix: guard TavilyClient is None
0206e8e task-12: HANDOFF.md
bdc4bed task-11: CI + ruff clean
7ca2f08 task-10: E2E Anthropic + Theranos
70d5455 task-9: EventWatcher
053af38 task-8: Storage + Langfuse
```

- Ветка: `main` (единственная)
- Remote: `github.com/dechernov-stack/ForJack` (публичное)
- CI: lint+test py3.11+3.13 ✓; deploy job — **GitHub Secrets не добавлены** → будет падать
- Faithfulness: gated на main-push с `ANTHROPIC_API_KEY` secret

---

## 12. Известные блокеры и открытые вопросы

| Проблема | Критичность |
|---|---|
| `PostgresStore` и `VectorStore` не вызываются из графа — данные не персистятся | **Высокая** |
| Нет embedding-ноды — Qdrant пустой, семантический поиск не работает | **Высокая** |
| `ON CONFLICT DO NOTHING` без уникального индекса — dedup в Postgres не работает | **Средняя** |
| Langfuse трейсы не идут (неверный HOST + пакет не установлен на VPS) | **Средняя** |
| OpenSanctions API 401 без ключа | **Средняя** |
| `classify_green` делегирует в MockClient даже при `LLM_PROVIDER=anthropic` | **Низкая** |
| OfflineIngest без OCR/PDF | **Низкая** |
| `storytelling_bot.py` монолит в корне конфликтует с `python3 -m` | **Низкая** (workaround: `storyteller` CLI) |
| GitHub Secrets не добавлены → deploy job падает | **Низкая** (VPS настраивается вручную пока) |

---

## TL;DR

**Что реально развёрнуто:** VPS (185.207.66.186) + Mac — Docker stack (Postgres, MinIO, Qdrant, Langfuse v2, nginx). MinIO заполнен (bronze/silver для stripe). Langfuse UI поднят, трейсы пусты.

**Этап:** все 12 задач формально закрыты. Критический gap: `PostgresStore` и `VectorStore` реализованы и протестированы изолированно, но **не подключены к пайплайну** — reporter пишет только JSON-файл, Qdrant пустой.

**Главные блокеры:** (1) нет персистенции в Postgres/Qdrant из графа, (2) нет embedding-ноды, (3) Langfuse не получает трейсы.

**Где нужен факт-чек:** реальный прогон с `LLM_PROVIDER=anthropic` не проводился; `classify_green` — mock; faithfulness-тест написан но не запускался в CI с реальным ключом.
