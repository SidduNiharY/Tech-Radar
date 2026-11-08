from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, Field

_EXCLUDED_REPETITIONS: Final[frozenset[str]] = frozenset(
    {"that", "had", "bye", "ha", "knock", "no", "so", "hear"}
)

_COMPARATIVES: Final[frozenset[str]] = frozenset(
    [
        "better",
        "worse",
        "faster",
        "slower",
        "bigger",
        "smaller",
        "easier",
        "harder",
        "stronger",
        "weaker",
        "quicker",
        "cheaper",
        "simpler",
        "nicer",
        "higher",
        "lower",
        "closer",
        "further",
        "farther",
        "longer",
        "shorter",
        "wider",
        "taller",
        "heavier",
        "lighter",
        "darker",
        "brighter",
        "fewer",
        "greater",
        "later",
        "earlier",
        "clearer",
        "finer",
        "richer",
        "poorer",
        "safer",
        "older",
        "younger",
        "colder",
        "warmer",
        "hotter",
        "deeper",
        "cooler",
        "sharper",
        "smoother",
        "tougher",
        "kinder",
        "braver",
        "cleaner",
        "dirtier",
    ]
)

_SUPERLATIVES: Final[frozenset[str]] = frozenset(
    [
        "best",
        "worst",
        "fastest",
        "slowest",
        "biggest",
        "smallest",
        "easiest",
        "hardest",
        "strongest",
        "weakest",
        "quickest",
        "cheapest",
        "simplest",
        "nicest",
        "highest",
        "lowest",
        "closest",
        "longest",
        "shortest",
        "widest",
        "tallest",
        "heaviest",
        "lightest",
        "darkest",
        "brightest",
        "greatest",
        "latest",
        "earliest",
        "clearest",
        "finest",
        "safest",
        "oldest",
        "youngest",
        "coldest",
        "warmest",
        "hottest",
        "deepest",
        "coolest",
        "cleanest",
    ]
)

_REPEATED_WORD_RE = re.compile(r"\b([a-zA-Z]+)\s+\1\b", re.IGNORECASE)
_COMPARATIVE_RE = re.compile(r"\b(more|less)\s+([a-zA-Z]+)\b", re.IGNORECASE)
_SUPERLATIVE_RE = re.compile(r"\b(most|least)\s+([a-zA-Z]+)\b", re.IGNORECASE)

_MODAL_VERBS: Final[frozenset[str]] = frozenset(
    {
        "will",
        "would",
        "can",
        "could",
        "should",
        "shall",
        "may",
        "might",
        "must",
        "did",
        "does",
        "do",
        "to",
    }
)

_SVA_RULES: list[tuple[re.Pattern[str], str, str, bool]] = [
    (
        re.compile(r"\b(he|she|it)\s+(?:don't|dont)\b", re.IGNORECASE),
        "subject_verb_disagreement",
        "doesn't",
        False,
    ),
    (
        re.compile(r"\b(they|we|you|i)\s+(?:doesn't|doesnt)\b", re.IGNORECASE),
        "subject_verb_disagreement",
        "don't",
        False,
    ),
    (
        re.compile(r"\b(they|we|you)\s+is\b", re.IGNORECASE),
        "subject_verb_disagreement",
        "are",
        False,
    ),
    (
        re.compile(r"\b(they|we|you)\s+was\b", re.IGNORECASE),
        "subject_verb_disagreement",
        "were",
        False,
    ),
    (
        re.compile(r"\b(he|she|it)\s+are\b", re.IGNORECASE),
        "subject_verb_disagreement",
        "is",
        False,
    ),
    (
        re.compile(r"\bi\s+(?:is|are)\b", re.IGNORECASE),
        "subject_verb_disagreement",
        "am",
        False,
    ),
    (
        re.compile(r"\b(they|we|you|i)\s+has\b", re.IGNORECASE),
        "subject_verb_disagreement",
        "have",
        False,
    ),
    (
        re.compile(r"\b(he|she|it)\s+have\b", re.IGNORECASE),
        "subject_verb_disagreement",
        "has",
        True,
    ),
]

_DOUBLE_NEGATIVE_RE = re.compile(
    r"\b(don't|didn't|can't|cannot|won't|haven't|hasn't|hadn't|wasn't|weren't|isn't|aren't|dont|didnt|cant|wont|havent|hasnt|hadnt|wasnt|werent|isnt|arent)\s+(?:have\s+|see\s+|find\s+|got\s+|get\s+)?(no\b|nothing\b|nobody\b|nowhere\b|none\b)",
    re.IGNORECASE,
)

_DID_PAST_TENSE_MAP: dict[str, str] = {
    "went": "go",
    "came": "come",
    "saw": "see",
    "took": "take",
    "wrote": "write",
    "spoke": "speak",
    "ate": "eat",
    "ran": "run",
    "bought": "buy",
}
_DID_PAST_TENSE_RE = re.compile(
    r"\bdid\s+(" + "|".join(_DID_PAST_TENSE_MAP.keys()) + r")\b",
    re.IGNORECASE,
)


class SpeechGrammarFeedback(BaseModel):
    """Speech grammar evaluation feedback."""

    total_sentences: int = Field(ge=0, description="Total sentence count in the transcript")
    issues: list[dict[str, str]] = Field(
        default_factory=list, description="List of detected grammar and speech issues"
    )
    clarity_rating: str = Field(
        description="Speech clarity rating: 'excellent', 'good', or 'needs_practice'"
    )


def _split_sentences(text: str) -> list[str]:
    """Split transcript text into sentences."""
    cleaned = text.strip()
    if not cleaned:
        return []
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
    return parts if parts else [cleaned]


def evaluate_speech_grammar(transcript: str) -> SpeechGrammarFeedback:
    """Evaluate common spoken English errors locally without external dependencies.

    Detects:
    - Repeated words (e.g., 'the the')
    - Double comparatives and superlatives (e.g., 'more better', 'most best')
    - Subject-verb disagreements (e.g., 'he don't', 'they is')
    - Double negatives (e.g., "didn't see nothing")
    - Auxiliary verb agreement (e.g., 'did went' -> 'did go')
    """
    sentences = _split_sentences(transcript)
    total_sentences = len(sentences)

    if total_sentences == 0:
        return SpeechGrammarFeedback(
            total_sentences=0,
            issues=[],
            clarity_rating="excellent",
        )

    issues: list[dict[str, str]] = []

    for sentence in sentences:
        # 1. Repeated words
        for match in _REPEATED_WORD_RE.finditer(sentence):
            word = match.group(1).lower()
            if word not in _EXCLUDED_REPETITIONS:
                issues.append(
                    {
                        "type": "repeated_word",
                        "match": match.group(0),
                        "message": f"Repeated word detected: '{match.group(1)}'",
                        "suggestion": match.group(1),
                    }
                )

        # 2. Double comparatives & superlatives
        for match in _COMPARATIVE_RE.finditer(sentence):
            adj = match.group(2).lower()
            if adj in _COMPARATIVES:
                issues.append(
                    {
                        "type": "double_comparative",
                        "match": match.group(0),
                        "message": f"Double comparative detected: '{match.group(0)}'",
                        "suggestion": match.group(2),
                    }
                )

        for match in _SUPERLATIVE_RE.finditer(sentence):
            adj = match.group(2).lower()
            if adj in _SUPERLATIVES:
                issues.append(
                    {
                        "type": "double_comparative",
                        "match": match.group(0),
                        "message": f"Double superlative detected: '{match.group(0)}'",
                        "suggestion": match.group(2),
                    }
                )

        # 3. Subject-verb disagreements
        for pattern, issue_type, suggestion_target, check_modal in _SVA_RULES:
            for match in pattern.finditer(sentence):
                if check_modal:
                    prefix_words = sentence[: match.start()].strip().split()
                    if prefix_words and prefix_words[-1].lower() in _MODAL_VERBS:
                        continue
                tokens = match.group(0).split()
                subj = tokens[0]
                issues.append(
                    {
                        "type": issue_type,
                        "match": match.group(0),
                        "message": f"Subject-verb disagreement: '{match.group(0)}'",
                        "suggestion": f"{subj} {suggestion_target}",
                    }
                )

        # 4. Double negatives
        for match in _DOUBLE_NEGATIVE_RE.finditer(sentence):
            issues.append(
                {
                    "type": "double_negative",
                    "match": match.group(0),
                    "message": f"Double negative detected: '{match.group(0)}'",
                    "suggestion": "Use a single negative formulation",
                }
            )

        # 5. Did + past tense
        for match in _DID_PAST_TENSE_RE.finditer(sentence):
            past_verb = match.group(1).lower()
            base_verb = _DID_PAST_TENSE_MAP.get(past_verb, "verb")
            issues.append(
                {
                    "type": "verb_tense",
                    "match": match.group(0),
                    "message": f"Use base verb after 'did': '{match.group(0)}'",
                    "suggestion": f"did {base_verb}",
                }
            )

    issue_count = len(issues)
    if issue_count == 0:
        clarity_rating = "excellent"
    elif issue_count <= 2:
        clarity_rating = "good"
    else:
        clarity_rating = "needs_practice"

    return SpeechGrammarFeedback(
        total_sentences=total_sentences,
        issues=issues,
        clarity_rating=clarity_rating,
    )
