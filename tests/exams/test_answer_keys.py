from __future__ import annotations

import re

import pytest

from techradar.exams.answer_keys import (
    load_capture_pattern,
    matching_links,
    render_answer_key_notice,
)


def test_matching_links_only_pattern_and_absolute():
    html = '<a href="/res/ans_key_cgl.pdf">Key</a><a href="https://evil.example/answer.pdf">x</a>'
    assert matching_links(
        html,
        "https://ssc.gov.in/notices",
        re.compile(r"^https://ssc\.gov\.in/.+ans.+\.pdf$"),
    ) == ["https://ssc.gov.in/res/ans_key_cgl.pdf"]


def test_pattern_must_anchor_official_host():
    # Official hosts accepted
    pat1 = load_capture_pattern(r"^https://ssc\.gov\.in/.+answer.+\.pdf$")
    assert isinstance(pat1, re.Pattern)
    pat2 = load_capture_pattern(r"^https://gate2024\.iisc\.ac\.in/.+\.pdf$")
    assert isinstance(pat2, re.Pattern)
    pat3 = load_capture_pattern(r"^https://ibps\.in/.+\.pdf$")
    assert isinstance(pat3, re.Pattern)

    # Non-official or unanchored rejected with ValueError
    with pytest.raises(ValueError):
        load_capture_pattern(r"^https://free-pdfs\.example/.+\.pdf$")
    with pytest.raises(ValueError):
        load_capture_pattern(r".+answer.+\.pdf")
    with pytest.raises(ValueError):
        load_capture_pattern(r"http://ssc.gov.in/answer.pdf")
    with pytest.raises(ValueError):
        load_capture_pattern(r"^https://.*\.gov\.in/.+\.pdf$")


def test_matching_links_deduplication_and_order():
    html = """
    <div>
        <a href="/doc1.pdf">Doc 1</a>
        <a href="/doc2.pdf">Doc 2</a>
        <a href="/doc1.pdf">Doc 1 Repeat</a>
        <a href="/doc3.pdf">Doc 3</a>
    </div>
    """
    pat = re.compile(r"^https://ssc\.gov\.in/doc\d\.pdf$")
    links = matching_links(html, "https://ssc.gov.in/list", pat)
    assert links == [
        "https://ssc.gov.in/doc1.pdf",
        "https://ssc.gov.in/doc2.pdf",
        "https://ssc.gov.in/doc3.pdf",
    ]


def test_matching_links_capped_at_20():
    html = "".join(f'<a href="/ans_{i}.pdf">Key {i}</a>' for i in range(50))
    pat = re.compile(r"^https://ssc\.gov\.in/ans_\d+\.pdf$")
    links = matching_links(html, "https://ssc.gov.in", pat)
    assert len(links) == 20
    assert links[0] == "https://ssc.gov.in/ans_0.pdf"
    assert links[19] == "https://ssc.gov.in/ans_19.pdf"


def test_render_answer_key_notice():
    msg = render_answer_key_notice("cgl_2025_tier1_key.pdf", "ssc cgl")
    assert msg == "New answer key saved: cgl_2025_tier1_key.pdf (SSC CGL). It's in your library."
