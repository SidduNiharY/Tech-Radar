from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class JarvisIntent(StrEnum):
    ASK_QUESTION = "ask_question"
    DAILY_BRIEFING = "daily_briefing"
    PRACTICE_DRILL = "practice_drill"
    STUDY_PLAN = "study_plan"
    SYSTEM_STATUS = "system_status"
    TAKE_NOTE = "take_note"
    DANGEROUS_ACTION = "dangerous_action"
    UNKNOWN = "unknown"


class IntentClassification(BaseModel):
    intent: JarvisIntent
    confidence: float
    entities: dict[str, Any] = Field(default_factory=dict)
    raw_query: str
    requires_confirmation: bool


# Destructive action pattern (SEC-56)
_DESTRUCTIVE_PATTERN = re.compile(
    r"\b(delete|remove|clear|wipe|purge|drop|shutdown|destroy|erase|format|reset|terminate|kill|prune|truncate)\b",
    re.IGNORECASE,
)

# Questions/explanations that may contain a destructive word as a subject
_EXPLANATION_PATTERN = re.compile(
    r"^(what\s+(is|are|does)|how\s+(does|do|can|to)|why\s+(is|does|do)|explain|tell\s+me\s+about|define)\b",
    re.IGNORECASE,
)

_DAILY_BRIEFING_PATTERN = re.compile(
    r"\b(daily\s+briefing|morning\s+briefing|today'?s\s+briefing|briefing|daily\s+digest|"
    r"morning\s+digest|daily\s+update|morning\s+update|brief\s+me|read\s+(my\s+)?briefing|"
    r"give\s+me\s+(my\s+|the\s+)?briefing)\b",
    re.IGNORECASE,
)

_TAKE_NOTE_PREFIX_PATTERN = re.compile(
    r"^(?:please\s+)?(?:take\s+a?\s*note|make\s+a\s+note|note\s+down|jot\s+down|write\s+down|"
    r"save\s+note|record\s+note|remember)(?:\s+that|\s+to|\s+this)?\s*[:,-]?\s*",
    re.IGNORECASE,
)

_PRACTICE_DRILL_PATTERN = re.compile(
    r"\b(practice\s+drill|practice\s+quiz|practice\s+questions|drill\s+me|quiz\s+me|mock\s+exam|"
    r"flashcards?|start\s+(?:a\s+)?drill|run\s+(?:a\s+)?drill|test\s+my\s+knowledge)\b|"
    r"^(?:start\s+|run\s+)?practice\b",
    re.IGNORECASE,
)

_STUDY_PLAN_PATTERN = re.compile(
    r"\b(study\s+plan|learning\s+plan|study\s+schedule|learning\s+schedule|study\s+roadmap|"
    r"learning\s+roadmap|study\s+goals?)\b|\bwhat\s+should\s+i\s+(study|learn)\b|"
    r"^(?:show|view|get|generate|create)\s+(?:my\s+)?study\s+plan\b",
    re.IGNORECASE,
)

_SYSTEM_STATUS_PATTERN = re.compile(
    r"\b(system\s+status|system\s+health|health\s+check|status\s+check|service\s+status|"
    r"services\s+status|cluster\s+status|cpu\s+status|memory\s+status|disk\s+status|"
    r"database\s+status|api\s+status|server\s+status|node\s+status|system\s+metrics|"
    r"check\s+(?:[a-zA-Z0-9_-]+\s+)?status|status\s+of\s+(?:the\s+)?system)\b|"
    r"\b(how\s+is\s+the\s+system|is\s+the\s+system\s+(?:healthy|running|up)|"
    r"are\s+(?:all\s+)?services\s+running)\b",
    re.IGNORECASE,
)

_QUESTION_PREFIX_PATTERN = re.compile(
    r"^(what|how|why|who|when|where|which|can\s+you|could\s+you|explain|tell\s+me|define|describe|"
    r"search\s+for|look\s+up|is\s+there|are\s+there|does|do)\b",
    re.IGNORECASE,
)


def classify_intent(query: str) -> IntentClassification:
    """Classify user voice query into a JarvisIntent with entities and confirmation flag.

    Clean offline deterministic intent classifier. High confidence (>=0.90) for matched
    intents. Destructive or state-changing queries map to DANGEROUS_ACTION and enforce
    requires_confirmation=True (SEC-56). Read-only intents have requires_confirmation=False.
    """
    clean_query = query.strip()
    if not clean_query:
        return IntentClassification(
            intent=JarvisIntent.UNKNOWN,
            confidence=0.0,
            entities={},
            raw_query=query,
            requires_confirmation=False,
        )

    # 1. Dangerous / state-changing action check (must precede other actions unless inquiry)
    is_explanation = bool(_EXPLANATION_PATTERN.search(clean_query))
    destructive_match = _DESTRUCTIVE_PATTERN.search(clean_query)

    if destructive_match and not is_explanation:
        action_verb = destructive_match.group(1).lower()
        remainder = clean_query[destructive_match.end() :].strip(" :-,.")
        target = remainder or "system"
        return IntentClassification(
            intent=JarvisIntent.DANGEROUS_ACTION,
            confidence=0.95,
            entities={"action": action_verb, "target": target},
            raw_query=query,
            requires_confirmation=True,
        )

    # 2. Daily Briefing
    if _DAILY_BRIEFING_PATTERN.search(clean_query):
        timeframe = "today"
        if "morning" in clean_query.lower():
            timeframe = "morning"
        return IntentClassification(
            intent=JarvisIntent.DAILY_BRIEFING,
            confidence=0.95,
            entities={"type": "daily_briefing", "timeframe": timeframe},
            raw_query=query,
            requires_confirmation=False,
        )

    # 3. Take Note
    note_prefix_match = _TAKE_NOTE_PREFIX_PATTERN.search(clean_query)
    if note_prefix_match:
        content = clean_query[note_prefix_match.end() :].strip()
        return IntentClassification(
            intent=JarvisIntent.TAKE_NOTE,
            confidence=0.95,
            entities={"content": content},
            raw_query=query,
            requires_confirmation=False,
        )

    # 4. Practice Drill
    if _PRACTICE_DRILL_PATTERN.search(clean_query):
        topic_match = re.search(
            r"\b(?:on|about|for)\s+([a-zA-Z0-9_\-\s]+)$", clean_query, re.IGNORECASE
        )
        topic = topic_match.group(1).strip() if topic_match else "general"
        drill_format = "drill"
        if "quiz" in clean_query.lower():
            drill_format = "quiz"
        elif "flashcard" in clean_query.lower():
            drill_format = "flashcard"
        elif "mock exam" in clean_query.lower():
            drill_format = "mock_exam"

        return IntentClassification(
            intent=JarvisIntent.PRACTICE_DRILL,
            confidence=0.95,
            entities={"topic": topic, "format": drill_format},
            raw_query=query,
            requires_confirmation=False,
        )

    # 5. Study Plan
    if _STUDY_PLAN_PATTERN.search(clean_query):
        timeframe = "today"
        lower = clean_query.lower()
        if "tomorrow" in lower:
            timeframe = "tomorrow"
        elif "this week" in lower or "weekly" in lower:
            timeframe = "this_week"

        topic_match = re.search(r"\b(?:for|on)\s+([a-zA-Z0-9_\-\s]+)$", clean_query, re.IGNORECASE)
        topic = topic_match.group(1).strip() if topic_match else "general"

        return IntentClassification(
            intent=JarvisIntent.STUDY_PLAN,
            confidence=0.95,
            entities={"topic": topic, "timeframe": timeframe},
            raw_query=query,
            requires_confirmation=False,
        )

    # 6. System Status
    if _SYSTEM_STATUS_PATTERN.search(clean_query):
        lower = clean_query.lower()
        component = "all"
        for comp in ("cpu", "memory", "disk", "database", "api", "cluster", "network"):
            if comp in lower:
                component = comp
                break

        return IntentClassification(
            intent=JarvisIntent.SYSTEM_STATUS,
            confidence=0.95,
            entities={"component": component},
            raw_query=query,
            requires_confirmation=False,
        )

    # 7. Ask Question
    is_question = bool(
        _QUESTION_PREFIX_PATTERN.search(clean_query) or clean_query.rstrip().endswith("?")
    )
    if is_question or is_explanation:
        return IntentClassification(
            intent=JarvisIntent.ASK_QUESTION,
            confidence=0.90,
            entities={"question": clean_query},
            raw_query=query,
            requires_confirmation=False,
        )

    # 8. Unknown
    return IntentClassification(
        intent=JarvisIntent.UNKNOWN,
        confidence=0.0,
        entities={},
        raw_query=query,
        requires_confirmation=False,
    )
