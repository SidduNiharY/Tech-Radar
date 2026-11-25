"""Story bank: a STAR interview-story state machine over `story_drafts` (Phase 6 Task 8).

The state lives in Postgres (one open draft per chat), never in memory. The finished story is
a `stories` row and, when a vault is given, `stories/<slug>-<id>.md`.

SEC: SEC-15, SEC-18, SEC-26.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Story, StoryDraft
from techradar.pipeline.writer import md_escape, slugify, write_note
from techradar.security.text import sanitize_text

STAR_FIELDS = ("situation", "task", "action", "result")
MAX_FIELD_CHARS = 600

PROMPTS = {
    "situation": "Situation? (what was happening)",
    "task": "Task? (what you had to do)",
    "action": "Action? (what you did)",
    "result": "Result? (what happened, with a number if you can)",
}


async def open_draft(session: AsyncSession, chat_id: int) -> StoryDraft | None:
    """The chat's unfinished draft, if any (the bot asks this to send plain replies here)."""
    return (
        (
            await session.execute(
                select(StoryDraft)
                .where(StoryDraft.chat_id == chat_id, StoryDraft.story_id.is_(None))
                .order_by(StoryDraft.id.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


def story_path(title: str, story_id: int) -> PurePosixPath:
    return PurePosixPath(f"stories/{slugify(title, 60)}-{story_id}.md")


async def story_step(
    session: AsyncSession,
    chat_id: int,
    text: str | None,
    vault_root: Path | None = None,
) -> str:
    """`/story` (text None) starts over; each reply fills the next field; the last one saves."""
    draft = await open_draft(session, chat_id)

    if text is None or draft is None:
        await session.execute(
            delete(StoryDraft).where(StoryDraft.chat_id == chat_id, StoryDraft.story_id.is_(None))
        )
        init: dict[str, Any] = {"step": 0, **{f: "" for f in STAR_FIELDS}}
        session.add(StoryDraft(chat_id=chat_id, content=json.dumps(init)))
        await session.commit()
        return PROMPTS["situation"]

    data = json.loads(draft.content)
    step = int(data.get("step", 0))
    data[STAR_FIELDS[step]] = sanitize_text(text)[:MAX_FIELD_CHARS]

    if step < len(STAR_FIELDS) - 1:
        data["step"] = step + 1
        draft.content = json.dumps(data)
        await session.commit()
        return PROMPTS[STAR_FIELDS[step + 1]]

    title = data["situation"][:40].strip() or "STAR story"
    body = "\n\n".join(f"**{f.capitalize()}:** {md_escape(data[f])}" for f in STAR_FIELDS)
    story = Story(title=title, category="interview", body=body)
    session.add(story)
    await session.flush()
    draft.story_id = story.id
    draft.content = json.dumps(data)
    await session.commit()

    if vault_root is not None:
        write_note(vault_root, story_path(title, story.id), f"# {md_escape(title)}\n\n{body}\n")
    return f"Saved your story: {title}."
