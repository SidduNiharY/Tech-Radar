"""Database models for TechRadar Brain."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
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
