from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest

from techradar.ops import alerts
from techradar.ops.alerts import ALERT_WINDOW, alert_on_failure, failure_text, raise_alert

NOW = datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC)


def test_alert_window_constant():
    assert ALERT_WINDOW == timedelta(hours=6)


def test_failure_text_names_the_exception_type_only():
    assert failure_text("demo", ValueError("super_secret_token_12345")) == (
        "⚠️ Job demo failed: ValueError"
    )


def _patch_alerting(monkeypatch):
    """A fake session factory and a recording `raise_alert`; no database."""
    sent: list[tuple[int, str, str]] = []
    commits: list[int] = []

    class FakeSession:
        async def commit(self) -> None:
            commits.append(1)

    @asynccontextmanager
    async def factory():
        yield FakeSession()

    async def fake_raise(session, owner_chat_id, key, text, now):
        sent.append((owner_chat_id, key, text))
        return True

    monkeypatch.setattr(alerts, "raise_alert", fake_raise)
    monkeypatch.setattr(
        alerts, "get_settings", lambda: type("S", (), {"telegram_owner_chat_id": 1})()
    )
    return factory, sent, commits


async def test_alert_text_has_no_exception_message(monkeypatch):
    factory, sent, commits = _patch_alerting(monkeypatch)

    @alert_on_failure("demo", session_factory=factory, owner_chat_id=123, now_fn=lambda: NOW)
    async def failing_job():
        raise ValueError("super_secret_token_12345")

    with pytest.raises(ValueError):
        await failing_job()

    assert sent == [(123, "job:demo", "⚠️ Job demo failed: ValueError")]
    assert commits == [1]
    assert "super_secret_token_12345" not in sent[0][2]


async def test_success_raises_no_alert_and_returns_the_result(monkeypatch):
    factory, sent, _ = _patch_alerting(monkeypatch)

    @alert_on_failure("demo", session_factory=factory, owner_chat_id=1)
    async def ok_job(x):
        return x + 1

    assert await ok_job(1) == 2
    assert sent == []


async def test_a_failing_alert_never_hides_the_job_error(monkeypatch):
    _patch_alerting(monkeypatch)

    def broken():
        raise RuntimeError("database down: password=hunter2")

    @alert_on_failure("demo", session_factory=broken, owner_chat_id=1)
    async def failing_job():
        raise KeyError("original")

    with pytest.raises(KeyError):
        await failing_job()


def test_alert_on_failure_refuses_a_sync_function():
    with pytest.raises(TypeError):
        alert_on_failure("demo")(lambda: None)


@pytest.mark.db
@pytest.mark.asyncio
async def test_alert_deduplicated_within_window(session):
    assert await raise_alert(session, 42, "job:x", "t", NOW) is True
    assert await raise_alert(session, 42, "job:x", "t", NOW + timedelta(hours=5)) is False
    assert await raise_alert(session, 42, "job:y", "t", NOW + timedelta(hours=5)) is True
    assert await raise_alert(session, 42, "job:x", "t", NOW + timedelta(hours=7)) is True
