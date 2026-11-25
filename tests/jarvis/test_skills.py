"""The ten read-only Jarvis skills (Phase 12 Task 8, read side).

Most tests are `db`: the skills read the same tables as the Phase 3-8 features. Every skill call
runs through `ReadOnlySession`, which fails on anything but a SELECT.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from techradar.db.models import (
    MCQ,
    Alert,
    Briefing,
    ExamWatch,
    Fact,
    Flashcard,
    LibraryChapter,
    LibraryDoc,
    Plan,
    StudySession,
    SyllabusTopic,
    TopicMastery,
    UserSettings,
)
from techradar.jarvis.skill_impl import (
    READ_SKILLS,
    SkillReply,
    ask,
    coach,
    exams,
    library,
    news,
    plan,
    progress,
    quiz,
    status,
    teach,
)

NOW = datetime(2026, 11, 25, 9, 30, tzinfo=UTC)  # a Wednesday
TODAY = NOW.date()


class WriteAttempt(AssertionError):
    pass


class ReadOnlySession:
    """Wraps a real session; add, delete, flush, commit and non-SELECT statements fail."""

    def __init__(self, inner: AsyncSession) -> None:
        self._inner = inner
        self.executed = 0

    def _deny(self, what: str) -> Any:
        raise WriteAttempt(f"read skill tried to {what}")

    def add(self, *_a: Any, **_k: Any) -> Any:
        return self._deny("add")

    def add_all(self, *_a: Any, **_k: Any) -> Any:
        return self._deny("add_all")

    async def delete(self, *_a: Any, **_k: Any) -> Any:
        return self._deny("delete")

    async def merge(self, *_a: Any, **_k: Any) -> Any:
        return self._deny("merge")

    async def flush(self, *_a: Any, **_k: Any) -> Any:
        return self._deny("flush")

    async def commit(self, *_a: Any, **_k: Any) -> Any:
        return self._deny("commit")

    async def execute(self, stmt: Any, *a: Any, **k: Any) -> Any:
        if isinstance(stmt, str | TextClause):  # raw SQL: look at the first word
            is_select = str(stmt).lstrip().upper().startswith("SELECT")
        else:
            is_select = bool(getattr(stmt, "is_select", False))
        if not is_select:
            self._deny(f"run {str(stmt)[:40]!r}")
        self.executed += 1
        return await self._inner.execute(stmt, *a, **k)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def ro(session: AsyncSession) -> AsyncSession:
    return ReadOnlySession(session)  # type: ignore[return-value]


# --- no database needed ---------------------------------------------------------------------


def test_registry_has_the_ten_skills():
    assert set(READ_SKILLS) == {
        "news",
        "ask",
        "teach",
        "quiz",
        "plan",
        "library",
        "exams",
        "progress",
        "coach",
        "status",
    }


def test_skill_sources_only_read():
    """No skill file may call anything that writes."""
    root = Path(__file__).parents[2] / "src/techradar/jarvis/skill_impl"
    banned = (
        ".add(",
        ".add_all(",
        ".delete(",
        ".flush(",
        ".commit(",
        ".merge(",
        "insert(",
        "update(",
    )
    for path in root.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        for word in banned:
            assert word not in src, f"{path.name} contains {word}"


def test_say_is_capped():
    assert len(SkillReply(say="x" * 5000).say) <= 1200


async def test_read_only_session_refuses_writes():
    class Inner:
        pass

    spy = ReadOnlySession(Inner())  # type: ignore[arg-type]
    with pytest.raises(WriteAttempt):
        spy.add(object())
    with pytest.raises(WriteAttempt):
        await spy.flush()
    with pytest.raises(WriteAttempt):
        await spy.delete(object())
    with pytest.raises(WriteAttempt):
        await spy.execute("DELETE FROM techradar.plans")


# --- database tests -------------------------------------------------------------------------

db = pytest.mark.db


async def _doc(session: AsyncSession, title: str, status_: str = "ready", sha: str = "a") -> int:
    d = LibraryDoc(
        sha256=sha * 64,
        title=title,
        kind="pdf",
        origin="library",
        original_path=f"/x/{title}.pdf",
        size_bytes=10,
        status=status_,
        trust="my_own",
    )
    session.add(d)
    await session.flush()
    return d.id


@db
async def test_news_lists_three_and_sets_list_len(session: AsyncSession):
    items = [
        {"title": f"Story {i}", "section": "tech", "why": f"reason {i}", "how_it_affects_me": "h"}
        for i in range(1, 6)
    ] + [{"title": "Budget", "section": "economy", "why": "tax", "how_it_affects_me": "pay"}]
    session.add(Briefing(date=TODAY, sent_at=NOW, items=items))
    await session.flush()
    r = await news.run(ro(session), NOW, section="tech")
    assert r.list_len == 3
    assert r.say.endswith("Which one do you want to know more about?")
    assert "Story 1: reason 1" in r.say and "Story 4" not in r.say and "Budget" not in r.say
    one = await news.run(ro(session), NOW, section="tech", item=2)
    assert "Story 2" in one.say and "How it affects you: h" in one.say
    assert "no story number 9" in (await news.run(ro(session), NOW, item=9)).say


@db
async def test_news_without_a_briefing(session: AsyncSession):
    r = await news.run(ro(session), NOW)
    assert r.say == news.NO_BRIEFING and r.list_len is None


@db
async def test_plan_reads_numbered_lines_for_the_day(session: AsyncSession):
    session.add(Plan(date=TODAY, lines=["🎓 GOV: polity (60 min)", "🎓 DEV: rag (90 min)"]))
    session.add(Plan(date=TODAY + timedelta(days=1), lines=["🎓 GATE: os (60 min)"]))
    await session.flush()
    r = await plan.run(ro(session), NOW)
    assert r.list_len == 2 and "1. 🎓 GOV: polity (60 min) 2. 🎓 DEV" in r.say
    t = await plan.run(ro(session), NOW, day="tomorrow")
    assert "os" in t.say and t.list_len == 1
    assert (await plan.run(ro(session), NOW, day=date(2030, 1, 1))).list_len == 0


@db
async def test_library_status_counts_read_chapters(session: AsyncSession):
    doc_id = await _doc(session, "Indian Economy")
    await _doc(session, "Queued Book", status_="queued", sha="b")
    for i in range(1, 4):
        session.add(
            LibraryChapter(
                doc_id=doc_id,
                ordinal=i,
                title=f"c{i}",
                text_path="x",
                read_at=NOW if i == 1 else None,
            )
        )
    await session.flush()
    r = await library.run(ro(session), NOW)
    assert "Indian Economy: 1 of 3 chapters read." in r.say and "Queued" not in r.say
    assert "can't find" in (await library.run(ro(session), NOW, book="Nope")).say


@db
async def test_exams_dates_and_alerts(session: AsyncSession):
    session.add(UserSettings(key="exam_dates", value={"gate": "2027-02-06", "bank": "2026-11-20"}))
    w = ExamWatch(title="GATE site", url="https://x.example/g", watch_uuid="u")
    session.add(w)
    await session.flush()
    session.add(Alert(watch_id=w.id, changed_at=NOW - timedelta(days=1)))
    await session.flush()
    r = await exams.run(ro(session), NOW, op="dates")
    assert "gate: 6 Feb, in 73 days." in r.say
    assert "bank: 20 Nov, already past." in r.say
    assert "Latest change: GATE site on 24 Nov." in r.say


@db
async def test_exams_progress_counts_topics(session: AsyncSession):
    for slug in ("a", "b"):
        session.add(
            SyllabusTopic(exam="gate", subject="OS", topic=slug, slug=slug, vault_path=f"v/{slug}")
        )
    await session.flush()
    r = await exams.run(ro(session), NOW, op="progress", exam="gate")
    assert "gate: 0 of 2 topics covered, 2 without a source." in r.say


@db
async def test_progress_minutes_against_targets_and_weakest_topic(session: AsyncSession):
    monday = datetime(2026, 11, 23, 8, 0, tzinfo=UTC)
    session.add(StudySession(goal="gov", topic="polity", started_at=monday, minutes=60))
    session.add(StudySession(goal="gov", topic="polity", started_at=NOW, minutes=30))
    session.add(
        StudySession(goal="gov", topic="old", started_at=monday - timedelta(days=3), minutes=999)
    )
    session.add(TopicMastery(topic="Banker's algorithm", level="learning", prev_level="mastered"))
    session.add(TopicMastery(topic="Polity", level="mastered", prev_level="learning"))
    await session.flush()
    r = await progress.run(ro(session), NOW)
    assert "gov: 90 of 420 minutes." in r.say
    assert "slipped most is Banker's algorithm" in r.say
    assert "dev: 0 of 600 minutes." in r.say


@db
async def test_quiz_starts_with_unanswered_mcqs(session: AsyncSession):
    fact = Fact(fact_key="k", statement="s", subject="rbi", section="economy", status="verified")
    session.add(fact)
    await session.flush()
    session.add(
        MCQ(
            fact_id=fact.id,
            question="Repo rate is set by?",
            options=["RBI", "SEBI", "NITI", "IMF"],
            answer_index=0,
            explanation="e",
        )
    )
    await session.flush()
    r = await quiz.run(ro(session), NOW, kind="mcq", count=5)
    assert "Repo rate is set by? A: RBI. B: SEBI." in r.say
    assert r.quiz is not None and r.quiz["kind"] == "mcq" and r.quiz["index"] == 0


@db
async def test_quiz_cards_read_first_due_card(session: AsyncSession):
    session.add(
        Flashcard(
            front="What is NPA?",
            back="b",
            source_kind="fact",
            due=NOW - timedelta(hours=1),
        )
    )
    await session.flush()
    r = await quiz.run(ro(session), NOW, kind="cards")
    assert "What is NPA?" in r.say and r.quiz is not None and r.quiz["kind"] == "cards"


@db
async def test_quiz_with_nothing_due(session: AsyncSession):
    assert "no quiz questions" in (await quiz.run(ro(session), NOW, kind="mcq")).say


@db
async def test_teach_brief_from_my_facts(session: AsyncSession):
    session.add(
        Fact(
            fact_key="p1",
            statement="Polity: the Preamble was amended in 1976.",
            subject="polity",
            section="india",
            status="verified",
        )
    )
    session.add(
        Fact(fact_key="p2", statement="Polity draft", subject="polity", section="india")
    )  # unverified: not used
    await session.flush()
    r = await teach.run(ro(session), NOW, topic="polity", minutes=60)
    assert r.practice == "explain" and r.brief is not None
    assert r.brief.facts == ["Polity: the Preamble was amended in 1976."]
    assert "60-minute plan" in r.say


@db
async def test_teach_passage_stays_inside_the_vault(session: AsyncSession, tmp_path: Path):
    (tmp_path / "ok.md").write_text("A short summary.", encoding="utf-8")
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("do not read", encoding="utf-8")
    doc_id = await _doc(session, "Book")
    session.add(
        LibraryChapter(
            doc_id=doc_id, ordinal=1, title="Polity", text_path="x", summary_path="ok.md"
        )
    )
    session.add(
        LibraryChapter(
            doc_id=doc_id,
            ordinal=2,
            title="Polity two",
            text_path="x",
            summary_path="../secret.txt",
        )
    )
    await session.flush()
    r = await teach.run(ro(session), NOW, topic="Polity", vault_root=tmp_path)
    assert r.brief is not None and r.brief.passage == "A short summary."
    r2 = await teach.run(ro(session), NOW, topic="Polity two", vault_root=tmp_path)
    assert r2.brief is not None and r2.brief.passage is None


@db
async def test_ask_picks_the_book_and_goes_slow_without_an_answer(session: AsyncSession):
    doc_id = await _doc(session, "Indian Economy")
    await _doc(session, "Indian Economy Workbook", sha="c")
    slow = await ask.run(
        ro(session), NOW, question="Explain the Taylor rule", book="indian economy"
    )
    assert slow.slow and slow.doc_id == doc_id

    async def fast(q: str, d: int | None) -> str | None:
        return f"{q} -> doc {d}"

    quick = await ask.run(
        ro(session), NOW, question="What is CPI?", book="Indian Economy", answer=fast
    )
    assert not quick.slow and quick.say == f"What is CPI? -> doc {doc_id}"
    missing = await ask.run(ro(session), NOW, question="x", book="Nonexistent")
    assert "can't find" in missing.say


@db
async def test_coach_returns_mode_and_brief(session: AsyncSession):
    r = await coach.run(ro(session), NOW, mode="interview_hr")
    assert r.practice == "interview_hr" and r.brief is not None and r.brief.questions


@db
async def test_status_reads_only(session: AsyncSession):
    async def ollama() -> list[str] | None:
        return ["qwen3"]

    r = await status.run(ro(session), NOW, check_ollama=ollama, check_disk=lambda: 55.0)
    assert "Database: ok" in r.say and "qwen3" in r.say and "Disk free: 55%" in r.say


@db
async def test_every_registered_skill_survives_a_read_only_session(session: AsyncSession):
    """Run each skill through the registry on empty tables: no write attempt, a spoken reply."""
    spy = ReadOnlySession(session)
    calls: dict[str, dict[str, Any]] = {
        "news": {},
        "ask": {"question": "What is GDP?"},
        "teach": {"topic": "polity"},
        "quiz": {"kind": "mcq"},
        "plan": {},
        "library": {},
        "exams": {"op": "progress"},
        "progress": {},
        "coach": {"mode": "conversation"},
        "status": {"check_ollama": _none, "check_disk": lambda: 90.0},
    }
    for name, fn in READ_SKILLS.items():
        r = await fn(spy, NOW, **calls[name])
        assert isinstance(r, SkillReply) and r.say, name
    assert spy.executed > 0


async def _none() -> list[str] | None:
    return None
