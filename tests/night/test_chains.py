from __future__ import annotations

from techradar.night.chains import chain_to_mermaid


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
