from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Story, StoryDraft

STAR_FIELDS = ("situation", "task", "action", "result")


async def story_step(session: AsyncSession, chat_id: int, text: str | None) -> str:
    """State machine guiding the user through the STAR storytelling framework."""
    # Find active draft for this chat
    stmt = select(StoryDraft).where(StoryDraft.story_id.is_(None)).order_by(StoryDraft.id.desc())
    res = await session.execute(stmt)
    draft = res.scalars().first()

    if text is None or draft is None:
        init_data: dict[str, Any] = {
            "chat_id": chat_id,
            "step": 0,
            "situation": "",
            "task": "",
            "action": "",
            "result": "",
        }
        draft = StoryDraft(content=json.dumps(init_data))
        session.add(draft)
        await session.commit()
        return "Situation? (what was happening)"

    data = json.loads(draft.content)
    step = data.get("step", 0)

    if step == 0:
        data["situation"] = text[:600]
        data["step"] = 1
        draft.content = json.dumps(data)
        await session.commit()
        return "Task? (what you had to do)"

    elif step == 1:
        data["task"] = text[:600]
        data["step"] = 2
        draft.content = json.dumps(data)
        await session.commit()
        return "Action? (what you did)"

    elif step == 2:
        data["action"] = text[:600]
        data["step"] = 3
        draft.content = json.dumps(data)
        await session.commit()
        return "Result? (what happened, with a number if you can)"

    else:
        # Step 3 -> complete
        data["result"] = text[:600]
        title = data.get("situation", "Interview Story")[:40].strip() or "STAR Story"
        body = (
            f"**Situation:** {data.get('situation')}\n\n"
            f"**Task:** {data.get('task')}\n\n"
            f"**Action:** {data.get('action')}\n\n"
            f"**Result:** {data.get('result')}"
        )

        story = Story(
            title=title,
            category="interview",
            body=body,
        )
        session.add(story)
        await session.flush()

        draft.story_id = story.id
        draft.content = json.dumps(data)
        await session.commit()

        return f"Saved your story: {title}."
