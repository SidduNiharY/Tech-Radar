"""Provenance tracking and delete-by-source cascade operations."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Fact, FactSource, Item, Note
from techradar.pipeline.verify import is_verified


class DeleteReport(BaseModel):
    """Summary of changes performed when purging a source domain."""

    model_config = ConfigDict(extra="forbid")

    notes_deleted: int
    facts_deleted: int
    facts_downgraded: int
    clusters_to_rerender: list[int]


async def delete_by_domain(
    session: AsyncSession,
    vault_root: Path,
    domain: str,
    official: frozenset[str],
) -> DeleteReport:
    """Cascade delete facts and notes originating from a purged domain."""
    # 1. Identify fact_sources for this domain
    fs_stmt = select(FactSource).where(FactSource.domain == domain)
    fs_res = await session.execute(fs_stmt)
    removed_fs = fs_res.scalars().all()
    affected_fact_ids = {fs.fact_id for fs in removed_fs}

    # Delete fact_sources for this domain
    await session.execute(delete(FactSource).where(FactSource.domain == domain))

    # 2. Check each affected fact
    facts_deleted = 0
    facts_downgraded = 0
    for fid in affected_fact_ids:
        # Check remaining sources
        rem_stmt = select(FactSource).where(FactSource.fact_id == fid)
        rem_res = await session.execute(rem_stmt)
        rem_sources = rem_res.scalars().all()

        fact_stmt = select(Fact).where(Fact.id == fid)
        fact_res = await session.execute(fact_stmt)
        fact = fact_res.scalar_one_or_none()
        if fact is None:
            continue

        if not rem_sources:
            await session.execute(delete(Fact).where(Fact.id == fid))
            facts_deleted += 1
        else:
            remaining_domains = {s.domain for s in rem_sources if s.supported}
            fact.source_count = len(rem_sources)
            was_verified = fact.status == "verified"
            now_verified = is_verified(remaining_domains, official)
            if was_verified and not now_verified:
                fact.status = "unverified"
                facts_downgraded += 1

    # 3. Identify items and clusters affected
    items_stmt = select(Item).where(Item.domain == domain)
    items_res = await session.execute(items_stmt)
    purged_items = items_res.scalars().all()
    purged_cluster_ids = {item.cluster_id for item in purged_items}

    # For each cluster, check if any items remain from other domains
    notes_deleted = 0
    clusters_to_rerender: list[int] = []

    for cid in purged_cluster_ids:
        other_items_stmt = select(Item).where(and_(Item.cluster_id == cid, Item.domain != domain))
        other_res = await session.execute(other_items_stmt)
        other_items = other_res.scalars().all()

        note_stmt = select(Note).where(Note.cluster_id == cid)
        note_res = await session.execute(note_stmt)
        note = note_res.scalar_one_or_none()

        if not other_items:
            # Delete note file and db row
            if note is not None:
                note_file = vault_root / note.vault_path
                if note_file.exists():
                    note_file.unlink(missing_ok=True)
                await session.execute(delete(Note).where(Note.id == note.id))
                notes_deleted += 1
        else:
            clusters_to_rerender.append(cid)

    # Clean up purged items
    await session.execute(delete(Item).where(Item.domain == domain))
    await session.flush()

    return DeleteReport(
        notes_deleted=notes_deleted,
        facts_deleted=facts_deleted,
        facts_downgraded=facts_downgraded,
        clusters_to_rerender=sorted(clusters_to_rerender),
    )
