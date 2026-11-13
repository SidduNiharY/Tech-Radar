# Phase 2c build order (2026-11-13)

How the Library plan ([2026-11-08-techradar-phase2c-library.md](2026-11-08-techradar-phase2c-library.md)) gets built from where the code is today. The plan stays the spec; this file only adds what exists, what to reuse, the order, which model builds each task, and what waits on the owner. Written on Opus (owner rule: plans and security work on Opus, other development on Sonnet).

## Where the code is

- `src/techradar/library/` has early modules under other names: `bulk.py` (settling, SHA-256, an in-memory `BulkDocumentManager`), `toc.py` (25-page ranges, outline chapters), `media.py` (ffmpeg argument builders, `probe_media`), `summarizer.py` (night window, citation check, note render), `starter_packs.py`, `models.py`. Nothing in the app calls them.
- No `0004b` migration, no library tables, no `chunks.doc_id`/`page`/`context_label` columns. `JobKind` is still `feed|page|pdf|md`. Settings have the `library_*` fields but not `night_start`/`night_end`.
- No `night/` package, no `bulk` queue, no `worker-bulk` service.
- `rag/indexer.py` still has phase 2b's `plan_library_jobs` (Task 2 replaces it).
- `rag/scoped_ask.py` scopes "ask this book" with a substring match on the path (`%<id>%`), so book 1 also matches books 10 and 21. Task 8 replaces it with an exact `doc_id` filter.
- `intake/filetype.py` imports `magic` (python-magic), which is not approved or locked.

Rule for the early modules: reuse logic that matches the plan's interfaces and tests (rename to the plan's names), delete what the plan replaces. Don't keep two versions.

## Owner decisions that block tasks

| Decision | Blocks | Notes |
|---|---|---|
| Approve direct use of `pypdfium2`, `pillow`, `defusedxml`, `rapidocr` | Tasks 3, 4, 5 | Already in `uv.lock` through Docling; only `approved_deps.yaml` entries, no new download |
| Approve `oletools` (new dependency) | Task 3 macro check | Not in the lock; needs `uv add` within the existing `exclude-newer` |
| `ffmpeg` (apt) in the parser image | Tasks 3, 5 | System package; pinned Debian version like the other apt pins |
| `python-magic` (or keep the current fallback) | Task 2 MIME detection | Open since Phase 2 |
| Starter-pack URLs, checked in a browser | Task 9 step 4 | Owner adds them; no URL is invented. Downloads are the internet stage |
| Syncthing Library folder (Mac send-only, server receive-only) | Real use of Task 2 | Runbook step; tests use a temp folder |

## Order and who builds it

Everything is offline: fakes for models and HTTP (respx), real runs come in the internet stage. Each task is TDD, one commit, `make lint test`, plus `make test-db` on the TUF for the `db` tests.

| # | Plan task | Model | Why | Depends on |
|---|---|---|---|---|
| 1 | T1 tables, schema fields, settings, limits | Sonnet | Feature schema | - |
| 2 | T4 parts, chapters, night window, `free_gpu` (no compose yet) | Sonnet | Feature logic; reuse `toc.py`, `summarizer.is_night_window` | 1 |
| 3 | T2 inbox intake (settling, symlink skip, 0o440 originals, duplicates) | Sonnet, Opus review | Touches file handling; security review of the moves and modes | 1 |
| 4 | T3 gateway steps 4-6: zip, office XML, media, pixel rebuild, EPUB, DOCX | **Opus** | Intake Gateway (SEC-44, SEC-54, SEC-57) | 1, approvals |
| 5 | T4 compose part: `worker-bulk` service, `bulk` queue, Falco expected programs | **Opus** | Container hardening and Falco | 2 |
| 6 | T5 video audio, frames, slide text | Opus for ffmpeg calls, Sonnet for job handling | ffmpeg runs on untrusted media | 4, ffmpeg |
| 7 | T6 chapter indexing, context labels, whole tables, page refs | Sonnet | RAG feature | 2 |
| 8 | T7 chapter summaries, Ready message, book evals | Sonnet | Feature; the citation check is existing code | 7 |
| 9 | T8 query rewrite, neighbours, exact `doc_id` scope, night answers | Sonnet, Opus review of the scope fix | Fixes the substring leak | 7 |
| 10 | T10 quarantine notices, two-step release, retention, backups | **Opus** | Release path and backups are security controls | 4 |
| 11 | T9 starter packs (loader, trust, allowlist checks, mocked downloads) | **Opus** | Egress allowlist (SEC-05) | 3 |
| 12 | T11 `simulate-2c` and `gate-2c` | **Opus** | Gate and attack simulation | all |

How a Sonnet task runs: a `model: "sonnet"` subagent gets the plan task text, the reuse notes above and the repo rules (AGENTS.md: TDD, no new dependencies, never read `secrets/`, one commit). Opus reviews the diff and runs the tests before it is committed and pushed.

## Done means

`make gate-2c` passes on the TUF, except the parts that need the internet or real models (pack downloads, real summaries, `rag-eval` with real models), which move to the internet stage and are marked as waiting in `docs/security/gates.md`.
