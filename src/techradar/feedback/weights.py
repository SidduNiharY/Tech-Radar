"""Bounded, fading topic and source weights and ranking adjustments."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import ImprovementLog, Weight

STEP: dict[str, float] = {
    "up": 0.1,
    "more_like_this": 0.1,
    "save": 0.1,
    "down": -0.1,
    "not_relevant": -0.1,
    "skip": -0.05,
}


def bounded(
    value: float,
    *,
    lo: float = 0.2,
    hi: float = 2.0,
    floor: float | None = None,
) -> float:
    """Clamp weight within bounds [lo, hi], respecting topic-specific floor."""
    lower = max(lo, floor) if floor is not None else lo
    clamped = max(lower, min(hi, value))
    return round(clamped, 4)


def effective(value: float, age_days: float, half_life: float = 60.0) -> float:
    """Calculate faded effective weight over elapsed days with half-life decay."""
    if half_life <= 0:
        return value
    decay = 0.5 ** (age_days / half_life)
    return 1.0 + (value - 1.0) * decay


def score(relevance: float, topic_w: float, source_w: float) -> float:
    """Combine relevance and component weights into ranking score."""
    return float(relevance * topic_w * source_w)


def _topic_keys(item: Any) -> list[str]:
    """The topic keys of a candidate: `topic_keys` (briefing stories) or one `topic`."""
    keys = getattr(item, "topic_keys", None)
    if keys:
        return list(keys)
    topic = getattr(item, "topic", None)
    if topic is None and isinstance(item, dict):
        topic = item.get("topic")
    return [topic] if topic else []


def _has_exam_tags(item: Any) -> bool:
    if hasattr(item, "exam_tags"):
        return bool(item.exam_tags)
    if isinstance(item, dict):
        return bool(item.get("exam_tags"))
    return False


def is_favourite(item: Any, weights: Mapping[str, float]) -> bool:
    """Check if item topic has weight >= 1.0."""
    known = [weights[k] for k in _topic_keys(item) if k in weights]
    return bool(known) and sum(known) / len(known) >= 1.0


def pick_outside_usual(
    candidates: Sequence[Any],
    chosen: Sequence[Any],
    weights: Mapping[str, float],
    share: float = 0.1,
) -> list[Any]:
    """Ensure at least ceil(share * len(chosen)) outside-usual items in briefing selection."""
    chosen_list = list(chosen)
    if not chosen_list:
        return chosen_list

    required_outside = math.ceil(share * len(chosen_list))
    outside_count = sum(1 for c in chosen_list if not is_favourite(c, weights))
    deficit = required_outside - outside_count
    if deficit <= 0:
        return chosen_list

    available_outside = [
        c for c in candidates if c not in chosen_list and not is_favourite(c, weights)
    ]
    if not available_outside:
        return chosen_list

    # Find replaceable non-exam favorite items with lowest scores
    def _score(item: Any) -> float:
        if hasattr(item, "score"):
            return float(item.score)
        if isinstance(item, dict):
            return float(item.get("score", 0.0))
        return 0.0

    replaceable_indices = [
        i for i, c in enumerate(chosen_list) if not _has_exam_tags(c) and is_favourite(c, weights)
    ]
    replaceable_indices.sort(key=lambda i: _score(chosen_list[i]))

    to_replace = min(deficit, len(available_outside), len(replaceable_indices))
    for k in range(to_replace):
        idx = replaceable_indices[k]
        chosen_list[idx] = available_outside[k]

    return chosen_list


async def apply_signal(
    session: AsyncSession,
    *,
    topics: Sequence[str],
    source: str | None,
    delta: float,
    exam_topic: bool,
    now: datetime,
) -> list[int]:
    """Apply weight change delta to topics and source, logging automatic changes."""
    log_ids: list[int] = []
    exam_floor = 0.8 if exam_topic else None

    for topic in topics:
        stmt = select(Weight).where(Weight.kind == "topic", Weight.key == topic)
        res = await session.execute(stmt)
        w_row = res.scalar_one_or_none()

        old_val = w_row.value if w_row else 1.0
        # a floor, once set for a topic, stays (a syllabus topic never drops below it)
        floor = exam_floor if exam_floor is not None else (w_row.floor if w_row else None)
        new_val = bounded(old_val + delta, floor=floor)

        if w_row:
            w_row.value = new_val
            w_row.floor = floor
            w_row.updated_at = now
        else:
            w_row = Weight(
                kind="topic",
                key=topic,
                value=new_val,
                floor=floor,
                updated_at=now,
            )
            session.add(w_row)

        log = ImprovementLog(
            kind="weight",
            key=topic,
            before={"value": old_val},
            after={"value": new_val},
            automatic=True,
            at=now,
        )
        session.add(log)
        await session.flush()
        log_ids.append(log.id)

    if source:
        stmt = select(Weight).where(Weight.kind == "source", Weight.key == source)
        res = await session.execute(stmt)
        s_row = res.scalar_one_or_none()

        old_val = s_row.value if s_row else 1.0
        new_val = bounded(old_val + delta)

        if s_row:
            s_row.value = new_val
            s_row.updated_at = now
        else:
            s_row = Weight(
                kind="source",
                key=source,
                value=new_val,
                floor=None,
                updated_at=now,
            )
            session.add(s_row)

        log = ImprovementLog(
            kind="weight",
            key=source,
            before={"value": old_val},
            after={"value": new_val},
            automatic=True,
            at=now,
        )
        session.add(log)
        await session.flush()
        log_ids.append(log.id)

    return log_ids


def source_key(domain: str) -> str:
    """The weight key of a source: `source:<registrable domain>`."""
    return f"source:{domain.strip().lower()}"


def entity_key(entity: str) -> str:
    """The weight key of an entity: `entity:<normalised entity>`."""
    return "entity:" + " ".join(entity.lower().split())[:80]


def story_topic_keys(section: str, entities: Sequence[str]) -> list[str]:
    """`section:<section>` plus `entity:<entity>` for each reader entity."""
    return [f"section:{section}", *(entity_key(e) for e in entities)]


async def load_weights(session: AsyncSession, now: datetime) -> dict[str, float]:
    """Every topic and source weight as it counts today: faded toward 1.0 by its age."""
    rows = (
        await session.execute(select(Weight).where(Weight.kind.in_(("topic", "source"))))
    ).scalars()
    out: dict[str, float] = {}
    for w in rows:
        age = max(0.0, (now - w.updated_at).total_seconds() / 86400) if w.updated_at else 0.0
        out[w.key] = effective(w.value, age)
    return out


def mean_weight(keys: Sequence[str], weights: Mapping[str, float]) -> float:
    """The average effective weight of the keys with a history; 1.0 when there is none."""
    known = [weights[k] for k in keys if k in weights]
    return sum(known) / len(known) if known else 1.0


async def apply_digest_signal(
    session: AsyncSession, cluster_id: int, delta: float, now: datetime
) -> list[int]:
    """Move the weights of one briefing story: its section, entities and sources.

    The story's own stored data names the topics (never the feedback sender). A story with
    exam tags counts as an exam topic, so its weight keeps the 0.8 floor.
    """
    from techradar.db.models import Item
    from techradar.schemas.pipeline import ReaderOutput

    items = (
        (await session.execute(select(Item).where(Item.cluster_id == cluster_id))).scalars().all()
    )
    reader = next((it.reader_json for it in items if getattr(it, "reader_json", None)), None)
    if reader is None:
        return []
    try:
        out = ReaderOutput.model_validate(reader)
    except ValueError:
        return []
    topics = story_topic_keys(str(out.section.value), out.entities)
    ids: list[int] = []
    domains = sorted({it.domain for it in items})
    exam = bool(out.exam_tags)
    ids += await apply_signal(
        session,
        topics=topics,
        source=source_key(domains[0]) if domains else None,
        delta=delta,
        exam_topic=exam,
        now=now,
    )
    for extra in domains[1:]:
        ids += await apply_signal(
            session, topics=[], source=source_key(extra), delta=delta, exam_topic=False, now=now
        )
    return ids
