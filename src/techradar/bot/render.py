"""Render Telegram bot responses."""

from techradar.ops.status import SystemStatus

START_TEXT: str = "Hi. TechRadar Brain is running. Send /status to check it."


def render_status(s: SystemStatus) -> str:
    """Render a SystemStatus object into human-readable text."""
    lines: list[str] = [f"TechRadar Brain v{s.version}"]

    # Database
    lines.append("Database: ok" if s.db_ok else "Database: down")

    # Models / Ollama
    if s.ollama_ok:
        if s.loaded_models:
            lines.append(f"Models: ok (loaded: {', '.join(s.loaded_models)})")
        else:
            lines.append("Models: ok (none loaded)")
    else:
        lines.append("Models: down")

    # Disk
    disk_pct = int(round(s.disk_free_pct))
    if s.disk_free_pct < 15.0:
        lines.append(f"Disk free: {disk_pct}% (low)")
    else:
        lines.append(f"Disk free: {disk_pct}%")

    return "\n".join(lines)
