from __future__ import annotations

from techradar.voice.fluency import (
    FILLER_WORDS,
    FluencyMetrics,
    analyze_fluency,
)


def test_clean_transcript_without_fillers_gets_high_fluency_score():
    transcript = (
        "Distributed systems require careful consideration of consensus algorithms, "
        "partition tolerance, and data replication strategies to ensure reliable operation."
    )
    # 18 words in 7.0 seconds => ~154.29 WPM (well within 100-200 WPM range)
    metrics = analyze_fluency(transcript, duration_seconds=7.0)

    assert isinstance(metrics, FluencyMetrics)
    assert metrics.word_count == 18
    assert metrics.filler_word_count == 0
    assert metrics.filler_word_frequency_pct == 0.0
    assert metrics.filler_words_breakdown == {}
    assert 150.0 < metrics.words_per_minute < 160.0
    assert metrics.fluency_score == 100.0


def test_filler_word_detection_single_and_multi_word():
    transcript = "Um, I think that, uh, this system is, you know, resilient."
    # Words: um, i, think, that, uh, this, system, is, you, know, resilient (11 words)
    metrics = analyze_fluency(transcript, duration_seconds=5.0)

    assert metrics.filler_word_count == 3
    assert metrics.filler_words_breakdown.get("um") == 1
    assert metrics.filler_words_breakdown.get("uh") == 1
    assert metrics.filler_words_breakdown.get("you know") == 1
    assert metrics.filler_word_frequency_pct == round((3 / 11) * 100.0, 2)
    assert metrics.fluency_score < 100.0


def test_all_default_filler_words_detected():
    transcript = "Um, uh, er, ah, like, you know, actually, basically, literally."
    metrics = analyze_fluency(transcript, duration_seconds=10.0)

    for filler in FILLER_WORDS:
        assert filler in metrics.filler_words_breakdown
        assert metrics.filler_words_breakdown[filler] == 1

    assert metrics.filler_word_count == len(FILLER_WORDS)


def test_wpm_calculation_and_extreme_rates():
    # 120 words in 60s => 120 WPM (normal, no penalty)
    normal_text = " ".join(["word"] * 120)
    normal_metrics = analyze_fluency(normal_text, duration_seconds=60.0)
    assert normal_metrics.words_per_minute == 120.0
    assert normal_metrics.fluency_score == 100.0

    # 40 words in 60s => 40 WPM (slow, penalty = (100 - 40) * 0.5 = 30)
    slow_text = " ".join(["word"] * 40)
    slow_metrics = analyze_fluency(slow_text, duration_seconds=60.0)
    assert slow_metrics.words_per_minute == 40.0
    assert slow_metrics.fluency_score == 70.0

    # 260 words in 60s => 260 WPM (fast, penalty = (260 - 200) * 0.5 = 30)
    fast_text = " ".join(["word"] * 260)
    fast_metrics = analyze_fluency(fast_text, duration_seconds=60.0)
    assert fast_metrics.words_per_minute == 260.0
    assert fast_metrics.fluency_score == 70.0


def test_boundary_edge_cases_zero_duration_and_empty_text():
    # Zero duration
    m_zero_dur = analyze_fluency("Hello world", duration_seconds=0.0)
    assert m_zero_dur.duration_seconds == 0.0
    assert m_zero_dur.words_per_minute == 0.0
    assert m_zero_dur.fluency_score == 0.0
    assert m_zero_dur.word_count == 2

    # Negative duration
    m_neg_dur = analyze_fluency("Hello world", duration_seconds=-5.0)
    assert m_neg_dur.duration_seconds == 0.0
    assert m_neg_dur.words_per_minute == 0.0
    assert m_neg_dur.fluency_score == 0.0

    # Empty transcript
    m_empty = analyze_fluency("", duration_seconds=30.0)
    assert m_empty.word_count == 0
    assert m_empty.words_per_minute == 0.0
    assert m_empty.filler_word_count == 0
    assert m_empty.filler_word_frequency_pct == 0.0
    assert m_empty.filler_words_breakdown == {}
    assert m_empty.fluency_score == 0.0

    # Whitespace only
    m_spaces = analyze_fluency("   \n\t  ", duration_seconds=20.0)
    assert m_spaces.word_count == 0
    assert m_spaces.words_per_minute == 0.0
    assert m_spaces.fluency_score == 0.0

    # Both empty and zero duration
    m_both = analyze_fluency("", duration_seconds=0.0)
    assert m_both.word_count == 0
    assert m_both.words_per_minute == 0.0
    assert m_both.fluency_score == 0.0


def test_case_insensitivity_and_punctuation():
    transcript = "UM... Like?! YOU know, actually!"
    metrics = analyze_fluency(transcript, duration_seconds=4.0)

    assert metrics.filler_words_breakdown.get("um") == 1
    assert metrics.filler_words_breakdown.get("like") == 1
    assert metrics.filler_words_breakdown.get("you know") == 1
    assert metrics.filler_words_breakdown.get("actually") == 1
    assert metrics.filler_word_count == 4
