"""Worker pipeline orchestration: result collection, clustering, reading, facts and story notes."""

import hashlib
import json
import logging
import urllib.parse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Fact, FactSource, IntakeLog, Item, Note, QuarantineItem, RawItem
from techradar.library.quarantine import held_file, notify_quarantined, should_notify
from techradar.llm.client import Completer, Embedder
from techradar.pipeline.filter import assign_cluster, profile_texts, relevance
from techradar.pipeline.reader import build_reader_graph, read_item
from techradar.pipeline.supersede import supersede_if_newer
from techradar.pipeline.verify import check_fact, fact_key, headline_ok, is_verified
from techradar.pipeline.writer import (
    StoryFact,
    StoryNote,
    StorySource,
    note_rel_path,
    render_story,
    write_note,
)
from techradar.schemas.pipeline import CleanDoc, ParseResult
from techradar.security.urls import UrlRejected, check_url, registrable_domain
from techradar.settings import Settings

logger = logging.getLogger(__name__)

ItemOutcome = Literal["filtered_out", "needs_review", "written", "retry"]


@dataclass
class PipelineDeps:
    """Dependency injection container for the worker pipeline."""

    session_factory: Any
    completer: Completer
    embedder: Embedder
    settings: Settings
    vault_root: Path
    clean_dir: Path
    jobs_dir: Path
    raw_dir: Path
    allowed: frozenset[str]
    official: frozenset[str]


async def collect_results(deps: PipelineDeps) -> dict[str, int]:
    """Scan clean_dir for ParseResults, register items, entries, and intake logs."""
    counts = {"feeds": 0, "docs": 0, "skipped_links": 0, "rejected": 0}
    deps.clean_dir.mkdir(parents=True, exist_ok=True)

    result_files = sorted(deps.clean_dir.glob("*.result.json"))
    if not result_files:
        return counts

    async with deps.session_factory() as session:
        for rpath in result_files:
            try:
                data = json.loads(rpath.read_text(encoding="utf-8"))
                result = ParseResult.model_validate(data)
            except Exception as e:
                logger.warning("Corrupted result file %s: %s", rpath, e)
                rpath.unlink(missing_ok=True)
                counts["rejected"] += 1
                continue

            # Library and clipping results are indexed by the RAG indexer
            if result.purpose != "news":
                continue

            # Record intake audit log if present
            if result.intake is not None:
                intake_entry = IntakeLog(
                    job_id=result.job_id,
                    origin="fetch",
                    kind=result.kind,
                    size_bytes=rpath.stat().st_size,
                    mime="application/json",
                    verdict=result.intake.verdict,
                    steps=[s.model_dump() for s in result.intake.steps],
                    reasons=result.intake.reasons,
                )
                session.add(intake_entry)

            # Handle non-ok parse statuses
            if result.status == "quarantined":
                # News results come from the fetcher: a ParseResult carries no origin, so
                # "fetch" is the only one this collector can know (no notice for it).
                origin = "fetch"
                q_item = QuarantineItem(
                    job_id=result.job_id,
                    origin=origin,
                    # the gateway's held copy, not this result file (it is removed below)
                    path=str(held_file(deps.settings.data_dir / "quarantine", result.job_id)),
                    reasons=result.intake.reasons if result.intake else ["quarantined"],
                )
                session.add(q_item)
                if should_notify(origin):
                    await notify_quarantined(
                        session,
                        deps.settings.telegram_owner_chat_id,
                        f"{result.kind} {result.job_id[:8]}",
                        q_item.reasons,
                    )
                counts["rejected"] += 1
                rpath.unlink(missing_ok=True)
                continue

            if result.status != "ok":
                counts["rejected"] += 1
                rpath.unlink(missing_ok=True)
                continue

            # Process OK result
            if result.kind == "feed":
                counts["feeds"] += 1
                for entry in result.entries:
                    try:
                        valid_link = check_url(entry.link, deps.allowed)
                    except UrlRejected:
                        counts["skipped_links"] += 1
                        continue

                    url_h = hashlib.sha256(valid_link.encode("utf-8")).hexdigest()
                    existing_raw = await session.execute(
                        select(RawItem.id).where(RawItem.url_hash == url_h)
                    )
                    if existing_raw.scalar_one_or_none() is not None:
                        continue

                    raw_item = RawItem(
                        source_id=1,
                        url=valid_link,
                        url_hash=url_h,
                        kind="page",
                        status="new",
                        published_at=entry.published,
                    )
                    session.add(raw_item)
                rpath.unlink(missing_ok=True)

            elif result.kind in ("page", "pdf") and result.doc is not None:
                counts["docs"] += 1
                doc = result.doc
                parsed_host = urllib.parse.urlsplit(doc.url).hostname or ""
                domain = registrable_domain(parsed_host)
                flags: list[str] = []
                if result.intake and result.intake.verdict == "flag":
                    flags.append("gateway_flagged")

                url_h = hashlib.sha256(doc.url.encode("utf-8")).hexdigest()
                existing_raw = await session.execute(
                    select(RawItem).where(RawItem.url_hash == url_h)
                )
                raw_item = existing_raw.scalar_one_or_none()
                if raw_item is None:
                    raw_item = RawItem(
                        source_id=1,
                        url=doc.url,
                        url_hash=url_h,
                        kind=result.kind,
                        status="done",
                        fetched_at=datetime.now(UTC),
                    )
                    session.add(raw_item)
                    await session.flush()

                c_hash = hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
                item = Item(
                    raw_item_id=raw_item.id,
                    url=doc.url,
                    domain=domain,
                    title=doc.title,
                    lang=doc.lang,
                    text_path=str(rpath),
                    content_hash=c_hash,
                    status="new",
                    flags=flags,
                )
                session.add(item)

        await session.commit()

    return counts


async def _get_next_cluster_id(session: AsyncSession) -> int:
    """Compute next cluster sequence id."""
    res = await session.execute(select(func.coalesce(func.max(Item.cluster_id), 0) + 1))
    return int(res.scalar_one())


def _read_clean_doc(path: Path) -> tuple[CleanDoc | None, str | None]:
    """Synchronously read and parse a CleanDoc from a result file."""
    if not path.exists():
        return None, "missing_text"
    try:
        presult = ParseResult.model_validate_json(path.read_text(encoding="utf-8"))
        if presult.doc is None or not presult.doc.text.strip():
            return None, "empty_text"
        return presult.doc, None
    except Exception:
        return None, "corrupt_text"


async def process_item(item_id: int, deps: PipelineDeps) -> ItemOutcome:
    """Execute pipeline processing on a single unindexed item."""
    async with deps.session_factory() as session:
        item = await session.get(Item, item_id)
        if item is None or item.status != "new":
            return "filtered_out"

        text_file = Path(item.text_path) if item.text_path else Path("")
        doc, err = _read_clean_doc(text_file)
        if doc is None:
            item.status = "needs_review"
            if err:
                item.flags = list(set(item.flags + [err]))
            await session.commit()
            return "needs_review"

        # 1. Embedding
        embed_input = f"{item.title}\n\n{doc.text[:2000]}"
        try:
            vecs = await deps.embedder.embed([embed_input])
            vec = vecs[0]
            item.embedding = vec
        except Exception as e:
            logger.warning("Embedding error for item %s: %s", item_id, e)
            item.attempts += 1
            if item.attempts >= 3:
                item.status = "needs_review"
                item.flags = list(set(item.flags + ["model_unavailable"]))
                await session.commit()
                return "needs_review"
            await session.commit()
            return "retry"

        # 2. Duplicate clustering against items from last 72 hours
        cutoff = datetime.now(UTC) - timedelta(hours=72)
        # `items` has no timestamp of its own; the source item's fetch time dates it.
        recent_res = await session.execute(
            select(Item.cluster_id, Item.embedding)
            .join(RawItem, RawItem.id == Item.raw_item_id)
            .where(
                and_(
                    Item.id != item.id,
                    Item.cluster_id.is_not(None),
                    Item.embedding.is_not(None),
                    RawItem.fetched_at >= cutoff,
                )
            )
        )
        recent_pairs: list[tuple[int, Sequence[float]]] = []
        for cid, emb in recent_res.all():
            if cid is not None and emb is not None:
                recent_pairs.append((cid, emb))

        assigned_cluster = assign_cluster(vec, recent_pairs, threshold=0.90)
        if assigned_cluster is None:
            item.cluster_id = await _get_next_cluster_id(session)
        else:
            item.cluster_id = assigned_cluster

        # 3. Relevance filtering against vault profile texts
        ptexts = profile_texts(deps.vault_root)
        if ptexts:
            pvecs = await deps.embedder.embed(ptexts)
            rel_score = relevance(vec, pvecs)
            if rel_score < 0.30:
                item.status = "filtered_out"
                await session.commit()
                return "filtered_out"

        # 4. Reader graph execution
        reader_graph = build_reader_graph(deps.completer)
        try:
            reader_res = await read_item(reader_graph, doc)
        except Exception as e:
            logger.warning("Reader error for item %s: %s", item_id, e)
            item.attempts += 1
            if item.attempts >= 3:
                item.status = "needs_review"
                item.flags = list(set(item.flags + ["model_unavailable"]))
                await session.commit()
                return "needs_review"
            await session.commit()
            return "retry"

        if reader_res.status == "needs_review" or reader_res.output is None:
            item.status = "needs_review"
            item.flags = list(set(item.flags + reader_res.flags))
            await session.commit()
            return "needs_review"

        output = reader_res.output

        # 5. Upsert facts and check fact claims
        is_gateway_flagged = "gateway_flagged" in item.flags

        # as_of = the source's publication date, or its fetch date if it has none (plan Task 9b).
        raw_row = await session.get(RawItem, item.raw_item_id)
        source_dt = (raw_row.published_at or raw_row.fetched_at) if raw_row else None
        as_of_date = source_dt.date() if source_dt else date.today()

        for f in output.facts:
            fkey = fact_key(f)
            fact_row_res = await session.execute(select(Fact).where(Fact.fact_key == fkey))
            fact_row = fact_row_res.scalar_one_or_none()
            if fact_row is None:
                fact_row = Fact(
                    fact_key=fkey,
                    statement=f.statement,
                    subject=f.subject,
                    value=f.value,
                    section=output.section.value,
                    status="unverified",
                    source_count=0,
                    as_of=as_of_date,
                )
                session.add(fact_row)
                await session.flush()

            # Fact verification logic
            if not is_gateway_flagged:
                verdict = await check_fact(deps.completer, f, doc)
                session.add(
                    FactSource(
                        fact_id=fact_row.id,
                        item_id=item.id,
                        domain=item.domain,
                        supported=verdict.supported,
                        quote=verdict.quote,
                    )
                )
                await session.flush()

                # Re-verify across all supporting sources
                srcs_res = await session.execute(
                    select(FactSource.domain).where(
                        and_(FactSource.fact_id == fact_row.id, FactSource.supported.is_(True))
                    )
                )
                supported_domains = set(srcs_res.scalars().all())
                fact_row.source_count = len(supported_domains)

                if is_verified(supported_domains, deps.official):
                    fact_row.status = "verified"
                    await supersede_if_newer(session, fact_row.id, deps.official)
                else:
                    fact_row.status = "unverified"

        # 6. Build and render cluster StoryNote
        cluster_items_res = await session.execute(
            select(Item).where(Item.cluster_id == item.cluster_id).order_by(Item.id.asc())
        )
        cluster_items = list(cluster_items_res.scalars().all())

        # Collect cluster sources
        # Items have no timestamp of their own; each source's fetch time is on its raw item.
        fetched_res = await session.execute(
            select(RawItem.id, RawItem.fetched_at).where(
                RawItem.id.in_([it.raw_item_id for it in cluster_items])
            )
        )
        fetched_at = {raw_id: ts for raw_id, ts in fetched_res.all()}
        story_sources = [
            StorySource(
                url=it.url,
                domain=it.domain,
                fetched_at=fetched_at.get(it.raw_item_id) or datetime.now(UTC),
            )
            for it in cluster_items
        ]

        # Gather cluster facts
        cluster_item_ids = [it.id for it in cluster_items]
        fact_sources_res = await session.execute(
            select(FactSource.fact_id).where(FactSource.item_id.in_(cluster_item_ids)).distinct()
        )
        fact_ids = fact_sources_res.scalars().all()
        cluster_facts: list[StoryFact] = []
        if fact_ids:
            facts_res = await session.execute(select(Fact).where(Fact.id.in_(fact_ids)))
            for f_row in facts_res.scalars().all():
                cluster_facts.append(
                    StoryFact(
                        statement=f_row.statement,
                        status=f_row.status if f_row.status == "verified" else "unverified",
                        source_count=f_row.source_count,
                    )
                )

        cluster_domains = {s.domain for s in story_sources}
        verified_headline = headline_ok(cluster_domains, output.section, deps.official)
        has_flag = any("gateway_flagged" in it.flags for it in cluster_items)

        story_note = StoryNote(
            cluster_id=item.cluster_id,
            title=item.title,
            published=date.today(),
            section=output.section,
            exam_tags=output.exam_tags,
            summary=output.summary,
            four_questions=output.four_questions,
            facts=cluster_facts,
            sources=story_sources,
            verified_headline=verified_headline,
            is_flagged=has_flag,
        )

        # 7. Write Note
        rendered_content = render_story(story_note)
        content_hash = hashlib.sha256(rendered_content.encode("utf-8")).hexdigest()
        note_row_res = await session.execute(select(Note).where(Note.cluster_id == item.cluster_id))
        note_row = note_row_res.scalar_one_or_none()
        if note_row is None:
            existing_notes_res = await session.execute(select(Note.vault_path))
            taken_paths = set(existing_notes_res.scalars().all())
            rel_path = note_rel_path(date.today(), item.title, taken_paths)
            note_row = Note(
                cluster_id=item.cluster_id,
                vault_path=str(rel_path),
                kind="news",
                title=item.title,
                content_hash=content_hash,
            )
            session.add(note_row)
        else:
            rel_path = PurePosixPath(note_row.vault_path)
            note_row.content_hash = content_hash

        write_note(deps.vault_root, rel_path, rendered_content)

        item.status = "written"
        await session.commit()
        return "written"


async def process_new_items(deps: PipelineDeps, limit: int = 20) -> dict[ItemOutcome, int]:
    """Batch process unprocessed new items."""
    async with deps.session_factory() as session:
        res = await session.execute(
            select(Item.id).where(Item.status == "new").order_by(Item.id.asc()).limit(limit)
        )
        item_ids = list(res.scalars().all())

    tally: dict[ItemOutcome, int] = {}
    for i_id in item_ids:
        outcome = await process_item(i_id, deps)
        tally[outcome] = tally.get(outcome, 0) + 1
    return tally
