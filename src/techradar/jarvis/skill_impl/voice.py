from __future__ import annotations


def speak_voice_feedback(score: float, top_fix: str | None) -> str:
    """Produce spoken text for pronunciation/voice coaching feedback."""
    score_str = f"{score:.1f}" if score % 1 != 0 else f"{int(score)}"
    base = f"Your speech score is {score_str}."

    if top_fix and top_fix.strip():
        return f"{base} Top area to focus on: {top_fix.strip()}."
    return f"{base} Great job, no critical pronunciation fixes needed."
