"""Scoped document retrieval ("Ask this PDF" / Phase 4 & Phase 2c).

Constrains hybrid retrieval (vector cosine search and full-text search)
to chunks belonging to a single document (doc_id), fused with RRF,
and reranked with cross-encoder.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import column, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Chunk
from techradar.rag.retrieve import Hit, RagDeps, RetrieveFilters, rrf


class ScopedHit(Hit):
    """Retrieved search result chunk with doc_id scoped to a specific document."""

    doc_id: str | None = None


def _doc_id_clause(doc_id: str) -> Any:
    """Generate SQLAlchemy WHERE clause to match chunk against doc_id."""
    doc_id_str = str(doc_id)
    doc_col = getattr(Chunk, "doc_id", column("doc_id"))
    return or_(
        doc_col == doc_id_str,
        Chunk.doc_path == doc_id_str,
        Chunk.doc_path.like(f"library/{doc_id_str}/%"),
        Chunk.doc_path.like(f"%/{doc_id_str}.%"),
        Chunk.doc_path.like(f"%{doc_id_str}%"),
    )


def _matches_doc_id(chunk: Chunk, doc_id: str) -> bool:
    """Verify in-memory that a Chunk belongs to doc_id."""
    doc_id_str = str(doc_id)
    chunk_doc_id = getattr(chunk, "doc_id", None)
    if chunk_doc_id is not None:
        return str(chunk_doc_id) == doc_id_str
    if chunk.doc_path == doc_id_str:
        return True
    if chunk.doc_path.startswith(f"library/{doc_id_str}/") or f"/{doc_id_str}." in chunk.doc_path:
        return True
    if doc_id_str in chunk.doc_path:
        return True
    return False


async def scoped_vector_search(
    session: AsyncSession,
    qvec: Sequence[float],
    doc_id: str,
    f: RetrieveFilters,
    limit: int,
) -> list[int]:
    """Retrieve top chunks for a given document by cosine distance against qvec."""
    stmt = select(Chunk.id).where(Chunk.embedding.is_not(None)).where(_doc_id_clause(doc_id))
    if not f.include_generated:
        stmt = stmt.where(Chunk.generated.is_(False))
    if f.verified_only:
        stmt = stmt.where(Chunk.verified.is_(True))
    if f.kinds:
        stmt = stmt.where(Chunk.doc_kind.in_(f.kinds))
    if f.exam_tags:
        stmt = stmt.where(Chunk.exam_tags.overlap(f.exam_tags))

    stmt = stmt.order_by(Chunk.embedding.cosine_distance(qvec)).limit(limit)
    res = await session.execute(stmt)
    return [row[0] for row in res.all()]


async def scoped_keyword_search(
    session: AsyncSession,
    query: str,
    doc_id: str,
    f: RetrieveFilters,
    limit: int,
) -> list[int]:
    """Retrieve top chunks for a given document by ts_rank_cd full-text search."""
    ts_q = func.websearch_to_tsquery("simple", query)
    stmt = select(Chunk.id).where(Chunk.tsv.op("@@")(ts_q)).where(_doc_id_clause(doc_id))
    if not f.include_generated:
        stmt = stmt.where(Chunk.generated.is_(False))
    if f.verified_only:
        stmt = stmt.where(Chunk.verified.is_(True))
    if f.kinds:
        stmt = stmt.where(Chunk.doc_kind.in_(f.kinds))
    if f.exam_tags:
        stmt = stmt.where(Chunk.exam_tags.overlap(f.exam_tags))

    stmt = stmt.order_by(func.ts_rank_cd(Chunk.tsv, ts_q).desc()).limit(limit)
    res = await session.execute(stmt)
    return [row[0] for row in res.all()]


async def scoped_retrieve(
    query: str,
    doc_id: str,
    rag_deps: RagDeps,
    *,
    k: int = 6,
    f: RetrieveFilters | None = None,
) -> list[Hit]:
    """Execute scoped retrieval returning top-k reranked hits from one document only."""
    if f is None:
        f = RetrieveFilters()

    # 1. Embed query
    vectors = await rag_deps.embedder.embed([query])
    qvec = vectors[0]

    k_candidates = max(rag_deps.settings.rag_k_candidates, k * 3)

    async with rag_deps.ro_session_factory() as session:
        vec_ids = await scoped_vector_search(session, qvec, doc_id, f, k_candidates)
        kw_ids = await scoped_keyword_search(session, query, doc_id, f, k_candidates)

        fused = rrf([vec_ids, kw_ids], k=60)
        candidate_ids = [item_id for item_id, _ in fused[:k_candidates]]

        if not candidate_ids:
            return []

        # Load chunks for candidate ids
        stmt = select(Chunk).where(Chunk.id.in_(candidate_ids))
        res = await session.execute(stmt)
        chunks_map = {c.id: c for c in res.scalars().all()}

    # Preserve order of candidate_ids and enforce document scope
    ordered_chunks = [
        chunks_map[cid]
        for cid in candidate_ids
        if cid in chunks_map and _matches_doc_id(chunks_map[cid], doc_id)
    ]
    if not ordered_chunks:
        return []

    passages = [c.text for c in ordered_chunks]
    scores = rag_deps.reranker.score(query, passages)

    hits: list[Hit] = []
    for chunk, score in zip(ordered_chunks, scores, strict=False):
        hits.append(
            ScopedHit(
                chunk_id=chunk.id,
                doc_path=chunk.doc_path,
                title=chunk.title or "",
                heading_path=chunk.heading_path or [],
                text=chunk.text,
                doc_kind=chunk.doc_kind or "library",
                verified=chunk.verified,
                generated=bool(chunk.generated) if chunk.generated is not None else False,
                score=score,
                flagged=bool(chunk.flagged) if chunk.flagged is not None else False,
                doc_id=getattr(chunk, "doc_id", None) or doc_id,
            )
        )

    # Sort descending by reranker score and return top k
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:k]
