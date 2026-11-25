"""Trending topics detection, velocity/momentum ranking, and digest generation."""

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Item, TrendCount
from techradar.messaging.outbox import enqueue_message


class TopicTrend(BaseModel):
    """Trending topic statistics including mention counts, velocity, and momentum."""

    topic: str = Field(..., description="Topic or technology term")
    recent_count: int = Field(..., description="Count of mentions in the recent window")
    baseline_count: int = Field(..., description="Count of mentions in the baseline window")
    velocity: float = Field(..., description="Mentions per day in the recent window")
    momentum: float = Field(..., description="Momentum acceleration metric relative to baseline")
    ratio: float = Field(..., description="Ratio of recent velocity to baseline velocity")


class Rising(BaseModel):
    """Phase 10 Rising fast trend data structure."""

    term: str
    today: int
    baseline: float
    ratio: float


def normalise_term(s: str) -> str:
    """Normalise topic/term string: lowercase, strip punctuation and collapse whitespace.

    Supports Unicode characters including Indian scripts (Devanagari, Telugu, etc.)
    and preserves combining marks (viramas, matras).
    """
    s = s.strip().lower()
    # Strip leading punctuation/symbols/whitespace
    while s and unicodedata.category(s[0]).startswith(("P", "S", "Z")):
        s = s[1:]
    # Strip trailing punctuation/symbols/whitespace
    while s and unicodedata.category(s[-1]).startswith(("P", "S", "Z")):
        s = s[:-1]
    # Collapse multiple consecutive whitespace characters
    s = re.sub(r"\s+", " ", s)
    return s


def rising(
    today: Mapping[str, int],
    history: Mapping[str, Sequence[int]],
    *,
    min_count: int = 5,
    ratio: float = 3.0,
    days: int = 14,
) -> list[Rising]:
    """Detect 'Rising fast' terms from today's counts and historical daily frequencies.

    - baseline is the mean of the last `days` in history (0 counts as 1.0).
    - A term qualifies if today >= min_count and today / baseline >= ratio.
    - Returns the top 3 items sorted by ratio descending.
    """
    results: list[Rising] = []

    for term, today_count in today.items():
        if today_count < min_count:
            continue

        term_history = history.get(term, [])
        recent_history = term_history[-days:] if term_history else []

        if recent_history:
            computed_mean = sum(recent_history) / float(len(recent_history))
            baseline = computed_mean if computed_mean > 0 else 1.0
        else:
            baseline = 1.0

        r = today_count / baseline
        if r >= ratio:
            results.append(
                Rising(
                    term=term,
                    today=today_count,
                    baseline=round(baseline, 2),
                    ratio=round(r, 2),
                )
            )

    results.sort(key=lambda item: (item.ratio, item.today), reverse=True)
    return results[:3]


RISING_PURPOSE = "rising"
HISTORY_DAYS = 14


def extract_terms(reader_json: object) -> list[str]:
    """The distinct normalised entities of one processed item (`reader_json["entities"]`)."""
    if not isinstance(reader_json, dict):
        return []
    entities = reader_json.get("entities")
    if not isinstance(entities, list):
        return []
    seen: dict[str, None] = {}
    for entity in entities:
        if not isinstance(entity, str) or len(entity) > 80:
            continue
        term = normalise_term(entity)
        if term:
            seen[term] = None
    return list(seen)


def render_rising(r: Rising) -> str:
    """The Telegram card text for one rising term."""
    term = r.term[:1].upper() + r.term[1:]
    return f"🔥 Rising fast: {term}, {r.today} mentions today vs about {r.baseline:g}/day usually."


def why_question(term: str) -> str:
    """The question the "Why is everyone talking about this?" button asks."""
    return f"Why is everyone talking about {term} this week?"


def why_since(today: date) -> date:
    """Retrieval window for that question: the last 7 days (`RetrieveFilters.since`)."""
    return today - timedelta(days=7)


async def count_day(session: AsyncSession, day: date, tz: str) -> int:
    """Rebuild `trend_counts` for local `day` from the items processed that day.

    A term counts once per item. Safe to run again: the day's rows are replaced.
    """
    zone = ZoneInfo(tz)
    start = datetime.combine(day, datetime.min.time(), tzinfo=zone)
    end = start + timedelta(days=1)
    rows = await session.execute(
        select(Item.reader_json).where(
            Item.status == "done",
            Item.processed_at >= start,
            Item.processed_at < end,
            Item.reader_json.is_not(None),
        )
    )
    counts: Counter[str] = Counter()
    for (reader_json,) in rows:
        counts.update(extract_terms(reader_json))
    await session.execute(delete(TrendCount).where(TrendCount.day == day))
    for term, count in counts.items():
        session.add(TrendCount(day=day, term=term, count=count))
    await session.flush()
    return len(counts)


async def run_trends(session: AsyncSession, today: date, owner_chat_id: int) -> int:
    """Queue one "Rising fast" message per rising term; returns how many were queued.

    Reads `trend_counts` only. The history is zero-filled for days with no row.
    WIRING(claude, later): the `Why is everyone talking about this?` button needs a callback
    in `bot/callbacks.py`; it would run the ask job with `why_question(term)` and
    `RetrieveFilters(since=why_since(today))`. Callback data must be numeric, so a trend id
    (or a short term table) is needed first.
    """
    today_rows = (
        await session.execute(
            select(TrendCount.term, TrendCount.count).where(TrendCount.day == today)
        )
    ).all()
    today_counts = {term: count for term, count in today_rows}
    if not today_counts:
        return 0
    first = today - timedelta(days=HISTORY_DAYS)
    hist_rows = await session.execute(
        select(TrendCount.term, TrendCount.day, TrendCount.count).where(
            TrendCount.day >= first, TrendCount.day < today, TrendCount.term.in_(list(today_counts))
        )
    )
    history: dict[str, list[int]] = {t: [0] * HISTORY_DAYS for t in today_counts}
    for term, day, count in hist_rows:
        history[term][(day - first).days] = count
    sent = 0
    for r in rising(today_counts, history, days=HISTORY_DAYS):
        await enqueue_message(session, owner_chat_id, render_rising(r), purpose=RISING_PURPOSE)
        sent += 1
    return sent


def rank_emerging_topics(
    mentions: Mapping[str, Sequence[datetime]],
    now: datetime,
    *,
    recent_days: int = 1,
    baseline_days: int = 14,
    min_mentions: int = 1,
) -> list[TopicTrend]:
    """Rank emerging topics by mention momentum and velocity.

    Args:
        mentions: Mapping of topic string to sequence of mention datetimes.
        now: Current reference datetime.
        recent_days: Duration of the recent surge window in days (default 1).
        baseline_days: Duration of the preceding baseline window in days (default 14).
        min_mentions: Minimum mentions in recent window to qualify.

    Returns:
        List of TopicTrend objects ranked by momentum descending.
    """
    recent_cutoff = now - timedelta(days=recent_days)
    baseline_cutoff = now - timedelta(days=recent_days + baseline_days)

    trends: list[TopicTrend] = []

    for raw_topic, timestamps in mentions.items():
        topic = normalise_term(raw_topic)
        if not topic:
            continue

        recent_mentions = [dt for dt in timestamps if recent_cutoff <= dt <= now]
        baseline_mentions = [dt for dt in timestamps if baseline_cutoff <= dt < recent_cutoff]

        recent_count = len(recent_mentions)
        if recent_count < min_mentions:
            continue

        baseline_count = len(baseline_mentions)
        velocity = round(recent_count / float(recent_days), 2)
        baseline_daily = baseline_count / float(baseline_days)

        effective_baseline = baseline_daily if baseline_daily > 0 else 1.0
        ratio = round(velocity / effective_baseline, 2)
        # Momentum captures velocity amplified by growth ratio
        momentum = round(velocity * ratio, 2)

        trends.append(
            TopicTrend(
                topic=topic,
                recent_count=recent_count,
                baseline_count=baseline_count,
                velocity=velocity,
                momentum=momentum,
                ratio=ratio,
            )
        )

    # Sort primarily by momentum, secondarily by velocity, then topic name
    trends.sort(key=lambda t: (t.momentum, t.velocity, t.recent_count), reverse=True)
    return trends


def format_trends_digest(trends: Sequence[TopicTrend]) -> str:
    """Format emerging topic trends into a concise digest message for Telegram / briefing.

    Returns an empty string if trends sequence is empty.
    """
    if not trends:
        return ""

    lines = ["🔥 Emerging topic trends:"]
    for t in trends:
        entry = (
            f"• {t.topic}: {t.recent_count} mentions recently "
            f"(velocity: {t.velocity:.1f}/day, momentum: {t.momentum:.1f}x)"
        )
        lines.append(entry)
    return "\n".join(lines)
