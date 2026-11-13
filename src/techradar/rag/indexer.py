"""Vault and library knowledge base indexer (Phase 2b Task 3 / SEC-06, SEC-17, SEC-39, SEC-40)."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from techradar.db.models import Chunk, DocsIndex
from techradar.fetcher.store import store_raw, write_job
from techradar.llm.client import Embedder
from techradar.pipeline.writer import slugify
from techradar.rag.chunker import parse_front_matter, split_markdown
from techradar.schemas.pipeline import ParseJob, ParseResult
from techradar.security.text import detect_lang, sanitize_text

logger = logging.getLogger(__name__)

MAX_DOC_BYTES = 2_000_000


def scan_vault(vault_root: Path, skip: Sequence[str] = ()) -> dict[str, str]:
    """Scan vault for markdown notes, returning {rel_posix_path: sha256_hex}."""
    result: dict[str, str] = {}
    if not vault_root.exists():
        return result

    skip_set = set(skip)

    for p in vault_root.rglob("*.md"):
        # Check skip list and hidden directories before opening or statting
        if p.name in skip_set:
            continue
        rel = p.relative_to(vault_root).as_posix()
        if rel in skip_set:
            continue
        if ".obsidian" in p.parts or ".trash" in p.parts:
            continue
        if p.is_symlink():
            continue
        try:
            st = p.stat()
            if st.st_size > MAX_DOC_BYTES or st.st_size == 0:
                continue
            # Read and compute sha256
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            result[rel] = h
        except OSError, PermissionError:
            continue

    return result


class DocMeta(BaseModel):
    """Metadata extracted from note front matter."""

    model_config = ConfigDict(extra="ignore")

    doc_kind: str
    title: str
    section: str | None = None
    exam_tags: list[str] = Field(default_factory=list)
    verified: bool | None = None
    generated: bool = False
    source_domains: list[str] = Field(default_factory=list)


def doc_meta(front_matter: dict[str, Any]) -> DocMeta:
    """Extract standard DocMeta from front matter dictionary."""
    doc_kind = front_matter.get("kind") or "user"
    title = front_matter.get("title") or "Untitled"
    section = front_matter.get("section")
    exam_tags = front_matter.get("exam_tags") or []
    if isinstance(exam_tags, str):
        exam_tags = [exam_tags]

    verified = front_matter.get("verified_headline")
    if verified is None:
        status = front_matter.get("status")
        if status == "verified":
            verified = True
        elif status == "unverified":
            verified = False

    generated = bool(front_matter.get("generated", False))
    source_domains = front_matter.get("source_domains") or []
    if isinstance(source_domains, str):
        source_domains = [source_domains]

    return DocMeta(
        doc_kind=doc_kind,
        title=title,
        section=section,
        exam_tags=list(exam_tags),
        verified=verified,
        generated=generated,
        source_domains=list(source_domains),
    )


@dataclass
class IndexDeps:
    """Dependency container for RAG indexing workflow."""

    session_factory: Any
    embedder: Embedder
    vault_root: Path
    library_dir: Path
    library_inbox: Path
    raw_dir: Path
    jobs_dir: Path
    clean_dir: Path
    skip: Sequence[str] = ()


def plan_clipping_jobs(
    vault_root: Path,
    changed: Mapping[str, str],
    raw_dir: Path,
    jobs_dir: Path | None = None,
) -> list[ParseJob]:
    """Create clipping ParseJobs for new or modified files under Clippings/."""
    jobs: list[ParseJob] = []
    for rel_path in changed:
        if not rel_path.startswith("Clippings/"):
            continue
        file_path = vault_root / rel_path
        if not file_path.is_file() or file_path.is_symlink():
            continue

        data = file_path.read_bytes()
        raw_name = store_raw(data, raw_dir, ext="md")
        job_id = hashlib.md5(f"clipping:{rel_path}".encode(), usedforsecurity=False).hexdigest()
        job = ParseJob(
            job_id=job_id,
            purpose="clipping",
            origin="clipping",
            kind="md",
            raw_name=raw_name,
            url=f"clipping:{rel_path}",
            source_id=0,
        )
        if jobs_dir is not None:
            write_job(job, jobs_dir)
        jobs.append(job)

    return jobs


async def collect_clipping_results(deps: IndexDeps) -> int:
    """Collect and index processed clipping results from clean_dir."""
    count = 0
    if not deps.clean_dir.exists():
        return 0

    result_files = sorted(deps.clean_dir.glob("*.result.json"))
    for rpath in result_files:
        try:
            data = json.loads(rpath.read_text(encoding="utf-8"))
            result = ParseResult.model_validate(data)
        except Exception as e:
            logger.warning("Failed parsing clipping result file %s: %s", rpath, e)
            continue

        if result.purpose != "clipping":
            continue

        if result.status == "ok" and result.doc:
            doc_path = result.doc.url.removeprefix("clipping:")
            clean_text = sanitize_text(result.doc.text)
            chunks = split_markdown(clean_text, doc_path)
            content_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
            flagged = (result.intake.verdict == "flag") if result.intake else False

            embeddings: list[list[float]] = []
            if chunks:
                for i in range(0, len(chunks), 16):
                    batch = [c.text for c in chunks[i : i + 16]]
                    embs = await deps.embedder.embed(batch)
                    embeddings.extend(embs)

            async with deps.session_factory() as session:
                await session.execute(delete(Chunk).where(Chunk.doc_path == doc_path))
                await session.execute(delete(DocsIndex).where(DocsIndex.doc_path == doc_path))

                for i, c in enumerate(chunks):
                    chunk_row = Chunk(
                        doc_path=doc_path,
                        doc_kind="user",
                        title=result.doc.title,
                        heading_path=c.heading_path,
                        ordinal=c.ordinal,
                        text=c.text,
                        lang=result.doc.lang,
                        section=None,
                        exam_tags=[],
                        verified=False,
                        generated=False,
                        flagged=flagged,
                        source_domains=[],
                        content_hash=content_hash,
                        embedding=embeddings[i] if i < len(embeddings) else None,
                    )
                    session.add(chunk_row)

                session.add(DocsIndex(doc_path=doc_path, content_hash=content_hash))
                await session.commit()
            count += 1

        rpath.unlink(missing_ok=True)

    return count


async def collect_library_results(deps: IndexDeps) -> int:
    """Write parsed library CleanDocs as markdown files in library_dir."""
    count = 0
    if not deps.clean_dir.exists():
        return 0

    deps.library_dir.mkdir(parents=True, exist_ok=True)
    result_files = sorted(deps.clean_dir.glob("*.result.json"))

    for rpath in result_files:
        try:
            data = json.loads(rpath.read_text(encoding="utf-8"))
            result = ParseResult.model_validate(data)
        except Exception as e:
            logger.warning("Failed parsing clipping result file %s: %s", rpath, e)
            continue

        if result.purpose != "library":
            continue

        if result.status == "ok" and result.doc:
            slug = slugify(result.doc.title)
            source_file = result.doc.url.removeprefix("library:")
            content = (
                f"---\nkind: library\ntitle: {result.doc.title}\nsource: {source_file}\n---\n\n"
                f"{result.doc.text}\n"
            )
            out_file = deps.library_dir / f"{slug}.md"
            out_file.write_text(content, encoding="utf-8")
            count += 1

        rpath.unlink(missing_ok=True)

    return count


async def sync_index(deps: IndexDeps) -> dict[str, int]:
    """Synchronize markdown vault notes and library docs into chunks and docs_index."""
    counts = {"added": 0, "updated": 0, "removed": 0, "skipped": 0}

    scanned_files = scan_vault(deps.vault_root, skip=deps.skip)
    if deps.library_dir.exists():
        lib_files = scan_vault(deps.library_dir, skip=deps.skip)
        for k, v in lib_files.items():
            scanned_files[f"library/{k}"] = v

    async with deps.session_factory() as session:
        result = await session.execute(select(DocsIndex))
        existing_index = {row.doc_path: row.content_hash for row in result.scalars().all()}

        # Identify added or updated
        for doc_path, new_hash in scanned_files.items():
            if doc_path.startswith("Clippings/"):
                continue

            old_hash = existing_index.get(doc_path)
            if old_hash == new_hash:
                counts["skipped"] += 1
                continue

            if doc_path.startswith("library/") and deps.library_dir.exists():
                file_path = deps.library_dir / doc_path.removeprefix("library/")
            else:
                file_path = deps.vault_root / doc_path

            if not file_path.exists():
                continue

            raw_text = file_path.read_text(encoding="utf-8")
            fm, body = parse_front_matter(raw_text)
            clean_text = sanitize_text(body)
            meta = doc_meta(fm)
            title = meta.title if meta.title != "Untitled" else doc_path
            lang = detect_lang(clean_text)

            chunks = split_markdown(clean_text, doc_path)
            embeddings: list[list[float]] = []
            if chunks:
                for i in range(0, len(chunks), 16):
                    batch = [c.text for c in chunks[i : i + 16]]
                    embs = await deps.embedder.embed(batch)
                    embeddings.extend(embs)

            # Atomic chunk replacement
            await session.execute(delete(Chunk).where(Chunk.doc_path == doc_path))
            await session.execute(delete(DocsIndex).where(DocsIndex.doc_path == doc_path))

            for i, c in enumerate(chunks):
                chunk_row = Chunk(
                    doc_path=doc_path,
                    doc_kind=meta.doc_kind,
                    title=title,
                    heading_path=c.heading_path,
                    ordinal=c.ordinal,
                    text=c.text,
                    lang=lang,
                    section=meta.section,
                    exam_tags=meta.exam_tags,
                    verified=meta.verified,
                    generated=meta.generated,
                    flagged=False,
                    source_domains=meta.source_domains,
                    content_hash=new_hash,
                    embedding=embeddings[i] if i < len(embeddings) else None,
                )
                session.add(chunk_row)

            session.add(DocsIndex(doc_path=doc_path, content_hash=new_hash))

            if old_hash is None:
                counts["added"] += 1
            else:
                counts["updated"] += 1

        # Identify removed
        for doc_path in existing_index:
            if doc_path.startswith("Clippings/"):
                continue
            if doc_path not in scanned_files:
                await session.execute(delete(Chunk).where(Chunk.doc_path == doc_path))
                await session.execute(delete(DocsIndex).where(DocsIndex.doc_path == doc_path))
                counts["removed"] += 1

        await session.commit()

    return counts
