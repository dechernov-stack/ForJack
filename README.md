# Storytelling Data Lake Bot

Мульти-агентная система, наполняющая 8-слойное озеро данных по компаниям и фаундерам, строящая таймлайны и предупреждающая о red flags. Базируется на исходном фреймворке из `DE.pdf` (см. рядом).

> **Статус:** v0.1 — рабочий прототип на детерминированных моках. Готов к замене моков на реальные источники (см. `CLAUDE_TASKS.md`).

## Что внутри

| Файл                             | Назначение                                                                         |
|----------------------------------|------------------------------------------------------------------------------------|
| `storytelling_bot.py`            | Самодостаточный прототип: граф агентов, классификация, флаги, decision engine, HTML-дашборд |
| `dashboard.html`                 | Сгенерированный интерактивный дашборд (открой в браузере)                          |
| `CLAUDE_TASKS.md`                | **Пошаговый план для Claude Code** — превратить прототип в production-репо         |
| `PROMPT_FOR_CLAUDE.md`           | Готовый промпт, который копируется в Claude Code и запускает все задачи            |
| `architecture.md`                | Краткая выжимка архитектурного решения (8 слоёв, агенты, red flags, decision matrix) |
| `examples/accumulator_demo_report.json` | Пример выгрузки Diamond-слоя по компании Accumulator                          |
| `requirements.txt`, `pyproject.toml`, `.env.example`, `Dockerfile`, `docker-compose.yml` | Инфраструктура для production |
| `tests/`                         | Юнит-тесты (decision engine, классификатор, dedup)                                 |
| `src/storytelling_bot/`          | Заготовка модульной структуры (Claude Code добьёт по `CLAUDE_TASKS.md`)            |

## Quickstart (3 команды)

```bash
# Запустить прототип на canonical-корпусе Accumulator
python storytelling_bot.py --entity accumulator \
    --output report.json --export-html dashboard.html

# Открыть дашборд в браузере
open dashboard.html        # macOS
xdg-open dashboard.html    # Linux

# Список всех CLI-команд
python storytelling_bot.py --help
```

## Как работать аналитику

```bash
# Список сущностей в watchlist
python storytelling_bot.py --list

# Полный пересбор + дашборд
python storytelling_bot.py --entity accumulator \
    --output report.json --export-html dashboard.html

# Добавить факт от руки (offline ingest со встречи)
python storytelling_bot.py --entity accumulator \
    --add-fact "Расшифровка встречи 2026-04-26: фаундер подтвердил план B…" \
    --add-fact-source offline_interview \
    --add-fact-url internal://meeting/2026-04-26

# Сравнить с предыдущим запуском (что изменилось)
python storytelling_bot.py --diff prev_report.json report.json

# Watch-режим (мок event watcher)
python storytelling_bot.py --watch --entity accumulator --interval 60
```

## Дальше — превратить прототип в production-репо

Открой `CLAUDE_TASKS.md` и/или скопируй `PROMPT_FOR_CLAUDE.md` в Claude Code. Claude разберёт текущий монофайл на модули, заменит моки на реальные источники (Claude API, Tavily, SEC EDGAR, YouTube + Whisper, GDELT, OpenSanctions), напишет тесты и прогонит на новой сущности (например, Stripe).

## Лицензия / контекст

Внутренний инструмент для команды аналитиков. Финальное решение по компании всегда принимает человек — бот выдаёт только обоснованную рекомендацию и логирует всё для аудита.
