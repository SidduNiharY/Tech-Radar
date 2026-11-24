from __future__ import annotations

import json

import pytest

from techradar.night.chains import (
    CHAIN_START,
    chain_to_mermaid,
    compose_chain,
    sanitize_label,
    with_chain,
)
from tests.fakes import FakeCompleter
from tests.night.hits import make_deps, make_hit, patch_retrieve


def test_mermaid_exact_format() -> None:
    assert chain_to_mermaid(["A", "B", "C"]) == 'flowchart LR\n  s1["A"] --> s2["B"] --> s3["C"]'


def test_mermaid_label_sanitised() -> None:
    out = chain_to_mermaid(
        [
            'Oil prices rise"]; click s1 "https://evil.example"',
            "Inflation rises",
            "RBI holds rates",
        ]
    )
    assert "click" not in out
    assert "https" not in out
    assert out.startswith('flowchart LR\n  s1["')
    assert out.count('"') == 6 and out.count("\n") == 1


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Rate <b>up</b> #quot; ;", "Rate b up b quot"),
        ("Gold hits ₹78,450 (10 g)", "Gold hits ₹78,450 (10 g)"),
        ("a %% comment", "a % comment"),
        ("style x fill:red", "x fill red"),
        ("रेपो दर बढ़ी", "रेपो दर बढ़ी"),
        ("x" * 100, "x" * 60),
        ("[[]]", ""),
    ],
)
def test_sanitize_label(raw: str, expected: str) -> None:
    assert sanitize_label(raw) == expected


def test_empty_label_gets_a_placeholder_and_no_steps_is_just_the_header() -> None:
    assert chain_to_mermaid(["", "B", "C"]).startswith('flowchart LR\n  s1["Step 1"]')
    assert chain_to_mermaid([]) == "flowchart LR"


def test_with_chain_replaces_only_its_block() -> None:
    md = "# T\nmine\n"
    once = with_chain(md, ["A", "B", "C"])
    twice = with_chain(once, ["X", "Y", "Z"])
    assert once.startswith(md.rstrip("\n")) and twice.count(CHAIN_START) == 1
    assert '```mermaid\nflowchart LR\n  s1["X"]' in twice and '"A"' not in twice


def chain_json(steps: list[str], citations: list[str]) -> str:
    return json.dumps({"steps": steps, "citations": citations})


async def test_compose_chain_sanitises_model_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_retrieve(monkeypatch, [make_hit(1), make_hit(2), make_hit(3)])
    reply = chain_json(['Oil up"]; click s1', "Inflation up", "Rates held"], ["C1"])
    status, steps = await compose_chain("oil", make_deps(FakeCompleter([reply])))
    assert status == "written" and steps is not None
    assert "click" not in " ".join(steps) and len(steps) == 3


async def test_compose_chain_rejects_bad_output(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_retrieve(monkeypatch, [make_hit(1), make_hit(2), make_hit(3)])
    three = ["A", "B", "C"]
    for reply in (
        chain_json(three, []),  # no citation
        chain_json(three, ["C7"]),  # not an excerpt
        chain_json(["See https://x.example", "B", "C"], ["C1"]),  # link
        chain_json(["A", "B"], ["C1"]),  # too short
    ):
        deps = make_deps(FakeCompleter([reply, reply]))
        assert await compose_chain("oil", deps) == ("needs_review", None)


async def test_compose_chain_needs_three_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_retrieve(monkeypatch, [make_hit(1), make_hit(2, flagged=True)])
    deps = make_deps(FakeCompleter([]))
    assert await compose_chain("oil", deps) == ("not_enough_sources", None)
    assert deps.completer.calls == []
