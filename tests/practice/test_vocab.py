from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.practice.vocab import (
    VocabMeaning,
    VocabResult,
    WordAnalyzer,
    candidate_words,
    run_vocab,
)
from tests.fakes import FakeCompleter

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
