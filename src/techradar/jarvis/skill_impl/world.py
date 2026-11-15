from __future__ import annotations


def speak_world_update(key_headline: str, series_change: str | None) -> str:
    """Produce spoken text for world affairs and economic indicators."""
    headline_clean = key_headline.strip()
    if not headline_clean:
        return "No world updates available right now."

    base = f"World update: {headline_clean}."
    if series_change and series_change.strip():
        return f"{base} Indicator trend: {series_change.strip()}."
    return base
