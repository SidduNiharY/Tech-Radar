"""The briefing stores its stories in `briefings.items`; `/v1/today` reads them back.

Phase 4 Task 2 (`briefing/compose.py: stores items in briefings.items`).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from techradar.api.routes.today import today_item
from techradar.briefing.compose import StoryCandidate, run_briefing
from techradar.db.models import Briefing
from techradar.schemas.pipeline import Section


class Session:
    def __init__(self) -> None:
        self.added: list[Any] = []

    async def execute(self, stmt: object) -> Any:
        class Result:
            def scalar_one_or_none(self) -> None:
                return None

            def scalars(self) -> list[Any]:  # Phase 11: no learned weights
                return []

        return Result()

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = 1


async def test_run_briefing_stores_items_the_today_route_can_read() -> None:
    story = StoryCandidate(
        cluster_id="c9",
        title="LangGraph 1.3 released",
        section=Section.TECH,
        exam_tags=["gate"],
        why="New API",
        how_it_affects_me="Upgrade the course code",
        domains={"blog.langchain.dev"},
        verified_headline=True,
    )
    session = Session()
    res = await run_briefing(
        session,  # type: ignore[arg-type]
        now=datetime(2026, 11, 22, 7, 0),
        owner_chat_id=1,
        candidates=[story],
    )
    assert res.items_count == 1
    [briefing] = [o for o in session.added if isinstance(o, Briefing)]
    assert briefing.date == date(2026, 11, 22)
    [stored] = briefing.items or []
    assert stored["domains"] == ["blog.langchain.dev"]  # JSON-safe (a set became a list)
    item = today_item(stored)
    assert item is not None
    assert (item.title, item.section, item.verified_headline) == (
        "LangGraph 1.3 released",
        Section.TECH,
        True,
    )
    assert item.four_questions.why == "New API"
    assert item.four_questions.how_it_affects_me == "Upgrade the course code"
