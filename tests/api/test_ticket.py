"""Tests for one-time action ticket verification (SEC-56, D43)."""

from concurrent.futures import ThreadPoolExecutor

from techradar.api.ticket import ActionTicket, TicketStore, create_ticket


def test_ticket_verification_success() -> None:
    secret_key = b"super-secret-key-32-bytes-long!!"
    payload = {"doc_id": 42, "reason": "user_approved"}
    action = "quarantine.release"
    now = 1_000_000.0

    ticket = create_ticket(
        action=action,
        payload=payload,
        secret_key=secret_key,
        ttl_s=60.0,
        created_at=now,
    )

    store = TicketStore()
    assert isinstance(ticket, ActionTicket)
    assert ticket.action == action
    assert ticket.created_at == now
    assert ticket.expires_at == now + 60.0

    # Consume at created_at + 10s (well within 60s window)
    consumed = store.consume_ticket(
        ticket=ticket,
        action=action,
        payload=payload,
        secret_key=secret_key,
        now=now + 10.0,
    )
    assert consumed is True
    assert store.is_consumed(ticket.ticket_id) is True


def test_ticket_expires() -> None:
    secret_key = b"super-secret-key-32-bytes-long!!"
    payload = {"item_id": 101}
    action = "quarantine.delete"
    created_at = 2_000_000.0
    ttl = 60.0

    ticket = create_ticket(
        action=action,
        payload=payload,
        secret_key=secret_key,
        ttl_s=ttl,
        created_at=created_at,
    )

    store = TicketStore()

    # Consuming past expires_at (now > expires_at) must fail
    expired_now = ticket.expires_at + 1.0
    result = store.consume_ticket(
        ticket=ticket,
        action=action,
        payload=payload,
        secret_key=secret_key,
        now=expired_now,
    )
    assert result is False
    assert store.is_consumed(ticket.ticket_id) is False


def test_ticket_runs_once() -> None:
    secret_key = b"super-secret-key-32-bytes-long!!"
    payload = {"setting": "dark_mode", "value": True}
    action = "settings.update"
    now = 3_000_000.0

    ticket = create_ticket(
        action=action,
        payload=payload,
        secret_key=secret_key,
        ttl_s=60.0,
        created_at=now,
    )

    store = TicketStore()

    # First consumption succeeds
    first_attempt = store.consume_ticket(
        ticket=ticket,
        action=action,
        payload=payload,
        secret_key=secret_key,
        now=now + 5.0,
    )
    assert first_attempt is True

    # Replay with same ticket fails
    second_attempt = store.consume_ticket(
        ticket=ticket,
        action=action,
        payload=payload,
        secret_key=secret_key,
        now=now + 6.0,
    )
    assert second_attempt is False

    # Third attempt also fails
    third_attempt = store.consume_ticket(
        ticket=ticket,
        action=action,
        payload=payload,
        secret_key=secret_key,
        now=now + 7.0,
    )
    assert third_attempt is False


def test_tampered_payload_rejected() -> None:
    secret_key = b"super-secret-key-32-bytes-long!!"
    original_payload = {"account": "user1", "amount": 100}
    tampered_payload = {"account": "user1", "amount": 9999}
    action = "payment.approve"
    now = 4_000_000.0

    ticket = create_ticket(
        action=action,
        payload=original_payload,
        secret_key=secret_key,
        ttl_s=60.0,
        created_at=now,
    )

    store = TicketStore()

    # Consuming with tampered payload returns False
    result = store.consume_ticket(
        ticket=ticket,
        action=action,
        payload=tampered_payload,
        secret_key=secret_key,
        now=now + 1.0,
    )
    assert result is False
    assert store.is_consumed(ticket.ticket_id) is False

    # Original payload still can be consumed since tampered call didn't consume it
    valid_result = store.consume_ticket(
        ticket=ticket,
        action=action,
        payload=original_payload,
        secret_key=secret_key,
        now=now + 2.0,
    )
    assert valid_result is True


def test_tampered_signature_rejected() -> None:
    secret_key = b"super-secret-key-32-bytes-long!!"
    payload = {"id": 1}
    action = "test.action"
    now = 5_000_000.0

    ticket = create_ticket(
        action=action,
        payload=payload,
        secret_key=secret_key,
        ttl_s=60.0,
        created_at=now,
    )

    # Forged signature
    forged_ticket = ticket.model_copy(update={"signature": "0" * 64})
    store = TicketStore()

    assert (
        store.consume_ticket(
            ticket=forged_ticket,
            action=action,
            payload=payload,
            secret_key=secret_key,
            now=now + 1.0,
        )
        is False
    )


def test_tampered_action_rejected() -> None:
    secret_key = b"super-secret-key-32-bytes-long!!"
    payload = {"id": 1}
    action = "quarantine.release"
    now = 6_000_000.0

    ticket = create_ticket(
        action=action,
        payload=payload,
        secret_key=secret_key,
        ttl_s=60.0,
        created_at=now,
    )

    store = TicketStore()

    assert (
        store.consume_ticket(
            ticket=ticket,
            action="quarantine.delete",
            payload=payload,
            secret_key=secret_key,
            now=now + 1.0,
        )
        is False
    )


def test_wrong_secret_key_rejected() -> None:
    key_a = b"key-a-32-bytes-long-super-secret"
    key_b = b"key-b-32-bytes-long-super-secret"
    payload = {"doc_id": 5}
    action = "doc.read"
    now = 7_000_000.0

    ticket = create_ticket(
        action=action,
        payload=payload,
        secret_key=key_a,
        ttl_s=60.0,
        created_at=now,
    )

    store = TicketStore()

    assert (
        store.consume_ticket(
            ticket=ticket,
            action=action,
            payload=payload,
            secret_key=key_b,
            now=now + 1.0,
        )
        is False
    )


def test_payload_key_order_independence() -> None:
    secret_key = b"super-secret-key-32-bytes-long!!"
    action = "test.canonical"
    now = 8_000_000.0

    # Payload with keys in one order
    ticket = create_ticket(
        action=action,
        payload={"zebra": 1, "alpha": 2, "nested": {"b": 2, "a": 1}},
        secret_key=secret_key,
        ttl_s=60.0,
        created_at=now,
    )

    store = TicketStore()

    # Consuming with keys inserted in different order
    reordered_payload = {"nested": {"a": 1, "b": 2}, "alpha": 2, "zebra": 1}
    assert (
        store.consume_ticket(
            ticket=ticket,
            action=action,
            payload=reordered_payload,
            secret_key=secret_key,
            now=now + 1.0,
        )
        is True
    )


def test_concurrent_consumption_thread_safety() -> None:
    secret_key = b"super-secret-key-32-bytes-long!!"
    action = "action.concurrent"
    payload = {"job_id": 999}
    now = 9_000_000.0

    ticket = create_ticket(
        action=action,
        payload=payload,
        secret_key=secret_key,
        ttl_s=60.0,
        created_at=now,
    )

    store = TicketStore()

    def attempt_consume() -> bool:
        return store.consume_ticket(
            ticket=ticket,
            action=action,
            payload=payload,
            secret_key=secret_key,
            now=now + 5.0,
        )

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda _: attempt_consume(), range(20)))

    # Exactly one thread succeeds, the remaining 19 fail (replay protection under concurrency)
    assert results.count(True) == 1
    assert results.count(False) == 19
