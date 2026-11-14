#!/bin/bash
set -euo pipefail

# TechRadar Brain: Phase 2c attack simulation (Library intake, Gate 2c).
#
# Hostile library files go through a TEMP copy of the real flow: the Library inbox
# intake (techradar.library.inbox, with an in-memory stand-in for the database row)
# and then the parser's own job loop (techradar.parser.main: build_gate + serve_once,
# so the Intake Gateway and the sandboxed parse are the production code). Everything
# runs in the parser image with --network none, a read-only root, no capabilities and
# only a temp folder mounted. Real data folders and the database are never touched.
#
# Each attack asserts its verdict (reject / quarantine / skipped) and the run then
# checks that nothing escaped: no file outside the expected folders, no link followed,
# no network inside the container. Any unexpected result exits non-zero.
#
# Antivirus is a stand-in that answers "clean" (the checks under test come before
# and after it); ClamAV itself is exercised by simulate-2 (phase2.sh).
#
# Usage: bash security/simulate/phase2c.sh            (gate run, on the server)
#        TR_SIM_PYTHON=.venv/bin/python bash security/simulate/phase2c.sh
#                                                     (LOCAL MODE: dev check only)

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="${TR_SIM_IMAGE:-techradar-parser}"
LOCAL_PY="${TR_SIM_PYTHON:-}"

echo "=== Starting Phase 2c Security Simulation ==="

if [ "$(id -u)" -eq 0 ]; then
    echo "FAIL: run as the owner, not root (the container runs as the caller's uid)"
    exit 1
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/tr-sim2c.XXXXXX")"
cleanup() {
    chmod -R u+rwX "$WORK" 2>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup EXIT

mkdir -p "$WORK/code" "$WORK/sim"
cp "$REPO/scripts/make_big_pdf.py" "$WORK/code/make_big_pdf.py"

# The parser parses in "spawn" children, which re-run the main script as __mp_main__:
# the entry point only imports the simulation when it really is __main__.
cat > "$WORK/code/harness.py" << 'PY'
"""Phase 2c attack harness entry point."""

if __name__ == "__main__":
    import sim_body  # noqa: F401
PY

cat > "$WORK/code/sim_body.py" << 'PY'
"""Phase 2c attack simulation: runs inside the parser image (or LOCAL MODE)."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import socket
import stat
import sys
import time
import uuid
import zipfile
from datetime import date
from pathlib import Path

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}", flush=True)
    if not ok:
        FAILURES.append(name)


p = argparse.ArgumentParser()
p.add_argument("sim", type=Path)
p.add_argument("--local", action="store_true")
p.add_argument("--src", type=Path)
p.add_argument("--infra", type=Path)
args = p.parse_args()
if args.src:
    sys.path.insert(0, str(args.src))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_big_pdf  # noqa: E402
from techradar.intake.av import AvResult  # noqa: E402
from techradar.intake.rules import load_rules  # noqa: E402
from techradar.library.inbox import load_limits, plan_library_intake  # noqa: E402
from techradar.parser.main import build_gate, default_guard_score, serve_once  # noqa: E402
from techradar.schemas.pipeline import ParseJob, ParseResult  # noqa: E402
from techradar.security.urls import load_allowlist  # noqa: E402

INFRA = args.infra or Path(os.environ.get("TR_INFRA_DIR", "/app/infra"))
SIM = args.sim
INBOX = SIM / "inbox"
OUTSIDE = SIM / "outside"
LIBRARY = SIM / "library"
ORIGINALS = LIBRARY / "originals"
QUARANTINE = SIM / "quarantine"
JOBS = SIM / "parse-jobs"
CLEAN = SIM / "clean"
RAW = SIM / "raw"
for d in (INBOX, OUTSIDE, ORIGINALS, LIBRARY / "media", QUARANTINE, JOBS, CLEAN, RAW):
    d.mkdir(parents=True, exist_ok=True)

# --- 0. The sandbox itself -------------------------------------------------------
if args.local:
    print("LOCAL MODE: network and read-only checks skipped; this is not a gate run")
else:
    nets = sorted(os.listdir("/sys/class/net"))
    check("sandbox: only the loopback interface", nets == ["lo"], str(nets))
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=3).close()
        reached = True
    except OSError:
        reached = False
    check("sandbox: no route to the internet", not reached)
    try:
        socket.getaddrinfo("example.com", 443)
        resolved = True
    except OSError:
        resolved = False
    check("sandbox: no DNS", not resolved)
    try:
        Path("/app/sim-write-probe").write_text("x")
        wrote = True
    except OSError:
        wrote = False
    check("sandbox: root filesystem is read-only", not wrote)

# --- 1. Hostile files -------------------------------------------------------------
CT = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
)
RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="word/document.xml"/></Relationships>'
)
DOC = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body><w:p><w:r><w:t>{}</w:t></w:r></w:p></w:body></w:document>"
)


def docx(path: Path, text: str, extra: dict[str, bytes] | None = None) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", DOC.format(text))
        for name, data in (extra or {}).items():
            z.writestr(name, data)


def zeros_entry(path: Path, n_bytes: int) -> None:
    """Append one deflated entry of zeros, streamed (never held in memory)."""
    with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo("word/media/zeros.bin")
        info.compress_type = zipfile.ZIP_DEFLATED  # a bare ZipInfo would store, not deflate
        with z.open(info, "w", force_zip64=True) as fh:
            block = b"\0" * (1 << 20)
            for _ in range(n_bytes >> 20):
                fh.write(block)


# Clean control: the gateway must not simply refuse everything.
docx(INBOX / "control.docx", "A clean library note.")
# Zip bomb: 250 MB of zeros in ~250 KB; inflates past the 200 MB archive cap.
docx(INBOX / "zip_bomb.docx", "bomb")
zeros_entry(INBOX / "zip_bomb.docx", 250 << 20)
# Decompression ratio: 4 MB of zeros, ratio ~1000 (limit 100), under the size cap.
docx(INBOX / "ratio_bomb.docx", "ratio")
zeros_entry(INBOX / "ratio_bomb.docx", 4 << 20)
# OOXML macro: a VBA project inside the package.
docx(INBOX / "macro.docx", "macro", {"word/vbaProject.bin": b"\xd0\xcf\x11\xe0" + b"\0" * 512})
# EPUB with an entity bomb (billion laughs) in a chapter.
LAUGHS = (
    '<?xml version="1.0"?><!DOCTYPE html [<!ENTITY a "lol">'
    + "".join(f'<!ENTITY {chr(98 + i)} "{("&" + chr(97 + i) + ";") * 10}">' for i in range(8))
    + ']><html xmlns="http://www.w3.org/1999/xhtml"><body><p>&i;</p></body></html>'
)
with zipfile.ZipFile(INBOX / "entity_bomb.epub", "w") as z:
    z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
    z.writestr(
        "META-INF/container.xml",
        '<?xml version="1.0"?><container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
        '<rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>",
    )
    z.writestr(
        "content.opf",
        '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<manifest><item id="c" href="c.xhtml" media-type="application/xhtml+xml"/>'
        '</manifest><spine><itemref idref="c"/></spine></package>',
    )
    z.writestr("c.xhtml", LAUGHS)
# A playlist named .mp4 (sniffed as a playlist) and one behind an MP4 header.
(INBOX / "playlist.mp4").write_bytes(b"#EXTM3U\n#EXTINF:-1,\nhttp://203.0.113.9/steal.ts\n")
(INBOX / "ftyp_playlist.mp4").write_bytes(
    b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    b"#EXTM3U\n#EXTINF:-1,\nhttp://203.0.113.9/steal.ts\n"
)
# PDF with JavaScript.
(INBOX / "pdf_with_js.pdf").write_bytes(
    b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R /Names << /JavaScript 3 0 R >> >>"
    b" endobj\n2 0 obj << /Type /Pages /Kids [4 0 R] /Count 1 >> endobj\n"
    b"3 0 obj << /Names [(x) 5 0 R] >> endobj\n"
    b"4 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj\n"
    b'5 0 obj << /S /JavaScript /JS (app.alert("x");) >> endobj\n'
    b"trailer << /Root 1 0 R >>\n%%EOF\n"
)
# Oversized: a sparse 301 MB PDF (library limit 300 MB); never read whole.
with (INBOX / "oversized.pdf").open("wb") as fh:
    fh.write(b"%PDF-1.4\n")
    fh.truncate(301_000_000)
# Symlinks in the inbox: to a file and to a folder outside it.
CANARY = OUTSIDE / "canary.pdf"
CANARY.write_bytes(make_big_pdf.build_pdf(30))
canary_sha = hashlib.sha256(CANARY.read_bytes()).hexdigest()
os.symlink(CANARY, INBOX / "linked.pdf")
os.symlink(OUTSIDE, INBOX / "linked_dir")
# The 300-page book for the probe and part path.
(INBOX / "big_300_pages.pdf").write_bytes(make_big_pdf.build_pdf())

# --- 2. Inbox intake (real code; an in-memory stand-in for the database row) -------


class _NoRow:
    def scalar_one_or_none(self) -> None:
        return None


class FakeSession:
    def __init__(self) -> None:
        self.docs: list = []
        self._next = 1

    async def execute(self, *_a, **_k) -> _NoRow:
        return _NoRow()

    def add(self, doc) -> None:
        self.docs.append(doc)

    async def flush(self) -> None:
        for d in self.docs:
            if d.id is None:
                d.id, self._next = self._next, self._next + 1

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


limits = load_limits(INFRA / "intake" / "limits.yaml")
session = FakeSession()
messages: list[str] = []
queued: list[int] = []


async def _send(text: str) -> None:
    messages.append(text)


async def _queue(doc_id: int) -> None:
    queued.append(doc_id)


asyncio.run(
    plan_library_intake(
        session,  # type: ignore[arg-type]
        [(INBOX, "library")],
        LIBRARY,
        time.time() + 3600,
        limits,
        queue_doc=_queue,
        send=_send,
    )
)
taken = {d.title: d for d in session.docs}
expected_taken = {
    "control",
    "zip bomb",
    "ratio bomb",
    "macro",
    "entity bomb",
    "ftyp playlist",
    "pdf with js",
    "big 300 pages",
}
check("inbox: expected files taken", set(taken) == expected_taken, str(sorted(taken)))
check("inbox: every taken file queued once", sorted(queued) == sorted(d.id for d in session.docs))
rejected = sorted(os.listdir(INBOX / "rejected")) if (INBOX / "rejected").exists() else []
check("inbox: playlist.mp4 rejected", "playlist.mp4" in rejected, str(rejected))
check("inbox: oversized.pdf rejected", "oversized.pdf" in rejected, str(rejected))
check(
    "inbox: owner told why (type, size)",
    any("playlist.mp4" in m and "unsupported type" in m for m in messages)
    and any("oversized.pdf" in m and "too large" in m for m in messages),
    "; ".join(messages),
)
check(
    "inbox: symlinks skipped, left in place, not followed",
    (INBOX / "linked.pdf").is_symlink()
    and (INBOX / "linked_dir").is_symlink()
    and not any(n.startswith(canary_sha) for n in os.listdir(ORIGINALS)),
)
check(
    "inbox: canary outside the inbox untouched",
    hashlib.sha256(CANARY.read_bytes()).hexdigest() == canary_sha
    and sorted(os.listdir(OUTSIDE)) == ["canary.pdf"],
)
bad = [
    n
    for n in os.listdir(ORIGINALS)
    if not re.fullmatch(r"[0-9a-f]{64}\.(pdf|docx|epub|mp4)", n)
    or (ORIGINALS / n).is_symlink()
    or stat.S_IMODE((ORIGINALS / n).lstat().st_mode) != 0o440
]
check("inbox: originals are hash-named, 0440, never links", not bad, str(bad))

# --- 3. Parser loop: Intake Gateway + sandboxed parse (production code) ------------


class CleanAv:
    """Stand-in: answers clean (ClamAV is exercised by simulate-2)."""

    def scan(self, path: Path) -> AvResult:
        return AvResult(status="clean", db_date=date.today())


gate = build_gate(
    RAW,
    QUARANTINE,
    av=CleanAv(),
    allowed_hosts=load_allowlist(INFRA / "squid" / "allowlist.txt"),
    limits=limits,
    rules=load_rules(INFRA / "intake" / "yara"),
    guard_score=default_guard_score(),
    library_dir=LIBRARY,
)
KIND = {"docx": "docx", "epub": "epub", "pdf": "pdf", "video": "video"}


def job_for(raw_name: str, kind: str, mode: str, doc_id: int, **extra) -> ParseJob:
    return ParseJob(
        job_id=uuid.uuid4().hex,
        kind=kind,  # type: ignore[arg-type]
        raw_name=raw_name,
        url=f"library:{doc_id}",
        source_id=0,
        origin="library",
        purpose="library",
        mode=mode,  # type: ignore[arg-type]
        doc_id=doc_id,
        **extra,
    )


def run(job: ParseJob) -> tuple[ParseResult, float]:
    (JOBS / f"{job.job_id}.job.json").write_text(job.model_dump_json(), encoding="utf-8")
    start = time.monotonic()
    serve_once(JOBS, RAW, CLEAN, gate=gate)
    took = time.monotonic() - start
    out = CLEAN / f"{job.job_id}.result.json"
    return ParseResult.model_validate_json(out.read_text(encoding="utf-8")), took


EXPECT = {
    "control": ("pass", "ok", "full"),
    "zip bomb": ("reject", "rejected", "full"),
    "ratio bomb": ("reject", "rejected", "full"),
    "macro": ("quarantine", "quarantined", "full"),
    "entity bomb": ("reject", "rejected", "full"),
    "ftyp playlist": ("reject", "rejected", "probe"),
    "pdf with js": ("quarantine", "quarantined", "probe"),
    "big 300 pages": ("pass", "ok", "probe"),
}
quarantined_jobs: dict[str, str] = {}
reasons_by_title: dict[str, list[str]] = {}
probe_text = ""
for title, (verdict, status, mode) in EXPECT.items():
    doc = taken.get(title)
    if doc is None:
        check(f"gateway: {title}", False, "not taken by the inbox")
        continue
    raw_name = Path(doc.original_path).name
    res, _ = run(job_for(raw_name, KIND[doc.kind], mode, doc.id))
    got = res.intake.verdict if res.intake else None
    reasons = res.intake.reasons if res.intake else []
    check(f"gateway: {title} -> {verdict}", (got, res.status) == (verdict, status),
          f"got {got}/{res.status} {reasons}")
    reasons_by_title[title] = list(reasons)
    if status == "quarantined":
        quarantined_jobs[res.job_id] = raw_name
    if title == "big 300 pages" and res.doc is not None:
        probe_text = res.doc.text

# Each refusal must be for the attack's own reason, not an earlier unrelated one.
for title, needle in [("zip bomb", "inflates past"), ("ratio bomb", "compression ratio"),
                      ("macro", "macros"), ("entity bomb", "xml_entities"),
                      ("ftyp playlist", "playlist"), ("pdf with js", "/JavaScript")]:
    got_reasons = " | ".join(reasons_by_title.get(title, []))
    check(f"gateway: {title} refused for its own reason", needle in got_reasons, got_reasons)

# The big book: probe, then parts at both ends (each inside the 120 s limit).
if probe_text:
    probe = json.loads(probe_text)
    chapters = [e for e in probe["outline"] if e["level"] == 1]
    check("book: probe sees 300 pages", probe["n_pages"] == 300, str(probe["n_pages"]))
    check("book: probe sees 10 chapters", len(chapters) == 10
          and chapters[4]["page"] == 121, str([c["page"] for c in chapters]))
else:
    check("book: probe result has text", False)

book = taken.get("big 300 pages")
artifacts = os.environ.get("TR_DOCLING_ARTIFACTS", "")
if book is not None and artifacts and Path(artifacts).is_dir():
    for start, end in [(1, 25), (276, 300)]:
        res, took = run(job_for(Path(book.original_path).name, "pdf", "part", book.id,
                                page_start=start, page_end=end))
        text = res.doc.text if res.doc else ""
        check(f"book: part {start}-{end} parsed", res.status == "ok", res.status)
        check(f"book: part {start}-{end} inside 120 s", took < 120, f"{took:.0f} s")
        check(f"book: part {start}-{end} keeps page refs",
              f"<!-- page {start} -->" in text and f"<!-- page {end} -->" in text
              and f"fact-{start}" in text and f"fact-{end}" in text)
        if start == 1:
            check("book: chapter heading on page 1 extracted",
                  "Chapter 1: Packets and Protocols" in text)
elif args.local:
    print("SKIP book parts (LOCAL MODE): Docling models live in the parser image")
else:
    check("book: Docling models present in the parser image", False, artifacts or "unset")

# Files that bypassed the inbox (an attacker writing into originals directly).
link_name = "f" * 64 + ".pdf"
os.symlink(CANARY, ORIGINALS / link_name)
res, _ = run(job_for(link_name, "pdf", "probe", 900))
check("gateway: symlink in originals -> reject", (res.intake.verdict if res.intake else None,
      res.status) == ("reject", "rejected"), res.status)
big_name = "e" * 64 + ".pdf"
with (ORIGINALS / big_name).open("wb") as fh:
    fh.write(b"%PDF-1.4\n")
    fh.truncate(301_000_000)
res, _ = run(job_for(big_name, "pdf", "probe", 901))
check("gateway: oversized file -> reject before reading",
      (res.intake.verdict if res.intake else None, res.status) == ("reject", "rejected")
      and any(s.name == "size" and s.outcome == "reject" for s in res.intake.steps),
      res.status)
playlist_name = "d" * 64 + ".mp4"
(ORIGINALS / playlist_name).write_bytes((INBOX / "rejected" / "playlist.mp4").read_bytes())
res, _ = run(job_for(playlist_name, "video", "probe", 902))
check("gateway: plain playlist named .mp4 -> reject",
      (res.intake.verdict if res.intake else None, res.status) == ("reject", "rejected"),
      res.status)

# --- 4. Nothing escaped -------------------------------------------------------------
check("parser: job spool empty", os.listdir(JOBS) == [], str(os.listdir(JOBS)))
check("parser: results only, hash-named",
      all(re.fullmatch(r"[0-9a-f]{32}\.result\.json", n) for n in os.listdir(CLEAN)))
held = {}
for job_dir in QUARANTINE.iterdir():
    held[job_dir.name] = sorted(os.listdir(job_dir))
check("quarantine: exactly the quarantined files held",
      held == {j: [n] for j, n in quarantined_jobs.items()}, str(held))
modes = [stat.S_IMODE(f.lstat().st_mode) for f in QUARANTINE.rglob("*") if f.is_file()]
check("quarantine: held files are 0400", modes and all(m == 0o400 for m in modes), str(modes))
check("library: no media written", os.listdir(LIBRARY / "media") == [])
allowed_links = {INBOX / "linked.pdf", INBOX / "linked_dir", ORIGINALS / link_name}
links = {Path(r) / n for r, ds, fs in os.walk(SIM) for n in ds + fs
         if (Path(r) / n).is_symlink()}
check("no links except the planted ones", links == allowed_links, str(sorted(links)))
allowed_top = {"inbox", "outside", "library", "quarantine", "parse-jobs", "clean", "raw"}
check("no files outside the expected folders", set(os.listdir(SIM)) <= allowed_top,
      str(sorted(os.listdir(SIM))))
check("raw (news) folder untouched", os.listdir(RAW) == [])
check("canary still intact", hashlib.sha256(CANARY.read_bytes()).hexdigest() == canary_sha)

if FAILURES:
    print(f"=== Phase 2c Simulation: FAIL ({len(FAILURES)}) ===")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("=== Phase 2c Simulation Complete: PASS ===")
PY

if [ -n "$LOCAL_PY" ]; then
    echo "LOCAL MODE: running with $LOCAL_PY instead of the parser image (not a gate run)"
    "$LOCAL_PY" "$WORK/code/harness.py" "$WORK/sim" --local \
        --src "$REPO/src" --infra "$REPO/infra"
    exit $?
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "FAIL: docker is not installed; run this on the server"
    exit 1
fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "FAIL: image $IMAGE not found; build the parser image first"
    exit 1
fi

# Same limits as the parser service (compose.yaml): no network, read-only root,
# no capabilities, no new privileges, only the temp folders mounted.
docker run --rm --pull never --network none --read-only --tmpfs /tmp \
    --cap-drop ALL --security-opt no-new-privileges:true \
    --user "$(id -u):$(id -g)" -e HOME=/tmp --memory 3g --cpus 2 --pids-limit 200 \
    -v "$WORK/code:/code:ro" -v "$WORK/sim:/sim" \
    --entrypoint python "$IMAGE" /code/harness.py /sim
