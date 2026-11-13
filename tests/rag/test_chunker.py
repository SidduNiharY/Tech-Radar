"""Unit tests for markdown chunker (Phase 2b Task 1 / SEC-41)."""

import re

from techradar.rag.chunker import context_label, page_of, parse_front_matter, split_markdown


def test_front_matter_excluded_and_parsed():
    fm, body = parse_front_matter("---\nkind: news\n---\n# T\nText")
    assert fm == {"kind": "news"} and not body.startswith("---")
    assert all(
        "kind: news" not in c.text
        for c in split_markdown("---\nkind: news\n---\n# T\nText", "a.md")
    )


def test_heading_path_kept():
    cs = split_markdown("# Economy\n## Inflation\nPrices rose.", "f.md")
    assert cs[0].heading_path == ["Economy", "Inflation"]


def test_long_section_split_with_overlap():
    cs = split_markdown("# H\n" + "\n\n".join(["word " * 200] * 6), "x.md")
    assert len(cs) >= 3 and cs[1].text.split()[:5] == cs[0].text.split()[-60:][:5]


def test_code_fence_not_split():
    md = "# H\n```python\n" + "x = 1\n" * 400 + "```\n"
    assert sum("```" in c.text for c in split_markdown(md, "c.md")) == 1


def test_empty_doc_gives_no_chunks():
    assert split_markdown("---\na: 1\n---\n", "e.md") == []


def test_indic_text_chunks():
    assert split_markdown("# भारत\nअर्थव्यवस्था बढ़ी।", "h.md")[0].text.endswith("बढ़ी।")


def _table(n_rows: int, header: str = "| a | b |") -> str:
    return "\n".join([header, "|---|---|"] + [f"| {i} | {i * 2} |" for i in range(n_rows)])


def test_table_kept_whole():
    md = "# T\n" + _table(40)
    cs = split_markdown(md, "t.md", target_tokens=50)
    assert sum("| a | b |" in c.text for c in cs) == 1  # a table under 4,000 chars is never split


def test_table_stays_whole_next_to_text_and_without_blank_lines():
    md = "# T\nintro words here\n" + _table(40) + "\noutro words " + "w " * 300
    cs = split_markdown(md, "t.md", target_tokens=50)
    holders = [c for c in cs if "| a | b |" in c.text]
    assert len(holders) == 1 and all(f"| {i} | {i * 2} |" in holders[0].text for i in range(40))


def test_text_after_table_carries_no_table_rows_as_overlap():
    md = "# T\n" + _table(40) + "\n\n" + "\n\n".join(["word " * 100] * 3)
    cs = split_markdown(md, "t.md", target_tokens=50)
    assert sum("| 39 | 78 |" in c.text for c in cs) == 1


def test_big_table_split_at_rows_with_header_repeated():
    md = "# T\nbefore\n\n" + _table(400) + "\n\nafter"
    assert len(_table(400)) > 4000
    cs = split_markdown(md, "t.md")
    pieces = [c for c in cs if "|---|---|" in c.text]
    assert len(pieces) >= 2
    seen: list[str] = []
    for c in pieces:
        lines = c.text.splitlines()
        assert lines[0] == "| a | b |" and lines[1] == "|---|---|"
        assert len(c.text) <= 4000
        assert all(re.fullmatch(r"\| \d+ \| \d+ \|", row) for row in lines[2:])  # no row cut
        seen += lines[2:]
    assert seen == [f"| {i} | {i * 2} |" for i in range(400)]  # every row exactly once
    assert cs[0].text == "before" and cs[-1].text == "after"
    assert [c.ordinal for c in cs] == list(range(len(cs)))


def test_keep_tables_false_keeps_phase_2b_behaviour():
    md = "# T\nintro\n" + _table(5)
    cs = split_markdown(md, "t.md", keep_tables=False)
    assert len(cs) == 1 and cs[0].text.startswith("intro\n| a | b |")


def test_table_inside_code_fence_is_not_a_table():
    md = "# H\n```\n" + _table(500) + "\n```\n"
    cs = split_markdown(md, "c.md")
    assert len(cs) == 1 and "```" in cs[0].text


def test_page_marker_sets_page_and_is_removed():
    page, text = page_of("<!-- page 12 -->\nThe repo rate is...", None)
    assert page == 12 and "<!--" not in text and text == "The repo rate is..."


def test_page_of_uses_last_marker_and_falls_back():
    two = "<!-- page 3 -->\nfirst\n\n<!-- page 4 -->\nsecond"
    assert page_of(two, 1) == (4, "first\n\nsecond")
    assert page_of("no marker here", 7) == (7, "no marker here")
    assert page_of("no marker here", None) == (None, "no marker here")


def test_page_of_removes_only_exact_page_markers():
    page, text = page_of("<!-- page 2 --> a <!-- note --> b <!-- page x --> c", None)
    assert page == 2 and text == "a <!-- note --> b <!-- page x --> c"
    assert page_of("<!-- page 99999999999 -->\nz", 5) == (5, "<!-- page 99999999999 -->\nz")


def test_context_label_format_and_cap():
    assert context_label("Indian Economy", "Money", ["Banks"]) == "Indian Economy › Money › Banks"
    assert context_label("Indian Economy", "Money", ["Banks", "RBI"]).endswith("Banks › RBI")
    assert context_label("Book", "Chapter", []) == "Book › Chapter"
    assert context_label("Book", "", [" ", "Sec"]) == "Book › Sec"
    long = context_label("B" * 150, "C" * 150, ["S" * 150])
    assert len(long) == 200 and long.startswith("B")
