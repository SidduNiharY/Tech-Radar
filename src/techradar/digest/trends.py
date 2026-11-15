"""Trending topics detection, velocity/momentum ranking, and digest generation."""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from pydantic import BaseModel, Field


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
