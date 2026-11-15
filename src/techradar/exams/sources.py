from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import LibraryChapter, PyqQuestion, SyllabusTopic, TopicSource
from techradar.llm.client import Completer, Embedder, complete_json
from techradar.llm.roles import Role


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def candidate_topics(
    chapter_vec: Sequence[float],
    topic_vecs: Mapping[int, Sequence[float]],
    k: int = 3,
    min_cos: float = 0.55,
) -> list[int]:
    """Rank topic candidates by cosine similarity descending, filtering >= min_cos."""
    scored: list[tuple[float, int]] = []
    for tid, vec in topic_vecs.items():
        sim = _cosine_similarity(chapter_vec, vec)
        if sim >= min_cos:
            scored.append((sim, tid))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [tid for _, tid in scored[:k]]


class _ChapterTopicSelection(BaseModel):
    topic_id: int


async def suggest_for_chapter(
    completer: Completer,
    chapter: Any,
    candidates: Sequence[Any],
) -> int | None:
    """Ask worker model to pick one candidate topic ID and checker to verify."""
    if not candidates:
        return None

    allowed_ids = {c.id for c in candidates}
    c_title = getattr(chapter, "title", str(chapter))
    c_summary = getattr(chapter, "summary_path", "")
    lines = [f"- ID {c.id}: {getattr(c, 'topic', str(c))}" for c in candidates]

    worker_user = f"Chapter: {c_title}\nSummary: {c_summary}\n\nCandidate topics:\n" + "\n".join(
        lines
    )

    worker_res = await complete_json(
        completer,
        Role.WORKER,
        "You are an assistant linking textbook chapters to exam syllabus topics. "
        "Pick exactly one topic_id from the candidates, or set topic_id to -1.",
        worker_user,
        _ChapterTopicSelection,
    )

    if worker_res.topic_id not in allowed_ids:
        return None

    checker_user = (
        f"Chapter: {c_title}\n"
        f"Proposed topic ID: {worker_res.topic_id}\n\n"
        "If this candidate topic is accurate, repeat the topic_id. Otherwise output -1."
    )

    checker_res = await complete_json(
        completer,
        Role.CHECKER,
        "You verify topic links. Confirm the topic_id or output -1.",
        checker_user,
        _ChapterTopicSelection,
    )

    if checker_res.topic_id == worker_res.topic_id:
        return worker_res.topic_id

    return None


async def suggest_topic_sources(
    session: AsyncSession,
    embedder: Embedder,
    completer: Completer,
    *,
    max_per_night: int = 30,
) -> int:
    """Link confirmed PYQs automatically and suggest syllabus topics for unlinked chapters."""
    created_count = 0
    now = datetime.now(UTC)

    # 1. Past papers: PYQs whose topic tag is confirmed
    pyq_stmt = select(PyqQuestion).where(
        PyqQuestion.tag_status == "confirmed",
        PyqQuestion.topic_id.is_not(None),
    )
    pyqs = list((await session.execute(pyq_stmt)).scalars().all())

    for pyq in pyqs:
        existing_stmt = select(TopicSource).where(
            TopicSource.topic_id == pyq.topic_id,
            TopicSource.kind == "pyq",
            TopicSource.ref_id == pyq.id,
        )
        existing = (await session.execute(existing_stmt)).scalar_one_or_none()
        if not existing and pyq.topic_id is not None:
            session.add(
                TopicSource(
                    topic_id=pyq.topic_id,
                    kind="pyq",
                    ref_id=pyq.id,
                    label=f"GATE {pyq.year} Q{pyq.number}",
                    status="confirmed",
                    created_at=now,
                    confirmed_at=now,
                )
            )
            created_count += 1

    await session.flush()

    # 2. Chapters: unlinked library chapters
    topics_stmt = select(SyllabusTopic)
    all_topics = list((await session.execute(topics_stmt)).scalars().all())
    if not all_topics:
        return created_count

    topic_map = {t.id: t for t in all_topics}
    topic_vecs: dict[int, list[float]] = {}
    for t in all_topics:
        vec = await embedder.embed(f"{t.subject}: {t.topic}")
        topic_vecs[t.id] = list(vec)

    # Find chapters without topic_sources
    existing_ch_subquery = (
        select(TopicSource.ref_id).where(TopicSource.kind == "chapter").scalar_subquery()
    )
    ch_stmt = (
        select(LibraryChapter)
        .where(LibraryChapter.id.not_in(existing_ch_subquery))
        .order_by(LibraryChapter.id)
        .limit(max_per_night)
    )
    chapters = list((await session.execute(ch_stmt)).scalars().all())

    for ch in chapters:
        if created_count >= max_per_night:
            break

        ch_vec = await embedder.embed(ch.title)
        cand_ids = candidate_topics(list(ch_vec), topic_vecs)
        if not cand_ids:
            continue

        cand_topics = [topic_map[cid] for cid in cand_ids if cid in topic_map]
        picked_id = await suggest_for_chapter(completer, ch, cand_topics)
        if picked_id is not None:
            session.add(
                TopicSource(
                    topic_id=picked_id,
                    kind="chapter",
                    ref_id=ch.id,
                    label=f"Chapter {ch.ordinal} · {ch.title}",
                    status="suggested",
                    created_at=now,
                    confirmed_at=None,
                )
            )
            created_count += 1

    await session.flush()
    return created_count


async def decide_source(
    session: AsyncSession,
    source_id: int,
    keep: bool,
    now: datetime,
) -> None:
    """Confirm or dismiss a suggested topic source."""
    stmt = select(TopicSource).where(TopicSource.id == source_id)
    source = (await session.execute(stmt)).scalar_one_or_none()
    if source is not None:
        if keep:
            source.status = "confirmed"
            source.confirmed_at = now
        else:
            source.status = "dismissed"
        await session.flush()


async def source_status(session: AsyncSession, topic_id: int, kind: str) -> str | None:
    """Retrieve the status of the first source matching topic_id and kind."""
    stmt = select(TopicSource).where(
        TopicSource.topic_id == topic_id,
        TopicSource.kind == kind,
    )
    src = (await session.execute(stmt)).scalars().first()
    return src.status if src else None


async def only_source_id(session: AsyncSession) -> int:
    """Retrieve the sole topic source id from the table."""
    stmt = select(TopicSource.id)
    return int((await session.execute(stmt)).scalar_one())


async def topics_without_sources(session: AsyncSession, exam: str) -> list[SyllabusTopic]:
    """Retrieve syllabus topics for an exam that do not have confirmed sources."""
    confirmed_subquery = (
        select(TopicSource.topic_id).where(TopicSource.status == "confirmed").scalar_subquery()
    )
    stmt = (
        select(SyllabusTopic)
        .where(
            SyllabusTopic.exam == exam,
            SyllabusTopic.id.not_in(confirmed_subquery),
        )
        .order_by(SyllabusTopic.subject, SyllabusTopic.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def run_suggest_topic_sources(
    session: AsyncSession,
    embedder: Embedder,
    completer: Completer,
    *,
    max_per_night: int = 30,
) -> int:
    """Nightly task helper for suggesting topic sources."""
    return await suggest_topic_sources(session, embedder, completer, max_per_night=max_per_night)


async def run_sources_digest(session: AsyncSession, limit: int = 10) -> str:
    """Generate weekly digest text for suggested sources waiting for confirmation."""
    stmt = (
        select(TopicSource, SyllabusTopic)
        .join(SyllabusTopic, TopicSource.topic_id == SyllabusTopic.id)
        .where(TopicSource.status == "suggested")
        .order_by(TopicSource.created_at)
        .limit(limit)
    )
    rows = list((await session.execute(stmt)).all())
    count_stmt = (
        select(func.count()).select_from(TopicSource).where(TopicSource.status == "suggested")
    )
    total_count = int((await session.execute(count_stmt)).scalar() or 0)
    if not rows:
        return "Sources to confirm: 0"

    lines = [f"Sources to confirm: {total_count}"]
    for src, topic in rows:
        lines.append(f"{topic.topic} ← {src.label}")
    return "\n".join(lines)
