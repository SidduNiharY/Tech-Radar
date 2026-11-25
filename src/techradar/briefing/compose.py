from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Briefing as BriefingModel
from techradar.db.models import Item, Note
from techradar.feedback.signals import TargetKind, feedback_buttons
from techradar.feedback.weights import (
    load_weights,
    mean_weight,
    pick_outside_usual,
    score,
    source_key,
    story_topic_keys,
)
from techradar.messaging.outbox import Button, enqueue_message
from techradar.pipeline.verify import headline_ok
from techradar.schemas.pipeline import ReaderOutput, Section

SECTION_ORDER = [
    Section.TECH,
    Section.INDIA,
    Section.WORLD,
    Section.ECONOMY,
    Section.SCIENCE,
    Section.DAILY_LIFE,
]


class StoryCandidate(BaseModel):
    cluster_id: str
    title: str
    section: Section
    exam_tags: list[str] = Field(default_factory=list)
    why: str = ""
    how_it_affects_me: str = ""
    domains: set[str] = Field(default_factory=set)
    verified_headline: bool = False
    relevance: float = 0.5
    # --- Phase 11: what the learned weights need (filled by load_candidates) ---
    topic_keys: list[str] = Field(default_factory=list)
    source_keys: list[str] = Field(default_factory=list)
    score: float = 0.0


def select_items(
    cands: Sequence[StoryCandidate],
    official: frozenset[str],
    *,
    per_section: int = 3,
    max_items: int = 15,
    weights: Mapping[str, float] | None = None,
) -> list[StoryCandidate]:
    """Selects and caps stories for the daily briefing.

    - Drops a politics story unless `headline_ok` (3 or more domains, D7).
    - Sorts by (verified_headline desc, score desc), where score is relevance times the
      learned topic and source weights (Phase 11, D46); with no weights, score is relevance.
    - Caps at per_section per section, and at most max_items total.
    - Keeps an outside-usual slot: at least 10% of the chosen come from topics with weight below
      1 or no history, never replacing an exam-tagged story.
    """
    w = weights or {}
    for c in cands:  # the learned score, kept on the story for the outside-usual step
        c.score = score(c.relevance, mean_weight(c.topic_keys, w), mean_weight(c.source_keys, w))
    valid = [
        c
        for c in cands
        if c.section is not Section.POLITICS or headline_ok(c.domains, c.section, official)
    ]

    sorted_cands = sorted(
        valid,
        key=lambda c: (c.verified_headline, c.score),
        reverse=True,
    )

    selected: list[StoryCandidate] = []
    section_counts: dict[Section | str, int] = defaultdict(int)
    for c in sorted_cands:
        if len(selected) >= max_items:
            break
        if section_counts[c.section] < per_section:
            selected.append(c)
            section_counts[c.section] += 1

    if w:
        selected = pick_outside_usual(sorted_cands, selected, w)
    return selected


def story_feedback_rows(message: str, items: Sequence[StoryCandidate]) -> list[list[Button]]:
    """One feedback row per story that this message shows (Phase 11 Task 2).

    Each button starts with the story's first words, so the row says which story it is about.
    """
    rows: list[list[Button]] = []
    for it in items:
        if f"• {it.title} " not in message or not it.cluster_id.isdigit():
            continue
        tag = it.title[:10].strip()
        row = [b for r in feedback_buttons(TargetKind.DIGEST_ITEM, int(it.cluster_id)) for b in r]
        rows.append(
            [
                Button(text=f"{b.text} {tag}"[:32] if i == 0 else b.text, data=b.data)
                for i, b in enumerate(row)
            ]
        )
    return rows


class Briefing(BaseModel):
    date: date
    items: list[StoryCandidate]
    plan_lines: list[str] = Field(default_factory=list)


def _format_item(item: StoryCandidate) -> str:
    status = "✅" if item.verified_headline else "⚠️"
    lines = [
        f"• {item.title} {status}",
        f"  Why: {item.why}",
        f"  For me: {item.how_it_affects_me}",
    ]
    if item.exam_tags:
        lines.append(f"  Tags: {', '.join(str(t) for t in item.exam_tags)}")
    return "\n".join(lines)


def _split_section(text: str, max_chars: int = 4096) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current_chunk = ""

    parts = text.split("\n\n")
    for part in parts:
        if not part:
            continue
        if len(part) > max_chars:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            lines = part.split("\n")
            line_chunk = ""
            for line in lines:
                if len(line) > max_chars:
                    if line_chunk:
                        chunks.append(line_chunk)
                        line_chunk = ""
                    for i in range(0, len(line), max_chars):
                        chunks.append(line[i : i + max_chars])
                elif len(line_chunk) + len(line) + 1 <= max_chars:
                    line_chunk = f"{line_chunk}\n{line}" if line_chunk else line
                else:
                    chunks.append(line_chunk)
                    line_chunk = line
            if line_chunk:
                current_chunk = line_chunk
        elif not current_chunk:
            current_chunk = part
        elif len(current_chunk) + 2 + len(part) <= max_chars:
            current_chunk = f"{current_chunk}\n\n{part}"
        else:
            chunks.append(current_chunk)
            current_chunk = part

    if current_chunk:
        chunks.append(current_chunk)

    return chunks if chunks else [text[:max_chars]]


def render_briefing(b: Briefing) -> list[str]:
    """Renders a list of Telegram messages (each <= 4096 characters)."""
    header = f"☀️ Today's Radar · {b.date.strftime('%a')} {b.date.day} {b.date.strftime('%b')}"
    if b.plan_lines:
        header = f"{header}\n\nTODAY'S PLAN\n" + "\n".join(b.plan_lines)

    footer = "Reply to any part of this briefing with your take (one line)."

    seen_sections: list[Section | str] = []
    for s in SECTION_ORDER:
        if any(it.section == s for it in b.items):
            seen_sections.append(s)
    for it in b.items:
        if it.section not in seen_sections:
            seen_sections.append(it.section)

    if not seen_sections:
        return [f"{header}\n\n{footer}"]

    raw_section_messages: list[str] = []
    for idx, sec in enumerate(seen_sections):
        sec_items = [it for it in b.items if it.section == sec]
        items_text = "\n\n".join(_format_item(it) for it in sec_items)
        sec_name = sec.name.upper() if hasattr(sec, "name") else str(sec).upper()
        sec_body = f"{sec_name}\n{items_text}"
        if idx == 0:
            raw_section_messages.append(f"{header}\n\n{sec_body}")
        else:
            raw_section_messages.append(sec_body)

    split_messages: list[str] = []
    for msg in raw_section_messages:
        split_messages.extend(_split_section(msg, max_chars=4096))

    last_msg = split_messages[-1]
    if len(last_msg) + 2 + len(footer) <= 4096:
        split_messages[-1] = f"{last_msg}\n\n{footer}"
    else:
        split_messages.append(footer)

    return split_messages


def briefing_due(
    now_local: datetime,
    last_sent: date | None,
    at: time = time(6, 30),
    grace_s: int = 21600,
) -> bool:
    """True when today's briefing is unsent and `at <= now_local <= at + grace_s`."""
    if last_sent is not None and last_sent == now_local.date():
        return False
    scheduled_dt = datetime.combine(now_local.date(), at, tzinfo=now_local.tzinfo)
    return scheduled_dt <= now_local <= scheduled_dt + timedelta(seconds=grace_s)


class BriefingResult(BaseModel):
    briefing_id: int | None = None
    messages_sent: int = 0
    items_count: int = 0
    skipped_reason: str | None = None


async def load_candidates(
    session: AsyncSession,
    official: frozenset[str],
    now: datetime,
    *,
    window_h: int = 24,
) -> list[StoryCandidate]:
    """Stories written in the last `window_h` hours: one candidate per cluster."""
    notes = (
        await session.execute(
            select(Note)
            .where(Note.cluster_id.is_not(None), Note.written_at >= now - timedelta(hours=window_h))
            .order_by(Note.id.desc())
        )
    ).scalars()
    cands: list[StoryCandidate] = []
    for note in notes:
        items = (
            (
                await session.execute(
                    select(Item)
                    .where(Item.cluster_id == note.cluster_id, Item.status == "written")
                    .order_by(Item.id.desc())
                )
            )
            .scalars()
            .all()
        )
        reader = next((it.reader_json for it in items if it.reader_json), None)
        if reader is None:
            continue
        try:
            out = ReaderOutput.model_validate(reader)
        except ValueError:
            continue
        domains = {it.domain for it in items}
        relevance = max((it.relevance for it in items if it.relevance is not None), default=0.5)
        cands.append(
            StoryCandidate(
                cluster_id=str(note.cluster_id),
                title=note.title,
                section=out.section,
                exam_tags=[str(t.value) for t in out.exam_tags],
                why=out.four_questions.why,
                how_it_affects_me=out.four_questions.how_it_affects_me,
                domains=domains,
                verified_headline=headline_ok(domains, out.section, official),
                relevance=relevance,
                topic_keys=story_topic_keys(str(out.section.value), out.entities),
                source_keys=sorted(source_key(d) for d in domains),
            )
        )
    return cands


async def run_briefing(
    session: AsyncSession,
    *,
    now: datetime,
    owner_chat_id: int,
    candidates: Sequence[StoryCandidate] | None = None,
    official_domains: frozenset[str] = frozenset(),
    at_time: time = time(6, 30),
    grace_s: int = 21600,
    plan_lines: list[str] | None = None,
) -> BriefingResult:
    """Body of briefing_job. `now` is local time. Checks due, composes, enqueues, records."""
    last_sent = (
        await session.execute(
            select(BriefingModel.date).order_by(BriefingModel.date.desc()).limit(1)
        )
    ).scalar_one_or_none()

    if not briefing_due(now, last_sent, at_time, grace_s):
        return BriefingResult(skipped_reason="not_due")

    if candidates is None:
        candidates = await load_candidates(session, official_domains, now)
    weights = await load_weights(session, now)
    selected = select_items(list(candidates), official_domains, weights=weights)

    briefing_obj = Briefing(date=now.date(), items=selected, plan_lines=plan_lines or [])

    # Phase 4: the web's Today screen reads the stories from briefings.items.
    briefing_row = BriefingModel(
        date=now.date(), sent_at=now, items=[c.model_dump(mode="json") for c in selected]
    )
    session.add(briefing_row)
    await session.flush()

    messages = render_briefing(briefing_obj)
    for msg in messages:
        await enqueue_message(
            session,
            chat_id=owner_chat_id,
            text=msg,
            purpose="briefing",
            buttons=story_feedback_rows(msg, selected) or None,
            ref_id=briefing_row.id,
        )

    return BriefingResult(
        briefing_id=briefing_row.id,
        messages_sent=len(messages),
        items_count=len(selected),
    )
