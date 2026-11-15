"""Voice pitch extraction and contour comparison using DTW."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PitchFeedback:
    """Feedback result comparing user and reference pitch contours."""

    score: float
    feedback: str

    @property
    def feedback_text(self) -> str:
        return self.feedback


def pitch_contour(
    wav: np.ndarray,
    sr: int = 16_000,
    step_s: float = 0.02,
) -> list[tuple[float, float]]:
    """Extract pitch contour as (timestamp_s, pitch_hz) pairs.

    Unvoiced frames and silence are dropped.
    """
    try:
        import parselmouth

        sound = parselmouth.Sound(wav, sampling_frequency=sr)
        pitch = sound.to_pitch(time_step=step_s)
        frames: list[tuple[float, float]] = []
        for t in pitch.xs():
            val = pitch.get_value_at_time(t)
            if val is not None and not np.isnan(val) and val > 0:
                frames.append((float(t), float(val)))
        return frames
    except ImportError:
        # High-accuracy autocorrelation fallback
        win_len = int(sr * 0.04)  # 40ms analysis window
        step_len = int(sr * step_s)
        min_lag = int(sr / 500)  # max pitch 500 Hz
        max_lag = int(sr / 75)  # min pitch 75 Hz
        results: list[tuple[float, float]] = []

        for start in range(0, len(wav) - win_len, step_len):
            frame = wav[start : start + win_len]
            energy = float(np.sum(frame**2))
            if energy < 1e-4:
                continue
            corr = np.correlate(frame, frame, mode="full")
            corr = corr[len(frame) - 1 :]
            if len(corr) <= max_lag:
                continue
            lag_window = corr[min_lag:max_lag]
            peak_idx = int(np.argmax(lag_window)) + min_lag
            if corr[0] > 0 and (corr[peak_idx] / corr[0]) > 0.3:
                # Parabolic peak interpolation
                if 0 < peak_idx < len(corr) - 1:
                    alpha = float(corr[peak_idx - 1])
                    beta = float(corr[peak_idx])
                    gamma = float(corr[peak_idx + 1])
                    denom = alpha - 2 * beta + gamma
                    delta = 0.5 * (alpha - gamma) / (denom + 1e-12) if abs(denom) > 1e-12 else 0.0
                    fine_lag = peak_idx + delta
                else:
                    fine_lag = float(peak_idx)
                hz = sr / fine_lag
                t = start / sr
                results.append((float(t), float(hz)))
        return results


def compare_pitch_contours(
    user_pitch: Sequence[float],
    ref_pitch: Sequence[float],
) -> PitchFeedback:
    """Compare user and reference pitch contours using semitone DTW."""
    u = np.array([float(x) for x in user_pitch if x > 0 and not np.isnan(x)], dtype=float)
    r = np.array([float(x) for x in ref_pitch if x > 0 and not np.isnan(x)], dtype=float)

    if len(u) == 0 or len(r) == 0:
        return PitchFeedback(
            score=0.0,
            feedback="No voiced pitch detected in one or both recordings.",
        )

    # Convert to relative semitones relative to median pitch
    med_u = float(np.median(u))
    med_r = float(np.median(r))
    st_u = 12.0 * np.log2(u / med_u)
    st_r = 12.0 * np.log2(r / med_r)

    # Dynamic Time Warping
    n, m = len(st_u), len(st_r)
    dtw = np.full((n + 1, m + 1), float("inf"))
    dtw[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = abs(st_u[i - 1] - st_r[j - 1])
            dtw[i, j] = cost + min(dtw[i - 1, j], dtw[i, j - 1], dtw[i - 1, j - 1])

    avg_cost = float(dtw[n, m]) / max(1, n + m)
    score = round(max(0.0, min(1.0, float(np.exp(-avg_cost / 1.5)))), 3)

    # Intonation feedback text
    range_u = float(np.ptp(st_u)) if len(st_u) > 1 else 0.0
    range_r = float(np.ptp(st_r)) if len(st_r) > 1 else 0.0

    if score >= 0.88:
        base_msg = "Excellent pitch contour match. Your intonation closely tracks the reference."
    elif score >= 0.72:
        base_msg = "Good pitch contour alignment with minor inflection variations."
    elif score >= 0.52:
        base_msg = "Moderate pitch match. Pay attention to pitch rise and fall patterns."
    else:
        base_msg = "Low pitch correlation. Practice mimicking the melodic contour of the speaker."

    if range_u < 0.5 * range_r and range_r > 2.0:
        notes = " Your voice is relatively monotone; try adding more pitch modulation."
    elif range_u > 2.0 * range_r and range_u > 4.0:
        notes = " Your pitch variations are wider than the reference."
    else:
        notes = ""

    return PitchFeedback(score=score, feedback=f"{base_msg}{notes}")
