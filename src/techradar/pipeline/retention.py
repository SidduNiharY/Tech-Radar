"""Retention policy cleaner: purges old raw files, results, and quarantine items."""

import logging
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, or_, select

from techradar.db.models import Item, QuarantineItem, RawItem
from techradar.pipeline.process import PipelineDeps

logger = logging.getLogger(__name__)


def _safe_unlink(p: Path, allowed_roots: set[Path]) -> bool:
    """Synchronously unlink file if it resides safely within allowed directories."""
    resolved = p.resolve()
    if any(str(resolved).startswith(str(root)) for root in allowed_roots):
        if p.exists() and p.is_file():
            p.unlink(missing_ok=True)
            return True
    return False


async def cleanup_retention(
    deps: PipelineDeps,
    now: datetime,
    retention_days: int = 7,
) -> dict[str, int]:
    """Clean up old raw, clean, orphan jobs and expired quarantine files."""
    counts = {"raw": 0, "clean": 0, "orphans": 0, "quarantine": 0}
    cutoff = now - timedelta(days=retention_days)
    orphan_cutoff = now - timedelta(days=1)

    allowed_roots = {
        deps.raw_dir.resolve(),
        deps.clean_dir.resolve(),
        deps.jobs_dir.resolve(),
        (deps.settings.data_dir / "quarantine").resolve(),
    }

    async with deps.session_factory() as session:
        # 1. Clean finished items raw / clean files older than retention_days
        raw_res = await session.execute(
            select(RawItem).where(
                and_(
                    RawItem.fetched_at.is_not(None),
                    RawItem.fetched_at < cutoff,
                    or_(RawItem.status == "done", RawItem.status == "rejected"),
                    RawItem.raw_name.is_not(None),
                )
            )
        )
        for raw_item in raw_res.scalars().all():
            if raw_item.raw_name:
                rp = deps.raw_dir / raw_item.raw_name
                if _safe_unlink(rp, allowed_roots):
                    counts["raw"] += 1
                raw_item.raw_name = None

        # Clean finished items text paths
        item_res = await session.execute(
            select(Item).where(
                and_(
                    Item.processed_at.is_not(None),
                    Item.processed_at < cutoff,
                    or_(Item.status == "written", Item.status == "filtered_out"),
                    Item.text_path.is_not(None),
                )
            )
        )
        for it in item_res.scalars().all():
            if it.text_path:
                tp = Path(it.text_path)
                if _safe_unlink(tp, allowed_roots):
                    counts["clean"] += 1
                it.text_path = None

        # 2. Clean orphan files in jobs and clean dirs older than 1 day
        for dir_to_scan in (deps.jobs_dir, deps.clean_dir):
            if dir_to_scan.exists():
                for f in dir_to_scan.glob("*.json"):
                    mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=now.tzinfo)
                    if mtime < orphan_cutoff and _safe_unlink(f, allowed_roots):
                        counts["orphans"] += 1

        # Also remove raw files older than retention days in raw_dir
        if deps.raw_dir.exists():
            for f in deps.raw_dir.iterdir():
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=now.tzinfo)
                if mtime < cutoff and _safe_unlink(f, allowed_roots):
                    counts["raw"] += 1

        # 3. Quarantined files past expires_at that have not been released
        q_res = await session.execute(
            select(QuarantineItem).where(
                and_(
                    QuarantineItem.expires_at < now,
                    QuarantineItem.released_at.is_(None),
                    QuarantineItem.deleted_at.is_(None),
                )
            )
        )
        for q_item in q_res.scalars().all():
            if q_item.path:
                qp = Path(q_item.path)
                if _safe_unlink(qp, allowed_roots):
                    counts["quarantine"] += 1
            q_item.deleted_at = now

        # Also scan quarantine folder for physical files
        q_dir = deps.settings.data_dir / "quarantine"
        if q_dir.exists():
            for qf in q_dir.rglob("*"):
                mtime = datetime.fromtimestamp(qf.stat().st_mtime, tz=now.tzinfo)
                if mtime < cutoff and _safe_unlink(qf, allowed_roots):
                    counts["quarantine"] += 1

        await session.commit()

    return counts
