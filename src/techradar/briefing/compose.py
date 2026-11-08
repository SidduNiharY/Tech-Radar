from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel, Field

from techradar.schemas.pipeline import Section

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


def select_items(
    cands: Sequence[StoryCandidate],
    official_domains: frozenset[str],
    *,
    per_section: int = 3,
    max_items: int = 15,
) -> list[StoryCandidate]:
    """Selects and caps stories for the daily briefing.

    - For Section.INDIA / politics: requires 3 or more distinct domains
      unless from official domains.
    - Sorts by (verified_headline desc, relevance desc).
    - Caps at per_section per section, and at most max_items total.
    """
    valid: list[StoryCandidate] = []
    for c in cands:
        if c.section in (Section.INDIA, Section.POLITICS, "india", "politics"):
            has_official = bool(c.domains & official_domains)
            if not (has_official or len(c.domains) >= 3):
                continue
        valid.append(c)

    sorted_cands = sorted(
        valid,
        key=lambda c: (c.verified_headline, c.relevance),
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

    return selected


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
    at_time: time | None = None,
    grace_s: int = 21600,
    *,
    at: time | None = None,
) -> bool:
    """Returns True if not sent today AND now_local >= at_time AND within grace_s."""
    if last_sent is not None and last_sent == now_local.date():
        return False
    target_time = at_time if at_time is not None else (at if at is not None else time(6, 30))
    scheduled_dt = datetime.combine(now_local.date(), target_time, tzinfo=now_local.tzinfo)
    deadline_dt = scheduled_dt + timedelta(seconds=grace_s)
    return scheduled_dt <= now_local <= deadline_dt
