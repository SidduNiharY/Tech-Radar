"""Study group leaderboard calculations, member security, and message rendering."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

GROUP_MESSAGE_KINDS: frozenset[str] = frozenset({"quiz_poll", "leaderboard", "gd_topic"})


@dataclass(frozen=True)
class LeaderboardEntry:
    """A ranked participant in the group leaderboard."""

    rank: int
    user_id: str
    display_name: str
    points: int
    completed_at: datetime | None = None

    @property
    def score(self) -> int:
        return self.points

    @property
    def member_hash(self) -> str:
        return self.user_id

    @property
    def member_id(self) -> str:
        return self.user_id


def member_hash(user_id: int, salt: str) -> str:
    """Return SHA-256 hash of user ID and group salt for privacy."""
    return hashlib.sha256(f"{user_id}{salt}".encode()).hexdigest()


def group_allowed(chat_id: int, allowed: Sequence[int]) -> bool:
    """Check if group chat ID is permitted."""
    return chat_id in allowed


def _extract_activity(item: Any) -> tuple[str, str, int, datetime | None]:
    """Extract user_id, display_name, points, and completion time from an activity object."""
    if isinstance(item, dict):
        user_id = str(item.get("user_id") or item.get("member_hash") or item.get("member_id") or "")
        display_name = str(item.get("display_name") or item.get("name") or user_id)
        raw_pts = item.get("points")
        if raw_pts is None:
            raw_pts = item.get("score", 1)
        points = int(raw_pts)
        completed_at = (
            item.get("completed_at")
            or item.get("timestamp")
            or item.get("sent_at")
            or item.get("created_at")
        )
    else:
        user_id = str(
            getattr(item, "user_id", None)
            or getattr(item, "member_hash", None)
            or getattr(item, "member_id", None)
            or ""
        )
        display_name = str(
            getattr(item, "display_name", None) or getattr(item, "name", None) or user_id
        )
        raw_pts = getattr(item, "points", None)
        if raw_pts is None:
            raw_pts = getattr(item, "score", 1)
        points = int(raw_pts)
        completed_at = (
            getattr(item, "completed_at", None)
            or getattr(item, "timestamp", None)
            or getattr(item, "sent_at", None)
            or getattr(item, "created_at", None)
        )
    return user_id, display_name, points, completed_at


def calculate_leaderboard(activities: Sequence[Any]) -> list[LeaderboardEntry]:
    """Aggregate points, break ties by earliest completion, and assign ranks."""
    if not activities:
        return []

    user_points: dict[str, int] = defaultdict(int)
    user_names: dict[str, str] = {}
    user_completions: dict[str, list[datetime]] = defaultdict(list)

    for act in activities:
        uid, name, pts, comp = _extract_activity(act)
        if not uid:
            continue
        user_points[uid] += pts
        if name:
            user_names[uid] = name
        elif uid not in user_names:
            user_names[uid] = uid
        if comp is not None:
            user_completions[uid].append(comp)

    far_future = datetime.max.replace(tzinfo=UTC)

    def sort_key(uid: str) -> tuple[int, datetime, str]:
        pts = user_points[uid]
        comps = user_completions.get(uid, [])
        earliest = min(comps) if comps else far_future
        return (-pts, earliest, uid)

    sorted_uids = sorted(user_points.keys(), key=sort_key)

    entries: list[LeaderboardEntry] = []
    for i, uid in enumerate(sorted_uids):
        pts = user_points[uid]
        name = user_names.get(uid, uid)
        comps = user_completions.get(uid, [])
        earliest = min(comps) if comps else None

        # Standard ranking: check if identical points and earliest completion
        if i > 0 and entries:
            prev = entries[-1]
            if pts == prev.points and earliest == prev.completed_at:
                rank = prev.rank
            else:
                rank = i + 1
        else:
            rank = 1

        entries.append(
            LeaderboardEntry(
                rank=rank,
                user_id=uid,
                display_name=name,
                points=pts,
                completed_at=earliest,
            )
        )

    return entries


def render_leaderboard(entries: Sequence[LeaderboardEntry], top: int = 5) -> str:
    """Render leaderboard entries as Telegram message text."""
    if not entries:
        return "🏆 This week: no activities yet"
    selected = entries[:top]
    formatted = " · ".join(f"{e.rank}. {e.display_name} {e.points}" for e in selected)
    return f"🏆 This week: {formatted}"


def leaderboard(rows: Sequence[tuple[str, int]], top: int = 5) -> str:
    """Render (display_name, points) rows as leaderboard text."""
    if not rows:
        return "🏆 This week: no activities yet"
    selected = rows[:top]
    formatted = " · ".join(f"{i + 1}. {name} {pts}" for i, (name, pts) in enumerate(selected))
    return f"🏆 This week: {formatted}"
