from __future__ import annotations

import pytest

from techradar.library.parts import PartSpec, split_pdf_parts


def test_split_pdf_parts():
    parts = split_pdf_parts(60, 25)
    assert [(p.page_start, p.page_end) for p in parts] == [(1, 25), (26, 50), (51, 60)]
    assert [p.ordinal for p in parts] == [1, 2, 3]
    assert isinstance(parts[0], PartSpec)


def test_split_pdf_parts_edges():
    assert split_pdf_parts(0) == []
    assert [(p.page_start, p.page_end) for p in split_pdf_parts(25)] == [(1, 25)]
    assert [(p.page_start, p.page_end) for p in split_pdf_parts(26)] == [(1, 25), (26, 26)]
    with pytest.raises(ValueError):
        split_pdf_parts(10, 0)
