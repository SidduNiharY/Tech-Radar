"""Retention policy cleaner: purges old raw files, results, and quarantine items.

The quarantine folder is written by the parser sandbox and the worker mounts it rw next to
data/library, so deletes there never trust a path check: every folder is opened by
descriptor with O_NOFOLLOW from the quarantine root, and only the entry itself is
unlinked (a link is removed, never followed). A folder swapped for a link after any check
can never lead a delete out of the quarantine folder.
"""

import contextlib
import logging
import os
import stat
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import and_, or_, select

from techradar.db.models import Item, QuarantineItem, RawItem
from techradar.pipeline.process import PipelineDeps

logger = logging.getLogger(__name__)

_DIR_NOFOLLOW = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def unlink_in_tree(root: Path, path: Path) -> bool:
    """Delete one regular file at `path` under `root`; refuse anything else.

    Containment is lexical (no resolve): a relative path, `..`, or a path outside `root`
    is refused. Each folder below `root` is opened relative to its parent with O_NOFOLLOW,
    so a link at any step is refused; the file is checked with lstat and unlinked through
    its folder's descriptor. Its folder is removed too when that leaves it empty.
    """
    if not path.is_absolute():
        return False
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    if not parts or any(p in ("", ".", "..") for p in parts):
        return False
    try:
        fds = [os.open(root, os.O_RDONLY | os.O_DIRECTORY)]
    except OSError:
        return False
    try:
        for part in parts[:-1]:
            fds.append(os.open(part, _DIR_NOFOLLOW, dir_fd=fds[-1]))
        st = os.stat(parts[-1], dir_fd=fds[-1], follow_symlinks=False)
        if not stat.S_ISREG(st.st_mode):
            return False
        os.unlink(parts[-1], dir_fd=fds[-1])
        if len(parts) > 1:
            with contextlib.suppress(OSError):
                os.rmdir(parts[-2], dir_fd=fds[-2])  # only when empty
        return True
    except OSError:
        return False
    finally:
        for fd in fds:
            os.close(fd)


def sweep_tree(root: Path, cutoff: datetime, empty_cutoff: datetime) -> int:
    """Delete entries under `root` last modified before `cutoff`; returns files removed.

    Walks by descriptor and never follows a link (os.fwalk, follow_symlinks=False): a link
    is an entry like any other (removed when old, never followed). A folder is removed when
    it is empty and either lost an entry in this sweep or is older than `empty_cutoff`.
    """
    if not root.is_dir():
        return 0
    removed = 0
    emptied: set[str] = set()
    old_ts, empty_ts = cutoff.timestamp(), empty_cutoff.timestamp()
    for dirpath, dirnames, filenames, dirfd in os.fwalk(root, topdown=False, follow_symlinks=False):
        for name in [*filenames, *dirnames]:
            try:
                st = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
            except OSError:
                continue
            try:
                if stat.S_ISDIR(st.st_mode):
                    if os.path.join(dirpath, name) in emptied or st.st_mtime < empty_ts:
                        os.rmdir(name, dir_fd=dirfd)  # fails (kept) unless empty
                        emptied.add(dirpath)
                elif st.st_mtime < old_ts:
                    os.unlink(name, dir_fd=dirfd)  # a link itself, never its target
                    emptied.add(dirpath)
                    removed += 1 if stat.S_ISREG(st.st_mode) else 0
            except OSError:
                continue
    return removed


def _safe_unlink(p: Path, allowed_roots: set[Path]) -> bool:
    """Synchronously unlink file if it resides safely within allowed directories."""
    resolved = p.resolve()
    # Path containment, not a string prefix: /data/quarantine-x is not inside /data/quarantine.
    if any(resolved.is_relative_to(root.resolve()) for root in allowed_roots):
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

    # The quarantine folder is not here: it has its own descriptor-based deletes below.
    allowed_roots = {
        deps.raw_dir.resolve(),
        deps.clean_dir.resolve(),
        deps.jobs_dir.resolve(),
    }
    q_dir = deps.settings.data_dir / "quarantine"

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
            if q_item.path and unlink_in_tree(q_dir, Path(q_item.path)):
                counts["quarantine"] += 1
            q_item.deleted_at = now

        # Also sweep the quarantine folder for old files nothing points to any more.
        counts["quarantine"] += sweep_tree(q_dir, cutoff, orphan_cutoff)

        await session.commit()

    return counts
