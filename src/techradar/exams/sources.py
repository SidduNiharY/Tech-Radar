from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import (
    LibraryChapter,
    LibraryDoc,
    PyqQuestion,
    SyllabusTopic,
    TopicSource,
)
from techradar.llm.client import Completer, Embedder, complete_json
from techradar.llm.roles import Role
from techradar.messaging.outbox import Button, enqueue_message
from techradar.security.text import sanitize_text
from techradar.security.untrusted import wrap_untrusted

SUMMARY_IDEAS_CHARS = 600
_SUMMARY_READ_BYTES = 16_000
_CITATION = re.compile(r"\s*\[C[0-9]+\]")


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
    lines = [f"- ID {c.id}: {getattr(c, 'topic', str(c))}" for c in candidates]

    c_summary = getattr(chapter, "summary", "") or ""
    # The chapter title and summary come from a book: data, never instructions.
    worker_user = (
        wrap_untrusted(f"Chapter: {sanitize_text(c_title)}\nKey ideas: {sanitize_text(c_summary)}")
        + "\n\nCandidate topics:\n"
        + "\n".join(lines)
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
        wrap_untrusted(f"Chapter: {sanitize_text(c_title)}\nKey ideas: {sanitize_text(c_summary)}")
        + "\n\n"
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


def read_key_ideas(vault_root: Path, summary_path: str | None) -> str:
    """The `## Key Ideas` bullets of a chapter summary note, without citations, capped.

    The path is relative to the vault and may be tampered with: it must stay inside the vault
    and is never followed through a symlink. Anything unreadable gives an empty string.
    """
    if not summary_path:
        return ""
    root = vault_root.resolve()
    candidate = root / summary_path
    try:
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(root):
            return ""
        with candidate.open("rb") as fh:
            raw = fh.read(_SUMMARY_READ_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return ""
    ideas: list[str] = []
    in_ideas = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if in_ideas:
                break
            in_ideas = stripped.lower() == "## key ideas"
        elif in_ideas and stripped.startswith(("- ", "* ")):
            ideas.append(_CITATION.sub("", stripped[2:]).strip())
    return " ".join(ideas)[:SUMMARY_IDEAS_CHARS]


async def topic_vectors(
    embedder: Embedder, topics: Sequence[SyllabusTopic]
) -> dict[int, list[float]]:
    """One embedding per syllabus topic (a single batched call; `embed` takes a list)."""
    if not topics:
        return {}
    vecs = await embedder.embed([f"{t.subject}: {t.topic}" for t in topics])
    return {t.id: list(v) for t, v in zip(topics, vecs, strict=True)}


async def chapter_vector(embedder: Embedder, title: str, key_ideas: str = "") -> list[float]:
    """The chapter's embedding: its title plus its summary's key ideas."""
    text = f"{title}. {key_ideas}" if key_ideas else title
    return list((await embedder.embed([text]))[0])


async def suggest_topic_sources(
    session: AsyncSession,
    embedder: Embedder,
    completer: Completer,
    *,
    max_per_night: int = 30,
    now: datetime | None = None,
    vault_root: Path | None = None,
) -> int:
    """Link confirmed PYQs automatically and suggest syllabus topics for unlinked chapters.

    A model-suggested chapter source stays `suggested` until the owner confirms it
    (`decide_source`); only a past-paper tag the owner already confirmed links at once.
    """
    created_count = 0
    when = now or datetime.now(UTC)

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
                    created_at=when,
                    confirmed_at=when,
                )
            )
            created_count += 1

    await session.flush()

    # 2. Chapters: unlinked library chapters (a dismissed suggestion counts as linked, so a
    # "Not this" is never asked again)
    all_topics = list((await session.execute(select(SyllabusTopic))).scalars().all())
    if not all_topics:
        return created_count

    topic_map = {t.id: t for t in all_topics}
    topic_vecs = await topic_vectors(embedder, all_topics)

    linked = select(TopicSource.ref_id).where(TopicSource.kind == "chapter")
    ch_stmt = (
        select(LibraryChapter, LibraryDoc.title)
        .join(LibraryDoc, LibraryChapter.doc_id == LibraryDoc.id)
        .where(LibraryChapter.id.not_in(linked))
        .order_by(LibraryChapter.id)
        .limit(max_per_night)
    )
    chapters = list((await session.execute(ch_stmt)).all())

    suggested = 0
    for ch, doc_title in chapters:
        if suggested >= max_per_night:
            break
        key_ideas = read_key_ideas(vault_root, ch.summary_path) if vault_root else ""
        ch_vec = await chapter_vector(embedder, ch.title, key_ideas)
        cand_ids = candidate_topics(ch_vec, topic_vecs)
        if not cand_ids:
            continue

        cand_topics = [topic_map[cid] for cid in cand_ids if cid in topic_map]
        picked_id = await suggest_for_chapter(
            completer, SimpleNamespace(title=ch.title, summary=key_ideas), cand_topics
        )
        if picked_id is not None:
            session.add(
                TopicSource(
                    topic_id=picked_id,
                    kind="chapter",
                    ref_id=ch.id,
                    label=_chapter_label(doc_title, ch),
                    status="suggested",
                    created_at=when,
                    confirmed_at=None,
                )
            )
            suggested += 1
            created_count += 1

    await session.flush()
    return created_count


def _chapter_label(doc_title: str, ch: LibraryChapter) -> str:
    """`Galvin · 8. Deadlocks · p. 318–352` (at most 200 characters)."""
    label = f"{doc_title} · {ch.ordinal}. {ch.title}"
    if ch.page_start is not None and ch.page_end is not None:
        label += f" · p. {ch.page_start}–{ch.page_end}"
    return label[:200]


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
    now: datetime | None = None,
    vault_root: Path | None = None,
) -> int:
    """Nightly task helper for suggesting topic sources."""
    return await suggest_topic_sources(
        session, embedder, completer, max_per_night=max_per_night, now=now, vault_root=vault_root
    )


class SourceSuggestion(BaseModel):
    """One suggested source waiting for the owner's Keep / Not this."""

    id: int
    topic: str
    label: str


async def sources_to_confirm(
    session: AsyncSession, limit: int = 10
) -> tuple[int, list[SourceSuggestion]]:
    """How many suggested sources wait, and the oldest `limit` of them."""
    stmt = (
        select(TopicSource, SyllabusTopic)
        .join(SyllabusTopic, TopicSource.topic_id == SyllabusTopic.id)
        .where(TopicSource.status == "suggested")
        .order_by(TopicSource.created_at, TopicSource.id)
        .limit(limit)
    )
    rows = list((await session.execute(stmt)).all())
    count_stmt = (
        select(func.count()).select_from(TopicSource).where(TopicSource.status == "suggested")
    )
    total = int((await session.execute(count_stmt)).scalar() or 0)
    return total, [SourceSuggestion(id=src.id, topic=t.topic, label=src.label) for src, t in rows]


def render_source_suggestion(s: SourceSuggestion) -> str:
    """`<topic> ← <label>`: one weekly-digest message."""
    return f"{s.topic} ← {s.label}"


async def enqueue_sources_digest(session: AsyncSession, chat_id: int, limit: int = 10) -> int:
    """Queue the weekly digest: `Sources to confirm: <n>`, then one message per suggestion
    with `Keep` (`srcok:<id>`) and `Not this` (`srcno:<id>`) buttons. At most `limit`.

    Sends nothing when no suggestion waits. Returns the number of suggestion messages.
    """
    total, items = await sources_to_confirm(session, limit)
    if not items:
        return 0
    await enqueue_message(session, chat_id, f"Sources to confirm: {total}", purpose="sources")
    for item in items:
        buttons = [
            [
                Button(text="Keep", data=f"srcok:{item.id}"),
                Button(text="Not this", data=f"srcno:{item.id}"),
            ]
        ]
        await enqueue_message(
            session,
            chat_id,
            render_source_suggestion(item),
            purpose="sources",
            buttons=buttons,
            ref_id=item.id,
        )
    return len(items)


async def run_sources_digest(session: AsyncSession, limit: int = 10) -> str:
    """Generate weekly digest text for suggested sources waiting for confirmation."""
    total, items = await sources_to_confirm(session, limit)
    if not items:
        return "Sources to confirm: 0"
    return "\n".join(
        [f"Sources to confirm: {total}", *(render_source_suggestion(i) for i in items)]
    )
