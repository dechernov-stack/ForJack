"""Collector Protocol + canonical demo corpus."""
from __future__ import annotations

from typing import Any, Dict, List, Protocol

from storytelling_bot.schema import SourceType, State

DEMO_CORPUS: Dict[str, List[Dict[str, Any]]] = {
    "accumulator": [
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
        {
            "source_type": SourceType.OFFLINE_INTERVIEW,
            "url": "internal://meetings/2026-04-12-accumulator-call",
            "captured_at": "2026-04-12",
            "text": "Внутренняя встреча: фаундер открыто признаёт, что у Accumulator нет публично известного CTO; технологическая команда формируется через нетворк Founders Forum.",
            "entity_focus": "accumulator",
        },
    ],
}


class Collector(Protocol):
    source_type: SourceType

    def collect(self, entity_id: str) -> List[Dict[str, Any]]: ...
