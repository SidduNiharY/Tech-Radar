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
