from techradar.bot.render import START_TEXT, render_status
from techradar.ops.status import SystemStatus


def test_render_status_ok():
    s = SystemStatus(
        version="0.1.0",
        db_ok=True,
        ollama_ok=True,
        loaded_models=["qwen3.5:4b"],
        disk_free_pct=72.4,
    )
    assert render_status(s) == (
        "TechRadar Brain v0.1.0\nDatabase: ok\nModels: ok (loaded: qwen3.5:4b)\nDisk free: 72%"
    )


def test_render_status_low_disk():
    s = SystemStatus(
        version="0.1.0",
        db_ok=True,
        ollama_ok=True,
        loaded_models=[],
        disk_free_pct=12.0,
    )
    assert render_status(s).splitlines()[2:] == [
        "Models: ok (none loaded)",
        "Disk free: 12% (low)",
    ]


def test_start_text():
    assert START_TEXT == "Hi. TechRadar Brain is running. Send /status to check it."
