"""The ten read-only Jarvis skills and a plain registry from skill name to function.

Every function is `async def run(session, now, **args) -> SkillReply` and only SELECTs.
Everything that changes data (plan add/move/remove, mark a chapter read, saving a teach
session, recording quiz answers, keeping a source) is a write: it needs a ticket and is not here.

WIRING(claude): the router (Task 2) validates the arguments with its models and calls
`READ_SKILLS[skill.value](session, now, **args)`; `now` is the owner's local time. The
write side of plan, library, teach and quiz goes through `execute` and tickets (Task 3).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from techradar.jarvis.skill_impl import (
    ask,
    coach,
    exams,
    library,
    news,
    plan,
    progress,
    quiz,
    status,
    teach,
)
from techradar.jarvis.skill_impl.result import SkillReply

ReadSkill = Callable[..., Awaitable[SkillReply]]

READ_SKILLS: dict[str, ReadSkill] = {
    "news": news.run,
    "ask": ask.run,
    "teach": teach.run,
    "quiz": quiz.run,
    "plan": plan.run,
    "library": library.run,
    "exams": exams.run,
    "progress": progress.run,
    "coach": coach.run,
    "status": status.run,
}

__all__ = ["READ_SKILLS", "ReadSkill", "SkillReply"]
