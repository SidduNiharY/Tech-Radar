"""Unit tests for pattern detection rules and candidate filtering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from techradar.db.models import PreferenceRule
from techradar.feedback.patterns import (
    Mode,
    StyleProposal,
    confusion_candidates,
    edit_candidates,
    find_patterns,
    frequency_candidates,
    mistakes_candidates,
    pairs_candidates,
    sequence_candidates,
    source_candidates,
    time_candidates,
)

NOW = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)


def skips(skip_count: int, of: int, topic: str = "crypto") -> list[dict[str, Any]]:
    """Helper creating a list of items with specified skip counts."""
    items: list[dict[str, Any]] = []
    for i in range(of):
        is_skip = i < skip_count
        items.append(
            {
                "id": i + 1,
                "topic": topic,
                "kind": "skip" if is_skip else "open",
            }
        )
    return items


def answers_followed_by(
    text: str,
    match_count: int,
    of: int,
    mode: str = "gate",
) -> list[dict[str, Any]]:
    """Helper creating answer follow-up sequence items."""
    items: list[dict[str, Any]] = []
    for i in range(of):
        txt = text if i < match_count else "ok thanks"
        items.append(
            {
                "id": i + 1,
                "mode": mode,
                "text": txt,
            }
        )
    return items


def edit(removed: list[str]) -> dict[str, Any]:
    """Helper creating mock edit item with removed sections."""
    return {
        "sections_removed": removed,
        "length_change": -50,
    }


def test_frequency_rule_needs_ten_items():
    """Frequency rule requires at least 10 items before proposing topic down-weighting."""
    assert frequency_candidates(skips(9, of=9)) == []
    cands = frequency_candidates(skips(8, of=10))
    assert len(cands) == 1
    assert cands[0].evidence.count == 8
    assert cands[0].evidence.total == 10
    assert cands[0].proposal.kind == "topic"


def test_sequence_rule_example_follow_ups():
    """Sequence rule proposes adding an example when user repeatedly asks for one."""
    cands = sequence_candidates(answers_followed_by("give me an example", 6, of=10, mode="gate"))
    assert len(cands) == 1
    c = cands[0]
    assert isinstance(c.proposal, StyleProposal)
    assert c.proposal.mode == Mode.GATE
    assert (c.proposal.field, c.proposal.value) == ("examples", "one")


def test_edit_rule_skip_section():
    """Edit rule proposes skip_section when user repeatedly deletes the same heading."""
    cands = edit_candidates([edit(removed=["Background"])] * 5)
    assert len(cands) == 1
    c = cands[0]
    assert isinstance(c.proposal, StyleProposal)
    assert (c.proposal.field, c.proposal.value) == ("skip_section", "Background")


def test_mistakes_candidates():
    """Repeated mistakes on same subject trigger focused_revision candidate."""
    mistakes = [
        {"id": 1, "subject": "Indian Polity - Fundamental Rights"},
        {"id": 2, "subject": "Indian Polity - Fundamental Rights"},
        {"id": 3, "subject": "Indian Polity - Fundamental Rights"},
    ]
    cands = mistakes_candidates(mistakes)
    assert len(cands) == 1
    assert cands[0].proposal.kind == "focused_revision"
    assert "Fundamental Rights" in cands[0].proposal.subject


def test_time_candidates_median():
    """Session durations map to nearest standard block minute (25, 45, 60)."""
    sessions = [{"id": i, "minutes": 42.0} for i in range(7)]
    cands = time_candidates(sessions)
    assert len(cands) == 1
    assert cands[0].proposal.field == "block_minutes"
    assert cands[0].proposal.value == "45"


def test_confusion_needs_five_pairwise_alike_asks():
    same = [(i, f"what is a repo rate {i}", [1.0, 0.0]) for i in range(1, 6)]
    cands = confusion_candidates(same)
    assert len(cands) == 1 and cands[0].proposal.kind == "foundation_page"
    assert cands[0].evidence.ids == [1, 2, 3, 4, 5] and cands[0].proposal.subject == "repo"
    assert confusion_candidates(same[:4]) == []
    mixed = [*same[:4], (9, "other", [0.0, 1.0])]
    assert confusion_candidates(mixed) == []


def test_source_rule_needs_five_negative_signals():
    rows = [{"id": i, "signal": "down", "source": "bad.example"} for i in range(1, 6)]
    cands = source_candidates(rows)
    assert len(cands) == 1 and cands[0].proposal.key == "source:bad.example"
    assert source_candidates(rows[:4]) == []


def test_pairs_rule_maps_variants_to_valid_style_rules():
    from techradar.feedback.rules import StyleRule

    rows = [{"id": i, "mode": "gate", "chosen": "a", "variant_a": "detailed"} for i in range(5)]
    c = pairs_candidates(rows)[0]
    assert c.evidence.table == "preference_pairs"
    StyleRule(mode=c.proposal.mode, field=c.proposal.field, value=c.proposal.value)  # valid


@pytest.mark.db
async def test_candidate_dropped_when_rule_active(session):
    from sqlalchemy import select

    from techradar.db.models import ActionLog, Edit

    for i in range(5):
        session.add(
            Edit(
                doc_path=f"n{i}.md",
                before_hash="a",
                after_hash="b",
                length_change=-10,
                sections_removed=["Background"],
                words_replaced=0,
                at=NOW,
            )
        )
    await session.flush()
    found = await find_patterns(session, now=NOW)
    edit_found = [c for c in found if c.kind == "edit"]
    assert len(edit_found) == 1 and edit_found[0].evidence.count == 5
    session.add(
        PreferenceRule(
            mode=None, field="skip_section", value="Background", evidence={}, status="active"
        )
    )
    await session.flush()
    assert [c for c in await find_patterns(session, now=NOW) if c.kind == "edit"] == []
    assert (await session.execute(select(ActionLog))).scalars().all() == []  # counting only


@pytest.mark.db
async def test_nightly_job_infers_skips_and_lowers_a_bad_source_once(session):
    from sqlalchemy import select

    from techradar.db.models import Feedback, ImprovementLog, Item, RawItem, Source, Weight
    from techradar.feedback.jobs import run_nightly_patterns

    src = Source(
        name="t-pat", url="https://t.example/f", host="t.example", section="tech", trust_tier="news"
    )
    session.add(src)
    await session.flush()
    raw = RawItem(source_id=src.id, url="https://t.example/a", url_hash="p" * 64, kind="feed")
    session.add(raw)
    await session.flush()
    session.add(
        Item(
            raw_item_id=raw.id,
            title="t",
            url="https://bad.example/a",
            domain="bad.example",
            lang="en",
            content_hash="c" * 64,
            cluster_id=777,
            status="written",
        )
    )
    for i in range(5):
        session.add(
            Feedback(
                target_kind="digest_item",
                target_id=777,
                signal=("down", "wrong", "wrong_source", "down", "wrong")[i],
                actor="telegram",
                day=NOW.date() - timedelta(days=i),
                at=NOW - timedelta(days=i),
            )
        )
    await session.flush()
    for _ in range(2):  # the second night changes nothing
        await run_nightly_patterns(session, None, now=NOW, owner_chat_id=42)
    w = (
        await session.execute(select(Weight).where(Weight.key == "source:bad.example"))
    ).scalar_one()
    assert w.value == pytest.approx(0.7)
    logs = (
        await session.execute(select(ImprovementLog).where(ImprovementLog.key == w.key))
    ).scalars()
    assert [r.automatic for r in logs] == [True]
