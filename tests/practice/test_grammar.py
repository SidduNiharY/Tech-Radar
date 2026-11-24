from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.practice.grammar import (
    GrammarItem,
    GrammarResult,
    GrammarRule,
    make_grammar_item,
    run_grammar,
)
from tests.fakes import FakeCompleter

ITEM_JSON_KEY_1 = json.dumps(
    {
        "kind": "fill_blank",
        "prompt": "She has ___ university degree.",
        "options": ["a", "an", "the", "no article"],
        "answer_index": 1,
        "rule": "articles",
        "explanation": "Use 'a' before consonant sound.",
    }
)


# ---------------------------------------------------------------------------
# Phase 3 Task 6 Grammar Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grammar_item_needs_checker_agreement():
    """Worker model writes item; checker model verifies answer_index.

    Returns None on disagreement, GrammarItem on agreement.
    """
    assert (
        await make_grammar_item(
            FakeCompleter([ITEM_JSON_KEY_1, '{"answer_index": 2}']),
            GrammarRule.ARTICLES,
            "fill_blank",
        )
        is None
    )

    res = await make_grammar_item(
        FakeCompleter([ITEM_JSON_KEY_1, '{"answer_index": 1}']),
        GrammarRule.ARTICLES,
        "fill_blank",
    )
    assert res is not None
    assert isinstance(res, GrammarItem)
    assert res.answer_index == 1
    assert res.rule == GrammarRule.ARTICLES
    assert res.options == ["a", "an", "the", "no article"]


def test_indian_language_context_passes_cleanly():
    """Indian-language context, administrative terms, regional names, and scripts pass cleanly."""
    item = GrammarItem(
        kind="fill_blank",
        prompt="Neither Rahul nor the sarpanch ___ aware of the new panchayat scheme.",
        options=["was", "were", "is", "are"],
        answer_index=0,
        rule=GrammarRule.SUBJECT_VERB,
        explanation="When subjects are joined by 'neither... nor', verb agrees with closer one.",
    )
    assert "Rahul" in item.prompt
    assert "sarpanch" in item.prompt
    assert "panchayat" in item.prompt
    assert item.rule == GrammarRule.SUBJECT_VERB

    # Indian script / multilingual greeting context
    item_script = GrammarItem(
        kind="sentence_improvement",
        prompt="The gathering in Varanasi greeted the guru with namaste (नमस्ते) and pranam.",
        options=["with namaste", "by namaste", "at namaste", "in namaste"],
        answer_index=0,
        rule=GrammarRule.PREPOSITIONS,
        explanation="Appropriate preposition with traditional Indian greeting.",
    )
    assert "नमस्ते" in item_script.prompt
    assert "Varanasi" in item_script.prompt


@pytest.mark.asyncio
async def test_make_grammar_item_indian_context():
    """Two-model verification handles Indian historical/geographical context seamlessly."""
    item_json = json.dumps(
        {
            "kind": "error_spotting",
            "prompt": "The delegation visited Varanasi to study the ancient ghats along the Ganga.",
            "options": [
                "The delegation visited",
                "Varanasi to study",
                "the ancient ghats",
                "along the Ganga",
            ],
            "answer_index": 2,
            "rule": "prepositions",
            "explanation": "No error or preposition check in Indian geography context.",
        }
    )
    item = await make_grammar_item(
        FakeCompleter([item_json, '{"answer_index": 2}']),
        GrammarRule.PREPOSITIONS,
        "error_spotting",
    )
    assert item is not None
    assert "Varanasi" in item.prompt
    assert item.answer_index == 2


def test_grammar_rule_enum_values():
    """Verify all 10 specified GrammarRule values."""
    expected = {
        "tense",
        "articles",
        "prepositions",
        "subject_verb",
        "pronouns",
        "modifiers",
        "conjunctions",
        "parallelism",
        "voice",
        "narration",
    }
    actual = {r.value for r in GrammarRule}
    assert actual == expected
    # Case insensitivity via _missing_
    assert GrammarRule("TENSE") == GrammarRule.TENSE
    assert GrammarRule("articles") == GrammarRule.ARTICLES


def test_grammar_item_validation_constraints():
    """GrammarItem validates 4 unique options, boundaries, and rejects URLs (SEC-20)."""
    # Valid item
    item = GrammarItem(
        kind="fill_blank",
        prompt="She has ___ university degree.",
        options=["a", "an", "the", "no article"],
        answer_index=0,
        rule=GrammarRule.ARTICLES,
        explanation="A comes before consonant sound.",
    )
    assert item.answer_index == 0

    # Less than 4 options fails
    with pytest.raises(ValueError, match="exactly 4 items"):
        GrammarItem(
            kind="fill_blank",
            prompt="She has ___ university degree.",
            options=["a", "an", "the"],
            answer_index=0,
            rule=GrammarRule.ARTICLES,
        )

    # Duplicate options fail
    with pytest.raises(ValueError, match="unique"):
        GrammarItem(
            kind="fill_blank",
            prompt="She has ___ university degree.",
            options=["a", "a", "the", "no article"],
            answer_index=0,
            rule=GrammarRule.ARTICLES,
        )

    # Link in prompt fails (SEC-20)
    with pytest.raises(ValueError, match="links are not allowed"):
        GrammarItem(
            kind="fill_blank",
            prompt="Check https://example.com/test for ___ answers.",
            options=["a", "b", "c", "d"],
            answer_index=0,
            rule=GrammarRule.ARTICLES,
        )


@pytest.mark.asyncio
async def test_run_grammar_job():
    """run_grammar generates items up to limit and adds them to DB session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    # Provide 2 agreed questions
    q1 = json.dumps(
        {
            "kind": "fill_blank",
            "prompt": "She has ___ university degree.",
            "options": ["a", "an", "the", "no article"],
            "answer_index": 0,
            "rule": "articles",
            "explanation": "Use 'a' before consonant sound.",
        }
    )
    q2 = json.dumps(
        {
            "kind": "error_spotting",
            "prompt": "Neither the manager nor his employees ___ present at work today.",
            "options": ["was", "were", "is", "are"],
            "answer_index": 1,
            "rule": "subject_verb",
            "explanation": "Agrees with closer plural subject.",
        }
    )

    completer = FakeCompleter([q1, '{"answer_index": 0}', q2, '{"answer_index": 1}'])
    now = datetime(2026, 11, 15, 5, 45, tzinfo=UTC)

    result = await run_grammar(session, completer, now=now, limit=2)
    assert isinstance(result, GrammarResult)
    assert result.items_created == 2
    assert len(result.items) == 2
    assert session.add.call_count == 2
    assert session.flush.call_count == 1
