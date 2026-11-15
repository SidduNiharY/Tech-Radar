from __future__ import annotations

from techradar.night.glossary import glossary_candidates


def test_glossary_candidates() -> None:
    assert glossary_candidates({"repo rate": 4, "GDP": 2, "CRR": 5}, {"crr"}) == ["repo rate"]
