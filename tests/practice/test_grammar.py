from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.practice.grammar import (
    GrammarItem,
    GrammarQuestion,
    GrammarQuizSession,
    GrammarResult,
    GrammarRule,
    make_grammar_item,
    run_grammar,
    validate_grammar_question,
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


def _make_sample_question(**kwargs) -> GrammarQuestion:
    defaults = {
        "id": "test_gq_1",
        "sentence_with_blank": "Neither the manager nor the employees ___ aware of the delay.",
        "options": ["was", "were", "is", "are being"],
        "correct_index": 1,
        "rule_explanation": "Verb agrees with closer plural subject 'employees'.",
        "category": "subject-verb-agreement",
    }
    defaults.update(kwargs)
    return GrammarQuestion(**defaults)


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


# ---------------------------------------------------------------------------
# Backward Compatibility Tests for GrammarQuestion and GrammarQuizSession
# ---------------------------------------------------------------------------


def test_grammar_question_four_options_requirement():
    # Exactly 4 options passes
    q_valid = _make_sample_question(options=["A", "B", "C", "D"])
    assert validate_grammar_question(q_valid) is True
    assert q_valid.is_valid() is True

    # 3 options fails
    q_three = _make_sample_question(options=["A", "B", "C"])
    assert validate_grammar_question(q_three) is False

    # 5 options fails
    q_five = _make_sample_question(options=["A", "B", "C", "D", "E"])
    assert validate_grammar_question(q_five) is False

    # Empty options fails
    q_empty = _make_sample_question(options=[])
    assert validate_grammar_question(q_empty) is False


def test_grammar_question_option_uniqueness():
    # Duplicate options fail
    q_dups = _make_sample_question(options=["was", "was", "were", "is"])
    assert validate_grammar_question(q_dups) is False

    # All unique options pass
    q_unique = _make_sample_question(options=["was", "were", "is", "are"])
    assert validate_grammar_question(q_unique) is True


def test_grammar_question_correct_index_boundaries():
    for idx in range(4):
        q = _make_sample_question(correct_index=idx)
        assert validate_grammar_question(q) is True

    q_neg = _make_sample_question(correct_index=-1)
    assert validate_grammar_question(q_neg) is False

    q_too_high = _make_sample_question(correct_index=4)
    assert validate_grammar_question(q_too_high) is False


def test_grammar_question_explanation_no_links():
    q_clean = _make_sample_question(
        rule_explanation="Subject-verb agreement rule explains that the verb must match.",
    )
    assert validate_grammar_question(q_clean) is True

    q_empty_exp = _make_sample_question(rule_explanation="")
    assert validate_grammar_question(q_empty_exp) is False

    q_http = _make_sample_question(
        rule_explanation="See explanation at http://grammar-rules.example.org/rule1",
    )
    assert validate_grammar_question(q_http) is False

    q_https = _make_sample_question(
        rule_explanation="Check https://rules.internal.net/grammar for details.",
    )
    assert validate_grammar_question(q_https) is False


def test_grammar_question_sentence_blank_required():
    q_no_blank = _make_sample_question(sentence_with_blank="")
    assert validate_grammar_question(q_no_blank) is False

    q_link_in_sentence = _make_sample_question(
        sentence_with_blank="Visit https://phishing.site ___ complete test.",
    )
    assert validate_grammar_question(q_link_in_sentence) is False


def test_grammar_quiz_session_generation():
    session = GrammarQuizSession()
    questions = session.generate_daily_set()
    assert len(questions) == 10
    assert len(session) == 10
    assert len(session.questions) == 10
    assert len(session.get_daily_questions()) == 10

    for q in questions:
        assert validate_grammar_question(q) is True
        assert len(q.options) == 4
        assert 0 <= q.correct_index <= 3


def test_grammar_quiz_session_custom_pool():
    custom_pool = [
        _make_sample_question(
            id=f"custom_{i}",
            sentence_with_blank=f"Sentence {i} ___ here.",
            options=[f"opt_{i}_a", f"opt_{i}_b", f"opt_{i}_c", f"opt_{i}_d"],
            correct_index=i % 4,
        )
        for i in range(12)
    ]
    session = GrammarQuizSession(questions=custom_pool)
    daily = session.generate_daily_set(count=10)
    assert len(daily) == 10
    assert daily[0].id == "custom_0"
    assert daily[9].id == "custom_9"


def test_grammar_quiz_session_filters_invalid_questions():
    mixed_pool = [
        _make_sample_question(id="valid_1"),
        _make_sample_question(id="invalid_1", options=["only_two", "options"]),
        _make_sample_question(
            id="invalid_2",
            rule_explanation="Visit https://malicious.com",
        ),
        _make_sample_question(id="valid_2"),
    ]
    session = GrammarQuizSession(questions=mixed_pool)
    daily = session.generate_daily_set(count=10)
    assert len(daily) == 2
    assert [q.id for q in daily] == ["valid_1", "valid_2"]
