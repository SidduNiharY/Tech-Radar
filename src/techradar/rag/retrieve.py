"""Hybrid retrieval with Reciprocal Rank Fusion (RRF) and vector search (Phase 2b Task 4).

SEC: SEC-23, SEC-39, SEC-40, SEC-41, SEC-42.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import Select, func, select
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
    doc_id: int | None = None
    chapter_id: int | None = None
    ordinal: int | None = None


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


def check_doc_id(doc_id: int | None) -> None:
    """Reject anything but a real integer, so a scope can never be built from text."""
    if doc_id is not None and (isinstance(doc_id, bool) or not isinstance(doc_id, int)):
        raise TypeError("doc_id must be an int or None")


def _apply_filters(
    stmt: Select[tuple[int]], f: RetrieveFilters, doc_id: int | None
) -> Select[tuple[int]]:
    """Add the shared WHERE clauses; a book scope is exact integer equality (never LIKE)."""
    if doc_id is not None:
        stmt = stmt.where(Chunk.doc_id == doc_id)
    if not f.include_generated:
        stmt = stmt.where(Chunk.generated.is_(False))
    if f.verified_only:
        stmt = stmt.where(Chunk.verified.is_(True))
    if f.kinds:
        stmt = stmt.where(Chunk.doc_kind.in_(f.kinds))
    if f.exam_tags:
        stmt = stmt.where(Chunk.exam_tags.overlap(f.exam_tags))
    return stmt


async def vector_search(
    session: AsyncSession,
    qvec: Sequence[float],
    f: RetrieveFilters,
    limit: int,
    *,
    doc_id: int | None = None,
) -> list[int]:
    """Retrieve top chunks by cosine distance against qvec (optionally within one book)."""
    check_doc_id(doc_id)
    stmt = _apply_filters(select(Chunk.id).where(Chunk.embedding.is_not(None)), f, doc_id)
    stmt = stmt.order_by(Chunk.embedding.cosine_distance(qvec)).limit(limit)
    res = await session.execute(stmt)
    return [row[0] for row in res.all()]


async def keyword_search(
    session: AsyncSession,
    query: str,
    f: RetrieveFilters,
    limit: int,
    *,
    doc_id: int | None = None,
) -> list[int]:
    """Retrieve top chunks by ts_rank_cd full-text search (optionally within one book)."""
    check_doc_id(doc_id)
    ts_q = func.websearch_to_tsquery("simple", query)
    stmt = _apply_filters(select(Chunk.id).where(Chunk.tsv.op("@@")(ts_q)), f, doc_id)
    stmt = stmt.order_by(func.ts_rank_cd(Chunk.tsv, ts_q).desc()).limit(limit)
    res = await session.execute(stmt)
    return [row[0] for row in res.all()]


def chunk_to_hit(chunk: Chunk, score: float) -> Hit:
    """Convert a stored chunk into a Hit."""
    return Hit(
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
        doc_id=chunk.doc_id,
        chapter_id=chunk.chapter_id,
        ordinal=chunk.ordinal,
    )


async def retrieve(
    question: str,
    deps: RagDeps,
    f: RetrieveFilters | None = None,
    *,
    doc_id: int | None = None,
) -> list[Hit]:
    """Execute hybrid retrieval with RRF and cross-encoder reranking.

    doc_id limits both searches to one library document (exact integer match).
    """
    return await retrieve_multi([question], deps, f, doc_id=doc_id)


async def retrieve_multi(
    queries: Sequence[str],
    deps: RagDeps,
    f: RetrieveFilters | None = None,
    *,
    doc_id: int | None = None,
) -> list[Hit]:
    """Run every query (vector and keyword), fuse all result lists with RRF, then rerank.

    The first query is the user's own question: it is the one the reranker scores against.
    Later queries are model rewrites and only widen the candidate pool.
    """
    check_doc_id(doc_id)
    if f is None:
        f = RetrieveFilters()

    unique: list[str] = []
    for q in queries:
        if q not in unique:
            unique.append(q)
    if not unique:
        return []

    vectors = await deps.embedder.embed(unique)

    k_candidates = deps.settings.rag_k_candidates
    k_final = deps.settings.rag_k_final

    async with deps.ro_session_factory() as session:
        rankings: list[list[int]] = []
        for query, qvec in zip(unique, vectors, strict=True):
            rankings.append(await vector_search(session, qvec, f, k_candidates, doc_id=doc_id))
            rankings.append(await keyword_search(session, query, f, k_candidates, doc_id=doc_id))

        fused = rrf(rankings, k=60)
        candidate_ids = [item_id for item_id, _ in fused[:k_candidates]]

        if not candidate_ids:
            return []

        # Load chunks for candidate ids
        stmt = select(Chunk).where(Chunk.id.in_(candidate_ids))
        if doc_id is not None:
            stmt = stmt.where(Chunk.doc_id == doc_id)
        res = await session.execute(stmt)
        # Defence in depth: re-check the book scope in memory, so a chunk of another book can
        # never reach the model even if a search above were ever wrong.
        chunks_map = {c.id: c for c in res.scalars().all() if doc_id is None or c.doc_id == doc_id}

    # Preserve order of candidate_ids
    ordered_chunks = [chunks_map[cid] for cid in candidate_ids if cid in chunks_map]
    if not ordered_chunks:
        return []

    passages = [c.text for c in ordered_chunks]
    scores = deps.reranker.score(unique[0], passages)

    hits = [
        chunk_to_hit(chunk, score) for chunk, score in zip(ordered_chunks, scores, strict=False)
    ]

    # Sort by reranker score descending and return top k_final
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:k_final]
