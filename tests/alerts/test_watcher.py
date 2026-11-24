from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from techradar.alerts.watcher import (
    ChangeEvent,
    PollResult,
    clean_exam_notice_title,
    is_alert_sent,
    record_and_enqueue_alert,
    render_alert,
    run_exam_poll,
)
from techradar.db.models import Alert, ExamWatch, Outbox


class FakeAsyncSession:
    """In-memory async session for testing alerts without requiring live Postgres."""

    def __init__(self) -> None:
        self.watches: list[ExamWatch] = []
        self.alerts: list[Alert] = []
        self.outbox: list[Outbox] = []
        self.added: list[object] = []
        self._next_id = 1

    def add(self, obj: object) -> None:
        self.added.append(obj)
        if isinstance(obj, ExamWatch):
            if not getattr(obj, "id", None):
                obj.id = self._next_id
                self._next_id += 1
            self.watches.append(obj)
        elif isinstance(obj, Alert):
            if not getattr(obj, "id", None):
                obj.id = self._next_id
                self._next_id += 1
            self.alerts.append(obj)
        elif isinstance(obj, Outbox):
            if not getattr(obj, "id", None):
                obj.id = self._next_id
                self._next_id += 1
            self.outbox.append(obj)

    async def flush(self) -> None:
        for obj in self.added:
            if not getattr(obj, "id", None):
                obj.id = self._next_id
                self._next_id += 1

    async def execute(self, stmt: object) -> object:
        class FakeResult:
            def __init__(self, items: list[Any]) -> None:
                self.items = items

            def scalar_one_or_none(self) -> Any:
                return self.items[0] if self.items else None

            def all(self) -> list[Any]:
                return self.items

        sql = str(stmt).lower()
        params = stmt.compile().params  # type: ignore[attr-defined]

        if "alerts" in sql:
            w_id = next((v for k, v in params.items() if k.startswith("watch_id")), None)
            c_at = next((v for k, v in params.items() if k.startswith("changed_at")), None)
            matched_alert_ids = [
                a.id
                for a in self.alerts
                if (w_id is None or a.watch_id == w_id) and (c_at is None or a.changed_at == c_at)
            ]
            return FakeResult(matched_alert_ids)

        if "exam_watches" in sql:
            w_uuid = next((v for k, v in params.items() if k.startswith("watch_uuid")), None)
            w_url = next((v for k, v in params.items() if k.startswith("url")), None)
            matched_watches = [
                w
                for w in self.watches
                if (w_uuid is not None and w.watch_uuid == w_uuid)
                or (w_url is not None and w.url == w_url)
            ]
            return FakeResult(matched_watches)

        return FakeResult([])


@pytest.fixture
def session() -> FakeAsyncSession:
    return FakeAsyncSession()


def test_render_alert_uses_configured_title_and_url() -> None:
    event = ChangeEvent(
        watch_uuid="uuid-ssc-123",
        title="SSC notices",
        url="https://ssc.gov.in/notices",
        changed_at=datetime(2026, 11, 15, 10, 0, tzinfo=UTC),
    )
    expected = "📅 Exam update: SSC notices changed. Open: https://ssc.gov.in/notices"
    assert render_alert(event) == expected


def test_clean_exam_notice_title() -> None:
    # 1. Strips HTML tags, scripts, and styles
    dirty_html = "<script>alert('xss')</script><b>SSC CGL 2026 Notice</b><style>body{}</style>"
    assert clean_exam_notice_title(dirty_html) == "SSC CGL 2026 Notice"

    # 2. Strips embedded URLs and external domain references
    with_urls = "GATE 2026 updates at https://evil.com/phish and www.bad-site.org"
    assert clean_exam_notice_title(with_urls) == "GATE 2026 updates at and"

    # 3. Strips trailing dates with various separators and formats
    assert (
        clean_exam_notice_title("IBPS RRB Officer Scale I - 15/11/2026")
        == "IBPS RRB Officer Scale I"
    )
    assert (
        clean_exam_notice_title("UPSC Civil Services Prelims (15-11-2026)")
        == "UPSC Civil Services Prelims"
    )
    assert (
        clean_exam_notice_title("SBI PO Interview Schedule [Dated: 15.11.2026]")
        == "SBI PO Interview Schedule"
    )
    assert clean_exam_notice_title("GATE 2026 Admit Card dt. 15/11/2026") == "GATE 2026 Admit Card"
    assert clean_exam_notice_title("SSC CHSL Notification - 15 Nov 2026") == "SSC CHSL Notification"
    assert clean_exam_notice_title("RBI Grade B Results (2026-11-15)") == "RBI Grade B Results"

    # 4. Preserves exam years that are part of the exam name itself
    assert (
        clean_exam_notice_title("SSC CGL 2026 Tier 1 Exam Date Announced")
        == "SSC CGL 2026 Tier 1 Exam Date Announced"
    )

    # 5. Collapses excessive whitespace and strips trailing noise
    messy_spaces = "  Multiple   spaces \n\n and \t tabs  -- "
    assert clean_exam_notice_title(messy_spaces) == "Multiple spaces and tabs"
    assert clean_exam_notice_title("") == ""
    assert clean_exam_notice_title("   ") == ""


def test_indian_exam_titles_and_language_characters() -> None:
    # Hindi (Devanagari) script preservation
    hindi_title = "कर्मचारी चयन आयोग - संयुक्त स्नातक स्तर परीक्षा - 15/11/2026"
    assert clean_exam_notice_title(hindi_title) == "कर्मचारी चयन आयोग - संयुक्त स्नातक स्तर परीक्षा"

    # Telugu script preservation
    telugu_title = "ఆంధ్రప్రదేశ్ పబ్లిక్ సర్వీస్ కమిషన్ గ్రూప్ 1 నోటిఫికేషన్ (2026-11-15)"
    assert clean_exam_notice_title(telugu_title) == "ఆంధ్రప్రదేశ్ పబ్లిక్ సర్వీస్ కమిషన్ గ్రూప్ 1 నోటిఫికేషన్"

    # Major Indian exams (SSC CGL, IBPS RRB, GATE, UPSC)
    exams = [
        (
            "SSC CGL 2026 Final Answer Key - 10/11/2026",
            "SSC CGL 2026 Final Answer Key",
        ),
        (
            "IBPS RRB XII Officer Scale-I Reserve List (05-11-2026)",
            "IBPS RRB XII Officer Scale-I Reserve List",
        ),
        (
            "GATE 2026 Information Brochure Released [2026-11-01]",
            "GATE 2026 Information Brochure Released",
        ),
        (
            "UPSC Combined Geo-Scientist Exam 2026 dt: 12.11.2026",
            "UPSC Combined Geo-Scientist Exam 2026",
        ),
    ]
    for raw, expected in exams:
        assert clean_exam_notice_title(raw) == expected


@pytest.mark.asyncio
async def test_is_alert_sent_deduplication(session: FakeAsyncSession) -> None:
    t1 = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)

    # Initial check: no alert recorded
    assert not await is_alert_sent(session, watch_id=1, changed_at=t1)

    # Record an alert for watch 1 at t1
    alert = Alert(watch_id=1, changed_at=t1)
    session.add(alert)
    await session.flush()

    # Now watch 1 at t1 is already sent
    assert await is_alert_sent(session, watch_id=1, changed_at=t1)

    # Different watch id is not sent
    assert not await is_alert_sent(session, watch_id=2, changed_at=t1)

    # Different changed_at timestamp is not sent
    assert not await is_alert_sent(session, watch_id=1, changed_at=t2)


@pytest.mark.asyncio
async def test_record_and_enqueue_alert(session: FakeAsyncSession) -> None:
    event = ChangeEvent(
        watch_uuid="uuid-ssc",
        title="SSC CGL 2026",
        url="https://ssc.gov.in/cgl",
        changed_at=datetime(2026, 11, 15, 10, 0, tzinfo=UTC),
    )
    owner_chat_id = 123456789

    # 1. First record and enqueue should succeed
    alert_id = await record_and_enqueue_alert(
        session,
        watch_id=1,
        event=event,
        owner_chat_id=owner_chat_id,
    )
    assert alert_id is not None
    assert isinstance(alert_id, int)

    # Verify Alert was saved in session
    assert len(session.alerts) == 1
    saved_alert = session.alerts[0]
    assert saved_alert.id == alert_id
    assert saved_alert.watch_id == 1
    assert saved_alert.changed_at == event.changed_at
    assert saved_alert.sent_at is None

    # Verify Outbox message was enqueued
    assert len(session.outbox) == 1
    outbox_msg = session.outbox[0]
    assert outbox_msg.chat_id == owner_chat_id
    assert outbox_msg.purpose == "alert"
    assert outbox_msg.ref_id == alert_id
    assert outbox_msg.text == render_alert(event)

    # 2. Second record and enqueue with same event should be skipped (idempotent deduplication)
    second_id = await record_and_enqueue_alert(
        session,
        watch_id=1,
        event=event,
        owner_chat_id=owner_chat_id,
    )
    assert second_id is None
    # No duplicate alerts or outbox messages
    assert len(session.alerts) == 1
    assert len(session.outbox) == 1


@pytest.mark.asyncio
async def test_run_exam_poll(session: FakeAsyncSession) -> None:
    now = datetime(2026, 11, 15, 10, 30, tzinfo=UTC)
    owner_chat_id = 987654321

    events = [
        ChangeEvent(
            watch_uuid="uuid-gate",
            title="GATE 2026 Schedule",
            url="https://gate2026.iitk.ac.in",
            changed_at=datetime(2026, 11, 15, 10, 0, tzinfo=UTC),
        ),
        ChangeEvent(
            watch_uuid="uuid-ibps",
            title="IBPS RRB Updates",
            url="https://ibps.in/rrb",
            changed_at=datetime(2026, 11, 15, 10, 15, tzinfo=UTC),
        ),
    ]

    for uuid, title, url in (
        ("uuid-gate", "GATE 2026 Schedule", "https://gate2026.iitk.ac.in"),
        ("uuid-ibps", "IBPS RRB Updates", "https://ibps.in/rrb"),
    ):
        session.add(ExamWatch(title=title, url=url, watch_uuid=uuid))
    await session.flush()

    # First poll: both events should be processed and alerted
    result = await run_exam_poll(
        session,
        now=now,
        events=events,
        owner_chat_id=owner_chat_id,
    )
    assert isinstance(result, PollResult)
    assert result.events_count == 2
    assert result.alerts_sent == 2
    assert result.alerts_skipped == 0
    assert len(result.alert_ids) == 2
    assert len(session.alerts) == 2
    assert len(session.outbox) == 2

    # Second poll with same events: both should be skipped
    result2 = await run_exam_poll(
        session,
        now=now,
        events=events,
        owner_chat_id=owner_chat_id,
    )
    assert result2.events_count == 2
    assert result2.alerts_sent == 0
    assert result2.alerts_skipped == 2
    assert len(result2.alert_ids) == 0
    # Still only 2 alerts and 2 outbox messages
    assert len(session.alerts) == 2
    assert len(session.outbox) == 2


@pytest.mark.asyncio
async def test_event_for_unconfigured_watch_is_dropped(session: FakeAsyncSession) -> None:
    event = ChangeEvent(
        watch_uuid="uuid-unknown",
        title="Click here: win a prize",
        url="https://evil.example/x",
        changed_at=datetime(2026, 11, 15, 10, 0, tzinfo=UTC),
    )
    result = await run_exam_poll(
        session, now=datetime(2026, 11, 15, 10, 30, tzinfo=UTC), events=[event], owner_chat_id=1
    )
    assert result.alerts_sent == 0 and result.alerts_skipped == 1
    assert session.watches == [] and session.alerts == [] and session.outbox == []
