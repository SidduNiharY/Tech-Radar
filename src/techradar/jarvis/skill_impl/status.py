from __future__ import annotations


def speak_system_status(uptime_h: float, ok: bool) -> str:
    """Produce spoken text for system health and uptime status."""
    uptime_str = f"{uptime_h:.1f}" if uptime_h % 1 != 0 else f"{int(uptime_h)}"
    hours_label = "hour" if uptime_h == 1.0 else "hours"

    if ok:
        return f"All systems are operational. Uptime is {uptime_str} {hours_label}."
    return f"System degradation detected. Uptime is {uptime_str} {hours_label}."
