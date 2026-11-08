from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from techradar.ops.alerts import (
    ALERT_WINDOW,
    AlertStore,
    alert_on_failure,
    raise_alert,
)

NOW = datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_alert_deduplicated_within_window():
    store = AlertStore()
    # First alert succeeds
    assert await raise_alert(store, 42, "job:x", "⚠️ Job x failed", NOW) is True
    # Alert within window is suppressed
    within_window = NOW + timedelta(hours=5)
    assert await raise_alert(store, 42, "job:x", "⚠️ Job x failed", within_window) is False
    # Different key is NOT suppressed
    assert await raise_alert(store, 42, "job:y", "⚠️ Job y failed", NOW + timedelta(hours=5)) is True
    # Alert after window succeeds
    assert await raise_alert(store, 42, "job:x", "⚠️ Job x failed", NOW + timedelta(hours=7)) is True


@pytest.mark.asyncio
async def test_alert_window_constant():
    assert ALERT_WINDOW == timedelta(hours=6)


@pytest.mark.asyncio
async def test_alert_text_has_no_exception_message():
    store = AlertStore()

    @alert_on_failure("demo", store=store, owner_chat_id=123, now_fn=lambda: NOW)
    async def failing_job():
        raise ValueError("super_secret_token_12345")

    with pytest.raises(ValueError):
        await failing_job()

    assert len(store.enqueued) == 1
    alert = store.enqueued[0]
    assert alert["key"] == "job:demo"
    assert alert["text"] == "⚠️ Job demo failed: ValueError"
    assert "super_secret_token_12345" not in alert["text"]
