"""Story timelines: every note about one entity in date order, built by code (Phase 7 Task 4).

No model is involved. A timeline is a list of links to the entity's news notes, so there is
nothing to ground; the only outside text is the note titles, which are cleaned before they
go inside a `[[link|title]]`.

SEC: SEC-28, SEC-37, SEC-38.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Item, Note, RawItem
from techradar.db.models import Timeline as TimelineRow
from techradar.night.grounding import safe_slug
from techradar.pipeline.writer import write_note
from techradar.security.text import sanitize_text

MIN_STORIES = 3
MAX_TIMELINES = 50
TITLE_CHARS = 160
_LINK_BREAKERS = re.compile(r"[\[\]|#^<>]")


class ClusterRow(BaseModel):
    """One written news story: when, what, where its note is, and the entities it names."""

    model_config = ConfigDict(frozen=True)

    cluster_id: int
    date: date
    title: str
    note_path: str
    entities: list[str]


class TimelineEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    title: str
    note_path: str


def entity_key(entity: str) -> str:
    return " ".join(entity.split()).casefold()


def timeline_entries(clusters: Sequence[ClusterRow], entity: str) -> list[TimelineEntry]:
    """Entries for the stories that name `entity`, oldest first (ties by title)."""
    key = entity_key(entity)
    entries = [
        TimelineEntry(date=c.date, title=c.title, note_path=c.note_path)
        for c in clusters
        if key in {entity_key(e) for e in c.entities}
    ]
    entries.sort(key=lambda e: (e.date, e.title.casefold()))
    return entries


def timeline_entities(clusters: Iterable[ClusterRow], min_stories: int = MIN_STORIES) -> list[str]:
    """Entities with at least `min_stories` stories, busiest first, in their common spelling."""
    spellings: dict[str, Counter[str]] = defaultdict(Counter)
    stories: Counter[str] = Counter()
    for c in clusters:
        for name in {entity_key(e): e.strip() for e in c.entities if e.strip()}.items():
            stories[name[0]] += 1
            spellings[name[0]][name[1]] += 1
    keys = [k for k, n in stories.items() if n >= min_stories]
    keys.sort(key=lambda k: (-stories[k], k))
    return [spellings[k].most_common(1)[0][0] for k in keys]


def _link_title(title: str) -> str:
    cleaned = " ".join(_LINK_BREAKERS.sub(" ", sanitize_text(title)).split())
    return cleaned[:TITLE_CHARS].strip() or "Story"


def _link_path(note_path: str) -> str:
    """A vault path that is safe inside `[[...]]`, or '' (then the title is shown unlinked)."""
    path = PurePosixPath(note_path)
    if (
        not note_path
        or path.is_absolute()
        or ".." in path.parts
        or _LINK_BREAKERS.search(note_path)
    ):
        return ""
    return str(path.with_suffix("")) if path.suffix == ".md" else str(path)


def render_timeline(entity: str, entries: Sequence[TimelineEntry]) -> str:
    """The timeline page: front matter and one line per story."""
    front = yaml.safe_dump(
        {"kind": "timeline", "entity": entity, "generated": True},
        sort_keys=False,
        allow_unicode=True,
    )
    shown = _link_title(entity)
    lines = [f"---\n{front}---", "", f"# Timeline: {shown}", ""]
    for e in entries:
        title, link = _link_title(e.title), _link_path(e.note_path)
        lines.append(f"- **{e.date.isoformat()}**: " + (f"[[{link}|{title}]]" if link else title))
    return "\n".join(lines) + "\n"


def timeline_rel_path(entity: str) -> str:
    return f"timelines/{safe_slug(entity)}.md"


async def cluster_rows(session: AsyncSession, *, tz: str) -> list[ClusterRow]:
    """Every written, unflagged news story with a note: its day, title, note and entities."""
    zone = ZoneInfo(tz)
    stmt = (
        select(
            Item.cluster_id,
            Note.title,
            Note.vault_path,
            func.coalesce(RawItem.published_at, RawItem.fetched_at, Note.written_at),
            Item.reader_json,
        )
        .join(RawItem, RawItem.id == Item.raw_item_id)
        .join(Note, Note.cluster_id == Item.cluster_id)
        .where(
            Item.status == "written",
            func.cardinality(Item.flags) == 0,
            Note.kind == "news",
        )
    )
    by_cluster: dict[int, dict] = {}
    for cluster_id, title, path, when, reader_json in (await session.execute(stmt)).all():
        names = reader_json.get("entities") if isinstance(reader_json, dict) else None
        day = (when if isinstance(when, datetime) else datetime.now(zone)).astimezone(zone).date()
        row = by_cluster.setdefault(
            cluster_id, {"title": title, "path": path, "day": day, "entities": set()}
        )
        row["day"] = min(row["day"], day)
        if isinstance(names, list):
            row["entities"].update(n.strip() for n in names if isinstance(n, str) and n.strip())
    return [
        ClusterRow(
            cluster_id=cid,
            date=r["day"],
            title=r["title"],
            note_path=r["path"],
            entities=sorted(r["entities"]),
        )
        for cid, r in sorted(by_cluster.items())
    ]


class TimelineResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    written: list[str]


async def run_timelines(
    session: AsyncSession, *, tz: str, vault_root: Path, limit: int = MAX_TIMELINES
) -> TimelineResult:
    """Regenerate the timeline page of every entity with enough stories; the caller commits."""
    clusters = await cluster_rows(session, tz=tz)
    written: list[str] = []
    for entity in timeline_entities(clusters)[:limit]:
        rel = timeline_rel_path(entity)
        write_note(
            vault_root,
            PurePosixPath(rel),
            render_timeline(entity, timeline_entries(clusters, entity)),
        )
        await session.merge(TimelineRow(entity=entity_key(entity), vault_path=rel))
        written.append(entity)
    await session.flush()
    return TimelineResult(written=written)
