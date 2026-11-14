"""Neighbour expansion for big-book answers (Phase 2c Task 8).

A good hit is often cut off mid-argument, so the chunk before and after it (same book, same
heading, same chapter) is added to the excerpts the model sees, within hard caps.

SEC: SEC-41 (at most 6 excerpts and 8,000 tokens of context).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import and_, or_, select

from techradar.db.models import Chunk
from techradar.rag.chunker import estimate_tokens
from techradar.rag.retrieve import Hit, RagDeps, RetrieveFilters, chunk_to_hit

NeighborFn = Callable[[Hit], tuple[Hit | None, Hit | None]]

MAX_EXCERPTS = 6
MAX_CONTEXT_TOKENS = 8000


def _same_section(anchor: Hit, other: Hit) -> bool:
    """A neighbour must come from the same book, path, chapter and heading as its anchor."""
    return (
        other.doc_id == anchor.doc_id
        and other.doc_path == anchor.doc_path
        and other.chapter_id == anchor.chapter_id
        and other.heading_path == anchor.heading_path
    )


def expand_with_neighbors(
    hits: Sequence[Hit],
    neighbors: NeighborFn,
    *,
    max_excerpts: int = MAX_EXCERPTS,
    max_tokens: int = MAX_CONTEXT_TOKENS,
) -> list[Hit]:
    """Add the chunk before and after each hit, in document order, within the caps.

    Hits (best first) are kept before any neighbour; neighbours are added best-hit first. A chunk
    that would break the excerpt or token cap is skipped. Pure: `neighbors` does the lookup.
    """
    chosen: list[Hit] = []
    used = 0
    for h in hits:
        if len(chosen) >= max_excerpts:
            break
        cost = estimate_tokens(h.text)
        if used + cost > max_tokens:
            continue
        chosen.append(h)
        used += cost

    seen = {h.chunk_id for h in chosen}
    before: dict[int, Hit] = {}
    after: dict[int, Hit] = {}
    count = len(chosen)
    for anchor in chosen:
        if count >= max_excerpts:
            break
        prev, nxt = neighbors(anchor)
        for slot, cand in ((before, prev), (after, nxt)):
            if count >= max_excerpts:
                break
            if cand is None or cand.chunk_id in seen or not _same_section(anchor, cand):
                continue
            cost = estimate_tokens(cand.text)
            if used + cost > max_tokens:
                continue
            slot[anchor.chunk_id] = cand
            seen.add(cand.chunk_id)
            used += cost
            count += 1

    # Document order: documents by their best hit, then reading order inside each document.
    first_rank: dict[tuple[int | None, str], int] = {}
    for rank, h in enumerate(chosen):
        first_rank.setdefault((h.doc_id, h.doc_path), rank)
    order = sorted(
        range(len(chosen)),
        key=lambda i: (
            first_rank[(chosen[i].doc_id, chosen[i].doc_path)],
            chosen[i].ordinal if chosen[i].ordinal is not None else i,
            i,
        ),
    )
    out: list[Hit] = []
    for i in order:
        h = chosen[i]
        if h.chunk_id in before:
            out.append(before[h.chunk_id])
        out.append(h)
        if h.chunk_id in after:
            out.append(after[h.chunk_id])
    return out


async def load_neighbors(
    deps: RagDeps,
    hits: Sequence[Hit],
    f: RetrieveFilters | None = None,
) -> NeighborFn:
    """Fetch the chunks at ordinal - 1 and + 1 of each hit (same doc_path) in one query.

    Returns the pure `neighbors` callable for `expand_with_neighbors`. Neighbours inherit the
    anchor's score and obey the same generated/verified filters as retrieval.
    """
    f = f or RetrieveFilters()
    anchors = [h for h in hits if h.ordinal is not None]
    lookup: dict[tuple[str, int | None, int | None, int], Chunk] = {}
    if anchors:
        clauses = [
            and_(
                Chunk.doc_path == h.doc_path,
                Chunk.ordinal.in_([h.ordinal - 1, h.ordinal + 1]),  # type: ignore[operator]
                Chunk.doc_id == h.doc_id if h.doc_id is not None else Chunk.doc_id.is_(None),
            )
            for h in anchors
        ]
        stmt = select(Chunk).where(or_(*clauses))
        if not f.include_generated:
            stmt = stmt.where(Chunk.generated.is_(False))
        if f.verified_only:
            stmt = stmt.where(Chunk.verified.is_(True))
        async with deps.ro_session_factory() as session:
            res = await session.execute(stmt)
            for c in res.scalars().all():
                lookup[(c.doc_path, c.doc_id, c.chapter_id, c.ordinal)] = c

    def neighbors(hit: Hit) -> tuple[Hit | None, Hit | None]:
        if hit.ordinal is None:
            return None, None

        def get(ordinal: int) -> Hit | None:
            chunk = lookup.get((hit.doc_path, hit.doc_id, hit.chapter_id, ordinal))
            return chunk_to_hit(chunk, hit.score) if chunk is not None else None

        return get(hit.ordinal - 1), get(hit.ordinal + 1)

    return neighbors
