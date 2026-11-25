from __future__ import annotations

from typing import Any

import pytest

from techradar.english.stories import story_step


@pytest.mark.db
async def test_story_state_machine(session: Any) -> None:
    assert await story_step(session, 42, None) == "Situation? (what was happening)"
    for t in ["S", "T", "A"]:
        await story_step(session, 42, t)
    assert (await story_step(session, 42, "Cut load time by 40%")).startswith("Saved your story")


@pytest.mark.db
async def test_story_drafts_are_per_chat_and_written_to_the_vault(
    session: Any, tmp_path: Any
) -> None:
    await story_step(session, 1, None)
    await story_step(session, 2, None)
    await story_step(session, 1, "chat one situation")
    await story_step(session, 2, "chat two situation")
    for t in ["T", "A"]:
        await story_step(session, 1, t, tmp_path)
    reply = await story_step(session, 1, "Cut load time by 40%", tmp_path)
    assert reply == "Saved your story: chat one situation."
    assert len(list((tmp_path / "stories").glob("chat-one-situation-*.md"))) == 1
    assert await story_step(session, 2, "T") == "Action? (what you did)"
