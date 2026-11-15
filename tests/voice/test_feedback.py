from __future__ import annotations

from techradar.english.grammar_check import GrammarIssue, GrammarRule
from techradar.voice.feedback import (
    Fix,
    VoiceFeedback,
    choose_fixes,
    render_voice_report,
)
from techradar.voice.metrics import SpeechMetrics
from techradar.voice.pronounce import WordScore


def test_choose_fixes_priority_and_cap() -> None:
    m = SpeechMetrics(
        words_per_min=180.0,
        filler_count=3,
        fillers_per_min=3.0,
        filler_breakdown={"um": 3},
        long_pauses=0,
        avg_sentence_words=10.0,
        type_token_ratio=0.8,
        overused=[("very", 6)],
    )
    issue = GrammarIssue(
        rule_id="EN_A_VS_AN",
        message="Use an instead of a",
        offset=0,
        length=1,
        replacements=["an"],
        category="Articles",
        rule=GrammarRule.ARTICLES,
    )
    word = WordScore(word="world", start_s=0.2, end_s=0.5, score=0.3, flagged=True)
    fixes = choose_fixes(m, [issue] * 3, [word])
    assert [f.kind for f in fixes] == ["grammar", "pronunciation", "filler"]


def test_render_voice_report_lines() -> None:
    m = SpeechMetrics(
        words_per_min=140.0,
        filler_count=2,
        fillers_per_min=1.0,
        filler_breakdown={"um": 2},
        long_pauses=0,
        avg_sentence_words=12.0,
        type_token_ratio=0.75,
        overused=[],
    )
    fb = VoiceFeedback(
        summary="Clear and articulate speech.",
        drill="Practice varied sentence structures.",
    )
    fixes = [
        Fix(
            kind="filler",
            detail="High filler rate",
            example="um",
        )
    ]
    report = render_voice_report(
        60.0,
        m,
        issues=[],
        words=[],
        fixes=fixes,
        fb=fb,
    )
    lines = report.splitlines()
    assert lines[0] == "🎙️ Voice note · 1.0 min"
    assert "Fluency: 140.0 words/min" in lines[1]
    assert "Grammar: 0 issues · clean" in lines[2]
    assert "Next drill: Practice varied sentence structures." in lines[-1]
