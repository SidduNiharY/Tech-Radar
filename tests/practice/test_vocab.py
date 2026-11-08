from __future__ import annotations

from datetime import UTC, datetime, timedelta

from techradar.practice.fsrs import Rating, State
from techradar.practice.vocab import (
    VocabDailyDeck,
    VocabItem,
    validate_vocab_item,
)


def _make_sample_vocab(**kwargs) -> VocabItem:
    defaults = {
        "word": "ubiquitous",
        "pos": "adjective",
        "definition": "Present, appearing, or found everywhere.",
        "synonyms": ["omnipresent", "pervasive"],
        "antonyms": ["rare", "scarce"],
        "example_sentence": "Smartphones have become ubiquitous across the globe.",
        "source_context": "Consumer electronics adoption is ubiquitous.",
    }
    defaults.update(kwargs)
    return VocabItem(**defaults)


def test_vocab_item_attributes_and_defaults():
    # Full attributes
    item = _make_sample_vocab()
    assert item.word == "ubiquitous"
    assert item.pos == "adjective"
    assert item.definition == "Present, appearing, or found everywhere."
    assert item.synonyms == ["omnipresent", "pervasive"]
    assert item.antonyms == ["rare", "scarce"]
    assert item.example_sentence == "Smartphones have become ubiquitous across the globe."
    assert item.source_context == "Consumer electronics adoption is ubiquitous."
    assert item.is_valid() is True

    # Defaults for optional fields
    item_minimal = VocabItem(
        word="lucid",
        pos="adjective",
        definition="Expressed clearly; easy to understand.",
        example_sentence="He gave a lucid explanation of the concept.",
    )
    assert item_minimal.synonyms == []
    assert item_minimal.antonyms == []
    assert item_minimal.source_context is None
    assert validate_vocab_item(item_minimal) is True


def test_vocab_item_validation_empty_fields():
    # Empty word fails validation
    assert validate_vocab_item(_make_sample_vocab(word="")) is False
    assert validate_vocab_item(_make_sample_vocab(word="   ")) is False

    # Empty pos fails validation
    assert validate_vocab_item(_make_sample_vocab(pos="")) is False

    # Empty definition fails validation
    assert validate_vocab_item(_make_sample_vocab(definition="")) is False

    # Empty example sentence fails validation
    assert validate_vocab_item(_make_sample_vocab(example_sentence="")) is False


def test_vocab_item_validation_rejects_links():
    # HTTP link in definition fails (SEC-20)
    assert (
        validate_vocab_item(
            _make_sample_vocab(definition="Defined at http://dictionary.com/word"),
        )
        is False
    )

    # HTTPS link in example sentence fails (SEC-20)
    assert (
        validate_vocab_item(
            _make_sample_vocab(
                example_sentence="See https://example.com for an example.",
            ),
        )
        is False
    )

    # Link in source_context fails (SEC-20)
    assert (
        validate_vocab_item(
            _make_sample_vocab(source_context="Extracted from https://news.site/article"),
        )
        is False
    )


def test_vocab_daily_deck_five_items_batching():
    deck = VocabDailyDeck()

    # Default deck has at least 8 items, but daily batch yields exactly 5 items
    batch = deck.get_daily_batch()
    assert len(batch) == 5
    assert len(deck.daily_batch()) == 5

    for item in batch:
        assert isinstance(item, VocabItem)
        assert validate_vocab_item(item) is True
        assert len(item.word) > 0
        assert len(item.definition) > 0


def test_vocab_daily_deck_custom_pool_batching():
    custom_items = [_make_sample_vocab(word=f"word_{i}") for i in range(12)]
    deck = VocabDailyDeck(items=custom_items)

    # Batch should be capped at 5
    batch = deck.get_daily_batch()
    assert len(batch) == 5
    assert [it.word for it in batch] == [f"word_{i}" for i in range(5)]

    # Custom pool smaller than 5 yields all available
    small_deck = VocabDailyDeck(items=custom_items[:3])
    small_batch = small_deck.get_daily_batch()
    assert len(small_batch) == 3


def test_vocab_daily_deck_fsrs_rating_loop_integration():
    deck = VocabDailyDeck()
    batch = deck.get_daily_batch()
    first_item = batch[0]

    # Initial state is NEW
    initial_card = deck.get_card(first_item)
    assert initial_card.state == State.NEW
    assert initial_card.reps == 0

    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)

    # Rating with GOOD transitions to REVIEW and updates stability
    updated_card = deck.review(first_item, Rating.GOOD, now=now)
    assert updated_card.reps == 1
    assert updated_card.state == State.REVIEW
    assert updated_card.stability > 0.0
    assert updated_card.last_review == now
    assert updated_card.due > now

    # Check deck's internal card mapping was updated
    assert deck.get_card(first_item.word) == updated_card

    # Rating with AGAIN counts as a lapse and transitions to RELEARNING
    now_later = now + timedelta(hours=1)
    lapsed_card = deck.review(first_item.word, Rating.AGAIN, now=now_later)
    assert lapsed_card.lapses == 1
    assert lapsed_card.reps == 2
    assert lapsed_card.state == State.RELEARNING

    # Rating using integer value directly
    now_next = now + timedelta(days=1)
    easy_card = deck.rate(first_item.word, 4, now=now_next)  # 4 == EASY
    assert easy_card.reps == 3


def test_vocab_daily_deck_due_batch_priority():
    items = [_make_sample_vocab(word=f"item_{i}") for i in range(8)]
    deck = VocabDailyDeck(items=items)

    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)

    # Review item_0 and item_1 so they have past due dates
    past_due_time = now - timedelta(days=2)
    card_0 = deck.review("item_0", Rating.GOOD, now=past_due_time)
    card_1 = deck.review("item_1", Rating.GOOD, now=past_due_time)

    # Ensure their due dates are before 'now'
    card_0.due = past_due_time
    card_1.due = past_due_time
    deck.cards["item_0"] = card_0
    deck.cards["item_1"] = card_1

    # Daily batch with `now` should prioritize due items first
    batch = deck.get_daily_batch(limit=5, now=now)
    words = [it.word for it in batch]
    assert words[0] in {"item_0", "item_1"}
    assert words[1] in {"item_0", "item_1"}
    assert len(batch) == 5
