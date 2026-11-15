# WIRING(claude): worker/tasks.py needs exam_poll_job (queue io, every 30m) calling run_exam_poll.
from __future__ import annotations

import html
import re
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Alert, ExamWatch
from techradar.messaging.outbox import enqueue_message
from techradar.security.text import sanitize_text

TRAILING_DATE_RE = re.compile(
    r"[-–—|:/,]?\s*"
    r"(?:"
    r"[\(\[]\s*(?:(?:dt\.?|dated|date)\s*[:.-]?\s*)?"
    r"(?:"
    r"\d{1,2}[-/.–]\d{1,2}[-/.–]\d{2,4}"
    r"|\d{4}[-/.–]\d{1,2}[-/.–]\d{1,2}"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+[,\s]+\d{2,4}"
    r"|[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?[,\s]+\d{2,4}"
    r")\s*[\)\]]"
    r"|"
    r"(?:(?:dt\.?|dated|date)\s*[:.-]?\s*)?"
    r"(?:"
    r"\d{1,2}[-/.–]\d{1,2}[-/.–]\d{2,4}"
    r"|\d{4}[-/.–]\d{1,2}[-/.–]\d{1,2}"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[,\s]+\d{2,4}"
    r")"
    r")\s*$",
    re.IGNORECASE,
)


def clean_exam_notice_title(title: str) -> str:
    """Clean noise, trailing dates, and excessive whitespace from an exam notice headline.

    Preserves Indian language characters and exam acronyms (e.g. SSC CGL, IBPS RRB, GATE, UPSC)
    while stripping scripts, styles, raw HTML tags, embedded URLs, and trailing dates.
    """
    if not title:
        return ""

    text = html.unescape(title)
    # Strip script, style, and iframe tags along with their contents
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<iframe[^>]*>.*?</iframe>", " ", text)
    # Strip all remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Strip embedded URLs from notice headline
    text = re.sub(r"(?i)\b(?:https?://|www\.|javascript:)\S+", "", text)
    # Strip external domain references from notice headline
    text = re.sub(
        r"(?i)\b[a-zA-Z0-9.-]+\.(?:com|org|net|io|site|xyz|info|biz|co|cc|online)\b/?\S*",
        "",
        text,
    )
    # Strip angle brackets to prevent any HTML tag reconstruction
    text = text.replace("<", "").replace(">", "")
    # Sanitize unicode control/bidi characters while preserving Indic scripts
    text = sanitize_text(text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Strip trailing dates
    text = TRAILING_DATE_RE.sub("", text)
    # Strip trailing separator noise
    text = text.rstrip(" -–—|:/,")
    # Collapse whitespace again after date/separator removal
    return re.sub(r"\s+", " ", text).strip()


class ChangeEvent(BaseModel):
    """Change event detected on a monitored exam watch target."""

    watch_uuid: str
    title: str
    url: str
    changed_at: datetime


def render_alert(e: ChangeEvent) -> str:
    """Render plain-text exam alert message for Telegram outbox.

    Title and URL come strictly from the ChangeEvent (configured exam_watches row),
    never from unvetted page body.
    """
    return f"📅 Exam update: {e.title} changed. Open: {e.url}"


async def is_alert_sent(
    session: AsyncSession,
    watch_id: int,
    changed_at: datetime,
) -> bool:
    """Check if an alert for this watch and timestamp has already been recorded/sent."""
    stmt = (
        select(Alert.id)
        .where(
            Alert.watch_id == watch_id,
            Alert.changed_at == changed_at,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def record_and_enqueue_alert(
    session: AsyncSession,
    watch_id: int,
    event: ChangeEvent,
    owner_chat_id: int,
) -> int | None:
    """Record an Alert row in the database and enqueue to outbox with purpose='alert'.

    Ref_id is set to alert.id. Returns the new Alert id, or None if already sent.
    """
    if await is_alert_sent(session, watch_id, event.changed_at):
        return None

    alert = Alert(
        watch_id=watch_id,
        changed_at=event.changed_at,
        sent_at=None,
    )
    session.add(alert)
    await session.flush()

    text = render_alert(event)
    await enqueue_message(
        session,
        owner_chat_id,
        text,
        purpose="alert",
        ref_id=alert.id,
    )
    return alert.id


class PollResult(BaseModel):
    """Summary of an exam poll run."""

    events_count: int = 0
    alerts_sent: int = 0
    alerts_skipped: int = 0
    alert_ids: list[int] = Field(default_factory=list)


async def run_exam_poll(
    session: AsyncSession,
    *,
    now: datetime,
    events: list[ChangeEvent],
    owner_chat_id: int,
) -> PollResult:
    """Process incoming change events, deduplicate, record alerts, and enqueue to outbox.

    Title and URL used in the alert message come strictly from the configured exam_watches row.
    """
    alerts_sent = 0
    alerts_skipped = 0
    alert_ids: list[int] = []

    for event in events:
        stmt = select(ExamWatch).where(
            (ExamWatch.watch_uuid == event.watch_uuid) | (ExamWatch.url == event.url)
        )
        result = await session.execute(stmt)
        watch = result.scalar_one_or_none()

        if watch is None:
            clean_title = clean_exam_notice_title(event.title)
            watch = ExamWatch(
                title=clean_title,
                url=event.url,
                watch_uuid=event.watch_uuid,
            )
            session.add(watch)
            await session.flush()

        # Title and URL come strictly from exam_watches row
        configured_event = ChangeEvent(
            watch_uuid=watch.watch_uuid,
            title=watch.title,
            url=watch.url,
            changed_at=event.changed_at,
        )

        alert_id = await record_and_enqueue_alert(
            session,
            watch.id,
            configured_event,
            owner_chat_id,
        )
        if alert_id is not None:
            alerts_sent += 1
            alert_ids.append(alert_id)
        else:
            alerts_skipped += 1

    return PollResult(
        events_count=len(events),
        alerts_sent=alerts_sent,
        alerts_skipped=alerts_skipped,
        alert_ids=alert_ids,
    )
