"""One-time confirmation tickets (Phase 4 Task 2b). SEC-56, D43.

Every confirm step (web, Telegram, voice) goes through a ticket in `pending_actions`:

- valid for one exact action and its arguments (`args_hash`), once, for a short time
  (`TTL_S`), and only in the session that asked for it;
- one open ticket per session: a new one cancels the old (also enforced by a partial
  unique index);
- confirming is one conditional UPDATE, so two confirms (two tabs, a replay, a double
  press) can never both succeed; when it fails, one SELECT names the reason;
- `run_confirmed` runs what was stored with the ticket, never anything the client sends,
  and only actions registered in `ACTIONS`.

Functions flush or execute only; the caller commits (with the action, in one transaction).
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import Update, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import PendingAction
from techradar.library.quarantine import delete_action, release_action

Channel = Literal["web", "telegram", "voice"]
TTL_S: dict[str, int] = {"web": 60, "telegram": 60, "voice": 10}
ConfirmResult = Literal[
    "ok", "expired", "used", "wrong_session", "tampered", "cancelled", "unknown"
]
Action = Callable[[AsyncSession, Mapping[str, Any]], Awaitable[str]]

MAX_SUMMARY = 300
MAX_SESSION_ID = 200
MAX_ACTION = 100
_TOKEN = re.compile(r"[0-9a-f]{32}")
_WEB_SESSION = re.compile(r"[A-Za-z0-9_-]{16,64}")


class Ticket(BaseModel):
    """What a caller shows the user: the summary, and when it stops being valid."""

    id: int
    token: str
    summary: str
    expires_at: datetime


# The confirmable actions. Phases 10, 11 and 12 add theirs.
ACTIONS: dict[str, Action] = {
    "quarantine.release": release_action,
    "quarantine.delete": delete_action,
}


def web_session_id(header: str | None) -> str | None:
    """`web:<X-TR-Session>`, the random id of one browser tab, or None when malformed."""
    if not header or not _WEB_SESSION.fullmatch(header):
        return None
    return f"web:{header}"


def tg_session_id(chat_id: int) -> str:
    return f"tg:{chat_id}"


def args_hash(action: str, args: Mapping[str, Any]) -> str:
    payload = json.dumps({"action": action, "args": args}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _check_args(value: Any) -> None:
    """Only values jsonb gives back unchanged: str keys; str, int, bool, None, lists, dicts."""
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError("ticket args keys must be strings")
            _check_args(v)
    elif isinstance(value, list):
        for v in value:
            _check_args(v)
    elif value is not None and not isinstance(value, str | int | bool):
        raise TypeError(f"ticket args cannot hold {type(value).__name__}")


async def create_ticket(
    session: AsyncSession,
    *,
    session_id: str,
    channel: Channel,
    action: str,
    args: Mapping[str, Any],
    summary: str,
    now: datetime,
    starts_at: datetime | None = None,
) -> Ticket:
    """Cancel the session's open ticket, then store a new one. Flushes only."""
    if channel not in TTL_S:
        raise ValueError("unknown channel")
    if not session_id or len(session_id) > MAX_SESSION_ID:
        raise ValueError("bad session id")
    if not action or len(action) > MAX_ACTION:
        raise ValueError("bad action")
    stored_args = dict(args)
    _check_args(stored_args)
    digest = args_hash(action, stored_args)
    await session.execute(
        update(PendingAction)
        .where(
            PendingAction.session_id == session_id,
            PendingAction.used_at.is_(None),
            PendingAction.cancelled_at.is_(None),
        )
        .values(cancelled_at=now)
        .execution_options(synchronize_session=False)
    )
    row = PendingAction(
        token=secrets.token_hex(16),
        session_id=session_id,
        channel=channel,
        action=action,
        args=stored_args,
        args_hash=digest,
        summary=summary[:MAX_SUMMARY],
        created_at=now,
        expires_at=(starts_at or now) + timedelta(seconds=TTL_S[channel]),
    )
    session.add(row)
    await session.flush()
    return Ticket(id=row.id, token=row.token, summary=row.summary, expires_at=row.expires_at)


async def open_window(session: AsyncSession, ticket_id: int, at: datetime) -> None:
    """Start an open ticket's window at `at` (phase 12: when Jarvis finishes speaking)."""
    row = (
        await session.execute(
            select(PendingAction)
            .where(
                PendingAction.id == ticket_id,
                PendingAction.used_at.is_(None),
                PendingAction.cancelled_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.channel not in TTL_S:
        return
    row.expires_at = at + timedelta(seconds=TTL_S[row.channel])
    await session.flush()


def claim_statement(token: str, session_id: str, digest: str, now: datetime) -> Update:
    """The one statement that uses a ticket: every condition in a single UPDATE."""
    return (
        update(PendingAction)
        .where(
            PendingAction.token == token,
            PendingAction.used_at.is_(None),
            PendingAction.cancelled_at.is_(None),
            PendingAction.expires_at > now,
            PendingAction.session_id == session_id,
            PendingAction.args_hash == digest,
        )
        .values(used_at=now)
        .returning(PendingAction.id)
        .execution_options(synchronize_session=False)
    )


async def confirm_ticket(
    session: AsyncSession,
    *,
    token: str,
    session_id: str,
    action: str,
    args: Mapping[str, Any],
    now: datetime,
) -> ConfirmResult:
    """Use the ticket if every condition holds; otherwise say why. Nothing else changes."""
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        return "unknown"
    digest = args_hash(action, args)
    claimed = (
        await session.execute(claim_statement(token, session_id, digest, now))
    ).scalar_one_or_none()
    if claimed is not None:
        return "ok"
    row = (
        await session.execute(
            select(
                PendingAction.session_id,
                PendingAction.used_at,
                PendingAction.cancelled_at,
                PendingAction.expires_at,
                PendingAction.args_hash,
            ).where(PendingAction.token == token)
        )
    ).first()
    if row is None:
        return "unknown"
    if row.session_id != session_id:
        return "wrong_session"  # tells another session nothing more
    if row.used_at is not None:
        return "used"
    if row.cancelled_at is not None:
        return "cancelled"
    if row.args_hash != digest:
        return "tampered"
    return "expired"


async def token_for(session: AsyncSession, ticket_id: int, session_id: str) -> str | None:
    """The token of a ticket of this session (Telegram buttons carry only the id)."""
    return (
        await session.execute(
            select(PendingAction.token).where(
                PendingAction.id == ticket_id, PendingAction.session_id == session_id
            )
        )
    ).scalar_one_or_none()


async def run_confirmed(
    session: AsyncSession,
    token: str,
    session_id: str,
    now: datetime,
    *,
    actions: Mapping[str, Action] = ACTIONS,
) -> tuple[ConfirmResult, str | None]:
    """Confirm the stored action with its stored args, then run it once.

    An action that is not registered is refused ("unknown") and the ticket stays unused.
    """
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        return "unknown", None
    row = (
        await session.execute(
            select(PendingAction.action, PendingAction.args).where(PendingAction.token == token)
        )
    ).first()
    if row is None:
        return "unknown", None
    run = actions.get(row.action)
    if run is None:
        return "unknown", None
    args: Mapping[str, Any] = row.args if isinstance(row.args, dict) else {}
    result = await confirm_ticket(
        session, token=token, session_id=session_id, action=row.action, args=args, now=now
    )
    if result != "ok":
        return result, None
    return "ok", await run(session, args)
