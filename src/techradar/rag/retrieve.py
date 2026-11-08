"""Hybrid retrieval with Reciprocal Rank Fusion (RRF) and vector search (Phase 2b Task 4).

SEC: SEC-23, SEC-39, SEC-40, SEC-41, SEC-42.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.models import Chunk
from techradar.llm.client import Completer, Embedder
from techradar.rag.rerank import Reranker
from techradar.settings import Settings


class Hit(BaseModel):
    """Retrieved search result chunk with metadata and reranker score."""

    chunk_id: int
    doc_path: str
    title: str
    heading_path: list[str]
    text: str
    doc_kind: str
    verified: bool | None
    generated: bool
    score: float
    flagged: bool = False


class RetrieveFilters(BaseModel):
    """Filters applied during vector and keyword retrieval."""

    kinds: list[str] | None = None
    exam_tags: list[str] | None = None
    verified_only: bool = False
    include_generated: bool = False


@dataclass
class RagDeps:
    """Dependencies required for RAG operations."""

    ro_session_factory: async_sessionmaker[AsyncSession]
    completer: Completer
    embedder: Embedder
    reranker: Reranker
    settings: Settings


def rrf(rankings: Sequence[Sequence[int]], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal rank fusion over candidate lists."""
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


async def vector_search(
    session: AsyncSession,
    qvec: Sequence[float],
    f: RetrieveFilters,
    limit: int,
) -> list[int]:
    """Retrieve top chunks by cosine distance against qvec."""
    stmt = select(Chunk.id).where(Chunk.embedding.is_not(None))
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


async def keyword_search(
    session: AsyncSession,
    query: str,
    f: RetrieveFilters,
    limit: int,
) -> list[int]:
    """Retrieve top chunks by ts_rank_cd full-text search."""
    ts_q = func.websearch_to_tsquery("simple", query)
    stmt = select(Chunk.id).where(Chunk.tsv.op("@@")(ts_q))
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


async def retrieve(
    question: str,
    deps: RagDeps,
    f: RetrieveFilters | None = None,
) -> list[Hit]:
    """Execute hybrid retrieval with RRF and cross-encoder reranking."""
    if f is None:
        f = RetrieveFilters()

    # 1. Embed question
    vectors = await deps.embedder.embed([question])
    qvec = vectors[0]

    k_candidates = deps.settings.rag_k_candidates
    k_final = deps.settings.rag_k_final

    async with deps.ro_session_factory() as session:
        vec_ids = await vector_search(session, qvec, f, k_candidates)
        kw_ids = await keyword_search(session, question, f, k_candidates)

        fused = rrf([vec_ids, kw_ids], k=60)
        candidate_ids = [item_id for item_id, _ in fused[:k_candidates]]

        if not candidate_ids:
            return []

        # Load chunks for candidate ids
        stmt = select(Chunk).where(Chunk.id.in_(candidate_ids))
        res = await session.execute(stmt)
        chunks_map = {c.id: c for c in res.scalars().all()}

    # Preserve order of candidate_ids
    ordered_chunks = [chunks_map[cid] for cid in candidate_ids if cid in chunks_map]
    if not ordered_chunks:
        return []

    passages = [c.text for c in ordered_chunks]
    scores = deps.reranker.score(question, passages)

    hits: list[Hit] = []
    for chunk, score in zip(ordered_chunks, scores, strict=False):
        hits.append(
            Hit(
                chunk_id=chunk.id,
                doc_path=chunk.doc_path,
                title=chunk.title,
                heading_path=chunk.heading_path or [],
                text=chunk.text,
                doc_kind=chunk.doc_kind,
                verified=chunk.verified,
                generated=chunk.generated,
                score=score,
                flagged=chunk.flagged,
            )
        )

    # Sort by reranker score descending and return top k_final
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:k_final]
