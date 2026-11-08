"""Unit tests for markdown chunker (Phase 2b Task 1 / SEC-41)."""

from techradar.rag.chunker import parse_front_matter, split_markdown


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
