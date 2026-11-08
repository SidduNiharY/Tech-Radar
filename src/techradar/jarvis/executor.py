from __future__ import annotations

import re
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel


class TicketExecutionError(PermissionError, ValueError):
    """Raised when an action cannot be executed due to an unconfirmed or expired ticket."""


class SpokenTicket(BaseModel):
    """Spoken confirmation ticket with strict expiry window (SEC-56)."""

    ticket_id: str
    action: str
    created_at: datetime
    expires_at: datetime
    confirmed: bool = False

    def is_expired(self, now: datetime | None = None) -> bool:
        """Check whether the ticket has exceeded its expiration time."""
        current_time = now if now is not None else datetime.now(UTC)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)

        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)

        return current_time > exp


_AFFIRMATIVE_WORDS: frozenset[str] = frozenset(
    {"yes", "confirm", "proceed", "yeah", "yep", "sure", "affirmative", "approved", "ok", "okay"}
)

_AFFIRMATIVE_PHRASES: tuple[str, ...] = (
    "go ahead",
    "do it",
    "confirm it",
    "proceed with it",
)

_NEGATIVE_WORDS: frozenset[str] = frozenset(
    {"no", "stop", "cancel", "abort", "deny", "negative", "dont", "never", "reject"}
)

_NEGATIVE_PHRASES: tuple[str, ...] = (
    "do not",
    "don't",
    "never mind",
    "nevermind",
    "no way",
)


def evaluate_spoken_response(spoken_response: str) -> bool:
    """Evaluate whether a spoken response represents explicit confirmation.

    Returns True only for affirmative responses ('yes', 'confirm', 'proceed', 'go ahead').
    Returns False for negative ('no', 'stop', 'cancel'), ambiguous, or empty responses.
    Negative expressions always take precedence.
    """
    cleaned = spoken_response.strip().lower()
    if not cleaned:
        return False

    # 1. Check multi-word negative phrases
    for phrase in _NEGATIVE_PHRASES:
        if phrase in cleaned:
            return False

    # 2. Tokenize words
    tokens = re.sub(r"[^\w\s]", " ", cleaned).split()

    # 3. Check individual negative words
    for token in tokens:
        if token in _NEGATIVE_WORDS:
            return False

    # 4. Check multi-word affirmative phrases
    for phrase in _AFFIRMATIVE_PHRASES:
        if phrase in cleaned:
            return True

    # 5. Check individual affirmative words
    for token in tokens:
        if token in _AFFIRMATIVE_WORDS:
            return True

    return False


class SpokenActionExecutor:
    """Evaluates and enforces 10-second spoken confirmation tickets for actions (SEC-56)."""

    def __init__(self) -> None:
        self._tickets: dict[str, SpokenTicket] = {}
        self._executed_ticket_ids: set[str] = set()
        self._lock = threading.Lock()

    def create_spoken_ticket(
        self,
        action: str,
        validity_seconds: float = 10.0,
    ) -> SpokenTicket:
        """Generate a spoken confirmation ticket with a strict 10-second expiry window (SEC-56)."""
        ticket_id = uuid.uuid4().hex
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=validity_seconds)

        ticket = SpokenTicket(
            ticket_id=ticket_id,
            action=action,
            created_at=now,
            expires_at=expires_at,
            confirmed=False,
        )
        with self._lock:
            self._tickets[ticket_id] = ticket
        return ticket

    def confirm_ticket(
        self,
        ticket_id: str,
        spoken_response: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Confirm a ticket with spoken response if within the validity window.

        Explicit affirmative responses ("yes", "confirm", "proceed", "go ahead")
        within the 10s window confirm the ticket. Negative ("no", "stop", "cancel")
        or expired attempts fail.
        """
        current_time = now if now is not None else datetime.now(UTC)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)

        with self._lock:
            ticket = self._tickets.get(ticket_id)
            if ticket is None:
                return False

            # Cannot confirm if already executed
            if ticket.ticket_id in self._executed_ticket_ids:
                return False

            # Check expiration
            if ticket.is_expired(current_time):
                return False

            # Evaluate response
            if evaluate_spoken_response(spoken_response):
                ticket.confirmed = True
                return True
            else:
                ticket.confirmed = False
                return False

    def execute_action(
        self,
        ticket: SpokenTicket,
        action_fn: Callable[[], Any],
        *,
        now: datetime | None = None,
    ) -> Any:
        """Execute action_fn only if ticket is valid and confirmed (SEC-56 single-use)."""
        current_time = now if now is not None else datetime.now(UTC)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)

        with self._lock:
            stored = self._tickets.get(ticket.ticket_id)
            is_confirmed = ticket.confirmed or (stored is not None and stored.confirmed)
            if not is_confirmed:
                raise TicketExecutionError(f"Ticket '{ticket.ticket_id}' has not been confirmed.")

            if ticket.is_expired(current_time):
                raise TicketExecutionError(f"Ticket '{ticket.ticket_id}' has expired.")

            if ticket.ticket_id in self._executed_ticket_ids:
                raise TicketExecutionError(
                    f"Ticket '{ticket.ticket_id}' has already been executed."
                )

            self._executed_ticket_ids.add(ticket.ticket_id)
            if stored is not None:
                stored.confirmed = True

        return action_fn()

    def get_ticket(self, ticket_id: str) -> SpokenTicket | None:
        """Retrieve stored ticket by ID."""
        with self._lock:
            return self._tickets.get(ticket_id)
