from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

from techradar.jarvis.executor import (
    SpokenActionExecutor,
    SpokenTicket,
    TicketExecutionError,
    evaluate_spoken_response,
)


def test_evaluate_spoken_response_affirmative():
    affirmative_inputs = [
        "yes",
        "Yes",
        "YES",
        "confirm",
        "Confirm",
        "proceed",
        "go ahead",
        "Go ahead!",
        "Yes, please proceed",
        "yes confirm",
        "yeah",
        "yep",
        "sure",
        "affirmative",
    ]
    for inp in affirmative_inputs:
        assert evaluate_spoken_response(inp) is True, f"Failed for {inp}"


def test_evaluate_spoken_response_negative():
    negative_inputs = [
        "no",
        "No",
        "stop",
        "Stop!",
        "cancel",
        "Cancel that",
        "don't do that",
        "do not proceed",
        "never mind",
        "nevermind",
        "abort",
        "no way",
        "no, stop",
        "no, go ahead",  # Negative overrides affirmative
    ]
    for inp in negative_inputs:
        assert evaluate_spoken_response(inp) is False, f"Expected False for {inp}"


def test_evaluate_spoken_response_ambiguous_or_empty():
    assert evaluate_spoken_response("") is False
    assert evaluate_spoken_response("   ") is False
    assert evaluate_spoken_response("what time is it?") is False
    assert evaluate_spoken_response("banana") is False
    assert evaluate_spoken_response("hello jarvis") is False


def test_create_spoken_ticket_default_10s_expiry():
    executor = SpokenActionExecutor()
    before = datetime.now(UTC)
    ticket = executor.create_spoken_ticket(action="delete_note_42")
    after = datetime.now(UTC)

    assert isinstance(ticket, SpokenTicket)
    assert ticket.action == "delete_note_42"
    assert ticket.confirmed is False
    assert len(ticket.ticket_id) > 0
    assert before <= ticket.created_at <= after

    # Default validity must be 10 seconds (SEC-56)
    delta = ticket.expires_at - ticket.created_at
    assert abs(delta.total_seconds() - 10.0) < 0.1
    assert not ticket.is_expired()


def test_confirm_ticket_with_affirmative_words():
    executor = SpokenActionExecutor()
    ticket = executor.create_spoken_ticket(action="wipe_cache")

    success = executor.confirm_ticket(ticket.ticket_id, "yes, proceed")
    assert success is True

    stored = executor.get_ticket(ticket.ticket_id)
    assert stored is not None
    assert stored.confirmed is True


def test_confirm_ticket_with_negative_words():
    executor = SpokenActionExecutor()
    ticket = executor.create_spoken_ticket(action="drop_table")

    success = executor.confirm_ticket(ticket.ticket_id, "no, cancel that")
    assert success is False

    stored = executor.get_ticket(ticket.ticket_id)
    assert stored is not None
    assert stored.confirmed is False


def test_confirm_nonexistent_ticket_fails():
    executor = SpokenActionExecutor()
    assert executor.confirm_ticket("non-existent-id", "yes") is False


def test_confirm_ticket_expired_rejection():
    executor = SpokenActionExecutor()
    ticket = executor.create_spoken_ticket(action="purge_logs", validity_seconds=0.05)

    time.sleep(0.08)
    assert ticket.is_expired() is True

    success = executor.confirm_ticket(ticket.ticket_id, "yes")
    assert success is False

    stored = executor.get_ticket(ticket.ticket_id)
    assert stored is not None
    assert stored.confirmed is False


def test_confirm_ticket_simulated_future_time():
    executor = SpokenActionExecutor()
    ticket = executor.create_spoken_ticket(action="purge_logs", validity_seconds=10.0)

    # 11 seconds later
    future_time = ticket.created_at + timedelta(seconds=11.0)
    success = executor.confirm_ticket(ticket.ticket_id, "yes", now=future_time)
    assert success is False


def test_execute_action_successful_flow():
    executor = SpokenActionExecutor()
    ticket = executor.create_spoken_ticket(action="delete_index")

    executor.confirm_ticket(ticket.ticket_id, "go ahead")

    executed = False

    def action():
        nonlocal executed
        executed = True
        return "SUCCESS"

    result = executor.execute_action(ticket, action)
    assert result == "SUCCESS"
    assert executed is True


def test_execute_action_fails_if_unconfirmed():
    executor = SpokenActionExecutor()
    ticket = executor.create_spoken_ticket(action="shutdown_cluster")

    executed = False

    def action():
        nonlocal executed
        executed = True

    with pytest.raises(TicketExecutionError, match="not been confirmed"):
        executor.execute_action(ticket, action)

    assert executed is False


def test_execute_action_fails_if_expired():
    executor = SpokenActionExecutor()
    ticket = executor.create_spoken_ticket(action="delete_all", validity_seconds=10.0)
    executor.confirm_ticket(ticket.ticket_id, "yes")

    # Time travels past expiration
    expired_time = ticket.created_at + timedelta(seconds=15.0)

    def action():
        return "SHOULD NOT RUN"

    with pytest.raises(TicketExecutionError, match="expired"):
        executor.execute_action(ticket, action, now=expired_time)


def test_execute_action_replay_prevention_single_use():
    executor = SpokenActionExecutor()
    ticket = executor.create_spoken_ticket(action="clear_vault")
    executor.confirm_ticket(ticket.ticket_id, "confirm")

    count = 0

    def action():
        nonlocal count
        count += 1
        return count

    # First execution succeeds
    res1 = executor.execute_action(ticket, action)
    assert res1 == 1

    # Second execution must fail (SEC-56 single-use)
    with pytest.raises(TicketExecutionError, match="already been executed"):
        executor.execute_action(ticket, action)

    assert count == 1
