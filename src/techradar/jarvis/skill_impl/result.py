"""What a read skill hands back: the words to speak and a few plain hints for the router."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from techradar.voice_live.briefs import SessionBrief

MAX_SAY = 1200  # the same cap as the plan's `SkillResult.say`


@dataclass(frozen=True)
class SkillReply:
    """`say` is spoken; the rest are hints (the real `SkillResult` comes with the router, Task 3).

    Read skills never write, so there is no pending change here.
    """

    say: str
    list_len: int | None = None
    slow: bool = False
    practice: str | None = None
    brief: SessionBrief | None = None
    quiz: dict[str, Any] | None = None
    doc_id: int | None = None

    def __post_init__(self) -> None:
        if len(self.say) > MAX_SAY:
            object.__setattr__(self, "say", self.say[: MAX_SAY - 1].rstrip() + "…")
