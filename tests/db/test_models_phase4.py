from __future__ import annotations

import secrets
from datetime import UTC, date, datetime

from techradar.db.models import Briefing, PendingAction, UserSettings


def test_phase4_models_instantiation():
    now = datetime.now(UTC)

    # Briefing with items
    b = Briefing(
        date=date(2026, 11, 15),
        sent_at=now,
        items=[{"cluster_id": 1, "title": "Test briefing"}],
    )
    assert b.date == date(2026, 11, 15)
    assert b.items == [{"cluster_id": 1, "title": "Test briefing"}]

    # UserSettings
    us = UserSettings(
        key="preferences",
        value={"briefing_time": "07:00", "sections": ["tech"]},
        updated_at=now,
    )
    assert us.key == "preferences"
    assert us.value["briefing_time"] == "07:00"

    # PendingAction
    sample_token = secrets.token_hex(16)
    pa = PendingAction(
        token=sample_token,
        session_id="web:tab123",
        channel="web",
        action="release_quarantine",
        args={"item_id": 42},
        args_hash="a" * 64,
        summary="Release item 42 from quarantine",
        expires_at=now,
    )
    assert pa.token == sample_token
    assert pa.channel == "web"
    assert pa.args == {"item_id": 42}
