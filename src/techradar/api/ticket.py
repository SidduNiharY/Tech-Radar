"""One-time action ticket verification system (SEC-56, D43)."""

import hashlib
import hmac
import json
import secrets
import threading
import time
from typing import Any

from pydantic import BaseModel


class ActionTicket(BaseModel):
    """One-time action confirmation ticket."""

    ticket_id: str
    action: str
    payload_hash: str
    created_at: float
    expires_at: float
    signature: str


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """Compute canonical SHA-256 hash of a payload dictionary."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_signature(
    secret_key: bytes,
    action: str,
    payload_hash: str,
    created_at: float,
    expires_at: float,
) -> str:
    """Compute HMAC-SHA256 signature over action, payload_hash, created_at, expires_at."""
    message = f"{action}:{payload_hash}:{created_at}:{expires_at}".encode()
    return hmac.new(secret_key, message, hashlib.sha256).hexdigest()


def create_ticket(
    action: str,
    payload: dict[str, Any],
    secret_key: bytes,
    ttl_s: float = 60.0,
    *,
    created_at: float | None = None,
    ticket_id: str | None = None,
) -> ActionTicket:
    """Create a new action ticket with TTL and HMAC signature."""
    if created_at is None:
        created_at = time.time()
    expires_at = created_at + ttl_s
    if ticket_id is None:
        ticket_id = secrets.token_hex(16)

    if isinstance(secret_key, str):
        secret_key = secret_key.encode("utf-8")

    payload_hash = compute_payload_hash(payload)
    signature = compute_signature(
        secret_key=secret_key,
        action=action,
        payload_hash=payload_hash,
        created_at=created_at,
        expires_at=expires_at,
    )
    return ActionTicket(
        ticket_id=ticket_id,
        action=action,
        payload_hash=payload_hash,
        created_at=created_at,
        expires_at=expires_at,
        signature=signature,
    )


class TicketStore:
    """State store for tracking and consuming one-time action tickets."""

    def __init__(self) -> None:
        self._consumed_ticket_ids: set[str] = set()
        self._lock = threading.Lock()

    def consume_ticket(
        self,
        ticket: ActionTicket,
        action: str,
        payload: dict[str, Any],
        secret_key: bytes,
        now: float | None = None,
    ) -> bool:
        """Validate and consume a ticket.

        Validation rules:
        1. Signature matches HMAC-SHA256
        2. now <= ticket.expires_at (rejects expired tickets)
        3. Action matches exactly
        4. Payload hash matches payload
        5. Single-use: once consumed, subsequent calls with same ticket_id return False.
        """
        if now is None:
            now = time.time()

        if isinstance(secret_key, str):
            secret_key = secret_key.encode("utf-8")

        # 1. Action matches exactly
        if ticket.action != action:
            return False

        # 2. Payload hash matches payload
        current_payload_hash = compute_payload_hash(payload)
        if not hmac.compare_digest(ticket.payload_hash, current_payload_hash):
            return False

        # 3. Signature matches HMAC-SHA256
        expected_sig = compute_signature(
            secret_key=secret_key,
            action=ticket.action,
            payload_hash=ticket.payload_hash,
            created_at=ticket.created_at,
            expires_at=ticket.expires_at,
        )
        if not hmac.compare_digest(ticket.signature, expected_sig):
            return False

        # 4. Check expiration (now <= ticket.expires_at)
        if now > ticket.expires_at:
            return False

        # 5. Single-use replay protection
        with self._lock:
            if ticket.ticket_id in self._consumed_ticket_ids:
                return False
            self._consumed_ticket_ids.add(ticket.ticket_id)

        return True

    def is_consumed(self, ticket_id: str) -> bool:
        """Check if a ticket ID has already been consumed."""
        with self._lock:
            return ticket_id in self._consumed_ticket_ids

    def reset(self) -> None:
        """Clear all consumed ticket records."""
        with self._lock:
            self._consumed_ticket_ids.clear()
