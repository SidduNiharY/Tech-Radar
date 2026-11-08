from techradar.bot.render import START_TEXT, render_answer, render_status
from techradar.ops.status import SystemStatus
from techradar.rag.answer import NOT_FOUND, Answer, Citation


def test_render_status_ok() -> None:
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


def test_render_status_low_disk() -> None:
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


def test_start_text() -> None:
    assert START_TEXT == "Hi. TechRadar Brain is running. Send /status to check it."


def test_render_answer_answered() -> None:
    cit = Citation(n=1, doc_path="d", title="RBI policy", heading="Rates", verified=True)
    a = Answer(
        text="It stayed at 5.5% [C1].",
        citations=[cit],
        status="answered",
        used_unverified=False,
        flags=[],
    )
    expected = "It stayed at 5.5% [C1].\n\nSources:\n[1] RBI policy › Rates (verified)"
    assert render_answer(a) == expected


def test_render_answer_not_found() -> None:
    empty = Answer(
        text=NOT_FOUND,
        citations=[],
        status="not_found",
        used_unverified=False,
        flags=[],
    )
    assert render_answer(empty) == NOT_FOUND


def test_render_answer_needs_review() -> None:
    a = Answer(
        text="Suspicious output",
        citations=[],
        status="needs_review",
        used_unverified=False,
        flags=["bad_citation", "too_long"],
    )
    assert render_answer(a) == "I couldn't answer that safely. (bad_citation, too_long)"


def test_render_answer_warnings() -> None:
    a = Answer(
        text="Draft fact [C1].",
        citations=[
            Citation(n=1, doc_path="d", title="Notes", heading="", verified=False),
        ],
        status="answered",
        used_unverified=True,
        flags=["used_flagged"],
    )
    rendered = render_answer(a)
    assert "⚠️ Uses unverified notes." in rendered
    assert "⚠️ Uses pages flagged by the Intake Gateway." in rendered
