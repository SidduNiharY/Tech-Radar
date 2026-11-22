"""Starter packs: free study documents from checked official and open sources (Task 9).

The owner lists items in `infra/sources/exam_packs.yaml` after checking each URL in a
browser, adds the domain to the Squid allowlist and sets `approved: true`. Nothing here
invents or adds a URL or a domain.

How a pack item travels:

1. `load_packs` reads the file strictly (unknown keys, exams or kinds refuse the whole
   file). An item is *refused* (kept, logged, shown by `/packs` as blocked, never
   downloaded) when its URL is not `https`, has userinfo or a port, its host is not in the
   Squid allowlist at load time, the host has no `trust_for` entry, or its `kind` does not
   match the URL's extension.
2. `sync_packs` mirrors the file into `starter_packs` / `starter_pack_items`.
3. `download_pack_items` (fetcher, the only container with internet) downloads only
   `pending` items of approved packs. Each download is size-capped, hashed while it is
   written to a private temp file, follows redirects only on the same host, and lands as
   `packs_dir/pack-<pack>/<sha256>.<ext>` (read-only, never overwritten; the `pack-`
   prefix keeps a pack named `gate` out of the intake's own `gate/` folder). The ext comes from
   the item's `kind`, never from the server.
4. The worker's library intake (`plan_library_intake`, origin `pack`) takes the file
   like any other library document: type sniffing, limits, the Intake Gateway, quarantine
   and flag rules are unchanged. Intake stores pack docs with trust `open`.
5. `link_pack_docs` (fetcher, next cycle) links the doc to its item through a small
   ledger (`packs_dir/.ledger/<sha256>`, a dot-folder intake skips) and sets the doc's
   trust from `trust_for(item host)` and its title from the item. It never touches the
   doc's status or `flagged`: trust never raises the file's own verdict.

Safest defaults where the plan is silent (documented in the plan's Task 9 notes):
- A failed download is not retried automatically (no hammering a site every minute).
- A doc that already exists with the same content is linked, and its trust is left as is.
- A file the intake refused marks its item `failed`.
- `rejected` in the database means "refused at load"; it is recomputed on every sync.

SEC: SEC-05, SEC-25, SEC-57.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import re
import urllib.parse
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import LibraryDoc, StarterPack, StarterPackItem
from techradar.intake.filetype import DOCX_MIME
from techradar.library.inbox import SKIPPED_DIRS, clean_text
from techradar.security.urls import UrlRejected, check_resolved, check_url

if TYPE_CHECKING:
    from techradar.fetcher.http import FetchDeps

log = logging.getLogger(__name__)

Exam = Literal["gate_cs", "gate_da", "ssc_cgl", "bank"]
PackKind = Literal["pdf", "html", "docx"]
Trust = Literal["official", "open"]

OFFICIAL_SUFFIXES = (".gov.in", ".nic.in")
OFFICIAL_DOMAINS = frozenset({"rbi.org.in", "ibps.in", "sbi.co.in", "nios.ac.in"})
# The year's GATE site (it moves between IITs each year). The owner adds it after checking
# it in a browser; nothing is guessed here.
GATE_SITES: frozenset[str] = frozenset()
OPEN_DOMAINS = frozenset({"nptel.ac.in", "ocw.mit.edu"})

PACK_TIMEOUT_S = 120.0
MAX_REDIRECTS = 3
LEDGER_DIR = ".ledger"
_SHA_RE = re.compile(r"[0-9a-f]{64}")
_NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_NEW_FILE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW

CONTENT_TYPES: dict[str, frozenset[str]] = {
    "pdf": frozenset({"application/pdf"}),
    "docx": frozenset({DOCX_MIME}),
    "html": frozenset({"text/html"}),
}
_BINARY_EXTS = (".pdf", ".docx")


def pack_folder(packs_dir: Path, name: str) -> Path:
    """`packs_dir/pack-<name>`. The prefix keeps a pack called `gate`, `done` or `rejected`
    out of the folders the library intake skips or uses at the inbox root."""
    folder = f"pack-{name}"
    if folder in SKIPPED_DIRS or not _NAME_RE.fullmatch(name):
        raise ValueError(f"bad pack name: {name!r}")
    return packs_dir / folder


def _under(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def trust_for(host: str) -> Trust | None:
    """`official` for government and regulator sites, `open` for open courseware, else None."""
    h = host.strip().lower().rstrip(".")
    if any(h.endswith(s) and len(h) > len(s) for s in OFFICIAL_SUFFIXES):
        return "official"
    if any(_under(h, d) for d in OFFICIAL_DOMAINS | GATE_SITES):
        return "official"
    if any(_under(h, d) for d in OPEN_DOMAINS):
        return "open"
    return None


# --- the file ------------------------------------------------------------------


class PackItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=300)
    kind: PackKind
    licence: str = Field(min_length=1, max_length=300)

    _refused: str | None = PrivateAttr(default=None)
    _host: str = PrivateAttr(default="")

    @property
    def refused(self) -> str | None:
        """Why this item is never downloaded, or None when it may be."""
        return self._refused

    @property
    def host(self) -> str:
        return self._host

    @property
    def trust(self) -> Trust | None:
        return trust_for(self._host) if self._host else None


class Pack(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    exam: Exam
    approved: bool
    items: list[PackItem] = Field(default_factory=list, max_length=200)

    @field_validator("name")
    @classmethod
    def _safe_name(cls, v: str) -> str:
        # The name becomes part of a folder name (`pack_folder`): no dots or slashes.
        if not _NAME_RE.fullmatch(v):
            raise ValueError(f"bad pack name: {v!r}")
        return v

    @model_validator(mode="after")
    def _unique_urls(self) -> Pack:
        urls = [i.url for i in self.items]
        if len(urls) != len(set(urls)):
            raise ValueError(f"pack {self.name}: the same URL is listed twice")
        return self

    def ready_items(self) -> list[PackItem]:
        return [i for i in self.items if i.refused is None]


class PacksFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    packs: list[Pack] = Field(max_length=50)

    @model_validator(mode="after")
    def _unique_names(self) -> PacksFile:
        names = [p.name for p in self.packs]
        if len(names) != len(set(names)):
            raise ValueError("the same pack name is listed twice")
        return self


def _refusal(item: PackItem, allowed: frozenset[str]) -> tuple[str | None, str]:
    """(reason or None, normalised host)."""
    parsed = urllib.parse.urlsplit(item.url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        return "not https", host
    try:
        check_url(item.url, allowed)
    except UrlRejected as exc:
        if exc.reason == "not_allowlisted":
            return "host not in the Squid allowlist", host
        return f"bad URL ({exc.reason})", host
    if trust_for(host) is None:
        return "host has no trust entry (official or open)", host
    path = parsed.path.lower()
    if item.kind in ("pdf", "docx") and not path.endswith("." + item.kind):
        return f"kind {item.kind} does not match the URL extension", host
    if item.kind == "html" and path.endswith(_BINARY_EXTS):
        return "kind html does not match the URL extension", host
    return None, host


def load_packs(path: Path, allowed_hosts: frozenset[str]) -> list[Pack]:
    """Read the packs file. A malformed file raises ValueError (nothing is used);
    a single item that breaks a rule is kept with `refused` set and logged."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{path.name}: not valid YAML") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected a mapping with 'packs'")
    try:
        packs = PacksFile.model_validate(data).packs
    except Exception as exc:  # pydantic.ValidationError is a ValueError subclass
        raise ValueError(f"{path.name}: {exc}") from exc
    for pack in packs:
        for item in pack.items:
            reason, host = _refusal(item, allowed_hosts)
            item._host = host
            item._refused = reason
            if reason is not None:
                log.warning(
                    "starter pack %s: item %s refused: %s",
                    pack.name,
                    clean_text(item.url, 200),
                    reason,
                )
    return packs


# --- one download ----------------------------------------------------------------


class PackDownload(BaseModel):
    status: Literal["downloaded", "duplicate", "failed", "rejected"]
    sha256: str | None = None
    reason: str | None = None


def _open_dir(path: Path) -> int:
    """Create (mode 0o750) and open the folder without following a symlink at its last
    step (the packs dir itself is created if missing)."""
    os.makedirs(path.parent, 0o750, exist_ok=True)
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with contextlib.suppress(FileExistsError):
            os.mkdir(path.name, 0o750, dir_fd=parent_fd)
        return os.open(path.name, _DIR_FLAGS, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)


async def _send(deps: FetchDeps, url: str) -> httpx.Response | PackDownload:
    """GET with redirects followed only on the same host (https, at most 3)."""
    host = urllib.parse.urlsplit(url).hostname or ""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        req = deps.client.build_request("GET", current, headers={"User-Agent": deps.user_agent})
        resp = await deps.client.send(req, stream=True, follow_redirects=False)
        if resp.status_code not in (301, 302, 303, 307, 308):
            return resp
        location = resp.headers.get("location")
        await resp.aclose()
        if not location:
            return PackDownload(status="failed", reason="redirect without location")
        try:
            current = check_url(urllib.parse.urljoin(current, location), deps.allowed)
        except UrlRejected as exc:
            return PackDownload(status="rejected", reason=f"redirect refused ({exc.reason})")
        if urllib.parse.urlsplit(current).hostname != host:
            return PackDownload(status="rejected", reason="redirect to another host")
    return PackDownload(status="rejected", reason="too many redirects")


def _write_all(fd: int, data: bytes) -> None:
    """os.write may write less than asked: loop until every byte is on disk."""
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


async def _stream_to(
    resp: httpx.Response, dir_fd: int, kind: PackKind, max_bytes: int
) -> PackDownload:
    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype not in CONTENT_TYPES[kind]:
        return PackDownload(status="rejected", reason="bad_type")
    length = resp.headers.get("content-length")
    if length and length.isdigit() and int(length) > max_bytes:
        return PackDownload(status="failed", reason="too_large")

    tmp = f".dl-{uuid.uuid4().hex}.part"  # a dotfile: intake never picks it up
    wfd = os.open(tmp, _NEW_FILE, 0o600, dir_fd=dir_fd)
    h = hashlib.sha256()
    size = 0
    try:
        try:
            async for chunk in resp.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    return PackDownload(status="failed", reason="too_large")
                h.update(chunk)
                _write_all(wfd, chunk)
            os.fsync(wfd)
            os.fchmod(wfd, 0o440)
        finally:
            os.close(wfd)
        sha = h.hexdigest()
        try:
            os.link(tmp, f"{sha}.{kind}", src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            status: Literal["downloaded", "duplicate"] = "downloaded"
        except FileExistsError:
            status = "duplicate"  # same bytes already waiting: never overwrite
        return PackDownload(status=status, sha256=sha)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp, dir_fd=dir_fd)


async def fetch_pack_file(
    deps: FetchDeps,
    url: str,
    kind: PackKind,
    dest_dir: Path,
    *,
    timeout_s: float = PACK_TIMEOUT_S,
) -> PackDownload:
    """Download one item into `dest_dir/<sha256>.<kind>`, capped at `deps.max_bytes`."""
    try:
        url = check_url(url, deps.allowed)
        host = urllib.parse.urlsplit(url).hostname or ""
        await check_resolved(host, deps.resolver)
    except UrlRejected as exc:
        return PackDownload(status="rejected", reason=exc.reason)
    if not await deps.robots.allowed(url):
        return PackDownload(status="rejected", reason="robots")
    try:
        dir_fd = _open_dir(dest_dir)
    except OSError as exc:
        log.warning("starter pack folder %s refused: %s", dest_dir.name, type(exc).__name__)
        return PackDownload(status="failed", reason="pack folder")
    try:
        await deps.limiter.wait(host)
        async with asyncio.timeout(timeout_s):
            sent = await _send(deps, url)
            if isinstance(sent, PackDownload):
                return sent
            try:
                if not 200 <= sent.status_code < 300:
                    return PackDownload(status="failed", reason=str(sent.status_code))
                return await _stream_to(sent, dir_fd, kind, deps.max_bytes)
            finally:
                await sent.aclose()
    except TimeoutError:
        return PackDownload(status="failed", reason="timeout")
    except httpx.HTTPError as exc:
        return PackDownload(status="failed", reason=type(exc).__name__)
    except OSError as exc:  # e.g. a full disk: the item fails, the cycle goes on
        log.warning("starter pack file not written: %s", type(exc).__name__)
        return PackDownload(status="failed", reason="write error")
    finally:
        os.close(dir_fd)


# --- the database side ------------------------------------------------------------


async def sync_packs(session: AsyncSession, packs: Sequence[Pack]) -> None:
    """Mirror the file into the tables. Refused items are `rejected` (recomputed every
    time); an item that is fine again goes back to `pending`. Downloaded and failed rows
    are history and stay. Pending or refused rows no longer in the file are removed, and a
    pack no longer in the file is no longer approved."""
    in_file = {p.name for p in packs}
    for row in (await session.execute(select(StarterPack))).scalars():
        if row.name not in in_file:
            row.approved = False
    for pack in packs:
        row = (
            await session.execute(select(StarterPack).where(StarterPack.name == pack.name))
        ).scalar_one_or_none()
        if row is None:
            row = StarterPack(name=pack.name, exam=pack.exam, approved=pack.approved)
            session.add(row)
            await session.flush()
        row.exam, row.approved = pack.exam, pack.approved
        existing = {
            i.url: i
            for i in (
                await session.execute(
                    select(StarterPackItem).where(StarterPackItem.pack_id == row.id)
                )
            ).scalars()
        }
        for item in pack.items:
            irow = existing.pop(item.url, None)
            if irow is None:
                irow = StarterPackItem(
                    pack_id=row.id,
                    url=item.url,
                    title=item.title,
                    kind=item.kind,
                    licence=item.licence,
                    status="pending",
                )
                session.add(irow)
            irow.title, irow.kind, irow.licence = item.title, item.kind, item.licence
            if item.refused is not None and irow.status in ("pending", "rejected"):
                irow.status = "rejected"
            elif item.refused is None and irow.status == "rejected":
                irow.status = "pending"
        for gone in existing.values():
            if gone.status in ("pending", "rejected"):
                await session.delete(gone)
    await session.commit()


def _write_ledger(packs_dir: Path, sha: str, item_id: int) -> None:
    fd = _open_dir(packs_dir / LEDGER_DIR)
    try:
        try:
            wfd = os.open(sha, _NEW_FILE, 0o640, dir_fd=fd)
        except FileExistsError:
            return  # the first item with these bytes is linked; later ones get doc_id there
        try:
            os.write(wfd, str(item_id).encode())
        finally:
            os.close(wfd)
    finally:
        os.close(fd)


async def download_pack_items(
    deps: FetchDeps,
    session: AsyncSession,
    packs: Sequence[Pack],
    packs_dir: Path,
    *,
    timeout_s: float = PACK_TIMEOUT_S,
) -> dict[str, int]:
    """Download the `pending` items of approved packs; returns counts.

    `deps.max_bytes` is the pack limit (the caller sets it to `pack_max_bytes`). Packs that
    are not approved, and refused items, are never touched: no database read, no HTTP.
    """
    counts = {"downloaded": 0, "failed": 0, "rejected": 0}
    wanted = [(p, p.ready_items()) for p in packs if p.approved and p.ready_items()]
    if not wanted:
        return counts
    for pack, items in wanted:
        prow = (
            await session.execute(select(StarterPack).where(StarterPack.name == pack.name))
        ).scalar_one_or_none()
        if prow is None or not prow.approved:
            continue
        for item in items:
            irow = (
                await session.execute(
                    select(StarterPackItem).where(
                        StarterPackItem.pack_id == prow.id, StarterPackItem.url == item.url
                    )
                )
            ).scalar_one_or_none()
            if irow is None or irow.status != "pending":
                continue
            res = await fetch_pack_file(
                deps, item.url, item.kind, pack_folder(packs_dir, pack.name), timeout_s=timeout_s
            )
            if res.sha256 is None:
                irow.status = "failed"  # not retried automatically
                counts["rejected" if res.status == "rejected" else "failed"] += 1
                log.warning(
                    "starter pack %s: %s %s: %s", pack.name, item.host, res.status, res.reason
                )
            else:
                known = (
                    await session.execute(
                        select(LibraryDoc.id).where(LibraryDoc.sha256 == res.sha256)
                    )
                ).scalar_one_or_none()
                if known is not None:
                    irow.doc_id = known  # already in the library; its trust is left as is
                    _drop_waiting_file(pack_folder(packs_dir, pack.name), res.sha256, item.kind)
                else:
                    _write_ledger(packs_dir, res.sha256, irow.id)
                irow.status = "downloaded"
                counts["downloaded"] += 1
            await session.commit()
    return counts


def _drop_waiting_file(folder: Path, sha: str, kind: str) -> None:
    with contextlib.suppress(OSError):
        fd = os.open(folder, _DIR_FLAGS)
        try:
            os.unlink(f"{sha}.{kind}", dir_fd=fd)
        finally:
            os.close(fd)


def _waiting(packs_dir: Path, pack: str, sha: str, kind: str) -> bool:
    try:
        fd = os.open(pack_folder(packs_dir, pack), _DIR_FLAGS)
    except OSError:
        return False
    try:
        os.stat(f"{sha}.{kind}", dir_fd=fd, follow_symlinks=False)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


async def link_pack_docs(session: AsyncSession, packs_dir: Path) -> int:
    """Link docs the intake created from pack files to their items; returns how many.

    Sets the doc's `pack_item_id`, trust (`trust_for` the item's host) and title. Never
    changes the doc's status or `flagged`. A ledger entry whose file is gone without a doc
    (the intake refused it) marks the item `failed`.
    """
    try:
        lfd = os.open(packs_dir / LEDGER_DIR, _DIR_FLAGS)
    except OSError:
        return 0
    linked = 0
    try:
        for name in sorted(os.listdir(lfd)):
            if not _SHA_RE.fullmatch(name):
                continue
            try:
                rfd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=lfd)
                try:
                    raw = os.read(rfd, 32)
                finally:
                    os.close(rfd)
                item_id = int(raw.decode("ascii").strip())
            except OSError, ValueError, UnicodeDecodeError:
                continue
            item = await session.get(StarterPackItem, item_id)
            pack = await session.get(StarterPack, item.pack_id) if item else None
            if item is None or pack is None:
                os.unlink(name, dir_fd=lfd)
                continue
            # File first, then the doc: intake commits the doc before removing the file.
            if _waiting(packs_dir, pack.name, name, item.kind):
                continue
            doc = (
                await session.execute(select(LibraryDoc).where(LibraryDoc.sha256 == name))
            ).scalar_one_or_none()
            if doc is None:
                item.status = "failed"
                log.warning("starter pack %s: the intake refused item %s", pack.name, item.id)
            else:
                if doc.origin == "pack" and doc.pack_item_id is None:
                    doc.pack_item_id = item.id
                    host = urllib.parse.urlsplit(item.url).hostname or ""
                    doc.trust = trust_for(host) or "open"
                    doc.title = clean_text(item.title, 300) or doc.title
                item.doc_id = doc.id
                linked += 1
            await session.commit()
            os.unlink(name, dir_fd=lfd)
    finally:
        os.close(lfd)
    return linked


# --- /packs ------------------------------------------------------------------------


class PackItemStatus(BaseModel):
    title: str
    host: str
    status: str


class PackStatus(BaseModel):
    name: str
    exam: str
    approved: bool
    items: list[PackItemStatus] = Field(default_factory=list)


_SHOWN = {
    "pending": "waiting",
    "downloaded": "downloaded",
    "failed": "failed",
    "rejected": "blocked",
}
MAX_ITEMS_SHOWN = 10
MAX_REPLY_CHARS = 3500


def render_packs(rows: Sequence[PackStatus]) -> str:
    """`<name> · <exam> · <approved|not approved> · <downloaded>/<total>`, then items."""
    if not rows:
        return "No starter packs yet. Add checked URLs to infra/sources/exam_packs.yaml."
    lines: list[str] = []
    for p in rows:
        done = sum(1 for i in p.items if i.status == "downloaded")
        state = "approved" if p.approved else "not approved"
        lines.append(
            f"{clean_text(p.name, 40)} · {clean_text(p.exam, 20)} · {state} · {done}/{len(p.items)}"
        )
        for i in p.items[:MAX_ITEMS_SHOWN]:
            shown = _SHOWN.get(i.status, "unknown")
            lines.append(f"  - {clean_text(i.title, 80)} ({clean_text(i.host, 60)}): {shown}")
        if len(p.items) > MAX_ITEMS_SHOWN:
            lines.append(f"  … and {len(p.items) - MAX_ITEMS_SHOWN} more")
    text = "\n".join(lines)
    if len(text) > MAX_REPLY_CHARS:
        text = text[: MAX_REPLY_CHARS - 2].rsplit("\n", 1)[0] + "\n…"
    return text


async def pack_statuses(session: AsyncSession) -> list[PackStatus]:
    packs = (await session.execute(select(StarterPack).order_by(StarterPack.name))).scalars()
    out: list[PackStatus] = []
    for p in packs:
        items = (
            await session.execute(
                select(StarterPackItem)
                .where(StarterPackItem.pack_id == p.id)
                .order_by(StarterPackItem.id)
            )
        ).scalars()
        out.append(
            PackStatus(
                name=p.name,
                exam=p.exam,
                approved=p.approved,
                items=[
                    PackItemStatus(
                        title=i.title,
                        host=urllib.parse.urlsplit(i.url).hostname or "",
                        status=i.status,
                    )
                    for i in items
                ],
            )
        )
    return out
