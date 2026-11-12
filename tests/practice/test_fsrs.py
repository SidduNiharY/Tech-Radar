from datetime import UTC, datetime, timedelta

import pytest

from techradar.practice.fsrs import Card, Rating, State, retrievability, schedule_card


def test_rating_and_state_enums():
    assert Rating.AGAIN == 1
    assert Rating.HARD == 2
    assert Rating.GOOD == 3
    assert Rating.EASY == 4

    assert State.NEW == 0
    assert State.LEARNING == 1
    assert State.REVIEW == 2
    assert State.RELEARNING == 3


def test_card_defaults():
    card = Card()
    assert card.stability == 0.0
    assert card.difficulty == 0.0
    assert card.reps == 0
    assert card.lapses == 0
    assert card.state == State.NEW
    assert card.last_review is None
    assert isinstance(card.due, datetime)


def test_retrievability_decay_over_time():
    stability = 10.0
    r0 = retrievability(stability=stability, elapsed_days=0.0)
    r5 = retrievability(stability=stability, elapsed_days=5.0)
    r10 = retrievability(stability=stability, elapsed_days=10.0)
    r30 = retrievability(stability=stability, elapsed_days=30.0)

    assert r0 == 1.0
    assert r0 > r5 > r10 > r30
    assert pytest.approx(r10, rel=1e-3) == 0.90


def test_retrievability_edge_cases():
    assert retrievability(stability=10.0, elapsed_days=-1.0) == 1.0
    assert retrievability(stability=0.0, elapsed_days=5.0) == 0.0
    assert retrievability(stability=-2.0, elapsed_days=5.0) == 0.0


def test_new_card_rated_good_moves_to_review():
    now = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
    card = Card(state=State.NEW)

    scheduled = schedule_card(card, Rating.GOOD, now)

    assert scheduled.state == State.REVIEW
    assert scheduled.reps == 1
    assert scheduled.lapses == 0
    assert scheduled.last_review == now
    assert scheduled.stability > 0.0
    assert scheduled.difficulty > 0.0
    assert scheduled.due > now


def test_again_increases_lapses():
    now = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
    card = Card(state=State.NEW, lapses=0)

    # First lapse on new card
    c1 = schedule_card(card, Rating.AGAIN, now)
    assert c1.lapses == 1
    assert c1.state == State.LEARNING

    # Move card to review
    c2 = schedule_card(c1, Rating.GOOD, now + timedelta(minutes=10))
    assert c2.state == State.REVIEW
    assert c2.lapses == 1

    # Lapse during review
    c3 = schedule_card(c2, Rating.AGAIN, now + timedelta(days=3))
    assert c3.lapses == 2
    assert c3.state == State.RELEARNING


def test_schedule_card_ordering_by_rating():
    now = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
    card = Card(state=State.NEW)

    again_card = schedule_card(card, Rating.AGAIN, now)
    hard_card = schedule_card(card, Rating.HARD, now)
    good_card = schedule_card(card, Rating.GOOD, now)
    easy_card = schedule_card(card, Rating.EASY, now)

    assert again_card.due < hard_card.due < good_card.due < easy_card.due
    assert again_card.stability < hard_card.stability < good_card.stability < easy_card.stability
    # Again is hardest, Easy is easiest
    assert (
        again_card.difficulty > hard_card.difficulty > good_card.difficulty > easy_card.difficulty
    )


def test_review_progression():
    now = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
    card = Card(state=State.NEW)

    # First review: Good
    c1 = schedule_card(card, Rating.GOOD, now)
    assert c1.state == State.REVIEW
    assert c1.reps == 1

    # Second review after due: Good
    review_time = c1.due
    c2 = schedule_card(c1, Rating.GOOD, review_time)
    assert c2.state == State.REVIEW
    assert c2.reps == 2
    assert c2.stability > c1.stability
    assert c2.due > review_time


def test_default_weights_match_the_fsrs5_reference():
    # fsrs-rs v1.4.3, src/inference.rs, DEFAULT_PARAMETERS (FSRS-5).
    # w[14] was 0.2269 here (a slipped digit); four others were rounded.
    from techradar.practice.fsrs import DEFAULT_WEIGHTS

    reference = (
        0.40255, 1.18385, 3.173, 15.69105, 7.1949, 0.5345, 1.4604, 0.0046, 1.54575,
        0.1192, 1.01925, 1.9395, 0.11, 0.29605, 2.2698, 0.2315, 2.9898, 0.51655, 0.6621,
    )  # fmt: skip
    assert DEFAULT_WEIGHTS == reference
