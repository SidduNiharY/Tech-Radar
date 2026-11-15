"""Tests for voice pitch contour extraction and DTW comparison."""

from __future__ import annotations

import numpy as np

from techradar.voice.pitch import compare_pitch_contours, pitch_contour


def test_pitch_of_220hz_sine():
    t = np.arange(16_000) / 16_000
    wav = (0.3 * np.sin(2 * np.pi * 220 * t)).astype("float32")
    hz = [f for _, f in pitch_contour(wav)]
    assert abs(np.median(hz) - 220) < 5


def test_compare_pitch_contours_identical():
    u = [200.0, 220.0, 240.0, 220.0, 200.0]
    ref = [200.0, 220.0, 240.0, 220.0, 200.0]
    result = compare_pitch_contours(u, ref)
    assert result.score == 1.0
    assert "Excellent" in result.feedback
    assert result.feedback_text == result.feedback


def test_compare_pitch_contours_transposed_contour():
    # Male vs female pitch range with identical relative intonation contour
    u = [100.0, 110.0, 120.0, 110.0, 100.0]
    ref = [200.0, 220.0, 240.0, 220.0, 200.0]
    result = compare_pitch_contours(u, ref)
    assert result.score == 1.0


def test_compare_pitch_contours_inverted():
    # Inverted inflection contour
    u = [240.0, 220.0, 200.0, 220.0, 240.0]
    ref = [200.0, 220.0, 240.0, 220.0, 200.0]
    result = compare_pitch_contours(u, ref)
    assert 0.0 < result.score < 0.7


def test_compare_pitch_contours_monotone_feedback():
    u = [200.0, 200.0, 200.0, 200.0, 200.0]
    ref = [180.0, 220.0, 280.0, 220.0, 180.0]
    result = compare_pitch_contours(u, ref)
    assert "monotone" in result.feedback


def test_compare_pitch_contours_empty():
    res1 = compare_pitch_contours([], [200.0, 220.0])
    assert res1.score == 0.0
    assert "No voiced pitch detected" in res1.feedback

    res2 = compare_pitch_contours([0.0, -10.0], [0.0])
    assert res2.score == 0.0
