"""Render Telegram bot responses."""

from techradar.ops.status import SystemStatus
from techradar.rag.answer import NOT_FOUND, Answer

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


def render_answer(a: Answer) -> str:
    """Format grounded answer into text with sources and security indicators."""
    if a.status == "not_found":
        return NOT_FOUND
    if a.status == "needs_review":
        flags_str = ", ".join(a.flags)
        return f"I couldn't answer that safely. ({flags_str})"

    lines = [a.text, "", "Sources:"]
    for c in a.citations:
        if c.verified is True:
            v_tag = "verified"
        elif c.verified is False:
            v_tag = "unverified"
        else:
            v_tag = "note"
        heading_part = f" › {c.heading}" if c.heading else ""
        lines.append(f"[{c.n}] {c.title}{heading_part} ({v_tag})")

    if a.used_unverified:
        lines.append("⚠️ Uses unverified notes.")
    if "used_flagged" in a.flags:
        lines.append("⚠️ Uses pages flagged by the Intake Gateway.")

    return "\n".join(lines)
