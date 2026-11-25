"""Unit tests for feedback weights, decay, bounds, and briefing ranking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from techradar.feedback.weights import (
    apply_signal,
    bounded,
    effective,
    is_favourite,
    pick_outside_usual,
    score,
)

NOW = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)


@dataclass
class CandidateStub:
    id: int
    topic: str
    score: float
    exam_tags: list[str] = field(default_factory=list)


def test_bounds_and_floor():
    """Verify bounds [0.2, 2.0] and topic-specific floors."""
    assert bounded(2.3) == 2.0
    assert bounded(0.1) == 0.2
    assert bounded(0.5, floor=0.8) == 0.8


def test_fading_half_life():
    """Verify exponential decay towards 1.0 with 60-day half-life."""
    assert effective(2.0, 60) == pytest.approx(1.5)
    assert effective(0.5, 120) == pytest.approx(0.875)


def test_score_product():
    """Score is product of relevance, topic weight and source weight."""
    assert score(0.8, 1.5, 1.2) == pytest.approx(0.8 * 1.5 * 1.2)


def test_outside_usual_slot_keeps_exam_items():
    """At least 1 outside-usual item is included without replacing exam-tagged ones."""
    weights = {"ai": 1.5, "crypto": 1.2, "polity": 1.3}

    # 10 chosen favorites
    chosen = [
        CandidateStub(id=1, topic="ai", score=0.95, exam_tags=["gate"]),
        CandidateStub(id=2, topic="ai", score=0.90, exam_tags=["gate"]),
        CandidateStub(id=3, topic="crypto", score=0.85),
        CandidateStub(id=4, topic="polity", score=0.80),
        CandidateStub(id=5, topic="ai", score=0.75),
        CandidateStub(id=6, topic="crypto", score=0.70),
        CandidateStub(id=7, topic="polity", score=0.65),
        CandidateStub(id=8, topic="ai", score=0.60),
        CandidateStub(id=9, topic="crypto", score=0.55),
        CandidateStub(id=10, topic="polity", score=0.50),  # lowest non-exam score
    ]
    assert all(is_favourite(c, weights) for c in chosen)

    # 10 extra candidates, some outside usual
    candidates = chosen + [
        CandidateStub(id=11, topic="biology", score=0.45),  # not in weights -> outside usual
        CandidateStub(id=12, topic="history", score=0.40),
    ]

    out = pick_outside_usual(candidates, chosen, weights, share=0.1)
    assert len(out) == 10
    # At least 1 outside usual
    assert sum(not is_favourite(c, weights) for c in out) >= 1
    # All exam items from chosen must still be in out
    for c in chosen:
        if c.exam_tags:
            assert c in out


class FakeWeightsSession:
    def __init__(self) -> None:
        self.weights: dict[tuple[str, str], Any] = {}
        self.logs: list[Any] = []

    def add(self, obj: Any) -> None:
        if hasattr(obj, "kind") and hasattr(obj, "key") and hasattr(obj, "value"):
            self.weights[(obj.kind, obj.key)] = obj
        else:
            self.logs.append(obj)

    async def flush(self) -> None:
        for idx, log in enumerate(self.logs, 1):
            if getattr(log, "id", None) is None:
                log.id = idx

    async def execute(self, stmt: Any) -> Any:
        class Res:
            def __init__(self, val: Any) -> None:
                self.val = val

            def scalar_one_or_none(self) -> Any:
                return self.val

        # look up from weights
        sql = str(stmt).lower()
        if "topic" in sql:
            # find key
            for (k, _key), row in self.weights.items():
                if k == "topic":
                    return Res(row)
        return Res(None)


async def test_apply_signal_exam_topic_floor():
    """Applying negative delta to exam topic respects 0.8 floor."""
    session = FakeWeightsSession()
    # Apply negative signal repeatedly
    for _ in range(5):
        await apply_signal(
            session,
            topics=["entity:polity"],
            source=None,
            delta=-0.1,
            exam_topic=True,
            now=NOW,
        )
    row = session.weights.get(("topic", "entity:polity"))
    assert row is not None
    assert row.value >= 0.8


# --- Phase 11 Task 4: the weights reach the briefing's ranking ---------------------------


def _story(cid: str, section: Any, rel: float, topics: list[str], exam: bool = False) -> Any:
    from techradar.briefing.compose import StoryCandidate

    return StoryCandidate(
        cluster_id=cid,
        title=f"t{cid}",
        section=section,
        relevance=rel,
        topic_keys=topics,
        exam_tags=["gate"] if exam else [],
    )


def test_select_items_sorts_by_learned_score_not_relevance():
    from techradar.briefing.compose import select_items
    from techradar.schemas.pipeline import Section

    liked = _story("1", Section.TECH, 0.5, ["entity:ai"])
    disliked = _story("2", Section.WORLD, 0.9, ["entity:crypto"])
    weights = {"entity:ai": 2.0, "entity:crypto": 0.2}
    out = select_items([disliked, liked], frozenset(), weights=weights)
    assert [c.cluster_id for c in out] == ["1", "2"]  # 0.5*2.0 beats 0.9*0.2


def test_select_items_without_weights_keeps_relevance_order():
    from techradar.briefing.compose import select_items
    from techradar.schemas.pipeline import Section

    a = _story("1", Section.TECH, 0.5, ["entity:ai"])
    b = _story("2", Section.WORLD, 0.9, ["entity:crypto"])
    assert [c.cluster_id for c in select_items([a, b], frozenset())] == ["2", "1"]


def test_select_items_keeps_an_outside_usual_story_and_every_exam_story():
    from techradar.briefing.compose import select_items
    from techradar.schemas.pipeline import Section

    fav = {"entity:ai": 1.5}
    chosen = [
        _story(
            str(i), Section.TECH if i < 3 else Section.WORLD, 0.9 - i / 100, ["entity:ai"], i == 0
        )
        for i in range(6)
    ]
    outside = _story("99", Section.SCIENCE, 0.1, ["entity:bio"])
    out = select_items([*chosen, outside], frozenset(), per_section=3, max_items=6, weights=fav)
    assert "99" in [c.cluster_id for c in out]
    assert "0" in [c.cluster_id for c in out]  # the exam story stays


@pytest.mark.db
async def test_exam_topic_floor(session):
    from sqlalchemy import select

    from techradar.db.models import ImprovementLog, Weight

    for _ in range(20):
        await apply_signal(
            session, topics=["entity:polity"], source=None, delta=-0.1, exam_topic=True, now=NOW
        )
    w = (await session.execute(select(Weight).where(Weight.key == "entity:polity"))).scalar_one()
    assert w.value == 0.8
    # a later signal without the exam flag keeps the floor
    await apply_signal(
        session, topics=["entity:polity"], source=None, delta=-0.1, exam_topic=False, now=NOW
    )
    await session.refresh(w)
    assert w.value == 0.8
    logged = (await session.execute(select(ImprovementLog))).scalars().all()
    assert len(logged) == 21 and all(r.automatic for r in logged)
