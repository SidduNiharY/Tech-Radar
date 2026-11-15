from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Revision, StudySession, SyllabusTopic, TopicSource
from techradar.pipeline.writer import slugify
from techradar.vault.frontmatter import FRONTMATTER_PATTERN


class TopicCoverage(BaseModel):
    subject: str
    topic: str
    studied_minutes: int
    revisions_done: int
    covered: bool
    n_sources: int = 0
    has_source: bool = False


def parse_topics(md: str) -> list[str]:
    """Parse list of topics from markdown text.

    Finds bullet lines ('- ') under '## Topics' heading up to the next heading.
    Each topic is capped at 120 characters.
    """
    topics: list[str] = []
    in_topics = False

    for line in md.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("#"):
            if trimmed.lower() == "## topics":
                in_topics = True
                continue
            elif in_topics:
                # Reached next section heading
                break
        elif in_topics and trimmed.startswith("- "):
            item = trimmed[2:].strip()[:120]
            if item:
                topics.append(item)

    return topics


async def sync_syllabus(session: AsyncSession, vault_root: Path) -> int:
    """Read every syllabus/**/*.md file and sync topics to syllabus_topics table.

    Front matter must specify `exam` and `title` (subject).
    Returns count of topics processed.
    """
    syllabus_dir = vault_root / "syllabus"
    if not syllabus_dir.exists():
        return 0

    count = 0
    for md_file in sorted(syllabus_dir.glob("**/*.md")):
        text = md_file.read_text(encoding="utf-8")
        match = FRONTMATTER_PATTERN.match(text)
        if not match:
            continue

        raw_fm = match.group(1) or ""
        fm = yaml.safe_load(raw_fm)
        if not isinstance(fm, dict):
            continue

        exam = fm.get("exam")
        title = fm.get("title")
        if not exam or not title:
            continue

        exam_str = str(exam).strip()
        subject_str = str(title).strip()
        rel_path = str(md_file.relative_to(vault_root))

        topics = parse_topics(text)
        for t in topics:
            slug = slugify(t)
            stmt = select(SyllabusTopic).where(
                SyllabusTopic.exam == exam_str,
                SyllabusTopic.subject == subject_str,
                SyllabusTopic.slug == slug,
            )
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing:
                existing.topic = t
                existing.vault_path = rel_path
            else:
                session.add(
                    SyllabusTopic(
                        exam=exam_str,
                        subject=subject_str,
                        topic=t,
                        slug=slug,
                        vault_path=rel_path,
                    )
                )
            count += 1

    await session.flush()
    return count


async def _coverage_for_topic(session: AsyncSession, topic_row: SyllabusTopic) -> TopicCoverage:
    # 1. Studied minutes: sum of StudySession.minutes where lower(topic) matches
    session_stmt = select(func.coalesce(func.sum(StudySession.minutes), 0)).where(
        func.lower(StudySession.topic) == func.lower(topic_row.topic)
    )
    studied_minutes: int = int((await session.execute(session_stmt)).scalar() or 0)

    # 2. Revisions done: count of Revision where lower(topic) matches and done_at is not null
    rev_stmt = (
        select(func.count())
        .select_from(Revision)
        .where(
            func.lower(Revision.topic) == func.lower(topic_row.topic),
            Revision.done_at.is_not(None),
        )
    )
    revisions_done: int = int((await session.execute(rev_stmt)).scalar() or 0)

    # 3. Sources: count of confirmed topic_sources for this topic_id
    src_stmt = (
        select(func.count())
        .select_from(TopicSource)
        .where(
            TopicSource.topic_id == topic_row.id,
            TopicSource.status == "confirmed",
        )
    )
    n_sources: int = int((await session.execute(src_stmt)).scalar() or 0)

    covered = (studied_minutes >= 30) or (revisions_done >= 1)
    has_source = n_sources > 0

    return TopicCoverage(
        subject=topic_row.subject,
        topic=topic_row.topic,
        studied_minutes=studied_minutes,
        revisions_done=revisions_done,
        covered=covered,
        n_sources=n_sources,
        has_source=has_source,
    )


async def coverage(session: AsyncSession, exam: str) -> list[TopicCoverage]:
    """Calculate syllabus topic coverage for an exam."""
    stmt = (
        select(SyllabusTopic)
        .where(SyllabusTopic.exam == exam)
        .order_by(SyllabusTopic.subject, SyllabusTopic.id)
    )
    topics = list((await session.execute(stmt)).scalars().all())

    results: list[TopicCoverage] = []
    for t in topics:
        cov = await _coverage_for_topic(session, t)
        results.append(cov)
    return results


async def coverage_for(session: AsyncSession, topic_id: int) -> TopicCoverage | None:
    """Calculate topic coverage for a specific topic id."""
    stmt = select(SyllabusTopic).where(SyllabusTopic.id == topic_id)
    topic_row = (await session.execute(stmt)).scalar_one_or_none()
    if not topic_row:
        return None
    return await _coverage_for_topic(session, topic_row)
