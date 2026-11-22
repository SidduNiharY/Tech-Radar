"""Starter packs (Phase 2c Task 9): loader, trust, downloads, status.

SEC: SEC-05 (egress allowlist), SEC-25, SEC-57 (one door: pack files enter through the
library inbox like any other document).

No real URL appears here: hosts are allowlist-shaped test names and every HTTP call is
mocked with respx.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import httpx
import pytest

from techradar.fetcher.http import FetchDeps
from techradar.fetcher.limiter import DomainLimiter
from techradar.fetcher.robots import RobotsCache
from techradar.library.inbox import stable_files
from techradar.library.packs import (
    PackItemStatus,
    PackStatus,
    download_pack_items,
    fetch_pack_file,
    load_packs,
    pack_folder,
    render_packs,
    trust_for,
)
from tests.fakes import FakeClock, FakeResolver

ALLOWED = frozenset({"ncert.nic.in", "nptel.ac.in", "free-pdfs.example", "rbi.org.in"})
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def yaml_with(
    tmp_path: Path,
    url: str,
    *,
    kind: str = "pdf",
    approved: bool = False,
    name: str = "gate",
) -> Path:
    p = tmp_path / "exam_packs.yaml"
    p.write_text(
        f"""
packs:
  - name: {name}
    exam: gate_cs
    approved: {"true" if approved else "false"}
    items:
      - url: "{url}"
        title: "Book one"
        kind: {kind}
        licence: "free to download"
""",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def deps() -> FetchDeps:
    async def robots_404(url: str) -> tuple[int, str]:
        return 404, ""

    return FetchDeps(
        client=httpx.AsyncClient(),
        limiter=DomainLimiter(0.0, FakeClock()),
        robots=RobotsCache(robots_404),
        allowed=ALLOWED,
        resolver=FakeResolver(ips=["93.184.216.34"]),
        max_bytes=1000,
    )


# --- trust ---------------------------------------------------------------------


def test_trust_mapping():
    assert trust_for("ncert.nic.in") == "official"
    assert trust_for("indiabudget.gov.in") == "official"
    assert trust_for("rbi.org.in") == "official"
    assert trust_for("www.rbi.org.in") == "official"
    assert trust_for("nptel.ac.in") == "open"
    assert trust_for("ocw.mit.edu") == "open"
    assert trust_for("example.com") is None


def test_trust_is_not_fooled_by_lookalike_hosts():
    assert trust_for("gov.in") is None
    assert trust_for("evilgov.in") is None
    assert trust_for("rbi.org.in.evil.example") is None
    assert trust_for("notrbi.org.in") is None
    assert trust_for("NCERT.NIC.IN.") == "official"


# --- loader --------------------------------------------------------------------


def test_repo_seed_has_no_items_and_nothing_approved():
    packs = load_packs(Path("infra/sources/exam_packs.yaml"), ALLOWED)
    assert {p.name for p in packs} == {"gate", "ssc_cgl", "bank"}
    assert all(not p.approved and p.items == [] for p in packs)


def test_non_allowlisted_or_http_item_refused(tmp_path: Path):
    [pack] = load_packs(yaml_with(tmp_path, "https://evil.example/book.pdf"), ALLOWED)
    assert pack.ready_items() == []
    assert "allowlist" in (pack.items[0].refused or "")

    [pack] = load_packs(yaml_with(tmp_path, "http://ncert.nic.in/a.pdf"), ALLOWED)
    assert pack.ready_items() == []
    assert "https" in (pack.items[0].refused or "")


def test_allowlisted_host_without_trust_refused(tmp_path: Path):
    [pack] = load_packs(yaml_with(tmp_path, "https://free-pdfs.example/book.pdf"), ALLOWED)
    assert pack.ready_items() == []
    assert "trust" in (pack.items[0].refused or "")


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pw@ncert.nic.in/a.pdf",
        "https://ncert.nic.in:8443/a.pdf",
        "https://ncert.nic.in.evil.example/a.pdf",
    ],
)
def test_odd_urls_refused(tmp_path: Path, url: str):
    [pack] = load_packs(yaml_with(tmp_path, url), ALLOWED)
    assert pack.ready_items() == [] and pack.items[0].refused


def test_kind_must_match_extension(tmp_path: Path):
    [pack] = load_packs(yaml_with(tmp_path, "https://ncert.nic.in/a.html", kind="pdf"), ALLOWED)
    assert "extension" in (pack.items[0].refused or "")
    [pack] = load_packs(yaml_with(tmp_path, "https://ncert.nic.in/a.pdf", kind="docx"), ALLOWED)
    assert "extension" in (pack.items[0].refused or "")
    [pack] = load_packs(yaml_with(tmp_path, "https://ncert.nic.in/a.pdf", kind="html"), ALLOWED)
    assert "extension" in (pack.items[0].refused or "")
    [pack] = load_packs(yaml_with(tmp_path, "https://ncert.nic.in/a.PDF", kind="pdf"), ALLOWED)
    assert pack.items[0].refused is None


def test_good_item_is_ready(tmp_path: Path):
    [pack] = load_packs(yaml_with(tmp_path, "https://ncert.nic.in/books/a.pdf"), ALLOWED)
    [item] = pack.ready_items()
    assert item.host == "ncert.nic.in" and item.trust == "official"


@pytest.mark.parametrize(
    "body",
    [
        "packs: [{name: gate, exam: gate_cs, approved: false, items: [], extra: 1}]",
        "packs: [{name: gate, exam: upsc, approved: false, items: []}]",
        "packs: [{name: gate, exam: gate_cs, approved: 'yes', items: []}]",
        "packs: [{name: ../x, exam: gate_cs, approved: false, items: []}]",
        "packs: [{name: .hidden, exam: gate_cs, approved: false, items: []}]",
        "packs: [{name: a, exam: gate_cs, approved: false, items: []},"
        " {name: a, exam: bank, approved: false, items: []}]",
        "packs: [{name: a, exam: gate_cs, approved: false, items: ["
        "{url: 'https://ncert.nic.in/a.pdf', title: t, kind: exe, licence: l}]}]",
        "packs: [{name: a, exam: gate_cs, approved: false, items: ["
        "{url: 'https://ncert.nic.in/a.pdf', title: t, kind: pdf}]}]",
        "packs: [{name: a, exam: gate_cs, approved: false, items: ["
        "{url: 'https://ncert.nic.in/a.pdf', title: t, kind: pdf, licence: l, refused: no}]}]",
        "packs: [{name: a, exam: gate_cs, approved: false, items: ["
        "{url: 'https://ncert.nic.in/a.pdf', title: t, kind: pdf, licence: l},"
        "{url: 'https://ncert.nic.in/a.pdf', title: u, kind: pdf, licence: l}]}]",
        "other: 1",
        "- just a list",
    ],
)
def test_malformed_file_refused_whole(tmp_path: Path, body: str):
    p = tmp_path / "exam_packs.yaml"
    p.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError):
        load_packs(p, ALLOWED)


def test_load_logs_refused_items(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    caplog.set_level("WARNING")
    load_packs(yaml_with(tmp_path, "https://evil.example/book.pdf"), ALLOWED)
    assert "evil.example" in caplog.text


# --- one download ----------------------------------------------------------------


async def test_download_hashes_and_names_by_content(deps: FetchDeps, respx_mock, tmp_path):
    body = b"%PDF-1.4 hello"
    respx_mock.get("https://ncert.nic.in/a.pdf").mock(
        return_value=httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=body)
    )
    res = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path)
    sha = hashlib.sha256(body).hexdigest()
    assert res.status == "downloaded" and res.sha256 == sha
    stored = tmp_path / f"{sha}.pdf"
    assert stored.read_bytes() == body
    assert stored.stat().st_mode & 0o777 == 0o440
    assert [p.name for p in tmp_path.iterdir()] == [f"{sha}.pdf"]  # no temp left


async def test_same_content_twice_never_overwrites(deps: FetchDeps, respx_mock, tmp_path):
    body = b"%PDF-1.4 same"
    respx_mock.get("https://ncert.nic.in/a.pdf").mock(
        return_value=httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=body)
    )
    first = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path)
    ino = (tmp_path / f"{first.sha256}.pdf").stat().st_ino
    second = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path)
    assert second.status == "duplicate" and second.sha256 == first.sha256
    assert (tmp_path / f"{first.sha256}.pdf").stat().st_ino == ino
    assert len(list(tmp_path.iterdir())) == 1


async def test_pack_item_over_limit_failed_no_file_kept(deps: FetchDeps, respx_mock, tmp_path):
    respx_mock.get("https://ncert.nic.in/big.pdf").mock(
        return_value=httpx.Response(
            200, headers={"Content-Type": "application/pdf"}, content=b"x" * 5000
        )
    )
    res = await fetch_pack_file(deps, "https://ncert.nic.in/big.pdf", "pdf", tmp_path)
    assert res.status == "failed" and res.reason == "too_large"
    assert list(tmp_path.iterdir()) == []


async def test_streamed_body_over_limit_without_length_header(
    deps: FetchDeps, respx_mock, tmp_path
):
    async def chunks():
        for _ in range(10):
            yield b"y" * 300

    respx_mock.get("https://ncert.nic.in/big.pdf").mock(
        return_value=httpx.Response(
            200, headers={"Content-Type": "application/pdf"}, content=chunks()
        )
    )
    res = await fetch_pack_file(deps, "https://ncert.nic.in/big.pdf", "pdf", tmp_path)
    assert res.status == "failed" and res.reason == "too_large"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.respx(assert_all_called=False)
async def test_redirect_to_other_host_refused(deps: FetchDeps, respx_mock, tmp_path):
    respx_mock.get("https://ncert.nic.in/a.pdf").mock(
        return_value=httpx.Response(302, headers={"Location": "https://rbi.org.in/a.pdf"})
    )
    other = respx_mock.get("https://rbi.org.in/a.pdf")
    res = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path)
    assert res.status == "rejected" and "redirect" in (res.reason or "")
    assert not other.called
    assert list(tmp_path.iterdir()) == []


async def test_redirect_on_same_host_followed(deps: FetchDeps, respx_mock, tmp_path):
    respx_mock.get("https://ncert.nic.in/a.pdf").mock(
        return_value=httpx.Response(301, headers={"Location": "/books/a.pdf"})
    )
    respx_mock.get("https://ncert.nic.in/books/a.pdf").mock(
        return_value=httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=b"%P")
    )
    res = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path)
    assert res.status == "downloaded"


async def test_redirect_to_http_refused(deps: FetchDeps, respx_mock, tmp_path):
    respx_mock.get("https://ncert.nic.in/a.pdf").mock(
        return_value=httpx.Response(302, headers={"Location": "http://ncert.nic.in/a.pdf"})
    )
    res = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path)
    assert res.status == "rejected"


async def test_wrong_content_type_refused(deps: FetchDeps, respx_mock, tmp_path):
    respx_mock.get("https://ncert.nic.in/a.pdf").mock(
        return_value=httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<html>")
    )
    res = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path)
    assert res.status == "rejected" and res.reason == "bad_type"
    assert list(tmp_path.iterdir()) == []


async def test_docx_content_type_and_extension(deps: FetchDeps, respx_mock, tmp_path):
    respx_mock.get("https://ncert.nic.in/a.docx").mock(
        return_value=httpx.Response(200, headers={"Content-Type": DOCX}, content=b"PK\x03\x04")
    )
    res = await fetch_pack_file(deps, "https://ncert.nic.in/a.docx", "docx", tmp_path)
    assert res.status == "downloaded"
    assert (tmp_path / f"{res.sha256}.docx").is_file()


@pytest.mark.respx(assert_all_called=False)
async def test_private_address_refused(deps: FetchDeps, respx_mock, tmp_path):
    deps.resolver = FakeResolver(ips=["10.0.0.5"])
    route = respx_mock.get("https://ncert.nic.in/a.pdf")
    res = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path)
    assert res.status == "rejected" and not route.called


@pytest.mark.respx(assert_all_called=False)
async def test_robots_disallow_refused(deps: FetchDeps, respx_mock, tmp_path):
    async def robots_deny(url: str) -> tuple[int, str]:
        return 200, "User-agent: *\nDisallow: /\n"

    deps.robots = RobotsCache(robots_deny)
    route = respx_mock.get("https://ncert.nic.in/a.pdf")
    res = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path)
    assert res.status == "rejected" and res.reason == "robots" and not route.called


async def test_http_error_failed(deps: FetchDeps, respx_mock, tmp_path):
    respx_mock.get("https://ncert.nic.in/a.pdf").mock(return_value=httpx.Response(503))
    res = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path)
    assert res.status == "failed" and res.reason == "503"


async def test_symlinked_pack_folder_refused(deps: FetchDeps, respx_mock, tmp_path):
    real = tmp_path / "elsewhere"
    real.mkdir()
    (tmp_path / "packs").mkdir()
    os.symlink(real, tmp_path / "packs" / "gate")
    respx_mock.get("https://ncert.nic.in/a.pdf").mock(
        return_value=httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=b"%P")
    )
    res = await fetch_pack_file(
        deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path / "packs" / "gate"
    )
    assert res.status == "failed"
    assert list(real.iterdir()) == []


async def test_short_writes_still_store_exactly_the_hashed_bytes(
    deps: FetchDeps, respx_mock, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    # os.write may write less than asked; the stored file must still be the hashed bytes.
    import stat

    real_write = os.write

    def short_write(fd: int, data) -> int:
        if stat.S_ISREG(os.fstat(fd).st_mode) and len(data) > 3:
            return real_write(fd, bytes(data[:3]))
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", short_write)
    body = b"%PDF-1.4 " + b"z" * 100
    respx_mock.get("https://ncert.nic.in/a.pdf").mock(
        return_value=httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=body)
    )
    res = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path)
    monkeypatch.undo()
    assert res.status == "downloaded" and res.sha256 == hashlib.sha256(body).hexdigest()
    assert (tmp_path / f"{res.sha256}.pdf").read_bytes() == body


async def test_write_error_fails_and_leaves_no_temp_file(
    deps: FetchDeps, respx_mock, tmp_path, monkeypatch: pytest.MonkeyPatch
):
    # A full disk is a failed item (not retried every minute), never a crashed cycle.
    import errno
    import stat

    real_write = os.write

    def disk_full(fd: int, data) -> int:
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", disk_full)
    respx_mock.get("https://ncert.nic.in/a.pdf").mock(
        return_value=httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=b"%P")
    )
    res = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path)
    monkeypatch.undo()
    assert res.status == "failed" and res.sha256 is None
    assert list(tmp_path.iterdir()) == []


async def test_slow_download_stops_at_the_timeout(deps: FetchDeps, respx_mock, tmp_path):
    import asyncio

    async def trickle():
        yield b"%PDF"
        await asyncio.sleep(5)
        yield b"never"

    respx_mock.get("https://ncert.nic.in/a.pdf").mock(
        return_value=httpx.Response(
            200, headers={"Content-Type": "application/pdf"}, content=trickle()
        )
    )
    res = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", tmp_path, timeout_s=0.1)
    assert res.status == "failed" and res.reason == "timeout"
    assert list(tmp_path.iterdir()) == []


async def test_pack_files_are_seen_by_the_library_intake(deps: FetchDeps, respx_mock, tmp_path):
    # A pack named `gate` must not land in the intake's own skipped `gate/` folder.
    packs_dir = tmp_path / "packs"
    packs_dir.mkdir()
    folder = pack_folder(packs_dir, "gate")
    assert folder.name == "pack-gate"
    respx_mock.get("https://ncert.nic.in/a.pdf").mock(
        return_value=httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=b"%P")
    )
    res = await fetch_pack_file(deps, "https://ncert.nic.in/a.pdf", "pdf", folder)
    seen = stable_files(packs_dir, now=10**12)
    assert [f.path.name for f in seen] == [f"{res.sha256}.pdf"]


# --- the cycle -----------------------------------------------------------------


class NoSession:
    """Any database use fails the test."""

    def __getattr__(self, name: str):
        raise AssertionError(f"database used: {name}")


async def test_unapproved_pack_never_downloaded(deps: FetchDeps, respx_mock, tmp_path):
    packs = load_packs(yaml_with(tmp_path, "https://ncert.nic.in/a.pdf", approved=False), ALLOWED)
    counts = await download_pack_items(deps, NoSession(), packs, tmp_path / "packs")  # type: ignore[arg-type]
    assert counts == {"downloaded": 0, "failed": 0, "rejected": 0}
    assert not respx_mock.calls
    assert not (tmp_path / "packs").exists()


async def test_approved_pack_with_only_refused_items_downloads_nothing(
    deps: FetchDeps, respx_mock, tmp_path
):
    packs = load_packs(yaml_with(tmp_path, "https://evil.example/a.pdf", approved=True), ALLOWED)
    counts = await download_pack_items(deps, NoSession(), packs, tmp_path / "packs")  # type: ignore[arg-type]
    assert counts == {"downloaded": 0, "failed": 0, "rejected": 0}
    assert not respx_mock.calls


def _no_session_factory():
    raise AssertionError("database used")


async def test_pack_cycle_without_file_or_with_a_bad_file_does_nothing(
    deps: FetchDeps, respx_mock, tmp_path
):
    from techradar.fetcher.packs_cycle import run_pack_cycle

    assert await run_pack_cycle(deps, _no_session_factory, None, tmp_path, 10) == {}
    bad = tmp_path / "exam_packs.yaml"
    bad.write_text("packs: [{name: gate, exam: upsc, approved: true, items: []}]")
    assert await run_pack_cycle(deps, _no_session_factory, bad, tmp_path, 10) == {}
    assert not respx_mock.calls


# --- /packs ----------------------------------------------------------------------


def test_render_packs_lines():
    rows = [
        PackStatus(
            name="gate",
            exam="gate_cs",
            approved=True,
            items=[
                PackItemStatus(title="Book one", host="ncert.nic.in", status="downloaded"),
                PackItemStatus(title="Book two", host="ncert.nic.in", status="pending"),
                PackItemStatus(title="Bad one", host="evil.example", status="rejected"),
            ],
        ),
        PackStatus(name="bank", exam="bank", approved=False, items=[]),
    ]
    text = render_packs(rows)
    lines = text.splitlines()
    assert lines[0] == "gate · gate_cs · approved · 1/3"
    assert "Book two (ncert.nic.in): waiting" in text
    assert "Bad one (evil.example): blocked" in text
    assert "bank · bank · not approved · 0/0" in text


def test_render_packs_empty():
    assert "exam_packs.yaml" in render_packs([])


def test_render_packs_cleans_titles_and_caps_length():
    items = [
        PackItemStatus(title="x‮\x00evil" + "y" * 400, host="ncert.nic.in", status="pending")
        for _ in range(200)
    ]
    text = render_packs([PackStatus(name="gate", exam="gate_cs", approved=True, items=items)])
    assert "‮" not in text and "\x00" not in text
    assert len(text) <= 3800


# --- the /packs command (owner chat only) ------------------------------------------


def test_packs_routed_only_from_the_owner_chat():
    from techradar.bot.routing import Routed, route_update

    assert route_update(chat_id=7, text="/packs", owner_id=7) == Routed("packs")
    assert route_update(chat_id=7, text="/packs@TechRadarBot", owner_id=7) == Routed("packs")
    assert route_update(chat_id=9, text="/packs", owner_id=7) == Routed("ignore")
    assert route_update(chat_id=-5, text="/packs", owner_id=7, group_ids={-5}) == Routed("ignore")


async def test_packs_reply_refuses_other_chats_and_renders_for_the_owner(
    monkeypatch: pytest.MonkeyPatch,
):
    from contextlib import asynccontextmanager

    from techradar.bot import packs_command

    used: list[str] = []

    @asynccontextmanager
    async def factory():
        used.append("session")
        yield object()

    async def statuses(session):
        return [PackStatus(name="gate", exam="gate_cs", approved=False, items=[])]

    monkeypatch.setattr(packs_command, "pack_statuses", statuses)
    assert await packs_command.packs_reply(9, 7, factory) is None
    assert used == []
    assert await packs_command.packs_reply(7, 7, None) == "Not available yet."
    reply = await packs_command.packs_reply(7, 7, factory)
    assert reply == "gate · gate_cs · not approved · 0/0"


# --- database tests (TUF: make test-db) -----------------------------------------


def _db_settings():
    from techradar.settings import Settings

    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


@pytest.fixture
async def session():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from techradar.db.engine import make_engine

    engine = make_engine("app", _db_settings())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
        # The pack functions commit, so remove what the tests created.
        await s.execute(
            text(
                "DELETE FROM techradar.starter_pack_items WHERE pack_id IN "
                "(SELECT id FROM techradar.starter_packs WHERE name LIKE 'tstpk%')"
            )
        )
        await s.execute(text("DELETE FROM techradar.starter_packs WHERE name LIKE 'tstpk%'"))
        await s.execute(text("DELETE FROM techradar.library_docs WHERE title LIKE 'tstpk%'"))
        await s.commit()
    await engine.dispose()


def _pack_name() -> str:
    return "tstpk" + os.urandom(4).hex()


async def _item_row(session, name: str):
    from sqlalchemy import select

    from techradar.db.models import StarterPack, StarterPackItem

    res = await session.execute(
        select(StarterPackItem)
        .join(StarterPack, StarterPack.id == StarterPackItem.pack_id)
        .where(StarterPack.name == name)
    )
    row = res.scalar_one()
    await session.refresh(row)
    return row


@pytest.mark.db
async def test_pack_item_over_limit_failed(session, deps: FetchDeps, respx_mock, tmp_path):
    name = _pack_name()
    packs = load_packs(
        yaml_with(tmp_path, "https://ncert.nic.in/big.pdf", approved=True, name=name), ALLOWED
    )
    from techradar.library.packs import sync_packs

    await sync_packs(session, packs)
    respx_mock.get("https://ncert.nic.in/big.pdf").mock(
        return_value=httpx.Response(
            200, headers={"Content-Type": "application/pdf"}, content=b"x" * 5000
        )
    )
    counts = await download_pack_items(deps, session, packs, tmp_path / "packs")
    assert counts == {"downloaded": 0, "failed": 1, "rejected": 0}
    assert (await _item_row(session, name)).status == "failed"
    assert list(pack_folder(tmp_path / "packs", name).iterdir()) == []

    # A failed item is not retried by the next cycle.
    again = await download_pack_items(deps, session, packs, tmp_path / "packs")
    assert again == {"downloaded": 0, "failed": 0, "rejected": 0}
    assert len(respx_mock.calls) == 1


@pytest.mark.db
async def test_sync_blocks_refused_items_and_unblocks_them(session, tmp_path):
    from techradar.library.packs import sync_packs

    name = _pack_name()
    url = "https://ncert.nic.in/a.pdf"
    path = yaml_with(tmp_path, url, approved=True, name=name)
    await sync_packs(session, load_packs(path, frozenset()))  # host not allowlisted yet
    assert (await _item_row(session, name)).status == "rejected"
    await sync_packs(session, load_packs(path, ALLOWED))  # the owner added the domain
    assert (await _item_row(session, name)).status == "pending"


@pytest.mark.db
async def test_download_then_link_sets_trust_but_keeps_the_verdict(
    session, deps: FetchDeps, respx_mock, tmp_path
):
    from techradar.db.models import LibraryDoc
    from techradar.library.packs import link_pack_docs, pack_statuses, sync_packs

    name = _pack_name()
    packs_dir = tmp_path / "packs"
    packs = load_packs(
        yaml_with(tmp_path, "https://ncert.nic.in/a.pdf", approved=True, name=name), ALLOWED
    )
    await sync_packs(session, packs)
    body = b"%PDF-1.4 " + os.urandom(16)
    sha = hashlib.sha256(body).hexdigest()
    respx_mock.get("https://ncert.nic.in/a.pdf").mock(
        return_value=httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=body)
    )
    assert (await download_pack_items(deps, session, packs, packs_dir))["downloaded"] == 1
    waiting = pack_folder(packs_dir, name) / f"{sha}.pdf"
    assert waiting.is_file()

    # While the file waits for the intake nothing is linked.
    assert await link_pack_docs(session, packs_dir) == 0

    # The intake took it (as `open`) and the gateway held it.
    doc = LibraryDoc(
        sha256=sha,
        title=f"tstpk {sha}",
        kind="pdf",
        origin="pack",
        original_path=f"originals/{sha}.pdf",
        size_bytes=len(body),
        status="quarantined",
        trust="open",
    )
    session.add(doc)
    await session.commit()
    waiting.unlink()

    assert await link_pack_docs(session, packs_dir) == 1
    await session.refresh(doc)
    assert doc.trust == "official" and doc.title == "Book one"
    assert doc.status == "quarantined" and doc.flagged is False
    item = await _item_row(session, name)
    assert item.doc_id == doc.id and doc.pack_item_id == item.id
    doc.title = f"tstpk {sha}"  # cleanup marker
    await session.commit()

    [status] = [s for s in await pack_statuses(session) if s.name == name]
    assert render_packs([status]).splitlines()[0].endswith("approved · 1/1")


@pytest.mark.db
async def test_file_refused_by_intake_marks_item_failed(
    session, deps: FetchDeps, respx_mock, tmp_path
):
    from techradar.library.packs import link_pack_docs, sync_packs

    name = _pack_name()
    packs_dir = tmp_path / "packs"
    packs = load_packs(
        yaml_with(tmp_path, "https://ncert.nic.in/a.pdf", approved=True, name=name), ALLOWED
    )
    await sync_packs(session, packs)
    body = os.urandom(32)
    respx_mock.get("https://ncert.nic.in/a.pdf").mock(
        return_value=httpx.Response(200, headers={"Content-Type": "application/pdf"}, content=body)
    )
    await download_pack_items(deps, session, packs, packs_dir)
    (pack_folder(packs_dir, name) / f"{hashlib.sha256(body).hexdigest()}.pdf").unlink()
    assert await link_pack_docs(session, packs_dir) == 0
    assert (await _item_row(session, name)).status == "failed"


@pytest.mark.db
async def test_pack_cycle_with_the_seed_makes_no_http_call(session, deps, respx_mock, tmp_path):
    from contextlib import asynccontextmanager

    from techradar.fetcher.packs_cycle import run_pack_cycle
    from techradar.library.packs import pack_statuses

    @asynccontextmanager
    async def factory():
        yield session

    seed = Path("infra/sources/exam_packs.yaml")
    counts = await run_pack_cycle(deps, factory, seed, tmp_path / "packs", 200_000_000)
    assert counts == {"downloaded": 0, "failed": 0, "rejected": 0, "linked": 0}
    assert not respx_mock.calls
    shown = {s.name: s for s in await pack_statuses(session)}
    assert {"gate", "ssc_cgl", "bank"} <= shown.keys()
    assert not any(shown[n].approved for n in ("gate", "ssc_cgl", "bank"))
