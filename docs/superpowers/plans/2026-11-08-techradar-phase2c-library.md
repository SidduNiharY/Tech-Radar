# TechRadar Brain Phase 2c: Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Whole books, long PDFs, DOCX, EPUB and lecture videos that I drop into a Library folder become checked, chaptered, searchable material with page and timestamp references, night-model chapter summaries and per-book eval questions. It also adds starter packs from official and open sources, and RAG upgrades for big books. It ends with `make gate-2c`.

**Architecture:**
- **Intake:** Syncthing delivers my Library folder to `data/library-inbox` (receive-only on the server). The worker moves each settled file to `data/library/originals/<sha>.<ext>` and records it.
- **Processing:** the `worker-bulk` service plans parse jobs for the parser sandbox:
  - a probe, then 25-page parts for PDFs
  - extraction jobs for media
  - every job passes the full Intake Gateway, now with steps 4–6 for office files, archives and media
- **Indexing and summaries:**
  - **Chapters:** found from the outline, the headings or page ranges.
  - **Chunks:** indexed with context labels; tables are kept whole.
  - **Summaries:** written by the night model in the night window; every key idea's citation is checked in code.
- **Videos:** audio and frames are extracted and slides read here; transcription comes with phase 6 (D38).

**Tech Stack:** Docling 2.146 + RapidOCR, pypdfium2, oletools, defusedxml, ffmpeg/ffprobe, Pillow, Procrastinate (queue `bulk`), Syncthing, pgvector, python-telegram-bot.

**Spec:**
- [06_Improvements.md](../../../06_Improvements.md) Part A (A1–A8), Part F (F3 steps 4–6, F9) and Part G (G4, G6)
- [05_Architecture.md](../../../05_Architecture.md) §6, §7.4, §7.10, §7.11, §7.14, SEC-15, SEC-20, SEC-43, SEC-44, SEC-54, SEC-57
- [02_Tech_Stack_and_Security.md](../../../02_Tech_Stack_and_Security.md) §5.6, §5.16, §6
- [overview](2026-11-07-techradar-00-overview.md) D32–D38
- builds on phase 2 (gateway core) and phase 2b (chunks, indexer, answers, outbox)

## Global Constraints

- The overview's Global Constraints 1–23 apply.
- **Migration:** `0004b_library`, revision ID `0004b`, revises phase 2b's `0004`. Phase 3's `0005_practice` revises `0004b` (D32).
- **Limits (D37):**

  | Kind | Limit |
  |---|---|
  | PDF | 300 MB |
  | DOCX, EPUB | 50 MB |
  | Video | 4 GB and 4 hours |
  | Audio | 1 GB |
  | HTML | 5 MB |
  | Starter-pack item | 200 MB |

  PDFs are processed in parts of 25 pages, each with the parser's 120 s and 2.5 GB limits.
- **Gateway (D34, D36):**
  - **Macros:** quarantine.
  - **Reject:** archives other than DOCX and EPUB, zip bombs (over 200 MB uncompressed, a ratio over 100, or over 10,000 entries), path traversal in archive names, and media playlists or concat lists.
  - **Pixel rebuild:** flagged documents are rebuilt from pixels (render, then OCR).
- **Library files are kept for good:** originals are mode 0o440, and the news retention job never touches `data/library` (SEC-43). Videos are deleted after extraction unless I keep them.
- **Flagged content:** flagged chunks are searchable and labelled, but never used for summaries, book evals, MCQs or cards.
- **GPU work** (night-model summaries) runs only in the night window, 01:00–05:00 Asia/Kolkata. Parsing in the sandbox runs any time on the `bulk` queue.
- **Starter packs:** only packs with `approved: true`, only `https` URLs on allowlisted domains, never file-sharing or "free PDF" sites (SEC-05).
- **Telegram:** plain text, link previews off; callback data matches `^[a-z_]{1,20}(:[0-9]{1,12}){1,2}$`.

## Review Focus

1. **The server restarts halfway through a 300-page book**, so processing resumes at the next unfinished part. Task 4 `test_bulk_resumes_after_restart`.
2. **A file that Syncthing is still writing** isn't picked up until it has settled. Task 2 `test_partial_sync_file_skipped`.
3. **The same book dropped twice** is recognised, not processed twice. Task 2 `test_duplicate_book_detected`.
4. **A part whose pages can't be read** still leaves its chapter usable, with a note about the missing pages. Task 4 `test_failed_part_noted_in_chapter`.
5. **A scanned PDF with no text layer** still gets text through OCR. Task 4 `test_scanned_part_uses_ocr` (marker `slow`).

---

### Task 1: Library tables, schema fields and settings

**SEC:** SEC-12, SEC-18

**Files:**
- Create: `src/techradar/db/migrations/versions/0004b_library.py`
- Modify: `src/techradar/db/models.py`, `src/techradar/schemas/pipeline.py`, `src/techradar/settings.py`, `infra/intake/limits.yaml`
- Test: `tests/db/test_library_tables.py` (marker `db`), `tests/schemas/test_pipeline.py` (add tests)

**Interfaces:**
- Produces:
  - **Tables:**

    | Table | Columns |
    |---|---|
    | `library_docs` | `id`, `sha256` char(64) unique, `title` varchar(300), `kind` (`pdf`, `docx`, `epub`, `video`, `audio`, `html`), `origin` (`library`, `pack`), `original_path` text, `size_bytes` bigint, `pages` int null, `duration_s` real null, `status` (`queued`, `processing`, `awaiting_transcription`, `ready`, `quarantined`, `rejected`, `failed`), `trust` (`official`, `open`, `my_own`), `exam_tags` text[], `pack_item_id` null, `keep_media` bool default false, `created_at`, `ready_at` null |
    | `library_parts` | `id`, `doc_id` fk, `ordinal`, `page_start` null, `page_end` null, `ts_start` null, `ts_end` null, `status` (`pending`, `done`, `failed`) default `pending`, `attempts` int default 0, `job_id` char(32) null, `result_path` null |
    | `library_chapters` | `id`, `doc_id` fk, `ordinal`, `title` varchar(300), `page_start` null, `page_end` null, `ts_start` null, `ts_end` null, `text_path`, `summary_path` null, `missing_pages` int[] default `{}`, `read_at` null |
    | `book_evals` | `id`, `doc_id` fk, `question` varchar(300), `expected_chunk_ids` bigint[], `created_at` |
    | `starter_packs` | `id`, `name` unique, `exam`, `approved` bool, `updated_at` |
    | `starter_pack_items` | `id`, `pack_id` fk, `url`, `title`, `kind`, `licence`, `status` (`pending`, `downloaded`, `failed`, `rejected`), `doc_id` null |

  - **New `chunks` columns:** `doc_id` bigint null, `chapter_id` bigint null, `page` int null, `ts_start` real null, `context_label` text null; index on `(doc_id, chapter_id, ordinal)`.
  - **Schemas:**
    - `JobKind` adds `docx`, `epub`, `video`, `audio`, `image`.
    - The `raw_name` pattern adds `docx|epub|mp4|mkv|webm|mov|mp3|m4a|wav|ogg|png|jpg|jpeg`.
    - `ParseJob` adds `mode: Literal["full","probe","part","media"] = "full"`, `page_start: int | None = None`, `page_end: int | None = None`, `doc_id: int | None = None` and `part_id: int | None = None`.
    - For `purpose="library"`, `raw_name` is relative to `/data/library/originals`.
  - **Settings:**

    | Field | Default |
    |---|---|
    | `library_inbox` | `/data/library-inbox` |
    | `library_packs_dir` | `/data/library-packs` |
    | `library_part_pages` | `25` |
    | `max_video_s` | `14_400` |
    | `pack_max_bytes` | `200_000_000` |
    | `night_start` | `"01:00"` |
    | `night_end` | `"05:00"` |

  - **`limits.yaml` additions (bytes):**
    - `library`: pdf 300,000,000; docx 50,000,000; epub 50,000,000; video 4,000,000,000; audio 1,000,000,000; html 5,000,000
    - `pack`: pdf 200,000,000; docx 50,000,000; html 5,000,000

- [ ] **Step 1: Write the failing tests**

```python
def test_parse_job_part_fields():
    j = ParseJob(job_id="a" * 32, kind="pdf", raw_name="b" * 64 + ".pdf", url="library:x", source_id=0,
                 raw_item_id=None, origin="library", purpose="library", mode="part", page_start=26, page_end=50, doc_id=1, part_id=2)
    assert (j.page_start, j.page_end) == (26, 50)

def test_raw_name_accepts_video_extension():
    ParseJob(job_id="a" * 32, kind="video", raw_name="c" * 64 + ".mp4", url="library:v", source_id=0, raw_item_id=None)

@pytest.mark.db
async def test_library_doc_sha_unique(app_conn): ...                 # second insert with the same sha256 raises IntegrityError

@pytest.mark.db
async def test_chunk_page_columns_exist(app_conn): ...                # insert a chunk with doc_id, chapter_id, page=12 → reads back 12
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/schemas -v && uv run pytest -m db tests/db/test_library_tables.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the migration, models, schema fields, settings and limits**

- [ ] **Step 4: Migrate and run the tests**

Run: `docker compose run --rm migrate && uv run pytest tests/schemas && uv run pytest -m db tests/db -v`
Expected: migrate reaches `0004b`; PASS (earlier database tests stay green).

- [ ] **Step 5: Commit**

```bash
git add src/techradar/db src/techradar/schemas src/techradar/settings.py infra/intake tests && git commit -m "feat(library): library tables, part fields and settings"
```

### Task 2: Library inbox intake

**SEC:** SEC-43, SEC-57

**Files:**
- Create: `src/techradar/library/__init__.py`, `src/techradar/library/inbox.py`
- Modify:
  - `src/techradar/rag/indexer.py`: `index_sync` calls `plan_library_intake` instead of phase 2b's `plan_library_jobs`, which is removed with its test
  - `compose.yaml`: the worker mounts `./data/library-inbox` read-write (files are moved to `done/` or `rejected/`) and `./data/library-packs` read-write
  - `infra/host/RUNBOOK.md`: Syncthing's Library folder
- Test: `tests/library/test_inbox.py` (some tests marked `db`)

**Interfaces:**
- Consumes: `detect_mime` (phase 2 Task 6b); `enqueue_message` (phase 2b); `library_docs` (Task 1).
- Produces:
  - `LibraryKind = Literal["pdf","docx","epub","video","audio","html"]`
  - `MIME_TO_KIND: dict[str, LibraryKind]`:
    - `application/pdf` → pdf
    - `application/vnd.openxmlformats-officedocument.wordprocessingml.document` → docx
    - `application/epub+zip` → epub
    - `video/mp4`, `video/x-matroska`, `video/webm`, `video/quicktime` → video
    - `audio/mpeg`, `audio/mp4`, `audio/x-m4a`, `audio/wav`, `audio/x-wav`, `audio/ogg` → audio
    - `text/html` → html
  - `class InboxFile(BaseModel)`: `path: Path`, `size: int`, `mtime: float`
  - `def stable_files(inbox: Path, now: float, settle_s: int = 60) -> list[InboxFile]`. It returns files unchanged for at least `settle_s`, and skips:
    - the `done/`, `rejected/` and `gate/` folders (phase 8 routes `gate/`)
    - dotfiles, `*.tmp`, Syncthing temporary files (`.syncthing.*`) and symlinks
  - `class IntakeDecision(BaseModel)`: `kind: LibraryKind | None`, `reason: str | None`
  - `def classify(f: InboxFile, mime: str, limits: Mapping[str, Mapping[str, int]], origin: Literal["library","pack"]) -> IntakeDecision`. The reasons, exactly:
    - `unsupported type <mime>`
    - `too large (<n> MB, limit <m> MB)`
  - `async def plan_library_intake(session, inboxes: Sequence[tuple[Path, Literal["library","pack"]]], library_dir: Path, now: float, limits) -> list[int]` returns the new doc IDs. For each stable file:
    1. **Detect and classify.** A refused file moves to `<inbox>/rejected/`, and the outbox sends `Couldn't add <name>: <reason>.`
    2. **Hash it** (SHA-256, streamed). A known hash moves the file to `done/`, and the outbox sends `Already in your library: <title>.`
    3. **Store it:** moves the file to `library_dir/originals/<sha>.<ext>` with mode 0o440 (`os.replace`, or copy plus `fsync` plus unlink across filesystems).
    4. **Record it:** creates the `library_docs` row:
       - `title`: the file name without its extension, with underscores turned into spaces
       - `status`: `queued`
       - `trust`: `my_own` for the library origin; packs set their own trust (Task 9)
    5. **Queue it:** defers `plan_doc(doc_id)` on the `bulk` queue (Task 4).
- **Syncthing (owner, RUNBOOK):**
  - the Mac folder `~/TechRadar Library` is "Send Only"
  - the server folder `data/library-inbox` is "Receive Only"
  - ignore patterns: `.DS_Store`, `*.partial`, `~*`

- [ ] **Step 1: Write the failing tests**

```python
def test_partial_sync_file_skipped(tmp_path):
    (tmp_path / ".syncthing.book.pdf.tmp").write_bytes(b"x"); f = tmp_path / "book.pdf"; f.write_bytes(b"%PDF")
    os.utime(f, (time.time(), time.time()))                         # just written
    assert stable_files(tmp_path, time.time()) == []

def test_classify_reasons():
    big = InboxFile(path=Path("b.pdf"), size=301_000_000, mtime=0)
    assert classify(big, "application/pdf", LIMITS, "library").reason == "too large (301 MB, limit 300 MB)"
    assert classify(big, "application/zip", LIMITS, "library").reason == "unsupported type application/zip"

@pytest.mark.db
async def test_duplicate_book_detected(session, inbox_with_same_pdf_twice, outbox):
    await plan_library_intake(session, [(inbox_with_same_pdf_twice, "library")], LIB, NOW, LIMITS)
    assert await count(session, "library_docs") == 1 and outbox.texts[-1].startswith("Already in your library: ")

@pytest.mark.db
async def test_original_stored_read_only_outside_raw(session, inbox_with_pdf, tmp_path):
    [doc_id] = await plan_library_intake(session, [(inbox_with_pdf, "library")], tmp_path / "library", NOW, LIMITS)
    f = next((tmp_path / "library" / "originals").iterdir())
    assert f.stat().st_mode & 0o777 == 0o440 and not (tmp_path / "raw").exists()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/library/test_inbox.py -v && uv run pytest -m db tests/library/test_inbox.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `inbox.py`, the indexer change, the mounts and the runbook section**

- [ ] **Step 4: Run the tests and the policy check**

Run: same as Step 2, then `uv run pytest tests/security/test_compose_policy.py -q`.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/library src/techradar/rag/indexer.py compose.yaml infra/host tests && git commit -m "feat(library): Library folder intake with duplicate and size checks"
```

### Task 3: Gateway steps 4–6 for documents and media

**SEC:** SEC-44, SEC-54, SEC-57

**Files:**
- Create:
  - `src/techradar/intake/office.py`, `src/techradar/intake/zipcheck.py`, `src/techradar/intake/media.py`, `src/techradar/intake/rebuild.py`
  - `src/techradar/parser/epub.py`, `src/techradar/parser/docx.py`
  - fixtures in `tests/intake/fixtures/`: `macro.docx` (a renamed `.docm`), `zip_bomb.docx`, `traversal.epub`, `playlist.mp4` (an HLS playlist named `.mp4`), `concat.mp4` (an ffconcat list), `ok.epub`, `ok.docx`, `xxe.docx`, `short.mp4` (2 s, generated)
- Modify:
  - `src/techradar/intake/gateway.py`: `ALLOWED_MIME` adds `docx`, `epub`, `video`, `audio`, `image`; the structure step runs per kind
  - `infra/docker/Dockerfile` (parser stage): `oletools`, `pypdfium2`, and `ffmpeg` from apt
  - `infra/policy/approved_deps.yaml`; `infra/falco/expected_programs.yaml` (`parser: [python, ffprobe, ffmpeg]`; rerun the generator)
- Test: `tests/intake/test_office_zip_media.py`, `tests/intake/test_rebuild.py`, `tests/parser/test_epub_docx.py`

**Interfaces:**
- Consumes: `IntakeStep`, `gate_job`, `combine` (phase 2 Task 6b); `html_to_doc` (phase 2 Task 6).
- Produces:
  - `def check_zip(path: Path, *, max_total: int = 200_000_000, max_ratio: float = 100.0, max_entries: int = 10_000) -> IntakeStep`. It rejects on:
    - too many entries
    - a total uncompressed size over the limit
    - any entry with a compression ratio over the limit
    - absolute names, or `..` in names
    - symlink entries (from the external attributes)
  - `def check_office(path: Path) -> IntakeStep`: quarantine when `oletools.olevba.VBA_Parser(str(path)).detect_vba_macros()` is true, or the archive holds `vbaProject.bin`
  - `def office_xml_safe(path: Path) -> IntakeStep`: each `word/*.xml` part is parsed with `defusedxml` and `forbid_dtd=True`. Any DTD or entity gives a reject with detail `xml_entities`.
  - **Media:**
    - `class MediaInfo(BaseModel)`: `format_name: str`, `duration_s: float`, `has_audio: bool`, `has_video: bool`
    - `def probe_media(path: Path, timeout_s: int = 30) -> MediaInfo`: runs `["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-print_format", "json", "-show_format", "-show_streams", str(path)]` as a list
    - `ALLOWED_CONTAINERS = frozenset({"mov,mp4,m4a,3gp,3g2,mj2", "matroska,webm", "mp3", "wav", "ogg"})`
    - `def check_media(info: MediaInfo, max_s: int) -> IntakeStep`: rejects unless `format_name` is allowed (so `hls`, `concat`, `applehttp` and `image2` are rejected), and when `duration_s > max_s`. A video with no audio is flagged with detail `no audio to transcribe`.
  - **Rebuild:**
    - `def render_pages(pdf: Path, out_dir: Path, page_start: int, page_end: int, *, dpi: int = 150) -> list[Path]`: pypdfium2, run inside the parser
    - `def pixel_rebuild(pdf: Path, page_start: int, page_end: int, ocr: Callable[[Path], str]) -> str`: renders the pages, then OCRs them with RapidOCR. It's used only when the pre-parse verdict is `flag` (D36), so that text comes from pixels instead of the PDF's structure.
    - `def reencode_image(src: Path, dst: Path, max_px: int = 2048) -> Path`:
      1. sets `Image.MAX_IMAGE_PIXELS = 50_000_000` (decompression-bomb guard)
      2. opens the image and converts it to RGB
      3. fits it within `max_px`
      4. saves a PNG without metadata

      Phases 8 and 9 reuse it.
  - **EPUB:**
    - `class EpubChapter(BaseModel)`: `title: str`, `text: str`
    - `def epub_to_chapters(path: Path, max_chars: int) -> list[EpubChapter]`:
      1. runs `check_zip` first
      2. reads `META-INF/container.xml` and the OPF with `defusedxml`
      3. follows the spine
      4. gets each XHTML part's text through the same extraction as `html_to_doc`, with the title from `<title>` or the first heading
  - **DOCX:** `def docx_to_doc(path: Path, url: str, max_chars: int, artifacts_path: Path) -> CleanDoc | None`, through Docling, only after `check_zip`, `check_office` and `office_xml_safe`

- [ ] **Step 1: Write the failing tests**

```python
def test_zip_bomb_rejected():
    assert check_zip(FIX("zip_bomb.docx")).outcome == "reject"

def test_epub_path_traversal_rejected():
    assert check_zip(FIX("traversal.epub")).outcome == "reject"

def test_macro_docx_quarantined():
    assert check_office(FIX("macro.docx")).outcome == "quarantine"

def test_xxe_docx_rejected():
    assert office_xml_safe(FIX("xxe.docx")).outcome == "reject"

@pytest.mark.parametrize("name", ["playlist.mp4", "concat.mp4"])
def test_playlist_media_rejected(name):
    assert check_media(probe_media(FIX(name)), 14_400).outcome == "reject"

def test_ffprobe_uses_list_args_and_protocol_whitelist(monkeypatch):
    seen = capture_subprocess(monkeypatch); probe_media(Path("x.mp4"))
    assert isinstance(seen.args, list) and seen.args[seen.args.index("-protocol_whitelist") + 1] == "file"

def test_epub_chapters_follow_spine():
    assert [c.title for c in epub_to_chapters(FIX("ok.epub"), 100_000)] == ["Chapter 1", "Chapter 2"]

def test_reencode_strips_metadata_and_fits(tmp_path):
    out = reencode_image(FIX_IMG_WITH_EXIF_4000PX, tmp_path / "o.png")
    im = Image.open(out); assert max(im.size) <= 2048 and not im.info.get("exif")

def test_flagged_pdf_uses_pixel_text(gate_with_flag, monkeypatch):
    r = gate_with_flag(pdf_part_job(), ocr=lambda p: "TEXT FROM PIXELS")
    assert r.doc.text.startswith("TEXT FROM PIXELS")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/intake/test_office_zip_media.py tests/intake/test_rebuild.py tests/parser/test_epub_docx.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the checks, the rebuild, the EPUB and DOCX readers and the gateway wiring**

- [ ] **Step 4: Run the tests, the sandbox test and the policy check**

Run: same as Step 2, then `docker compose build parser && uv run pytest -m egress tests/security/test_parser_sandbox.py && uv run pytest tests/security/test_compose_policy.py -q`.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/intake src/techradar/parser infra tests && git commit -m "security(intake): office, archive and media checks with pixel rebuild"
```

### Task 4: Big PDFs in resumable parts, chapters and the night window

**SEC:** SEC-09, SEC-57

**Files:**
- Create:
  - `src/techradar/library/parts.py`, `src/techradar/library/chapters.py`
  - `src/techradar/night/__init__.py`, `src/techradar/night/window.py`
  - `src/techradar/ops/gpu.py`
- Modify:
  - `src/techradar/parser/pdf.py`: probe mode, page ranges and page markers
  - `src/techradar/worker/app.py`: queue `bulk`
  - `src/techradar/worker/tasks.py`
  - `compose.yaml`: the `worker-bulk` service, which is the worker image running `procrastinate … worker --queues=bulk --concurrency=1`
    - network `db` only
    - mounts `./data/library` (rw), `./data/parse-jobs` (rw), `./data/clean` (rw)
    - secret `tr_app_password`
    - baseline hardening
  - `infra/falco/expected_programs.yaml`: `worker-bulk: [python]`; `worker-bulk` added to `internal_only`
- Test: `tests/library/test_parts.py` (some tests marked `db`), `tests/library/test_chapters.py`, `tests/night/test_window.py`, `tests/ops/test_gpu.py`

**Interfaces:**
- Consumes: `write_job` (phase 2); `ParseJob` (Task 1); `library_parts`, `library_chapters` (Task 1).
- Produces:
  - **Parser, probe mode:**
    - `class OutlineEntry(BaseModel)`: `title` (≤300), `page: int`, `level: int`
    - `class PdfProbe(BaseModel)`: `n_pages: int`, `outline: list[OutlineEntry]` (≤500)
    - `def pdf_probe(path: Path) -> PdfProbe`, using pypdfium2's `get_toc()`; the result travels in `ParseResult` as `CleanDoc.text = PdfProbe.model_dump_json()` with `title="probe"`
  - **Parser, part mode:** Docling converts only `page_start`–`page_end` and writes a `<!-- page N -->` line before each page's text. Docling's OCR (RapidOCR) reads pages with no text layer.
  - `class PartSpec(BaseModel)`: `ordinal: int`, `page_start: int`, `page_end: int` (1-based, inclusive)
  - `def split_pdf_parts(n_pages: int, part_pages: int = 25) -> list[PartSpec]`
  - **Jobs** (queue `bulk`):
    - `plan_doc(doc_id)`: PDFs get a probe job. DOCX, EPUB and HTML get one `full` job. Videos and audio get a `media` job (Task 5).
    - `collect_bulk_results()`, every minute:
      - a probe result creates the `library_parts` rows and their part jobs
      - a part result marks the part `done` and stores `result_path`
      - a failed part is retried; after 3 attempts it becomes `failed`
      - when every part is done or failed, `build_chapters(doc_id)` runs
    - `resume_parts(doc_id)`: re-queues every `pending` part whose job file is missing from `parse-jobs`. `worker-bulk` runs it on start for every `processing` doc.
  - `class ChapterSpec(BaseModel)`: `ordinal`, `title`, `page_start`, `page_end`
  - `def detect_chapters(n_pages: int, outline: Sequence[OutlineEntry], headings: Sequence[tuple[int, int, str]], part_pages: int = 25) -> list[ChapterSpec]`, in order of preference:
    1. level-1 outline entries (at least 2)
    2. level-1 headings `(page, level, title)` found in the parsed parts
    3. fixed ranges titled `Pages <a>–<b>`
  - `def assemble_chapter_text(part_texts: Mapping[int, str], ch: ChapterSpec, failed_pages: Sequence[int]) -> str`:
    - joins the pages of the chapter in order, keeping the `<!-- page N -->` markers
    - adds `> Pages <a>–<b> couldn't be read.` at the place of each failed range
    - writes `data/library/text/<doc_id>/<NN>.md` and the chapter's `missing_pages`
  - **Night window and GPU** (here because 2c needs them first; phases 6 and 7 import them):
    - `def in_night_window(now_local: datetime, start: time, end: time) -> bool`
    - `def next_window_start(now_local: datetime, start: time) -> datetime`
    - `def night_only(fn)`: a decorator that re-defers the job at `next_window_start` outside the window, and calls `free_gpu` first inside it
    - `async def free_gpu(client: httpx.AsyncClient, ollama_url: str) -> list[str]` (`techradar.ops.gpu`): `/api/ps`, then `/api/generate {"model": name, "keep_alive": 0}` for each loaded model

- [ ] **Step 1: Write the failing tests**

```python
def test_split_pdf_parts():
    assert [(p.page_start, p.page_end) for p in split_pdf_parts(60, 25)] == [(1, 25), (26, 50), (51, 60)]

@pytest.mark.db
async def test_bulk_resumes_after_restart(session, doc_with_parts):      # parts 1–3 done, part 4 pending, its job file gone
    requeued = await resume_parts(session, doc_with_parts.id, jobs_dir=JOBS)
    assert requeued == [4] and (JOBS / f"{doc_with_parts.part4_job_id}.job.json").exists()

def test_detect_chapters_prefers_outline():
    out = [OutlineEntry(title="Money", page=1, level=1), OutlineEntry(title="Banks", page=30, level=1)]
    assert [(c.title, c.page_start, c.page_end) for c in detect_chapters(60, out, [])] == [("Money", 1, 29), ("Banks", 30, 60)]

def test_detect_chapters_falls_back_to_page_ranges():
    assert [c.title for c in detect_chapters(60, [], [])] == ["Pages 1–25", "Pages 26–50", "Pages 51–60"]

def test_failed_part_noted_in_chapter():
    text = assemble_chapter_text({1: "<!-- page 1 -->\nA"}, ChapterSpec(ordinal=1, title="T", page_start=1, page_end=50), failed_pages=range(26, 51))
    assert "> Pages 26–50 couldn't be read." in text

@pytest.mark.parametrize("hhmm,inside", [("00:59", False), ("01:00", True), ("04:59", True), ("05:00", False)])
def test_in_night_window(hhmm, inside):
    assert in_night_window(at(hhmm), time(1), time(5)) is inside

async def test_night_only_reschedules_outside_window(fake_defer):
    await night_only(fake_job)(now=at("06:00"))
    assert fake_defer.calls[0][1]["scheduled_at"] == at("01:00", next_day=True)

async def test_free_gpu_unloads_each_loaded_model(respx_mock): ...   # /api/ps lists 2 models → 2 keep_alive:0 calls

@pytest.mark.slow
def test_scanned_part_uses_ocr(): ...                                 # an image-only 2-page PDF fixture → part text contains its known words
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/library tests/night tests/ops -v && uv run pytest -m db tests/library/test_parts.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the parser modes, the parts and chapters modules, the jobs, the night window, `free_gpu` and `worker-bulk`**

- [ ] **Step 4: Run the tests, the slow test and the policy check**

Run: same as Step 2, then `uv run pytest -m slow tests/library -v && uv run pytest tests/security/test_compose_policy.py tests/security/test_falco_rules.py -q`.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar infra compose.yaml tests && git commit -m "feat(library): resumable 25-page parts, chapters and the night window"
```

### Task 5: Videos: audio, frames and slides

**SEC:** SEC-44

**Files:**
- Create: `src/techradar/parser/media_extract.py`
- Modify: `src/techradar/library/parts.py` (media jobs and their results), `compose.yaml` (the parser mounts `./data/library/media` read-write)
- Test: `tests/parser/test_media_extract.py`, `tests/library/test_media_jobs.py` (marker `db`)

**Interfaces:**
- Consumes: `probe_media`, `check_media` (Task 3); RapidOCR (already in the parser image).
- Produces:
  - `def extract_audio_parts(src: Path, out_dir: Path, part_s: int = 600, timeout_s: int = 900) -> list[Path]`: runs `["ffmpeg", "-nostdin", "-protocol_whitelist", "file", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-f", "segment", "-segment_time", str(part_s), "-c:a", "flac", str(out_dir / "part-%03d.flac")]`
  - `def extract_frames(src: Path, out_dir: Path, every_s: int = 30, timeout_s: int = 900) -> list[tuple[float, Path]]`: `-vf fps=1/<every_s>`, PNG files, each with its timestamp
  - `class SlideText(BaseModel)`: `ts_s: float`, `text: str` (≤4000)
  - `def slide_text(frames: Sequence[tuple[float, Path]], ocr: Callable[[Path], str]) -> list[SlideText]`: drops frames with no text, and frames whose normalized text equals the previous slide's
  - **Media job results:**
    - the audio parts and `slides.json` in `data/library/media/<doc_id>/`
    - one `library_parts` row per audio part, with `ts_start` and `ts_end`
    - the doc status becomes `awaiting_transcription` (D38)
  - **Chapters for videos and audio:** every 15 minutes, titled `Part <n> (<mm:ss>–<mm:ss>)`; created when the transcription arrives in phase 6
  - **After extraction:** the original video is deleted unless `keep_media` is true; the audio parts stay until phase 6 transcribes them
  - **Ready notice:** `Got <title>: audio and slides are ready; the transcript comes when phase 6 is built.` is sent once (replaced in phase 6)

- [ ] **Step 1: Write the failing tests**

```python
def test_extract_audio_uses_list_args_and_whitelist(monkeypatch, tmp_path):
    seen = capture_subprocess(monkeypatch); extract_audio_parts(Path("v.mp4"), tmp_path)
    assert isinstance(seen.args, list) and "-protocol_whitelist" in seen.args and seen.kwargs["timeout"] == 900

def test_slide_text_drops_repeats():
    texts = iter(["Deadlocks", "Deadlocks", "", "Banker's algorithm"])
    s = slide_text([(0, P), (30, P), (60, P), (90, P)], ocr=lambda p: next(texts))
    assert [x.ts_s for x in s] == [0, 90]

@pytest.mark.db
async def test_media_result_awaits_transcription(session, media_result):
    await collect_bulk_results(session)
    assert await doc_status(session, media_result.doc_id) == "awaiting_transcription"

@pytest.mark.db
async def test_video_deleted_unless_kept(session, media_result, library_dir):
    await collect_bulk_results(session)
    assert not (library_dir / "originals" / media_result.raw_name).exists()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/parser/test_media_extract.py -v && uv run pytest -m db tests/library/test_media_jobs.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the extraction, the job handling and the mount**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/parser src/techradar/library compose.yaml tests && git commit -m "feat(library): video audio, frames and slide text in the sandbox"
```

### Task 6: Indexing chapters with context labels, tables and page references

**SEC:** SEC-17, SEC-39, SEC-40

**Files:**
- Create: `src/techradar/library/index.py`
- Modify: `src/techradar/rag/chunker.py` (tables kept whole; page markers)
- Test: `tests/rag/test_chunker.py` (add tests), `tests/library/test_index.py` (marker `db`)

**Interfaces:**
- Consumes: `split_markdown` (phase 2b); `Embedder`; `library_chapters` (Task 1).
- Produces:
  - **Chunker changes:** `split_markdown(md, doc_path, *, target_tokens=500, overlap_tokens=60, keep_tables=True)`:
    - a Markdown table (consecutive lines starting with `|`) is never split
    - a table over 4,000 characters becomes its own chunks, split at row boundaries, with the header row repeated in each
  - `def page_of(chunk_text: str, last_page: int | None) -> tuple[int | None, str]`: the last `<!-- page N -->` marker in or before the chunk, plus the text with the markers removed
  - `def context_label(book: str, chapter: str, heading_path: Sequence[str]) -> str`: `"<book> › <chapter> › <section>"`, cut to 200 characters
  - **Embedding input:** `context_label + "\n\n" + text`. The stored `text` doesn't include the label; `context_label` has its own column.
  - `async def index_library_chapter(deps: IndexDeps, chapter_id: int) -> int` writes chunks with:
    - `doc_path = "library/<doc_id>/<NN>.md"`, `doc_kind = "library"`
    - `doc_id`, `chapter_id`, `page` (or `ts_start` for transcripts), `context_label`
    - `flagged` from the gateway verdict of the part that produced the text
    - `verified = None`, plus the doc's trust shown as a label in answers (`official`, `open` or `my own`)

    It returns the chunk count. `build_chapters` (Task 4) calls it for every new chapter.

- [ ] **Step 1: Write the failing tests**

```python
def test_table_kept_whole():
    md = "# T\n" + "\n".join(["| a | b |", "|---|---|"] + [f"| {i} | {i * 2} |" for i in range(40)])
    cs = split_markdown(md, "t.md", target_tokens=50)
    assert sum("| a | b |" in c.text for c in cs) == 1

def test_page_marker_sets_page_and_is_removed():
    page, text = page_of("<!-- page 12 -->\nThe repo rate is…", None)
    assert page == 12 and "<!--" not in text

@pytest.mark.db
async def test_context_label_used_for_embedding_not_text(index_deps, chapter, spy_embedder):
    await index_library_chapter(index_deps, chapter.id)
    assert spy_embedder.inputs[0].startswith("Indian Economy › Money › ") and not (await first_chunk_text(index_deps)).startswith("Indian Economy ›")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/rag/test_chunker.py -v && uv run pytest -m db tests/library/test_index.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the chunker changes and `index.py`**

- [ ] **Step 4: Run the tests**

Run: same as Step 2, then `uv run pytest -m db tests/rag -q` (the phase 2b tests stay green).
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/rag src/techradar/library tests && git commit -m "feat(library): chapter chunks with context labels, whole tables and page references"
```

### Task 7: Chapter summaries, the Ready message and book evals

**SEC:** SEC-18, SEC-37, SEC-38, SEC-39

**Files:**
- Create: `src/techradar/library/summaries.py`, `src/techradar/library/evals.py`, `src/techradar/vault/templates/chapter.md.j2`
- Modify: `src/techradar/worker/tasks.py` (`summarize_chapters_job`: queue `llm`, `night_only`), `evals/rag/` (book evals in `make rag-eval`)
- Test: `tests/library/test_summaries.py`, `tests/library/test_evals.py` (marker `db`)

**Interfaces:**
- Consumes: `complete_json`, `Role.NIGHT`, `Role.WORKER`; `check_citations`, `build_context` (phase 2b); `write_note`, `slugify` (phase 2); `night_only` (Task 4); `enqueue_message`.
- Produces:
  - `class TermDef(BaseModel)`: `term: NoLinks` (≤60), `meaning: NoLinks` (≤200)
  - `class ChapterSummary(BaseModel)`:
    - `key_ideas: list[NoLinks]` (3–8, each ≤240 and ending with a `[C#]` citation)
    - `terms: list[TermDef]` (≤12)
    - `formulas: list[str]` (≤10, LaTeX, each ≤200)
  - `async def summarize_chapter(completer, chapter: ChapterRow, excerpts: Sequence[Excerpt]) -> ChapterSummary | None`:
    - **Input:** the night role gets up to 12 of the chapter's chunks, in order and wrapped as untrusted; flagged chunks are left out.
    - **Citations:** every key idea must pass `check_citations`; otherwise the result is `None`.
    - **Formulas:** a formula that doesn't appear in the chapter text (after whitespace normalisation) is dropped.
  - `def render_chapter_note(doc: DocRow, chapter: ChapterRow, s: ChapterSummary, page_of_citation: Mapping[int, int | None]) -> str`:
    - **Front matter:** `kind: chapter_summary`, `generated: true`, `doc_id`, `chapter_id`, `source: <title>`, `pages: <a>–<b>`
    - **Body:** `## Key ideas` (each `[C#]` replaced by `(p. <n>)`), `## Terms`, `## Formulas`
  - **Note path:** `library/<book-slug>/<NN>-<chapter-slug>.md`, through `write_note`
  - `def render_ready(title: str, n_chapters: int) -> str`, exactly `Ready: <title> · <n> chapters, summaries in your vault. Reply to this message with a question to ask this book.`. It's sent with `purpose="library_ready"`, `ref_id=<doc_id>` and the button `Chapters` (`chap:<doc_id>`).
  - `async def make_book_evals(completer, session, doc_id: int, n: int = 15) -> int`:
    1. picks `n` unflagged chunks spread across the chapters
    2. the worker model writes one question per chunk that the chunk answers (`NoLinks`, ≤200)
    3. stores each question with `expected_chunk_ids=[chunk.id]`

    `make rag-eval` reports recall@5 for each book.

- [ ] **Step 1: Write the failing tests**

```python
async def test_uncited_key_idea_rejects_summary():
    fc = FakeCompleter([summary_json(key_ideas=["Inflation is rising."])] * 2)    # no [C#]
    assert await summarize_chapter(fc, CHAPTER, EXCERPTS) is None

async def test_formula_not_in_text_dropped():
    fc = FakeCompleter([summary_json(formulas=[r"E = mc^2", r"r = \frac{i}{n}"])])
    s = await summarize_chapter(fc, CHAPTER_WITH_R_FORMULA, EXCERPTS)
    assert s.formulas == [r"r = \frac{i}{n}"]

def test_render_ready_exact():
    assert render_ready("Indian Economy", 10) == ("Ready: Indian Economy · 10 chapters, summaries in your vault. "
                                                  "Reply to this message with a question to ask this book.")

def test_chapter_note_uses_page_numbers():
    md = render_chapter_note(DOC, CHAPTER, SUMMARY_C1, {1: 12})
    assert "(p. 12)" in md and "[C1]" not in md and "generated: true" in md

@pytest.mark.db
async def test_book_evals_point_at_their_chunks(session, indexed_doc):
    n = await make_book_evals(FakeCompleter([question_json()] * 15), session, indexed_doc.id)
    assert n == 15 and await all_expected_ids_exist(session, indexed_doc.id)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/library/test_summaries.py -v && uv run pytest -m db tests/library/test_evals.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the summaries, the note template, the Ready message, the evals and the job**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/library src/techradar/vault src/techradar/worker evals tests && git commit -m "feat(library): cited chapter summaries, Ready message and per-book evals"
```

### Task 8: RAG upgrades for big books

**SEC:** SEC-37, SEC-38, SEC-41

**Files:**
- Create: `src/techradar/rag/rewrite.py`, `src/techradar/rag/expand.py`
- Modify:
  - `src/techradar/rag/retrieve.py`: the `doc_id` scope, several queries, neighbours
  - `src/techradar/rag/answer.py`: the night fallback
  - `src/techradar/bot/routing.py`: a reply to a Ready message asks that book
  - `src/techradar/worker/tasks.py`: `ask_night` (queue `llm`, `night_only`)
- Test: `tests/rag/test_rewrite_expand.py`, `tests/rag/test_scope.py` (marker `db`), `tests/bot/test_ask_scope.py`

**Interfaces:**
- Consumes: `retrieve`, `answer_question`, `Answer` (phase 2b); `night_only` (Task 4).
- Produces:
  - `class Rewrites(BaseModel)`: `queries: list[NoLinks]` (1–2, each ≤200)
  - `async def rewrite_query(completer, question: str) -> list[str]`: the original question plus up to 2 rewrites from the worker model; on any failure, only the original. Retrieval runs every query and fuses all the lists with reciprocal rank fusion.
  - `def expand_with_neighbors(hits: Sequence[Hit], neighbors: Callable[[Hit], tuple[Hit | None, Hit | None]], *, max_excerpts: int = 6, max_tokens: int = 8000) -> list[Hit]`: adds the chunk before and after each top hit from the same `doc_id` and heading path. It keeps document order and stays within 6 excerpts and the 8k-token limit (SEC-41).
  - `retrieve(question: str, deps, *, doc_id: int | None = None, …)`: `doc_id` limits the search to one library document
  - `answer_question(question, deps, f=RetrieveFilters(), *, doc_id: int | None = None, role: Role = Role.WORKER) -> Answer`: passes `doc_id` to `retrieve`. `ask_night` (and phase 12's slow path) uses `role=Role.NIGHT`.
  - **Bot:** a message that replies to a Ready message (outbox `purpose="library_ready"`) is asked with `doc_id=<ref_id>`. `/ask` used as such a reply does the same.
  - **Hard questions:** when `answer_question` returns `needs_review` twice, or `not_found` with a best score between 0.20 and `rag_min_score`:
    - the job defers `ask_night(question, chat_id, doc_id)` and replies `I'll answer this one tonight with the bigger model.`
    - `ask_night` uses `Role.NIGHT` with the same citation checks, and replies through the outbox

- [ ] **Step 1: Write the failing tests**

```python
async def test_rewrite_falls_back_to_original():
    assert await rewrite_query(FakeCompleter(["nope", "nope"]), "What is CRR?") == ["What is CRR?"]

async def test_rewrites_capped_and_link_free():
    qs = await rewrite_query(FakeCompleter(['{"queries": ["cash reserve ratio", "CRR banks RBI"]}']), "What is CRR?")
    assert qs == ["What is CRR?", "cash reserve ratio", "CRR banks RBI"]

def test_expand_respects_caps():
    out = expand_with_neighbors(HITS_6, neighbors_always_two)
    assert len(out) == 6

@pytest.mark.db
async def test_doc_scope_returns_only_that_book(rag_deps, two_books):
    hits = await retrieve("repo rate", rag_deps, doc_id=two_books.first)
    assert {h.doc_id for h in hits} == {two_books.first}

async def test_reply_to_ready_message_scopes_ask(bot_ctx, ready_message):
    await handle_text(bot_ctx, reply_to=ready_message, text="What is CRR?")
    assert bot_ctx.deferred == [("ask", {"question": "What is CRR?", "chat_id": OWNER, "doc_id": ready_message.ref_id})]

async def test_hard_question_deferred_to_night(ask_deps_two_bad_citations, fake_defer):
    await ask_job("Explain the Taylor rule in this book", chat_id=OWNER, deps=ask_deps_two_bad_citations)
    assert fake_defer.calls[0][0] == "ask_night"
    assert ask_deps_two_bad_citations.outbox_texts[-1] == "I'll answer this one tonight with the bigger model."
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/rag/test_rewrite_expand.py tests/bot/test_ask_scope.py -v && uv run pytest -m db tests/rag/test_scope.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the rewrite, expansion, scope, routing and night fallback**

- [ ] **Step 4: Run the tests and the RAG eval**

Run: same as Step 2, then `make rag-eval`.
Expected: PASS; English recall@5 stays at least 0.80.

- [ ] **Step 5: Commit**

```bash
git add src/techradar/rag src/techradar/bot src/techradar/worker tests && git commit -m "feat(rag): query rewriting, neighbours, Ask this book and night answers"
```

### Task 9: Starter packs

**SEC:** SEC-05, SEC-25, SEC-57

**Files:**
- Create: `infra/sources/exam_packs.yaml`, `src/techradar/library/packs.py`
- Modify:
  - `src/techradar/fetcher/main.py`: the `download_pack_items` cycle
  - `compose.yaml`: the fetcher mounts `./data/library-packs` read-write
  - `src/techradar/bot/routing.py`: `/packs`
  - `infra/squid/allowlist.txt`: the domains below, each only after I've checked it
- Test: `tests/library/test_packs.py` (some tests marked `db`)

**Interfaces:**
- Consumes: `fetch_url`, `FetchDeps` (phase 2); `registrable_domain` (phase 2); `plan_library_intake` (Task 2).
- Produces:
  - **`exam_packs.yaml`:**
    - **Schema:** `packs: [{name, exam: Literal["gate_cs","gate_da","ssc_cgl","bank"], approved: bool, items: [{url, title, kind: Literal["pdf","html","docx"], licence: str}]}]`.
    - **Seed:** packs `gate`, `ssc_cgl` and `bank`, each with `approved: false` and an empty `items` list, plus a commented example item. I add item URLs after checking each one in a browser (owner step); no URL is invented.
  - `OFFICIAL_SUFFIXES = (".gov.in", ".nic.in")` and `OFFICIAL_DOMAINS = {"rbi.org.in", "ibps.in", "sbi.co.in", "nios.ac.in"}`, plus the year's GATE site
  - `OPEN_DOMAINS = {"nptel.ac.in", "ocw.mit.edu"}`
  - `def trust_for(host: str) -> Literal["official","open"] | None`
  - `class PackItem(BaseModel)`, `class Pack(BaseModel)`
  - `def load_packs(path: Path, allowed_hosts: frozenset[str]) -> list[Pack]`. It refuses an item whose:
    - URL isn't `https`
    - host isn't allowlisted
    - host has no `trust_for`
    - `kind` doesn't match the URL's extension (for `pdf` and `docx`)
  - `async def download_pack_items(deps: FetchDeps, session, packs: Sequence[Pack], packs_dir: Path) -> dict[str, int]`:
    - only packs with `approved: true`, and only `pending` items
    - `fetch_url` with `max_bytes = pack_max_bytes` and a 120 s timeout
    - each file is stored as `packs_dir/<pack>/<sha>.<ext>`; `plan_library_intake` then picks it up with origin `pack` and the item's trust
    - returns counts `downloaded`, `failed`, `rejected`
  - `def render_packs(rows: Sequence[PackStatus]) -> str`: one line per pack, `<name> · <exam> · <approved|not approved> · <downloaded>/<total>`
  - **Allowlist candidates (06 G6.5):** ncert.nic.in, nios.ac.in, nptel.ac.in, ocw.mit.edu, rbi.org.in, indiabudget.gov.in, pib.gov.in, ibps.in, sbi.co.in, ssc.gov.in, and the year's GATE site

- [ ] **Step 1: Write the failing tests**

```python
def test_unapproved_pack_never_downloaded(tmp_path, respx_mock): ...   # approved: false → no HTTP call at all

def test_non_allowlisted_or_http_item_refused():
    with pytest.raises(ValueError, match="allowlist"): load_packs(yaml_with("https://free-pdfs.example/book.pdf"), ALLOWED)
    with pytest.raises(ValueError, match="https"): load_packs(yaml_with("http://ncert.nic.in/a.pdf"), ALLOWED)

def test_trust_mapping():
    assert trust_for("ncert.nic.in") == "official" and trust_for("nptel.ac.in") == "open" and trust_for("example.com") is None

@pytest.mark.db
async def test_pack_item_over_limit_failed(session, approved_pack, respx_mock): ...   # 201 MB body → status failed, no file kept
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/library/test_packs.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the packs module, the fetcher cycle, the mount and `/packs`**

- [ ] **Step 4 (owner): Fill and approve the first pack**

1. Check each URL in a browser and add it to `exam_packs.yaml`.
2. Add its domain to the allowlist.
3. Set `approved: true` for the pack.
4. Run `docker compose restart squid fetcher`.

Expected: `/packs` shows the downloads progressing; each file arrives through the Intake Gateway and appears in the library.

- [ ] **Step 5: Run the tests and commit**

Run: `uv run pytest tests/library/test_packs.py -v && uv run pytest -m db tests/library -v`
Expected: PASS

```bash
git add infra/sources src/techradar/library src/techradar/fetcher src/techradar/bot compose.yaml infra/squid tests && git commit -m "feat(library): approved starter packs from allowlisted official and open sources"
```

### Task 10: Quarantine notices, release and retention

**SEC:** SEC-14, SEC-15, SEC-43, SEC-57

**Files:**
- Create: `src/techradar/library/quarantine.py`
- Modify:
  - `src/techradar/bot/routing.py`: `/quarantine`
  - `src/techradar/bot/callbacks.py`: `qrel`, `qrel_ok`, `qdel`
  - `src/techradar/pipeline/process.py`: the notice when an item is quarantined
  - `infra/backup/backup.sh`: `data/library` included, with `data/library/media/` excluded
  - `infra/backup/restic-excludes.txt`
- Test: `tests/library/test_quarantine.py` (marker `db`), `tests/pipeline/test_retention.py` (add a test), `tests/infra/test_backup_units.py` (add a test)

**Interfaces:**
- Consumes: `quarantine_items` (phase 2); `gate_job` (phase 2 Task 6b); `cleanup_retention` (phase 2).
- Produces:
  - **Notice** for every quarantined `telegram`, `library` or `pack` item: `🔒 Held for review: <file name> (<reasons>). Use /quarantine to release or delete it.`
  - `def render_quarantine(rows: Sequence[QuarantineRow]) -> tuple[str, list[list[Button]]]`:
    - up to 10 lines, `<id>. <name> · <reasons> · deleted on <d MMM>`
    - buttons `Release` (`qrel:<id>`) and `Delete` (`qdel:<id>`)
  - **Release (two steps):**
    1. `qrel:<id>` replies `Release <name>? It will be processed as flagged: searchable, but never used for facts, cards or questions.`, with `Yes, release` (`qrel_ok:<id>`). The button is valid for 60 s; phase 4 replaces this with a ticket.
    2. `qrel_ok` re-runs the job through `gate_job` with `owner_released=True`, which turns a `quarantine` outcome into `flag`; a `reject` stays a reject.
  - **Delete:** `qdel:<id>` deletes the file and sets `deleted_at`.
  - **Backups:** restic includes `data/library` without `data/library/media/`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.db
async def test_release_processes_as_flagged(session, quarantined_macro_docx, gate):
    await release(session, quarantined_macro_docx.id, gate=gate, now=NOW)
    assert await doc_flagged(session, quarantined_macro_docx.doc_id) is True

@pytest.mark.db
async def test_release_button_expires(session, quarantined_item):
    await request_release(session, quarantined_item.id, now=NOW)
    assert await confirm_release(session, quarantined_item.id, now=NOW + timedelta(seconds=61)) == "expired"

@pytest.mark.db
async def test_retention_never_touches_library(deps, library_original_400_days_old):
    await cleanup_retention(deps, datetime.now(UTC))
    assert library_original_400_days_old.exists()

def test_backup_includes_library_without_media():
    sh = Path("infra/backup/backup.sh").read_text()
    assert "data/library" in sh and "data/library/media" in Path("infra/backup/restic-excludes.txt").read_text()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -m db tests/library/test_quarantine.py tests/pipeline/test_retention.py -v && uv run pytest tests/infra -v`
Expected: FAIL

- [ ] **Step 3: Implement the quarantine module, the commands, the notice and the backup change**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/library src/techradar/bot src/techradar/pipeline infra/backup tests && git commit -m "feat(library): quarantine notices, two-step release, library kept and backed up"
```

### Task 11: Gate 2c

**SEC:** SEC-15, SEC-20, SEC-43, SEC-44, SEC-54, SEC-57; re-check of all earlier controls

**Files:**
- Create: `security/simulate/phase2c.sh`, `tests/fixtures/library/big_300_pages.pdf` (generated by `scripts/make_big_pdf.py`, git-ignored)
- Modify: `Makefile` (add `gate-2c`, `simulate-2c`), `docs/security/gates.md`

**Interfaces:**
- Produces:
  - **`make simulate-2c`:**
    1. drops `zip_bomb.docx`, `macro.docx` and `playlist.mp4` into the Library inbox, and expects reject, quarantine (with a notice) and reject
    2. drops `big_300_pages.pdf`, restarts `worker-bulk` after 3 parts, and expects the book to reach `ready` with no part processed twice
  - **`make gate-2c`:**
    1. `gate-2b`
    2. `pytest tests/library tests/intake tests/night tests/ops` (and `-m db`, `-m slow`)
    3. `make rag-eval`, including the book evals
    4. `make simulate-2c`
    5. the policy test and the Falco rules test
    6. print the signing reminder

- [ ] **Step 1: Run the gate on the server**

Run: `make gate-2c`
Expected: every step passes; book-eval recall@5 is at least 0.80.

- [ ] **Step 2 (owner): Try it with real material**

1. Drop one book I own and one lecture video into the Library folder on the Mac.

Expected:
- The book's Ready message arrives, and its chapter summaries appear in Obsidian.
- A reply to the Ready message answers from that book, with page numbers.
- The video waits as `awaiting_transcription` until phase 6.

- [ ] **Step 3: Commit and sign**

```bash
git add Makefile security/simulate docs/security/gates.md && git commit -m "docs(security): gate 2c passed"
```
