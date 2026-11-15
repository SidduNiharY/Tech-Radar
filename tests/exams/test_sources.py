from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import LibraryChapter, PyqQuestion, SyllabusTopic
from techradar.exams.sources import (
    candidate_topics,
    decide_source,
    only_source_id,
    source_status,
    suggest_for_chapter,
    suggest_topic_sources,
)
from techradar.exams.syllabus import coverage_for
from techradar.settings import Settings
from tests.fakes import FakeCompleter, FakeEmbedder


def test_candidate_topics_threshold():
    assert candidate_topics([1.0, 0.0], {1: [1.0, 0.0], 2: [0.0, 1.0]}, k=3, min_cos=0.55) == [1]
    assert candidate_topics([1.0, 0.0], {1: [0.0, 1.0]}, k=3, min_cos=0.55) == []


async def test_suggestion_must_be_in_candidates():
    chapter = SimpleNamespace(title="Deadlocks", summary_path="")
    topic = SimpleNamespace(id=1, topic="Deadlocks")
    completer = FakeCompleter(['{"topic_id": 999}'])
    assert await suggest_for_chapter(completer, chapter, [topic]) is None


async def test_suggestion_checker_agrees():
    chapter = SimpleNamespace(title="Deadlocks", summary_path="")
    topic = SimpleNamespace(id=1, topic="Deadlocks")
    completer = FakeCompleter(['{"topic_id": 1}', '{"topic_id": 1}'])
    assert await suggest_for_chapter(completer, chapter, [topic]) == 1


@pytest.fixture
def db_settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


@pytest.fixture
async def session(db_settings: Settings) -> AsyncGenerator[AsyncSession]:
    engine = make_engine("app", db_settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest.mark.db
async def test_confirmed_pyq_tag_links_automatically(session: AsyncSession):
    topic = SyllabusTopic(
        exam="GATE CS",
        subject="OS",
        topic="Deadlocks",
        slug="deadlocks",
        vault_path="syllabus/gate/os.md",
    )
    session.add(topic)
    await session.flush()

    pyq = PyqQuestion(
        exam="GATE CS",
        year=2023,
        paper="CS",
        number=14,
        text="Which of the following is true regarding Banker's algorithm?",
        options=None,
        qtype="MCQ",
        answer_key="A",
        marks=1.0,
        topic_id=topic.id,
        tag_status="confirmed",
    )
    session.add(pyq)
    await session.flush()

    await suggest_topic_sources(session, FakeEmbedder(dim=2), FakeCompleter([]))
    status = await source_status(session, topic.id, "pyq")
    assert status == "confirmed"


@pytest.mark.db
async def test_suggested_source_needs_my_confirmation(session: AsyncSession):
    topic = SyllabusTopic(
        exam="GATE CS",
        subject="OS",
        topic="Deadlocks",
        slug="deadlocks",
        vault_path="syllabus/gate/os.md",
    )
    session.add(topic)
    await session.flush()

    chapter = LibraryChapter(
        doc_id=1,
        ordinal=8,
        title="Deadlocks",
        text_path="library/docs/1/ch8.txt",
        summary_path=None,
        missing_pages=[],
    )
    session.add(chapter)
    await session.flush()

    embedder = FakeEmbedder(dim=2, table={"OS: Deadlocks": [1.0, 0.0], "Deadlocks": [1.0, 0.0]})
    completer = FakeCompleter([f'{{"topic_id": {topic.id}}}', f'{{"topic_id": {topic.id}}}'])

    await suggest_topic_sources(session, embedder, completer)

    cov = await coverage_for(session, topic.id)
    assert cov is not None
    assert not cov.has_source

    sid = await only_source_id(session)
    now = datetime.now(UTC)
    await decide_source(session, sid, keep=True, now=now)

    cov_after = await coverage_for(session, topic.id)
    assert cov_after is not None
    assert cov_after.has_source
