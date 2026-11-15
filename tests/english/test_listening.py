from __future__ import annotations

from techradar.english.listening import (
    Coverage,
    KeyPoints,
    render_coverage,
)


def test_listening_coverage_reply() -> None:
    assert (
        render_coverage(KeyPoints(points=["a", "b", "c", "d"]), Coverage(covered=[0, 2]))
        == "You covered 2 of 4 key points. Missed: b, d."
    )


def test_listening_coverage_all_covered() -> None:
    assert (
        render_coverage(
            KeyPoints(points=["alpha", "beta", "gamma"]),
            Coverage(covered=[0, 1, 2]),
        )
        == "You covered 3 of 3 key points. Missed: none."
    )
