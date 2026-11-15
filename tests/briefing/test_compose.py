from __future__ import annotations

from datetime import date, datetime, time

import pytest

from techradar.briefing.compose import (
    SECTION_ORDER,
    Briefing,
    StoryCandidate,
    briefing_due,
    render_briefing,
    run_briefing,
    select_items,
)
from techradar.schemas.pipeline import Section


def test_select_items_politics_needs_three_domains():
    official = frozenset({"pib.gov.in"})

    cand_2_domains = StoryCandidate(
        cluster_id="c1",
        title="India 2 Domains",
        section=Section.INDIA,
        domains={"ndtv.com", "thehindu.com"},
        relevance=0.9,
    )
    cand_3_domains = StoryCandidate(
        cluster_id="c2",
        title="India 3 Domains",
        section=Section.INDIA,
        domains={"ndtv.com", "thehindu.com", "indianexpress.com"},
        relevance=0.8,
    )
    cand_official = StoryCandidate(
        cluster_id="c3",
        title="India Official 1 Domain",
        section=Section.INDIA,
        domains={"pib.gov.in"},
        relevance=0.7,
    )
    cand_politics_2_domains = StoryCandidate(
        cluster_id="c4",
        title="Politics 2 Domains",
        section=Section.POLITICS,
        domains={"ndtv.com", "thehindu.com"},
        relevance=0.9,
    )

    items = select_items(
        [cand_2_domains, cand_3_domains, cand_official, cand_politics_2_domains],
        official,
    )
    assert cand_2_domains not in items
    assert cand_politics_2_domains not in items
    assert cand_3_domains in items
    assert cand_official in items


def test_select_items_caps_per_section_and_total():
    # 5 tech stories -> capped at 3
    tech_cands = [
        StoryCandidate(
            cluster_id=f"tech_{i}",
            title=f"Tech {i}",
            section=Section.TECH,
            relevance=0.1 * i,
        )
        for i in range(5)
    ]
    res_tech = select_items(tech_cands, frozenset(), per_section=3)
    assert len(res_tech) == 3

    # 30 stories across 6 sections -> capped at 15
    many_cands = [
        StoryCandidate(
            cluster_id=f"{sec.value}_{i}",
            title=f"{sec.value} {i}",
            section=sec,
            relevance=0.1 * i,
            domains={"d1.com", "d2.com", "d3.com"},
        )
        for sec in SECTION_ORDER
        for i in range(5)
    ]
    res_many = select_items(many_cands, frozenset(), per_section=3, max_items=15)
    assert len(res_many) == 15


def test_select_items_prefers_verified():
    cands = [
        StoryCandidate(
            cluster_id="unverified",
            title="Unverified High Relevance",
            section=Section.TECH,
            verified_headline=False,
            relevance=0.99,
        ),
        StoryCandidate(
            cluster_id="verified",
            title="Verified Low Relevance",
            section=Section.TECH,
            verified_headline=True,
            relevance=0.10,
        ),
    ]
    res = select_items(cands, frozenset())
    assert [c.cluster_id for c in res] == ["verified", "unverified"]


def test_render_briefing_exact_item_text():
    tech_item = StoryCandidate(
        cluster_id="c1",
        title="LangGraph 1.3 released",
        section=Section.TECH,
        verified_headline=True,
        why="Major update to agent orchestration framework.",
        how_it_affects_me="Directly impacts multi-agent architectures.",
        relevance=0.9,
    )
    briefing = Briefing(date=date(2026, 11, 8), items=[tech_item])
    msgs = render_briefing(briefing)
    assert msgs[0].startswith(
        "☀️ Today's Radar · Sun 8 Nov\n\nTECH\n• LangGraph 1.3 released ✅\n  Why: "
    )
    assert msgs[-1].endswith("Reply to any part of this briefing with your take (one line).")


def test_render_briefing_with_exam_tags_and_multiple_sections():
    item1 = StoryCandidate(
        cluster_id="c1",
        title="Quantum Processor Breakthrough",
        section=Section.TECH,
        verified_headline=True,
        why="New coherence record.",
        how_it_affects_me="Hardware scaling milestone.",
        exam_tags=["GATE", "SSC CGL"],
    )
    item2 = StoryCandidate(
        cluster_id="c2",
        title="Monetary Policy Review",
        section=Section.ECONOMY,
        verified_headline=False,
        why="Repo rate unchanged.",
        how_it_affects_me="Inflation tracking.",
        exam_tags=["BANK"],
    )
    briefing = Briefing(
        date=date(2026, 11, 8),
        items=[item1, item2],
        plan_lines=["📰 Radar (10–15 min)", "📝 Quiz: 10 MCQs"],
    )
    msgs = render_briefing(briefing)
    assert "TODAY'S PLAN\n📰 Radar (10–15 min)\n📝 Quiz: 10 MCQs" in msgs[0]
    assert "Tags: GATE, SSC CGL" in msgs[0]
    assert any("Tags: BANK" in m for m in msgs)
    assert msgs[-1].endswith("Reply to any part of this briefing with your take (one line).")


def test_render_briefing_splits_long_sections():
    long_items = [
        StoryCandidate(
            cluster_id=f"long_{i}",
            title=f"Long Story {i} " + "A" * 500,
            section=Section.TECH,
            verified_headline=False,
            why="Why reason " + "B" * 500,
            how_it_affects_me="How it affects me " + "C" * 500,
            relevance=0.8,
        )
        for i in range(5)
    ]
    briefing = Briefing(date=date(2026, 11, 8), items=long_items)
    msgs = render_briefing(briefing)
    assert len(msgs) > 1
    assert all(len(m) <= 4096 for m in msgs)
    assert msgs[0].startswith("☀️ Today's Radar · Sun 8 Nov\n\nTECH\n")
    assert msgs[-1].endswith("Reply to any part of this briefing with your take (one line).")


@pytest.mark.parametrize(
    ("hhmm", "last", "due"),
    [
        ("06:00", None, False),
        ("06:30", None, True),
        ("09:00", None, True),
        ("13:00", None, False),
        ("07:00", "today", False),
    ],
)
def test_briefing_due_cases(hhmm: str, last: str | None, due: bool):
    hour, minute = map(int, hhmm.split(":"))
    now_local = datetime(2026, 11, 8, hour, minute)
    last_sent = now_local.date() if last == "today" else None
    assert briefing_due(now_local, last_sent, at_time=time(6, 30)) == due


def test_render_briefing_indian_languages_pass_through():
    hindi_title = "भारतीय रिजर्व बैंक (RBI) ने रेपो रेट 5.5% पर बरकरार रखा"
    telugu_why = "ఆర్థిక వ్యవస్థ స్థిరత్వం కోసం ఈ నిర్ణయం తీసుకున్నారు"
    item = StoryCandidate(
        cluster_id="ind_lang_1",
        title=hindi_title,
        section=Section.ECONOMY,
        why=telugu_why,
        how_it_affects_me="होम लोन ईएमआई में कोई बदलाव नहीं",
        verified_headline=True,
    )
    briefing = Briefing(date=date(2026, 11, 8), items=[item])
    msgs = render_briefing(briefing)
    assert hindi_title in msgs[0]
    assert telugu_why in msgs[0]
    assert "होम लोन ईएमआई में कोई बदलाव नहीं" in msgs[0]


class FakeAsyncSession:
    """Mock async session for testing run_briefing without Postgres."""

    def __init__(self, last_sent: date | None = None) -> None:
        self.last_sent = last_sent
        self.added: list[object] = []
        self.flushed = False

    async def execute(self, stmt: object) -> object:
        class FakeResult:
            def __init__(self, val: object) -> None:
                self.val = val

            def scalar_one_or_none(self) -> object:
                return self.val

        return FakeResult(self.last_sent)

    def add(self, obj: object) -> None:
        self.added.append(obj)
        if hasattr(obj, "id"):
            obj.id = 101

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_run_briefing_not_due():
    session = FakeAsyncSession(last_sent=date(2026, 11, 8))
    now = datetime(2026, 11, 8, 7, 0)
    res = await run_briefing(session, now=now, owner_chat_id=123)
    assert res.briefing_id is None
    assert res.skipped_reason == "not_due"


@pytest.mark.asyncio
async def test_run_briefing_due_enqueues():
    session = FakeAsyncSession(last_sent=None)
    now = datetime(2026, 11, 8, 7, 0)
    item = StoryCandidate(
        cluster_id="c1",
        title="Tech News",
        section=Section.TECH,
        why="Big deal",
        how_it_affects_me="Good",
        verified_headline=True,
    )
    res = await run_briefing(session, now=now, owner_chat_id=123, candidates=[item])
    assert res.briefing_id == 101
    assert res.messages_sent >= 1
    assert res.items_count == 1
    assert any(hasattr(a, "chat_id") and a.chat_id == 123 for a in session.added)
