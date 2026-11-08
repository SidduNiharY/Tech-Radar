from __future__ import annotations

from datetime import UTC, datetime, timedelta

from techradar.fetcher.due import SourceRow, due_sources


def test_due_sources_after_long_sleep():
    now = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
    rows = [
        SourceRow(1, "u", 120, now - timedelta(hours=30), True),
        SourceRow(2, "v", 120, now - timedelta(minutes=10), True),
        SourceRow(3, "w", 120, None, False),
    ]
    assert [r.id for r in due_sources(rows, now)] == [1]


def test_due_sources_never_fetched_is_due():
    now = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
    rows = [
        SourceRow(1, "u", 120, None, True),
        SourceRow(2, "v", 120, None, False),
    ]
    assert [r.id for r in due_sources(rows, now)] == [1]


def test_due_sources_exact_boundary():
    now = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
    # Exactly 120 minutes ago -> should be due
    rows = [
        SourceRow(1, "u", 120, now - timedelta(minutes=120), True),
        SourceRow(2, "v", 120, now - timedelta(minutes=119), True),
    ]
    assert [r.id for r in due_sources(rows, now)] == [1]


def test_due_sources_timezone_naive_compatibility():
    now = datetime(2026, 11, 8, 9, 0)  # naive
    last = datetime(2026, 11, 8, 6, 0, tzinfo=UTC)  # aware
    rows = [
        SourceRow(1, "u", 120, last, True),
    ]
    assert [r.id for r in due_sources(rows, now)] == [1]


def test_due_sources_empty():
    assert due_sources([], datetime.now(UTC)) == []
