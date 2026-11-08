from __future__ import annotations

from datetime import UTC, datetime, timedelta

from techradar.planner.catchup import CatchupEngine, QueuedTask


def test_queued_task_defaults():
    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    task = QueuedTask(id="task-1", task_type="sync_feed", scheduled_at=now)
    assert task.id == "task-1"
    assert task.task_type == "sync_feed"
    assert task.scheduled_at == now
    assert task.priority == 1
    assert task.payload == {}


def test_detect_missed_tasks_empty():
    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    assert CatchupEngine.detect_missed_tasks([], now) == []


def test_detect_missed_tasks_filters_future_tasks():
    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    past_task = QueuedTask(
        id="past-1",
        task_type="digest",
        scheduled_at=now - timedelta(hours=2),
    )
    future_task = QueuedTask(
        id="future-1",
        task_type="digest",
        scheduled_at=now + timedelta(hours=2),
    )

    missed = CatchupEngine.detect_missed_tasks([past_task, future_task], now)
    assert len(missed) == 1
    assert missed[0].id == "past-1"


def test_detect_missed_tasks_exact_match_included():
    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    exact_task = QueuedTask(id="exact-1", task_type="crawl", scheduled_at=now)
    missed = CatchupEngine.detect_missed_tasks([exact_task], now)
    assert len(missed) == 1
    assert missed[0].id == "exact-1"


def test_detect_missed_tasks_sorting_by_priority():
    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    t_low = QueuedTask(
        id="low-pri",
        task_type="backup",
        scheduled_at=now - timedelta(hours=1),
        priority=1,
    )
    t_high = QueuedTask(
        id="high-pri",
        task_type="alert",
        scheduled_at=now - timedelta(hours=1),
        priority=5,
    )
    t_med = QueuedTask(
        id="med-pri",
        task_type="report",
        scheduled_at=now - timedelta(hours=1),
        priority=3,
    )

    missed = CatchupEngine.detect_missed_tasks([t_low, t_high, t_med], now)
    assert [t.id for t in missed] == ["high-pri", "med-pri", "low-pri"]


def test_detect_missed_tasks_sorting_by_scheduled_at_ascending():
    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    t_newer = QueuedTask(
        id="newer",
        task_type="sync",
        scheduled_at=now - timedelta(minutes=10),
        priority=1,
    )
    t_older = QueuedTask(
        id="older",
        task_type="sync",
        scheduled_at=now - timedelta(minutes=50),
        priority=1,
    )

    missed = CatchupEngine.detect_missed_tasks([t_newer, t_older], now)
    assert [t.id for t in missed] == ["older", "newer"]


def test_detect_missed_tasks_priority_takes_precedence_over_time():
    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    t_recent_high = QueuedTask(
        id="recent-high",
        task_type="quiz",
        scheduled_at=now - timedelta(minutes=5),
        priority=10,
    )
    t_ancient_low = QueuedTask(
        id="ancient-low",
        task_type="cleanup",
        scheduled_at=now - timedelta(days=2),
        priority=1,
    )

    missed = CatchupEngine.detect_missed_tasks([t_ancient_low, t_recent_high], now)
    assert [t.id for t in missed] == ["recent-high", "ancient-low"]


def test_detect_missed_tasks_batch_capping_thundering_herd():
    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    tasks = [
        QueuedTask(
            id=f"task-{i}",
            task_type="eval",
            scheduled_at=now - timedelta(minutes=i + 1),
            priority=i,
        )
        for i in range(10)
    ]

    # Default cap is 5
    missed_default = CatchupEngine.detect_missed_tasks(tasks, now)
    assert len(missed_default) == 5
    # Should be priorities 9, 8, 7, 6, 5
    assert [t.id for t in missed_default] == [
        "task-9",
        "task-8",
        "task-7",
        "task-6",
        "task-5",
    ]

    # Custom cap
    missed_custom = CatchupEngine.detect_missed_tasks(tasks, now, max_catchup_limit=3)
    assert len(missed_custom) == 3
    assert [t.id for t in missed_custom] == ["task-9", "task-8", "task-7"]


def test_detect_missed_tasks_zero_and_negative_limit():
    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    task = QueuedTask(
        id="t1",
        task_type="sync",
        scheduled_at=now - timedelta(hours=1),
    )
    assert CatchupEngine.detect_missed_tasks([task], now, max_catchup_limit=0) == []
    assert CatchupEngine.detect_missed_tasks([task], now, max_catchup_limit=-3) == []


def test_detect_missed_tasks_mixed_timezone_naive_and_aware():
    now_aware = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
    # Naive datetime 1 hour prior
    naive_past = datetime(2026, 11, 8, 11, 0)
    task = QueuedTask(
        id="t-naive",
        task_type="worker",
        scheduled_at=naive_past,
    )
    missed = CatchupEngine.detect_missed_tasks([task], now_aware)
    assert len(missed) == 1
    assert missed[0].id == "t-naive"
