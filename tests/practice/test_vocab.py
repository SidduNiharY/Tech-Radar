from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.practice.fsrs import Rating, State
from techradar.practice.vocab import (
    VocabDailyDeck,
    VocabItem,
    VocabMeaning,
    VocabResult,
    WordAnalyzer,
    candidate_words,
    run_vocab,
    validate_vocab_item,
)
from tests.fakes import FakeCompleter


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


# ---------------------------------------------------------------------------
# Phase 3 Task 6 Vocab Tests
# ---------------------------------------------------------------------------


def test_candidate_words_skips_common_and_proper_nouns():
    """candidate_words skips proper nouns (Delhi) and common words (economy)."""
    text = "Delhi saw an ubiquitous economy rebound. Officials obfuscate data."
    words = [w for w, _ in candidate_words(text)]
    assert (
        "obfuscate" in words
        and "economy" not in words
        and "delhi" not in [w.lower() for w in words]
    )


def test_candidate_sentence_is_verbatim():
    """candidate_words returns the exact verbatim original sentence."""
    candidates = candidate_words("Officials obfuscate data.")
    assert len(candidates) >= 1
    lemma, sent = candidates[0]
    assert lemma == "obfuscate"
    assert sent == "Officials obfuscate data."


def test_vocab_meaning_validation():
    """VocabMeaning validates meaning length, max 3 synonyms/antonyms, and no links (SEC-20)."""
    vm = VocabMeaning(
        meaning="To deliberately make something obscure or unclear.",
        synonyms=["obscure", "confuse", "blur", "muddle"],  # should be capped to 3
        antonyms=["clarify", "illuminate"],
    )
    assert vm.meaning == "To deliberately make something obscure or unclear."
    assert len(vm.synonyms) == 3
    assert vm.synonyms == ["obscure", "confuse", "blur"]
    assert len(vm.antonyms) == 2

    # Empty meaning fails
    with pytest.raises(ValueError, match="meaning cannot be empty"):
        VocabMeaning(meaning="   ")

    # Links in meaning fail (SEC-20)
    with pytest.raises(ValueError, match="links are not allowed"):
        VocabMeaning(meaning="Defined at https://dictionary.example.com/obfuscate")


def test_custom_word_analyzer_protocol():
    """A custom WordAnalyzer implementation can be provided to candidate_words."""

    class StubAnalyzer:
        def zipf_frequency(self, word: str) -> float:
            if word == "special":
                return 2.0  # Rare
            return 5.0  # Common

        def lemmatize(self, word: str) -> str:
            return word.lower().rstrip("s")

        def is_proper_noun(self, word: str, sentence: str) -> bool:
            return word.startswith("Proper")

    analyzer: WordAnalyzer = StubAnalyzer()
    text = "ProperNoun introduced specials features."
    res = candidate_words(text, analyzer=analyzer)
    assert len(res) == 1
    assert res[0][0] == "special"
    assert res[0][1] == text


@pytest.mark.asyncio
async def test_run_vocab_job():
    """run_vocab extracts candidate words, queries LLM for meanings, and creates cards."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    # Mock DB query for existing vocab returning empty set
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_res

    completer = FakeCompleter(
        [
            json.dumps(
                {
                    "meaning": "To deliberately obscure or make unclear.",
                    "synonyms": ["confuse", "blur"],
                    "antonyms": ["clarify"],
                }
            )
        ]
    )

    now = datetime(2026, 11, 15, 5, 45, tzinfo=UTC)
    result = await run_vocab(
        session,
        completer,
        now=now,
        limit=1,
        corpus=["Officials obfuscate data in quarterly reports."],
    )

    assert isinstance(result, VocabResult)
    assert result.items_created == 1
    assert "obfuscate" in result.words
    assert session.add.call_count == 2  # 1 DBVocab + 1 DBFlashcard
    assert session.flush.call_count >= 1


# ---------------------------------------------------------------------------
# Backward Compatibility Tests for VocabItem and VocabDailyDeck
# ---------------------------------------------------------------------------


def test_vocab_item_attributes_and_defaults():
    item = _make_sample_vocab()
    assert item.word == "ubiquitous"
    assert item.pos == "adjective"
    assert item.definition == "Present, appearing, or found everywhere."
    assert item.synonyms == ["omnipresent", "pervasive"]
    assert item.antonyms == ["rare", "scarce"]
    assert item.example_sentence == "Smartphones have become ubiquitous across the globe."
    assert item.source_context == "Consumer electronics adoption is ubiquitous."
    assert item.is_valid() is True

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
    assert validate_vocab_item(_make_sample_vocab(word="")) is False
    assert validate_vocab_item(_make_sample_vocab(word="   ")) is False
    assert validate_vocab_item(_make_sample_vocab(pos="")) is False
    assert validate_vocab_item(_make_sample_vocab(definition="")) is False
    assert validate_vocab_item(_make_sample_vocab(example_sentence="")) is False


def test_vocab_item_validation_rejects_links():
    assert (
        validate_vocab_item(
            _make_sample_vocab(definition="Defined at http://dictionary.com/word"),
        )
        is False
    )
    assert (
        validate_vocab_item(
            _make_sample_vocab(
                example_sentence="See https://example.com for an example.",
            ),
        )
        is False
    )
    assert (
        validate_vocab_item(
            _make_sample_vocab(source_context="Extracted from https://news.site/article"),
        )
        is False
    )


def test_vocab_daily_deck_five_items_batching():
    deck = VocabDailyDeck()
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

    batch = deck.get_daily_batch()
    assert len(batch) == 5
    assert [it.word for it in batch] == [f"word_{i}" for i in range(5)]

    small_deck = VocabDailyDeck(items=custom_items[:3])
    small_batch = small_deck.get_daily_batch()
    assert len(small_batch) == 3


def test_vocab_daily_deck_fsrs_rating_loop_integration():
    deck = VocabDailyDeck()
    batch = deck.get_daily_batch()
    first_item = batch[0]

    initial_card = deck.get_card(first_item)
    assert initial_card.state == State.NEW
    assert initial_card.reps == 0

    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)

    updated_card = deck.review(first_item, Rating.GOOD, now=now)
    assert updated_card.reps == 1
    assert updated_card.state == State.REVIEW
    assert updated_card.stability > 0.0
    assert updated_card.last_review == now
    assert updated_card.due > now

    assert deck.get_card(first_item.word) == updated_card

    now_later = now + timedelta(hours=1)
    lapsed_card = deck.review(first_item.word, Rating.AGAIN, now=now_later)
    assert lapsed_card.lapses == 1
    assert lapsed_card.reps == 2
    assert lapsed_card.state == State.RELEARNING

    now_next = now + timedelta(days=1)
    easy_card = deck.rate(first_item.word, 4, now=now_next)
    assert easy_card.reps == 3


def test_vocab_daily_deck_due_batch_priority():
    items = [_make_sample_vocab(word=f"item_{i}") for i in range(8)]
    deck = VocabDailyDeck(items=items)

    now = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)

    past_due_time = now - timedelta(days=2)
    card_0 = deck.review("item_0", Rating.GOOD, now=past_due_time)
    card_1 = deck.review("item_1", Rating.GOOD, now=past_due_time)

    card_0.due = past_due_time
    card_1.due = past_due_time
    deck.cards["item_0"] = card_0
    deck.cards["item_1"] = card_1

    batch = deck.get_daily_batch(limit=5, now=now)
    words = [it.word for it in batch]
    assert words[0] in {"item_0", "item_1"}
    assert words[1] in {"item_0", "item_1"}
    assert len(batch) == 5
