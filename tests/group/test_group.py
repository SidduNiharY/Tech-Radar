"""Tests for study group leaderboard maths, privacy hashing, and formatting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from techradar.group.group import (
    GROUP_MESSAGE_KINDS,
    LeaderboardEntry,
    calculate_leaderboard,
    group_allowed,
    leaderboard,
    member_hash,
    render_leaderboard,
)


@dataclass
class MockActivity:
    user_id: str
    display_name: str
    points: int
    completed_at: datetime | None = None


def test_group_kinds_allowlist():
    assert "quiz_poll" in GROUP_MESSAGE_KINDS
    assert "leaderboard" in GROUP_MESSAGE_KINDS
    assert "gd_topic" in GROUP_MESSAGE_KINDS
    assert "arbitrary_spam" not in GROUP_MESSAGE_KINDS


def test_member_hash_stable_and_salted():
    h1 = member_hash(7, "s1")
    h2 = member_hash(7, "s1")
    h3 = member_hash(7, "s2")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_group_allowed():
    allowed_groups = [-1001, -1002]
    assert group_allowed(-1001, allowed_groups) is True
    assert group_allowed(-9999, allowed_groups) is False


def test_calculate_leaderboard_aggregation():
    t1 = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 11, 15, 11, 0, tzinfo=UTC)
    activities = [
        MockActivity(user_id="u1", display_name="Alice", points=10, completed_at=t1),
        MockActivity(user_id="u1", display_name="Alice", points=15, completed_at=t2),
        MockActivity(user_id="u2", display_name="Bob", points=20, completed_at=t1),
    ]
    board = calculate_leaderboard(activities)
    assert len(board) == 2
    # Alice total: 25, Bob total: 20 -> Alice rank 1, Bob rank 2
    assert board[0].user_id == "u1"
    assert board[0].display_name == "Alice"
    assert board[0].points == 25
    assert board[0].rank == 1

    assert board[1].user_id == "u2"
    assert board[1].display_name == "Bob"
    assert board[1].points == 20
    assert board[1].rank == 2


def test_calculate_leaderboard_tie_breaking_by_earliest_completion():
    t_early = datetime(2026, 11, 15, 9, 30, tzinfo=UTC)
    t_late = datetime(2026, 11, 15, 10, 30, tzinfo=UTC)

    # Bob and Alice both have 50 points, but Alice finished earlier
    activities = [
        {"user_id": "u_bob", "display_name": "Bob", "points": 50, "completed_at": t_late},
        {"user_id": "u_alice", "display_name": "Alice", "points": 50, "completed_at": t_early},
    ]
    board = calculate_leaderboard(activities)
    assert len(board) == 2
    assert board[0].user_id == "u_alice"
    assert board[0].rank == 1
    assert board[1].user_id == "u_bob"
    assert board[1].rank == 2


def test_calculate_leaderboard_identical_tie():
    t_same = datetime(2026, 11, 15, 9, 30, tzinfo=UTC)
    activities = [
        MockActivity(user_id="u1", display_name="Alice", points=30, completed_at=t_same),
        MockActivity(user_id="u2", display_name="Bob", points=30, completed_at=t_same),
    ]
    board = calculate_leaderboard(activities)
    assert len(board) == 2
    assert board[0].rank == 1
    assert board[1].rank == 1


def test_calculate_leaderboard_empty():
    assert calculate_leaderboard([]) == []


def test_render_leaderboard():
    entries = [
        LeaderboardEntry(rank=1, user_id="u1", display_name="Alice", points=100),
        LeaderboardEntry(rank=2, user_id="u2", display_name="Bob", points=80),
    ]
    rendered = render_leaderboard(entries)
    assert rendered == "🏆 This week: 1. Alice 100 · 2. Bob 80"


def test_render_leaderboard_empty():
    assert render_leaderboard([]) == "🏆 This week: no activities yet"


def test_leaderboard_from_tuples():
    rows = [("Alice", 100), ("Bob", 80)]
    assert leaderboard(rows) == "🏆 This week: 1. Alice 100 · 2. Bob 80"
    assert leaderboard([]) == "🏆 This week: no activities yet"
