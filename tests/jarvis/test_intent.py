from __future__ import annotations

import pytest

from techradar.jarvis.intent import (
    IntentClassification,
    JarvisIntent,
    classify_intent,
)


def test_classify_empty_or_whitespace_query():
    res_empty = classify_intent("")
    assert res_empty.intent == JarvisIntent.UNKNOWN
    assert res_empty.confidence == 0.0
    assert res_empty.requires_confirmation is False
    assert res_empty.entities == {}

    res_ws = classify_intent("   \n\t  ")
    assert res_ws.intent == JarvisIntent.UNKNOWN
    assert res_ws.confidence == 0.0
    assert res_ws.requires_confirmation is False


def test_classify_unknown_gibberish():
    res = classify_intent("xyzqwerty987654321")
    assert res.intent == JarvisIntent.UNKNOWN
    assert res.confidence == 0.0
    assert res.requires_confirmation is False
    assert res.entities == {}


@pytest.mark.parametrize(
    ("query", "expected_verb"),
    [
        ("delete all notes", "delete"),
        ("Please clear the database cache", "clear"),
        ("wipe all user session records", "wipe"),
        ("purge old logs immediately", "purge"),
        ("drop table student_records", "drop"),
        ("shutdown server right now", "shutdown"),
        ("destroy cluster", "destroy"),
        ("erase the history", "erase"),
        ("format disk partition", "format"),
        ("reset factory settings", "reset"),
        ("kill process 999", "kill"),
        ("terminate container", "terminate"),
        ("prune docker cache", "prune"),
    ],
)
def test_classify_dangerous_action_requires_confirmation(query: str, expected_verb: str):
    res = classify_intent(query)
    assert isinstance(res, IntentClassification)
    assert res.intent == JarvisIntent.DANGEROUS_ACTION
    assert res.confidence >= 0.90
    assert res.requires_confirmation is True
    assert res.entities["action"] == expected_verb
    assert "target" in res.entities


def test_explanation_containing_destructive_word_is_ask_question():
    # An educational inquiry asking about a dangerous keyword should NOT trigger confirmation
    res = classify_intent("What is a drop table attack?")
    assert res.intent == JarvisIntent.ASK_QUESTION
    assert res.requires_confirmation is False
    assert res.confidence >= 0.90

    res2 = classify_intent("Explain why delete is dangerous")
    assert res2.intent == JarvisIntent.ASK_QUESTION
    assert res2.requires_confirmation is False


@pytest.mark.parametrize(
    "query",
    [
        "Give me my daily briefing",
        "Today's briefing please",
        "What is on my morning briefing?",
        "Brief me on today's items",
        "Read my daily update",
        "Can you read the daily digest",
    ],
)
def test_classify_daily_briefing(query: str):
    res = classify_intent(query)
    assert res.intent == JarvisIntent.DAILY_BRIEFING
    assert res.confidence >= 0.90
    assert res.requires_confirmation is False
    assert res.entities.get("type") == "daily_briefing"
    assert "timeframe" in res.entities


@pytest.mark.parametrize(
    ("query", "expected_format", "expected_topic"),
    [
        ("Start a practice drill on Kubernetes networking", "drill", "Kubernetes networking"),
        ("Quiz me on Python asyncio", "quiz", "Python asyncio"),
        ("Run flashcards on system design", "flashcard", "system design"),
        ("Practice mock exam for CKA", "mock_exam", "CKA"),
        ("Test my knowledge about distributed consensus", "drill", "distributed consensus"),
    ],
)
def test_classify_practice_drill(query: str, expected_format: str, expected_topic: str):
    res = classify_intent(query)
    assert res.intent == JarvisIntent.PRACTICE_DRILL
    assert res.confidence >= 0.90
    assert res.requires_confirmation is False
    assert res.entities.get("format") == expected_format
    assert res.entities.get("topic") == expected_topic


@pytest.mark.parametrize(
    ("query", "expected_timeframe"),
    [
        ("What should I study today?", "today"),
        ("Show my study plan for tomorrow", "tomorrow"),
        ("Generate study plan for this week", "this_week"),
        ("Show me my study goals", "today"),
        ("What should I learn next?", "today"),
    ],
)
def test_classify_study_plan(query: str, expected_timeframe: str):
    res = classify_intent(query)
    assert res.intent == JarvisIntent.STUDY_PLAN
    assert res.confidence >= 0.90
    assert res.requires_confirmation is False
    assert res.entities.get("timeframe") == expected_timeframe


@pytest.mark.parametrize(
    ("query", "expected_component"),
    [
        ("System status check", "all"),
        ("Check system health", "all"),
        ("How is the system running?", "all"),
        ("What is the CPU status?", "cpu"),
        ("Check database status", "database"),
        ("Memory status check", "memory"),
    ],
)
def test_classify_system_status(query: str, expected_component: str):
    res = classify_intent(query)
    assert res.intent == JarvisIntent.SYSTEM_STATUS
    assert res.confidence >= 0.90
    assert res.requires_confirmation is False
    assert res.entities.get("component") == expected_component


@pytest.mark.parametrize(
    ("query", "expected_content"),
    [
        ("Take a note: Buy milk on the way home", "Buy milk on the way home"),
        ("Make a note that Raft uses quorum for commit", "Raft uses quorum for commit"),
        ("Note down: Review chapter 4 before evening", "Review chapter 4 before evening"),
        ("Remember to check the database logs", "check the database logs"),
        ("Jot down: Look into eBPF tracepoints", "Look into eBPF tracepoints"),
    ],
)
def test_classify_take_note(query: str, expected_content: str):
    res = classify_intent(query)
    assert res.intent == JarvisIntent.TAKE_NOTE
    assert res.confidence >= 0.90
    assert res.requires_confirmation is False
    assert res.entities.get("content") == expected_content


@pytest.mark.parametrize(
    "query",
    [
        "What is Raft consensus?",
        "How do distributed transactions work in Spanner?",
        "Why is WAL needed in SQLite?",
        "Can you explain vector embeddings?",
        "Tell me about Paxos algorithm",
        "Search for documentation on B-trees",
    ],
)
def test_classify_ask_question(query: str):
    res = classify_intent(query)
    assert res.intent == JarvisIntent.ASK_QUESTION
    assert res.confidence >= 0.90
    assert res.requires_confirmation is False
    assert res.entities.get("question") == query
