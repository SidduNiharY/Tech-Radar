from __future__ import annotations

from collections.abc import Sequence


def speak_briefing(summary: str, highlights: Sequence[str]) -> str:
    """Produce spoken text for a daily briefing."""
    summary_clean = summary.strip()
    clean_highlights = [h.strip() for h in highlights if h.strip()]

    if not summary_clean and not clean_highlights:
        return "You have no briefing updates available today."

    parts: list[str] = []
    if summary_clean:
        parts.append(summary_clean)

    if clean_highlights:
        if len(clean_highlights) == 1:
            parts.append(f"Key highlight: {clean_highlights[0]}.")
        else:
            bullets = ". ".join(clean_highlights)
            parts.append(f"Key highlights: {bullets}.")

    return " ".join(parts)
