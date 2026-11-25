"""Morning greeting with at most three suggestions (Phase 12 Task 9).

Everything is read from Postgres (today's briefing, due cards, revisions, topic mastery, topic
sources, topic weights) and one row is written: today's `jarvis_greetings` row.

WIRING(claude): `Suggestion.call` is a plain `{"skill": ..., "args": {...}}` dict until the
router's `SkillCall` exists (Task 2). `GET /v1/jarvis/greeting` (api-voice, Task 4) reads
`jarvis_greetings`, adds the device to `shown_devices`, and uses `is_quiet_hours` so that
voice-live does not speak a greeting in quiet hours. Accepting a `no_source` suggestion is
the `jarvis.keep_source` write and needs a ticket (Task 3).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import (
    Briefing,
    JarvisGreeting,
    Revision,
    SyllabusTopic,
    TopicMastery,
    TopicSource,
    UserSettings,
    Weight,
)
from techradar.feedback.weights import is_favourite
from techradar.hostsec.alerts import parse_quiet_hours
from techradar.practice.flashcards import due_cards
from techradar.schemas.pipeline import NoLinks

SuggestionKind = Literal[
    "news", "due_cards", "revision", "weak_topic", "no_source", "outside_usual"
]

DEFAULT_QUIET_HOURS = "23:00-06:00"
QUIET_HOURS_KEY = "jarvis_quiet_hours"
LIMIT = 3
LEVELS = ["new", "learning", "exam_ready", "mastered"]
# The order the plan sets: exam news, then due cards and revisions, a weak topic, a topic with
# no source. "outside_usual" is not in it: it gets a slot only on its own days.
PRIORITY: tuple[SuggestionKind, ...] = ("news", "due_cards", "revision", "weak_topic", "no_source")


class Suggestion(BaseModel):
    kind: SuggestionKind
    text: Annotated[NoLinks, Field(min_length=1, max_length=160)]
    call: dict[str, Any] | None = None


class Greeting(BaseModel):
    opening: Annotated[NoLinks, Field(min_length=1, max_length=60)]
    suggestions: list[Suggestion] = Field(default_factory=list, max_length=LIMIT)


# --- choosing and rendering (pure) ----------------------------------------------------------


def outside_usual_day(day: date) -> bool:
    """One day in every ten is an "outside the usual" day (so 1 greeting in 10 has one)."""
    return day.toordinal() % 10 == 0


def choose_suggestions(
    candidates: Sequence[Suggestion],
    *,
    limit: int = LIMIT,
    include_outside_usual: bool = False,
) -> list[Suggestion]:
    """At most `limit`, in priority order; on an outside-usual day one slot goes to that kind."""
    limit = max(0, min(limit, LIMIT))
    outside = next((c for c in candidates if c.kind == "outside_usual"), None)
    ranked = [c for kind in PRIORITY for c in candidates if c.kind == kind]
    if include_outside_usual and outside is not None and limit > 0:
        return [*ranked[: limit - 1], outside]
    return ranked[:limit]


def render_greeting(g: Greeting) -> str:
    n = len(g.suggestions)
    if n == 0:
        return f"{g.opening} Nothing urgent today. What do you want to start with?"
    words = {1: "One thing", 2: "Two things", 3: "Three things"}
    lines = "\n".join(f"{i}. {s.text}" for i, s in enumerate(g.suggestions, 1))
    return f"{g.opening} {words[n]} today:\n{lines}\nWhat do you want to start with?"


def opening_for(now: datetime) -> str:
    hour = now.hour
    if hour < 12:
        return "Good morning."
    if hour < 17:
        return "Good afternoon."
    return "Good evening."


# --- quiet hours ----------------------------------------------------------------------------


def is_quiet_hours(now_local: datetime, quiet: tuple[time, time]) -> bool:
    """`quiet` is (start, end); a range that crosses midnight (23:00-06:00) is handled."""
    start, end = quiet
    t = now_local.time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end


async def load_quiet_hours(session: AsyncSession) -> tuple[time, time]:
    """The `jarvis_quiet_hours` setting ("HH:MM-HH:MM"); the default when unset or malformed."""
    row = await session.get(UserSettings, QUIET_HOURS_KEY)
    raw = row.value if row and isinstance(row.value, str) else DEFAULT_QUIET_HOURS
    try:
        return parse_quiet_hours(raw)
    except ValueError, IndexError:
        return parse_quiet_hours(DEFAULT_QUIET_HOURS)


# --- candidates from the database -----------------------------------------------------------


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


async def collect_candidates(session: AsyncSession, now: datetime) -> list[Suggestion]:
    today = now.date()
    out: list[Suggestion] = []

    briefing = (
        await session.execute(select(Briefing).where(Briefing.date == today))
    ).scalar_one_or_none()
    items = [i for i in (briefing.items or []) if isinstance(i, dict)] if briefing else []

    exam_news = [i for i in items if i.get("exam_tags")]
    if exam_news:
        out.append(
            Suggestion(
                kind="news",
                text=f"{_plural(len(exam_news), 'news story is', 'news stories are')} "
                "relevant to your exams.",
                call={"skill": "news", "args": {}},
            )
        )

    due = await due_cards(session, now)
    if due:
        out.append(
            Suggestion(
                kind="due_cards",
                text=f"{_plural(len(due), 'flashcard is', 'flashcards are')} due.",
                call={"skill": "quiz", "args": {"kind": "cards"}},
            )
        )

    revisions = (
        await session.execute(
            select(func.count())
            .select_from(Revision)
            .where(Revision.due_date <= today, Revision.done_at.is_(None))
        )
    ).scalar_one()
    if revisions:
        out.append(
            Suggestion(
                kind="revision",
                text=f"{_plural(revisions, 'revision is', 'revisions are')} due today.",
                call={"skill": "plan", "args": {"op": "read"}},
            )
        )

    fell = (
        await session.execute(select(TopicMastery).where(TopicMastery.prev_level.is_not(None)))
    ).scalars()
    worst: tuple[int, str] | None = None
    for r in fell:
        if r.level in LEVELS and r.prev_level in LEVELS:
            drop = LEVELS.index(r.prev_level) - LEVELS.index(r.level)
            if drop > 0 and (worst is None or drop > worst[0]):
                worst = (drop, r.topic)
    if worst:
        out.append(
            Suggestion(
                kind="weak_topic",
                text=f"{worst[1]} has slipped since last week. Want a quick practice?",
                call={"skill": "progress", "args": {}},
            )
        )

    # A topic that has no confirmed source but has a suggested one.
    confirmed = select(TopicSource.topic_id).where(TopicSource.status == "confirmed")
    row = (
        await session.execute(
            select(SyllabusTopic.topic, TopicSource.label)
            .join(TopicSource, TopicSource.topic_id == SyllabusTopic.id)
            .where(TopicSource.status == "suggested", SyllabusTopic.id.not_in(confirmed))
            .order_by(SyllabusTopic.id, TopicSource.id)
            .limit(1)
        )
    ).first()
    if row:
        out.append(
            Suggestion(
                kind="no_source",
                text=f"{row[0]} has no material yet. Add {row[1]}?",
                call={"skill": "exams", "args": {"op": "progress"}},
            )
        )

    # A story from outside what I usually read (weight below 1 or no history), not exam news.
    weights = {
        w.key: w.value
        for w in (await session.execute(select(Weight).where(Weight.kind == "topic"))).scalars()
    }
    outside = _first_outside_usual(items, weights)
    if outside is not None:
        out.append(
            Suggestion(
                kind="outside_usual",
                text=f"Something different: a {outside} story you don't usually read.",
                call={"skill": "news", "args": {"section": outside}},
            )
        )
    return out


def _first_outside_usual(
    items: Sequence[Mapping[str, Any]], weights: Mapping[str, float]
) -> str | None:
    for item in items:
        section = item.get("section")
        if not isinstance(section, str) or item.get("exam_tags"):
            continue
        if not is_favourite({"topic": section}, weights):
            return section
    return None


# --- the job body ---------------------------------------------------------------------------


async def run_prepare_greeting(session: AsyncSession, now: datetime) -> Greeting | None:
    """Store today's greeting once. Returns it, or `None` when nothing was stored:

    - in quiet hours (`jarvis_quiet_hours`, default 23:00-06:00): nobody is greeted at night,
      and the next tick tries again;
    - before the briefing exists: there is nothing to greet with yet;
    - when today's greeting is already stored (the job is safe to repeat).

    `now` is the owner's local time.
    """
    if is_quiet_hours(now, await load_quiet_hours(session)):
        return None
    today = now.date()
    if await session.get(JarvisGreeting, today) is not None:
        return None
    if (await session.execute(select(Briefing.id).where(Briefing.date == today))).first() is None:
        return None
    greeting = Greeting(
        opening=opening_for(now),
        suggestions=choose_suggestions(
            await collect_candidates(session, now),
            include_outside_usual=outside_usual_day(today),
        ),
    )
    await session.execute(
        pg_insert(JarvisGreeting)
        .values(date=today, greeting=greeting.model_dump(mode="json"), shown_devices=[])
        .on_conflict_do_nothing(index_elements=["date"])
    )
    return greeting


__all__ = [
    "Greeting",
    "Suggestion",
    "choose_suggestions",
    "collect_candidates",
    "is_quiet_hours",
    "load_quiet_hours",
    "outside_usual_day",
    "render_greeting",
    "run_prepare_greeting",
]
