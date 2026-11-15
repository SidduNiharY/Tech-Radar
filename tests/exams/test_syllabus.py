from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import Revision, StudySession, SyllabusTopic
from techradar.exams.syllabus import coverage, parse_topics, sync_syllabus
from techradar.settings import Settings


def test_parse_topics_stops_at_next_heading():
    md = "# OS\n## Topics\n- Processes\n- Deadlocks\n## Notes\n- not a topic\n"
    assert parse_topics(md) == ["Processes", "Deadlocks"]


def test_parse_topics_caps_length():
    long_topic = "A" * 150
    md = f"## Topics\n- {long_topic}\n"
    parsed = parse_topics(md)
    assert len(parsed) == 1
    assert len(parsed[0]) == 120


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
async def test_sync_syllabus_from_vault(tmp_path: Path, session: AsyncSession):
    vault = tmp_path / "vault"
    vault.mkdir()
    syllabus_dir = vault / "syllabus" / "gate"
    syllabus_dir.mkdir(parents=True)

    note = syllabus_dir / "os.md"
    note.write_text(
        "---\nexam: GATE CS\ntitle: Operating Systems\n---\n"
        "# Operating Systems\n\n## Topics\n- Processes\n- Deadlocks\n\n"
        "## References\n- Silberschatz\n",
        encoding="utf-8",
    )

    count = await sync_syllabus(session, vault)
    assert count == 2

    # Second run is idempotent
    count2 = await sync_syllabus(session, vault)
    assert count2 == 2


@pytest.mark.db
async def test_coverage_rules(session: AsyncSession):
    # Setup syllabus topics
    t1 = SyllabusTopic(
        exam="GATE CS",
        subject="Operating Systems",
        topic="Deadlocks",
        slug="deadlocks",
        vault_path="syllabus/gate/os.md",
    )
    t2 = SyllabusTopic(
        exam="GATE CS",
        subject="Operating Systems",
        topic="Processes",
        slug="processes",
        vault_path="syllabus/gate/os.md",
    )
    t3 = SyllabusTopic(
        exam="GATE CS",
        subject="Operating Systems",
        topic="Paging",
        slug="paging",
        vault_path="syllabus/gate/os.md",
    )
    session.add_all([t1, t2, t3])
    await session.flush()

    # 45 min study on "deadlocks" (case-insensitive) -> covered
    now = datetime.now(UTC)
    s1 = StudySession(
        goal="GATE CS",
        topic="deadlocks",
        started_at=now,
        minutes=45,
    )
    session.add(s1)

    # 10 min study + 0 revisions on "processes" -> not covered
    s2 = StudySession(
        goal="GATE CS",
        topic="processes",
        started_at=now,
        minutes=10,
    )
    session.add(s2)

    # 0 min study + 1 revision done on "paging" -> covered
    r1 = Revision(
        goal="GATE CS",
        topic="Paging",
        due_date=now.date(),
        done_at=now,
    )
    session.add(r1)
    await session.flush()

    cov_list = await coverage(session, "GATE CS")
    cov_by_topic = {c.topic: c for c in cov_list}

    assert cov_by_topic["Deadlocks"].covered is True
    assert cov_by_topic["Deadlocks"].studied_minutes == 45
    assert cov_by_topic["Processes"].covered is False
    assert cov_by_topic["Processes"].studied_minutes == 10
    assert cov_by_topic["Paging"].covered is True
    assert cov_by_topic["Paging"].revisions_done == 1
