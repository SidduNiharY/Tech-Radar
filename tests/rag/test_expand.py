"""Neighbour expansion (Phase 2c Task 8): same document, same heading, hard caps (SEC-41)."""

import math

from techradar.rag.chunker import estimate_tokens
from techradar.rag.expand import expand_with_neighbors
from techradar.rag.retrieve import Hit


def words_for(tokens: int) -> str:
    return " ".join(["w"] * math.ceil(tokens / 1.3))


def mk(
    cid: int,
    ordinal: int | None,
    *,
    doc_id: int | None = 1,
    doc_path: str = "library/1/book.md",
    heading: list[str] | None = None,
    tokens: int = 20,
    chapter_id: int | None = 5,
    score: float = 0.9,
) -> Hit:
    return Hit(
        chunk_id=cid,
        doc_path=doc_path,
        title="Book",
        heading_path=["Ch"] if heading is None else heading,
        text=words_for(tokens),
        doc_kind="library",
        verified=True,
        generated=False,
        score=score,
        doc_id=doc_id,
        chapter_id=chapter_id,
        ordinal=ordinal,
    )


def chain(hits: list[Hit]):
    """A neighbours callable over a doc chain keyed by ordinal."""
    by_key = {(h.doc_path, h.ordinal): h for h in hits}

    def neighbors(hit: Hit) -> tuple[Hit | None, Hit | None]:
        assert hit.ordinal is not None
        return (
            by_key.get((hit.doc_path, hit.ordinal - 1)),
            by_key.get((hit.doc_path, hit.ordinal + 1)),
        )

    return neighbors


HITS_6 = [mk(i, 10 * i, doc_path=f"library/1/c{i}.md") for i in range(1, 7)]


def neighbors_always_two(hit: Hit) -> tuple[Hit | None, Hit | None]:
    assert hit.ordinal is not None
    return (
        mk(1000 + hit.chunk_id, hit.ordinal - 1, doc_path=hit.doc_path),
        mk(2000 + hit.chunk_id, hit.ordinal + 1, doc_path=hit.doc_path),
    )


def test_expand_respects_caps():
    out = expand_with_neighbors(HITS_6, neighbors_always_two)
    assert len(out) == 6
    assert {h.chunk_id for h in out} == {h.chunk_id for h in HITS_6}


def test_expand_empty():
    assert expand_with_neighbors([], neighbors_always_two) == []


def test_expand_adds_before_and_after_in_document_order():
    book = [mk(i, i) for i in range(1, 10)]
    out = expand_with_neighbors([book[4]], chain(book))
    assert [h.ordinal for h in out] == [4, 5, 6]


def test_expand_edges_of_a_book_have_one_neighbour():
    book = [mk(i, i) for i in range(1, 4)]
    out = expand_with_neighbors([book[0]], chain(book))
    assert [h.ordinal for h in out] == [1, 2]


def test_expand_dedupes_adjacent_hits():
    book = [mk(i, i) for i in range(1, 10)]
    out = expand_with_neighbors([book[4], book[3]], chain(book))
    assert [h.ordinal for h in out] == [3, 4, 5, 6]
    assert len({h.chunk_id for h in out}) == len(out)


def test_expand_groups_by_document_best_ranked_first_then_reading_order():
    a = [mk(i, i, doc_id=1, doc_path="library/1/a.md") for i in range(1, 10)]
    b = [mk(100 + i, i, doc_id=2, doc_path="library/2/b.md") for i in range(1, 10)]
    both = {(h.doc_path, h.ordinal): h for h in a + b}

    def neighbors(h: Hit) -> tuple[Hit | None, Hit | None]:
        assert h.ordinal is not None
        return both.get((h.doc_path, h.ordinal - 1)), both.get((h.doc_path, h.ordinal + 1))

    out = expand_with_neighbors([b[1], a[6], a[2]], neighbors, max_excerpts=20)
    assert [(h.doc_id, h.ordinal) for h in out] == [
        (2, 1),
        (2, 2),
        (2, 3),
        (1, 2),
        (1, 3),
        (1, 4),
        (1, 6),
        (1, 7),
        (1, 8),
    ]


def test_neighbours_never_cross_documents():
    hit = mk(1, 5, doc_id=1, doc_path="library/1/a.md")
    other_doc = mk(2, 4, doc_id=2, doc_path="library/1/a.md")
    other_path = mk(3, 6, doc_id=1, doc_path="library/2/a.md")
    out = expand_with_neighbors([hit], lambda _h: (other_doc, other_path))
    assert out == [hit]


def test_neighbours_must_share_the_doc_id_even_when_the_hit_has_none():
    hit = mk(1, 5, doc_id=None, doc_path="notes/a.md")
    foreign = mk(2, 4, doc_id=7, doc_path="notes/a.md")
    own = mk(3, 6, doc_id=None, doc_path="notes/a.md")
    out = expand_with_neighbors([hit], lambda _h: (foreign, own))
    assert [h.chunk_id for h in out] == [1, 3]


def test_neighbours_must_share_the_heading_path_and_chapter():
    hit = mk(1, 5, heading=["Ch", "A"])
    other_heading = mk(2, 4, heading=["Ch", "B"])
    other_chapter = mk(3, 6, heading=["Ch", "A"], chapter_id=6)
    out = expand_with_neighbors([hit], lambda _h: (other_heading, other_chapter))
    assert out == [hit]


def test_max_excerpts_prefers_hits_over_neighbours():
    book = [mk(i, i) for i in range(1, 30)]
    hits = [book[3], book[10], book[20]]
    out = expand_with_neighbors(hits, chain(book), max_excerpts=4)
    assert len(out) == 4
    ids = {h.chunk_id for h in out}
    assert {4, 11, 21} <= ids
    # the best-ranked hit (id 4) gets its neighbour first
    assert ids - {4, 11, 21} <= {3, 5}


def test_token_cap_with_huge_chunks():
    hit = mk(1, 5, tokens=1000)
    huge_before = mk(2, 4, tokens=5000)
    huge_after = mk(3, 6, tokens=5000)
    out = expand_with_neighbors([hit], lambda _h: (huge_before, huge_after), max_tokens=8000)
    assert sum(estimate_tokens(h.text) for h in out) <= 8000
    assert [h.chunk_id for h in out] == [2, 1]


def test_token_cap_applies_to_the_hits_themselves():
    hits = [mk(i, i * 10, tokens=5000, doc_path=f"library/1/{i}.md") for i in range(1, 4)]
    out = expand_with_neighbors(hits, neighbors_always_two, max_tokens=8000)
    # only the first 5000-token hit fits; the other two would pass 8000 and are skipped
    assert [h.chunk_id for h in out if h.chunk_id < 1000] == [1]
    assert sum(estimate_tokens(h.text) for h in out) <= 8000


def test_oversized_hit_is_skipped_not_truncated():
    big = mk(1, 10, tokens=9000)
    small = mk(2, 20, tokens=100, doc_path="library/1/other.md")
    out = expand_with_neighbors([big, small], lambda _h: (None, None), max_tokens=8000)
    assert [h.chunk_id for h in out] == [2]


def test_expand_does_not_mutate_input_and_keeps_hit_scores():
    hits = [mk(1, 5, score=0.77)]
    book = [mk(i, i) for i in range(1, 10)]
    out = expand_with_neighbors(hits, chain(book))
    assert len(hits) == 1
    assert [h.score for h in out if h.chunk_id == 1] == [0.77]
