# Storytelling-Bot — Handoff Document

> Production-grade multi-agent pipeline that fills an 8-layer storytelling data lake on companies and founders, builds timelines, surfaces red flags, and emits a human-in-the-loop decision.

---

## Quick start

```bash
# 1. Start infrastructure (Postgres, MinIO, Qdrant, Langfuse)
docker compose up -d

# 2. Install package in editable mode
pip install -e ".[dev]"

# 3. Copy and fill secrets
cp .env.example .env   # set ANTHROPIC_API_KEY, TAVILY_API_KEY, etc.

# 4. Apply database migrations (first deploy or after schema changes)
alembic upgrade head

# 5. Run against a target
storyteller run --entity stripe

# 6. Run unit tests (fast, no external calls)
pytest --ignore=tests/test_faithfulness.py --ignore=tests/test_e2e.py
```

---

## Architecture overview

```
CLI (__main__.py)
  └─ LangGraph StateGraph (graph.py)
       ├─ node_collector       — runs all four collectors in parallel
       ├─ node_classifier      — LLM: assigns Layer + subcategory to each Fact
       ├─ node_flag_detector   — deterministic sanctions rules, then LLM judge
       ├─ node_timeline        — orders facts chronologically per layer
       ├─ node_synthesizer     — LLM: writes narrative for each layer
       ├─ node_metrics         — counts green/soft/hard flags
       ├─ node_decision_engine — rule-based: continue / pause / terminate
       └─ node_reporter        — emits JSON + Markdown report
```

All nodes receive and return `State` (Pydantic BaseModel).  
Nodes return `dict` patches; LangGraph merges them.

---

## Module map

| Path | Purpose |
|---|---|
| `src/storytelling_bot/schema.py` | `Layer`, `SourceType`, `Flag`, `Fact`, `State` data contracts |
| `src/storytelling_bot/graph.py` | LangGraph `StateGraph` wiring |
| `src/storytelling_bot/__main__.py` | Typer CLI entry point |
| `src/storytelling_bot/llm/base.py` | `LLMClient` Protocol |
| `src/storytelling_bot/llm/claude.py` | Claude implementation (via `anthropic` SDK) |
| `src/storytelling_bot/llm/mock.py` | Deterministic mock for CI (no API calls) |
| `src/storytelling_bot/collectors/research.py` | Tavily search + GDELT news + SEC EDGAR |
| `src/storytelling_bot/collectors/interview.py` | YouTube URLs → yt-dlp → faster-whisper (CPU, int8) |
| `src/storytelling_bot/collectors/archival.py` | Wayback Machine CDX → snapshot text |
| `src/storytelling_bot/collectors/offline.py` | Manual document upload stub |
| `src/storytelling_bot/collectors/base.py` | `DEMO_CORPUS` — pre-seeded facts for stripe / theranos |
| `src/storytelling_bot/sanctions/checker.py` | Keyword regex rules + OpenSanctions REST API |
| `src/storytelling_bot/nodes/flag_detector.py` | Sanctions-first, then LLM judge (hard ≥ 0.85 conf) |
| `src/storytelling_bot/nodes/decision_engine.py` | Hard flag → terminate, soft → pause, else → continue |
| `src/storytelling_bot/storage/postgres.py` | SQLAlchemy 2.0 Core — `facts` + `decisions` tables |
| `src/storytelling_bot/storage/minio_store.py` | boto3 S3-compatible Bronze/Silver file store |
| `src/storytelling_bot/storage/vector_store.py` | Qdrant — `upsert_fact`, `search`, `count` |
| `src/storytelling_bot/watcher/event_watcher.py` | RSS + GDELT polling; Slack webhook alerts |
| `src/storytelling_bot/dashboard.py` | Rich terminal dashboard (live metrics) |

---

## Data lake layers

| Layer | Bronze | Silver | Gold | Diamond |
|---|---|---|---|---|
| Storage | MinIO `bronze/` | MinIO `silver/` | Postgres `facts` | Qdrant `facts` |
| Format | Raw JSON (SHA-256 dedup) | Normalised JSON with provenance | Typed `Fact` rows | Embedded vectors |

Every `Fact` carries: `entity_id`, `layer`, `subcategory`, `source_type`, `source_url`, `source_hash`, `captured_at`, `text`, `flag`, `confidence`, `red_flag_category`.

---

## Flag system

### Hard flags (deterministic — no LLM)

| Category | Keywords |
|---|---|
| `hard:sanctions` | OFAC, SDN list, EU sanctions, UN sanctions … |
| `hard:criminal` | criminal indictment, felony conviction … |
| `hard:sec_enforcement` | SEC enforcement action, consent decree … |
| `hard:fraud` | Ponzi scheme, confirmed fraud, investor fraud … |
| `hard:data_breach_fine` | GDPR fine, CCPA fine, ICO fine … |

Source: `sanctions/checker.py` → `_HARD_PATTERNS`

### Soft flags (LLM judge, conf ≥ 0.85)

High-confidence LLM output that does not match a hard keyword; results in `decision = "pause"` for human review.

---

## Decision engine logic

```
any hard flag  → terminate   (never auto-acts; human approval required = True)
any soft flag  → pause       (human approval required = True)
else           → continue
```

`human_approval_required` is **always** `True`; the pipeline never self-executes termination.

---

## LLM switching

Set `LLM_PROVIDER` env var:

| Value | Implementation |
|---|---|
| `anthropic` (default) | `llm/claude.py` — claude-opus-4-7 |
| `mock` | `llm/mock.py` — deterministic, no API key needed |

Add a new provider by implementing the `LLMClient` Protocol in `llm/base.py`.

---

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | for live runs | — | Claude API |
| `TAVILY_API_KEY` | for live runs | — | Web search |
| `LLM_PROVIDER` | no | `anthropic` | Switch LLM backend |
| `POSTGRES_URL` | no | `postgresql://...` | Postgres DSN |
| `MINIO_ENDPOINT` | no | `localhost:9000` | MinIO / S3 |
| `MINIO_ACCESS_KEY` | no | `minioadmin` | MinIO credentials |
| `MINIO_SECRET_KEY` | no | `minioadmin` | MinIO credentials |
| `QDRANT_HOST` | no | `localhost` | Qdrant host |
| `LANGFUSE_PUBLIC_KEY` | no | — | Tracing (optional) |
| `LANGFUSE_SECRET_KEY` | no | — | Tracing (optional) |
| `SLACK_WEBHOOK_URL` | no | — | EventWatcher alerts |
| `OPENSANCTIONS_API_KEY` | no | — | OpenSanctions REST |

---

## Running tests

```bash
# Fast unit tests (mock LLM, no external services)
LLM_PROVIDER=mock pytest --ignore=tests/test_faithfulness.py --ignore=tests/test_e2e.py -v

# Faithfulness tests (require ANTHROPIC_API_KEY)
pytest tests/test_faithfulness.py

# End-to-end (require ANTHROPIC_API_KEY + network)
pytest tests/test_e2e.py
```

CI runs unit tests on every push (Python 3.11 + 3.13).  
Faithfulness job runs on `main` push only (see `.github/workflows/ci.yml`).

---

## Infrastructure (docker-compose.yml)

| Service | Port | Purpose |
|---|---|---|
| `postgres` | 5432 | Main Postgres for facts + decisions |
| `minio` | 9000 / 9001 | Bronze/Silver object store (S3-compatible) |
| `qdrant` | 6333 | Vector store |
| `langfuse-db` | internal | Langfuse Postgres |
| `langfuse` | 3000 | Observability UI (`http://localhost:3000`) |

Default Langfuse keys (local dev only):  
`pk-lf-local-dev` / `sk-lf-local-dev`

---

## Commit history

| Commit | Task |
|---|---|
| `c32940a` | Initial import — prototype monolith |
| `efe56f3` | Modularise into `src/storytelling_bot/` |
| `a7b4c77` | Real Claude classifier, synthesizer, red-flag judge |
| `9d082da` | Task 4 — ResearchCollector: Tavily, GDELT, SEC EDGAR |
| `80a1a5e` | Task 5 — InterviewCollector: YouTube + faster-whisper |
| `40a6ef1` | Task 6 — ArchivalCollector: Wayback Machine CDX |
| `ebf5081` | Task 7 — FlagDetector: sanctions rules + OpenSanctions |
| `053af38` | Task 8 — Storage: Postgres, MinIO, Qdrant, Langfuse |
| `7ca2f08` | Task 9 — EventWatcher: RSS + GDELT + Slack |
| `70d5455` | Task 10 — E2E: Anthropic (target) + Theranos (regression) |
| `bdc4bed` | Task 11 — CI workflow + ruff clean |

---

## Known limitations and next steps

- **SEC EDGAR**: uses EFTS search (free), not full filing download. `sec-edgar-downloader` import was removed; add back if full 10-K/10-Q text is needed.
- **YouTube throttling**: yt-dlp cookies may be needed for age-gated or high-traffic periods. Pass `--cookies-from-browser` via `YDL_OPTS`.
- **Wayback Machine**: CDX API rate-limits aggressively. Add `Retry-After` header parsing if hitting 429s in production.
- **Offline collector** (`collectors/offline.py`): stub only — wire up a file-upload endpoint or S3 trigger.
- **LinkedIn / Crunchbase**: Playwright stub exists in base DEMO_CORPUS. Real scraping requires authenticated session management.
- **Vector embeddings**: `VectorStore` expects pre-computed 1536-d vectors. Add an embedding node (e.g. `text-embedding-3-small`) between `node_classifier` and `node_flag_detector`.
- **Multi-entity runs**: CLI supports one entity per run. For batch runs, loop externally or add a `--entities` flag.
