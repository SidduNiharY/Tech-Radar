"""Database models for TechRadar Brain."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarative class for all models."""


class AuditEvent(Base):
    """Security and operations audit log entry."""

    __tablename__ = "audit_log"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Source(Base):
    """Feed and content ingestion source configuration."""

    __tablename__ = "sources"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(Text, default="rss", nullable=False)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str] = mapped_column(Text, nullable=False)
    trust_tier: Mapped[str] = mapped_column(Text, nullable=False)
    interval_min: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class FetchRun(Base):
    """Record of individual fetch execution per source."""

    __tablename__ = "fetch_runs"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("techradar.sources.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    new_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class RawItem(Base):
    """Raw downloaded item metadata before parsing."""

    __tablename__ = "raw_items"
    __table_args__ = (
        Index("ix_raw_items_status", "status"),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("techradar.sources.id"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="new", nullable=False)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Item(Base):
    """Parsed and sanitized article or document."""

    __tablename__ = "items"
    __table_args__ = (
        Index("ix_items_status", "status"),
        Index("ix_items_cluster_id", "cluster_id"),
        Index(
            "ix_items_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    raw_item_id: Mapped[int] = mapped_column(
        ForeignKey("techradar.raw_items.id"), unique=True, nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str] = mapped_column(Text, nullable=False)
    text_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[Any | None] = mapped_column(Vector(1024), nullable=True)
    cluster_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    relevance: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="new", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    exam_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}", default=list)
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}", default=list)
    reader_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Fact(Base):
    """Verified or atomic factual claim."""

    __tablename__ = "facts"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fact_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    section: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="unverified", nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    subject_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    superseded_by: Mapped[int | None] = mapped_column(
        ForeignKey("techradar.facts.id"), nullable=True
    )


class FactChange(Base):
    """History of fact value mutations and notifications."""

    __tablename__ = "fact_changes"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    subject_key: Mapped[str] = mapped_column(Text, nullable=False)
    old_fact_id: Mapped[int] = mapped_column(ForeignKey("techradar.facts.id"), nullable=False)
    new_fact_id: Mapped[int] = mapped_column(ForeignKey("techradar.facts.id"), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IntakeLog(Base):
    """Audit log of Intake Gateway verdicts and stages."""

    __tablename__ = "intake_log"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(32), nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    reasons: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}", default=list, nullable=False
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class QuarantineItem(Base):
    """Suspicious or quarantined jobs with automated retention."""

    __tablename__ = "quarantine_items"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    reasons: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}", default=list, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now() + interval '7 days'"), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FactSource(Base):
    """Association between facts and source items supporting them."""

    __tablename__ = "fact_sources"
    __table_args__ = {"schema": "techradar"}

    fact_id: Mapped[int] = mapped_column(ForeignKey("techradar.facts.id"), primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("techradar.items.id"), primary_key=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str | None] = mapped_column(String(300), nullable=True)
    supported: Mapped[bool] = mapped_column(Boolean, nullable=False)


class Note(Base):
    """Markdown vault story note metadata."""

    __tablename__ = "notes"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    vault_path: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    cluster_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    source_domains: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}", default=list, nullable=False
    )
    source_urls: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}", default=list, nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    written_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Chunk(Base):
    """Structured text chunk for semantic vector and full-text search."""

    __tablename__ = "chunks"
    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_tsv_gin", "tsv", postgresql_using="gin"),
        Index("ix_chunks_doc_path", "doc_path"),
        Index("ix_chunks_doc_chapter_ordinal", "doc_id", "chapter_id", "ordinal"),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    doc_path: Mapped[str] = mapped_column(Text, nullable=False)
    doc_kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    heading_path: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}", default=list, nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    exam_tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}", default=list, nullable=False
    )
    verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    generated: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False, nullable=False
    )
    flagged: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False, nullable=False
    )
    source_domains: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}", default=list, nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', text)", persisted=True), nullable=True
    )
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    doc_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    chapter_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ts_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_label: Mapped[str | None] = mapped_column(Text, nullable=True)


class DocsIndex(Base):
    """Document hash tracking for incremental vault and library indexing."""

    __tablename__ = "docs_index"
    __table_args__ = {"schema": "techradar"}

    doc_path: Mapped[str] = mapped_column(Text, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Answer(Base):
    """History of generated RAG answers and their citations."""

    __tablename__ = "answers"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default="[]", default=list, nullable=False
    )
    used_unverified: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False, nullable=False
    )
    flags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}", default=list, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    saved_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class Outbox(Base):
    """Queue of outgoing Telegram messages, voice clips, or documents."""

    __tablename__ = "outbox"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(String(4096), nullable=False)
    buttons: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, server_default="0", default=0, nullable=False)
    ref_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class LibraryDoc(Base):
    """A book, video or other document in the library."""

    __tablename__ = "library_docs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('pdf','docx','epub','video','audio','html')", name="ck_library_docs_kind"
        ),
        CheckConstraint("origin IN ('library','pack')", name="ck_library_docs_origin"),
        CheckConstraint(
            "status IN ('queued','processing','awaiting_transcription','ready',"
            "'quarantined','rejected','failed')",
            name="ck_library_docs_status",
        ),
        CheckConstraint("trust IN ('official','open','my_own')", name="ck_library_docs_trust"),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    trust: Mapped[str] = mapped_column(Text, nullable=False)
    exam_tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}", default=list, nullable=False
    )
    pack_item_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    keep_media: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False, nullable=False
    )
    # Released by the owner from quarantine (SEC-14): searchable, but never used for
    # summaries, evals, MCQs or cards.
    flagged: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LibraryPart(Base):
    """A page range or time range of a library doc processed as one job."""

    __tablename__ = "library_parts"
    __table_args__ = (
        CheckConstraint("status IN ('pending','done','failed')", name="ck_library_parts_status"),
        Index("ux_library_parts_doc_ordinal", "doc_id", "ordinal", unique=True),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("techradar.library_docs.id"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ts_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    ts_end: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        Text, server_default="pending", default="pending", nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, server_default="0", default=0, nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class LibraryChapter(Base):
    """A chapter (or video segment) of a library doc."""

    __tablename__ = "library_chapters"
    __table_args__ = (
        Index("ux_library_chapters_doc_ordinal", "doc_id", "ordinal", unique=True),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("techradar.library_docs.id"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ts_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    ts_end: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_path: Mapped[str] = mapped_column(Text, nullable=False)
    summary_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_pages: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), server_default="{}", default=list, nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BookEval(Base):
    """A retrieval check question for a library doc."""

    __tablename__ = "book_evals"
    __table_args__ = (Index("ix_book_evals_doc_id", "doc_id"), {"schema": "techradar"})

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("techradar.library_docs.id"), nullable=False)
    question: Mapped[str] = mapped_column(String(300), nullable=False)
    expected_chunk_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StarterPack(Base):
    """A curated list of free study documents for one exam."""

    __tablename__ = "starter_packs"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    exam: Mapped[str] = mapped_column(Text, nullable=False)
    approved: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StarterPackItem(Base):
    """One downloadable document in a starter pack."""

    __tablename__ = "starter_pack_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','downloaded','failed','rejected')",
            name="ck_starter_pack_items_status",
        ),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    pack_id: Mapped[int] = mapped_column(ForeignKey("techradar.starter_packs.id"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    licence: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, server_default="pending", default="pending", nullable=False
    )
    doc_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


# --- Phase 3: practice ---


class Briefing(Base):
    """Daily morning briefing record."""

    __tablename__ = "briefings"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    items: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), default=list, nullable=True
    )


class Take(Base):
    """User's one-line take on a briefing."""

    __tablename__ = "takes"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    briefing_id: Mapped[int] = mapped_column(ForeignKey("techradar.briefings.id"), nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MCQ(Base):
    """Multiple choice question generated from verified facts or library chunks."""

    __tablename__ = "mcqs"
    __table_args__ = (
        CheckConstraint(
            "(fact_id IS NOT NULL AND chunk_id IS NULL) "
            "OR (fact_id IS NULL AND chunk_id IS NOT NULL)",
            name="ck_mcqs_single_source",
        ),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    fact_id: Mapped[int | None] = mapped_column(ForeignKey("techradar.facts.id"), nullable=True)
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("techradar.chunks.id"), nullable=True)
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("techradar.library_chapters.id"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    answer_index: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, default="active", server_default="active", nullable=False
    )


class QuizAttempt(Base):
    """Attempt and outcome for a quiz question."""

    __tablename__ = "quiz_attempts"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    mcq_id: Mapped[int] = mapped_column(ForeignKey("techradar.mcqs.id"), nullable=False)
    chosen_index: Mapped[int] = mapped_column(Integer, nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)


class Flashcard(Base):
    """FSRS flashcard for spaced repetition."""

    __tablename__ = "flashcards"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fsrs_card: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), default=dict, nullable=False
    )
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_shown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("techradar.chunks.id"), nullable=True)
    doc_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ts_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retired: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False, nullable=False
    )


class Mistake(Base):
    """Mistake notebook record for wrong quiz or drill answers."""

    __tablename__ = "mistakes"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    ref_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Vocab(Base):
    """Vocabulary item extracted from reading."""

    __tablename__ = "vocab"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    word: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    sentence: Mapped[str] = mapped_column(Text, nullable=False)
    meaning: Mapped[str] = mapped_column(Text, nullable=False)
    synonyms: Mapped[list[str]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), default=list, nullable=False
    )
    antonyms: Mapped[list[str]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), default=list, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GrammarItem(Base):
    """Grammar drill question generated and verified."""

    __tablename__ = "grammar_items"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    answer_index: Mapped[int] = mapped_column(Integer, nullable=False)
    rule: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExamWatch(Base):
    """Configured exam watch targets."""

    __tablename__ = "exam_watches"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    watch_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    capture_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    capture_exam: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Alert(Base):
    """Alert for exam watch changes."""

    __tablename__ = "alerts"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    watch_id: Mapped[int] = mapped_column(ForeignKey("techradar.exam_watches.id"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewDecision(Base):
    """Review decisions made on quarantined or flagged intake items."""

    __tablename__ = "review_decisions"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# --- Phase 4: web ---


class UserSettings(Base):
    """User key-value preferences and schedule configurations."""

    __tablename__ = "user_settings"
    __table_args__ = {"schema": "techradar"}

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PendingAction(Base):
    """Two-step confirmation ticket for sensitive operations."""

    __tablename__ = "pending_actions"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    token: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    args_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Phase 5: planner ---


class StudySession(Base):
    """User study sessions tracked for goals and topics."""

    __tablename__ = "study_sessions"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(String(120), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_closed: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False, nullable=False
    )


class Revision(Base):
    """Spaced 1-7-30 revision items scheduled for topics and chapters."""

    __tablename__ = "revisions"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("techradar.study_sessions.id"), nullable=True
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("techradar.library_chapters.id"), nullable=True
    )


class Checkin(Base):
    """Daily sleep, energy, and mood self-assessments."""

    __tablename__ = "checkins"
    __table_args__ = {"schema": "techradar"}

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    sleep_band: Mapped[int | None] = mapped_column(Integer, nullable=True)
    energy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Plan(Base):
    """Generated daily morning plan lines."""

    __tablename__ = "plans"
    __table_args__ = {"schema": "techradar"}

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    lines: Mapped[list[str]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), default=list, nullable=False
    )


class JobAlert(Base):
    """Last time a failure or health alert was raised per key (at most one per 6 hours).

    Not `alerts`: that table belongs to the exam watcher.
    """

    __tablename__ = "job_alerts"
    __table_args__ = {"schema": "techradar"}

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# --- Phase 6: voice ---


class VoiceSession(Base):
    """Recorded voice note or practice session."""

    __tablename__ = "voice_sessions"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    kept: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False, nullable=False
    )
    delete_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    peaks: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)
    transcript: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class VoiceMetrics(Base):
    """Speech and fluency metrics computed for a voice session."""

    __tablename__ = "voice_metrics"
    __table_args__ = {"schema": "techradar"}

    session_id: Mapped[int] = mapped_column(
        ForeignKey("techradar.voice_sessions.id"), primary_key=True
    )
    words_per_min: Mapped[float] = mapped_column(Float, nullable=False)
    filler_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fillers_per_min: Mapped[float] = mapped_column(Float, nullable=False)
    filler_breakdown: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    long_pauses: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_sentence_words: Mapped[float] = mapped_column(Float, nullable=False)
    type_token_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    overused: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)


class PronunciationScore(Base):
    """Phoneme-level pronunciation accuracy score for a word."""

    __tablename__ = "pronunciation_scores"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("techradar.voice_sessions.id"), nullable=False
    )
    word: Mapped[str] = mapped_column(Text, nullable=False)
    start_s: Mapped[float] = mapped_column(Float, nullable=False)
    end_s: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False)


class WritingFeedback(Base):
    """Grammar and style feedback for user writing practice."""

    __tablename__ = "writing_feedback"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    critique: Mapped[str] = mapped_column(Text, nullable=False)
    polished_text: Mapped[str] = mapped_column(Text, nullable=False)


class Story(Base):
    """Personal stories and anecdotes in the story bank."""

    __tablename__ = "stories"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StoryDraft(Base):
    """Drafts and revisions of stories in the story bank."""

    __tablename__ = "story_drafts"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    story_id: Mapped[int | None] = mapped_column(ForeignKey("techradar.stories.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Listening(Base):
    """Audio clips and transcripts used for English listening comprehension."""

    __tablename__ = "listening"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    audio_path: Mapped[str] = mapped_column(Text, nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Reflection(Base):
    """Weekly self-reflections on learning and practice."""

    __tablename__ = "reflections"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VoiceNotice(Base):
    """Tracking of one-time privacy notices sent to Telegram chats."""

    __tablename__ = "voice_notices"
    __table_args__ = {"schema": "techradar"}

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# --- Phase 7: understanding and world ---


class DeepDive(Base):
    """Weekly in-depth topical research report."""

    __tablename__ = "deep_dives"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    week: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    vault_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GlossaryTerm(Base):
    """Domain concept, term or acronym definition."""

    __tablename__ = "glossary_terms"
    __table_args__ = {"schema": "techradar"}

    term: Mapped[str] = mapped_column(Text, primary_key=True)
    vault_path: Mapped[str] = mapped_column(Text, nullable=False)


class Timeline(Base):
    """Chronological event timeline for a person, company or story."""

    __tablename__ = "timelines"
    __table_args__ = {"schema": "techradar"}

    entity: Mapped[str] = mapped_column(Text, primary_key=True)
    vault_path: Mapped[str] = mapped_column(Text, nullable=False)


class Prediction(Base):
    """User forward-looking forecasts with resolution tracking."""

    __tablename__ = "predictions"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    text: Mapped[str] = mapped_column(String(280), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    outcome: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class EconSeries(Base):
    """Macroeconomic indicator timeseries observations."""

    __tablename__ = "econ_series"
    __table_args__ = (
        UniqueConstraint("series", "period", "source_kind", name="uq_econ_series_period_source"),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    series: Mapped[str] = mapped_column(Text, nullable=False)
    period: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FactCheck(Base):
    """Claim extraction, verification verdict and evidence."""

    __tablename__ = "fact_checks"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    claims: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    verdicts: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    saved_path: Mapped[str | None] = mapped_column(Text, nullable=True)


# --- Phase 8: exams ---


class SyllabusTopic(Base):
    """Syllabus topics for competitive and academic exams."""

    __tablename__ = "syllabus_topics"
    __table_args__ = (
        UniqueConstraint("exam", "subject", "slug", name="uq_syllabus_topics_exam_subject_slug"),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    exam: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    vault_path: Mapped[str] = mapped_column(Text, nullable=False)


class PyqQuestion(Base):
    """Past-year question with official answer keys."""

    __tablename__ = "pyq_questions"
    __table_args__ = (
        CheckConstraint("qtype IN ('MCQ','MSQ','NAT')", name="ck_pyq_questions_qtype"),
        CheckConstraint(
            "tag_status IN ('none','suggested','confirmed')", name="ck_pyq_questions_tag_status"
        ),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    exam: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    paper: Mapped[str] = mapped_column(Text, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    qtype: Mapped[str] = mapped_column(Text, nullable=False)  # MCQ, MSQ, NAT
    answer_key: Mapped[str] = mapped_column(Text, nullable=False)
    marks: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("techradar.syllabus_topics.id"), nullable=True
    )
    tag_status: Mapped[str] = mapped_column(
        Text, server_default="none", default="none", nullable=False
    )


class DrillAttempt(Base):
    """User attempt record on daily aptitude and reasoning drills."""

    __tablename__ = "drill_attempts"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    item: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    chosen: Mapped[str] = mapped_column(Text, nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    seconds: Mapped[float] = mapped_column(Float, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MockResult(Base):
    """Recorded scores from full-length mock examinations."""

    __tablename__ = "mock_results"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    exam: Mapped[str] = mapped_column(Text, nullable=False)
    taken_on: Mapped[date] = mapped_column(Date, nullable=False)
    total: Mapped[float] = mapped_column(Float, nullable=False)
    max_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Cutoff(Base):
    """Official qualification thresholds by exam year, tier and category."""

    __tablename__ = "cutoffs"
    __table_args__ = {"schema": "techradar"}

    exam: Mapped[str] = mapped_column(Text, primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    tier: Mapped[str] = mapped_column(Text, primary_key=True)
    category: Mapped[str] = mapped_column(Text, primary_key=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)


class TopicWeight(Base):
    """Subject and topic question mark weights based on past analysis."""

    __tablename__ = "topic_weights"
    __table_args__ = {"schema": "techradar"}

    exam: Mapped[str] = mapped_column(Text, primary_key=True)
    subject: Mapped[str] = mapped_column(Text, primary_key=True)
    topic: Mapped[str] = mapped_column(Text, primary_key=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)


class TopicSource(Base):
    """Learning sources mapped to syllabus topics."""

    __tablename__ = "topic_sources"
    __table_args__ = (
        UniqueConstraint("topic_id", "kind", "ref_id", name="uq_topic_sources_topic_kind_ref"),
        CheckConstraint(
            "kind IN ('chapter','pyq','pack_item','note')", name="ck_topic_sources_kind"
        ),
        CheckConstraint(
            "status IN ('suggested','confirmed','dismissed')", name="ck_topic_sources_status"
        ),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("techradar.syllabus_topics.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # chapter, pyq, pack_item, note
    ref_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # suggested, confirmed, dismissed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Phase 9: live voice and study group ---


class GroupMember(Base):
    """Study group members identified by hashed salt for privacy."""

    __tablename__ = "group_members"
    __table_args__ = {"schema": "techradar"}

    member_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(32), nullable=False)


class GroupPoll(Base):
    """Quiz polls sent to allowed study groups."""

    __tablename__ = "group_polls"
    __table_args__ = {"schema": "techradar"}

    poll_id: Mapped[str] = mapped_column(Text, primary_key=True)
    mcq_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    group_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GroupAnswer(Base):
    """Member answers to group quiz polls."""

    __tablename__ = "group_answers"
    __table_args__ = {"schema": "techradar"}

    poll_id: Mapped[str] = mapped_column(Text, primary_key=True)
    member_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)


class LiveSession(Base):
    """Live voice coach session records."""

    __tablename__ = "live_sessions"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    dir: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)


# --- Phase 11: feedback and self-improvement ---


class Feedback(Base):
    """User feedback signals on items, answers, summaries, cards, MCQs and voice."""

    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint(
            "target_kind", "target_id", "signal", "day", name="uq_feedback_target_signal_day"
        ),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    target_kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    signal: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)  # telegram, web, voice
    day: Mapped[date] = mapped_column(Date, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ActionLog(Base):
    """Activity action log for implicit feedback and usage patterns."""

    __tablename__ = "action_log"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # open, skip, save, ask, follow_up, session_start, session_end, card_review, quiz_answer
    target: Mapped[str] = mapped_column(String(200), nullable=False)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Edit(Base):
    """User edits made to generated notes or summaries."""

    __tablename__ = "edits"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    doc_path: Mapped[str] = mapped_column(Text, nullable=False)
    before_hash: Mapped[str] = mapped_column(Text, nullable=False)
    after_hash: Mapped[str] = mapped_column(Text, nullable=False)
    length_change: Mapped[int] = mapped_column(Integer, nullable=False)
    sections_removed: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}", default=list, nullable=False
    )
    words_replaced: Mapped[int] = mapped_column(Integer, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Weight(Base):
    """Topic, source, and search weights for ranking and retrieval."""

    __tablename__ = "weights"
    __table_args__ = {"schema": "techradar"}

    kind: Mapped[str] = mapped_column(Text, primary_key=True)  # topic, source, search
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    floor: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PreferenceRule(Base):
    """Style rules proposed by night pattern detection and approved by owner."""

    __tablename__ = "preference_rules"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    field: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # proposed, active, ignored, undone
    proposed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class RegressionCase(Base):
    """Saved negative feedback cases to guard against model regressions."""

    __tablename__ = "regression_cases"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    doc_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bad_answer: Mapped[str] = mapped_column(Text, nullable=False)
    must_not_include: Mapped[str] = mapped_column(String(300), nullable=False)
    must_include: Mapped[str | None] = mapped_column(String(300), nullable=True)
    from_feedback_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    passing: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ImprovementLog(Base):
    """Log of all automatic and approved self-improvement modifications."""

    __tablename__ = "improvement_log"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # weight, rule, search, fsrs, content
    key: Mapped[str] = mapped_column(Text, nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    automatic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StyleProfile(Base):
    """Mode-level style profile configuration from /setup."""

    __tablename__ = "style_profiles"
    __table_args__ = {"schema": "techradar"}

    mode: Mapped[str] = mapped_column(Text, primary_key=True)
    setup: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TopicMastery(Base):
    """Learner topic mastery levels computed from reviews and quizzes."""

    __tablename__ = "topic_mastery"
    __table_args__ = {"schema": "techradar"}

    topic: Mapped[str] = mapped_column(Text, primary_key=True)
    level: Mapped[str] = mapped_column(Text, nullable=False)  # new, learning, exam_ready, mastered
    quiz_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    stability_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviews: Mapped[int] = mapped_column(Integer, server_default="0", default=0, nullable=False)
    prev_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LikedExample(Base):
    """High-quality answers approved as few-shot style examples."""

    __tablename__ = "liked_examples"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    from_feedback_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fact_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), server_default="{}", default=list, nullable=False
    )
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )


class PreferencePair(Base):
    """Which-is-better comparison pairs for human preference alignment."""

    __tablename__ = "preference_pairs"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    version_a: Mapped[str] = mapped_column(Text, nullable=False)
    version_b: Mapped[str] = mapped_column(Text, nullable=False)
    variant_a: Mapped[str] = mapped_column(Text, nullable=False)
    variant_b: Mapped[str] = mapped_column(Text, nullable=False)
    chosen: Mapped[str | None] = mapped_column(Text, nullable=True)  # a, b, skip
    asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ImprovementReport(Base):
    """Weekly self-improvement digest reports sent to owner."""

    __tablename__ = "improvement_reports"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Phase 10: models admin and tech extras ---


class ModelRegistry(Base):
    """Model assignment registry by role."""

    __tablename__ = "model_registry"
    __table_args__ = {"schema": "techradar"}

    role: Mapped[str] = mapped_column(Text, primary_key=True)
    ollama_tag: Mapped[str] = mapped_column(Text, nullable=False)
    family: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ModelChange(Base):
    """Log of model switches and rollbacks."""

    __tablename__ = "model_changes"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    old_tag: Mapped[str] = mapped_column(Text, nullable=False)
    new_tag: Mapped[str] = mapped_column(Text, nullable=False)
    test_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    rolled_back: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False, nullable=False
    )


class ModelTest(Base):
    """Evaluation test results for candidate models."""

    __tablename__ = "model_tests"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    tag: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ModelRequest(Base):
    """Requests to pull new candidate models."""

    __tablename__ = "model_requests"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tag: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)  # pending, pulled, rejected
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class PlaygroundRun(Base):
    """Test inference runs in model playground."""

    __tablename__ = "playground_runs"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TrendCount(Base):
    """Daily mention counts for emerging tech and world topics."""

    __tablename__ = "trend_counts"
    __table_args__ = {"schema": "techradar"}

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    term: Mapped[str] = mapped_column(Text, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


# --- Phase 12: Jarvis ---


class JarvisSession(Base):
    """Active or past conversation sessions with Jarvis."""

    __tablename__ = "jarvis_sessions"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    device: Mapped[str] = mapped_column(Text, nullable=False)  # mac, phone, server
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    practice: Mapped[str | None] = mapped_column(Text, nullable=True)
    quiz: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class JarvisTurn(Base):
    """Individual spoken or typed dialog turns in a Jarvis session."""

    __tablename__ = "jarvis_turns"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("techradar.jarvis_sessions.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # me, jarvis
    text: Mapped[str] = mapped_column(String(2000), nullable=False)
    skill: Mapped[str | None] = mapped_column(Text, nullable=True)
    list_len: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ticket_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reply_to: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reply: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    keep: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class JarvisWrite(Base):
    """Pending or confirmed write actions requested by voice."""

    __tablename__ = "jarvis_writes"
    __table_args__ = {"schema": "techradar"}

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    inverse_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    inverse_args: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # awaiting_tap, done, expired, undone
    tap_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JarvisGreeting(Base):
    """Daily greeting generated for Jarvis devices."""

    __tablename__ = "jarvis_greetings"
    __table_args__ = {"schema": "techradar"}

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    greeting: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    shown_devices: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}", default=list, nullable=False
    )


class GpuLease(Base):
    """Single-row GPU lease coordinator."""

    __tablename__ = "gpu_lease"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_gpu_lease_single_row"),
        {"schema": "techradar"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    holder: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
