# Security Validation Gates

One row per gate from the overview plan (`docs/superpowers/plans/2026-11-07-techradar-00-overview.md`, "Security gates"). A gate is signed only when every check in its definition has passed, with the evidence named here. Columns follow Phase 1 Task 19.

**Reset on 2026-11-12.** The rows recorded on 2026-11-08 (gates 1, 2, 2b, 2c, 3, 4 and 5 marked PASS) are withdrawn. They cited nmap scans and a received heartbeat although the Linux server did not exist yet, the `make gate-N` targets ran far less than the gate definitions, gate 4 was signed before the web UI was committed, and the rows for gates 6 to 14 named phases that are not in the plans (there are no phases 13 or 14). An audit on 2026-11-10 found the database code had never run against Postgres.

| Gate | Date | Commit | nmap LAN | nmap tailnet | Heartbeat | Notes | Signed |
|---|---|---|---|---|---|---|---|
| gate-1: Secure foundation | | | not run | not run | not set up | NOT PASSED. Verified 2026-11-13 on the TUF at `2f8e7a2`: unit and policy tests (814), all 31 db tests on a fresh Postgres 18 volume, all 8 egress tests (denials logged by Squid), compose policy, import contracts; `make security` clean for semgrep, gitleaks, Trivy config, hadolint and shellcheck; `make security-images` passes (bot, migrate, postgres: 0 fixable HIGH/CRITICAL). Open: OSV-Scanner fails on `filelock` 3.32.7 (fix 4.2.1 is blocked by `litellm` requiring <4; owner decision). Added 2026-11-13: host monitoring installed with `infra/host/install_host.sh` (Falco 0.45.2, audit rules, AIDE, timers, alerter running offline); `check_host.sh` passes except disk encryption (accepted), text-mode boot (owner decision) and the heartbeat (Telegram stage); `make simulate-1` 8 of 8 PASS (rules at `81d26fa`; rerun after the pinned exceptions in `328a829`). Restore test 2026-11-13: RESTORE OK (20 tables match) from the nightly dump. Missing: nmap from the Mac; heartbeat (Telegram stage); OSV `filelock` owner decision; disk encryption skipped by owner decision (accepted risk, will show as FAIL). | |
| gate-2: Secure ingest and vault | | | | | | NOT PASSED. Verified: the Intake Gateway now runs on every parser job (2026-11-12); end-to-end fake pipeline on Postgres; import contracts; the parser, worker and fetcher images build and import (2026-11-13; before that the parser and worker images could not start). Missing: `clamav` no-network test, parser no-network runtime test, promptfoo on real models, `make guard-eval` (needs the injection model). | |
| gate-2b: Knowledge index and Ask | | | | | | NOT PASSED. Verified: RAG db tests. Missing: poisoned-note tests on the server, `make rag-eval` with real models. | |
| gate-2c: Library | | | | | | NOT PASSED. `make gate-2c` and `make simulate-2c` wired on 2026-11-14 (see "Gate 2c" below); not yet run on the TUF. Waiting on the internet stage: Telegram messages, real models (summaries, book evals), pack downloads; and the owner's real-material check. | |
| gate-3: Briefing, practice, exam alerts | | | | | | NOT PASSED. Not wired yet; needs the owner's 50-MCQ check. | |
| gate-4: Web app v1 | | | | | | NOT PASSED. API fails closed since 2026-11-12; web pages still show placeholder data; no Playwright, ZAP or axe suite yet. | |
| gate-5: Planner, progress, reliability | | | | | | NOT PASSED. Logic only; no tables or jobs yet. | |
| gate-6: Voice Coach and English | | | | | | NOT PASSED. Not started. | |
| gate-7: Understanding and World | | | | | | NOT PASSED. Not started. | |
| gate-8: Exams | | | | | | NOT PASSED. Not started. | |
| gate-9: Study smarter and live voice | | | | | | NOT PASSED. Not started. | |
| gate-10: Models admin and tech extras | | | | | | NOT PASSED. Not started. | |
| gate-11: Feedback and self-improvement | | | | | | NOT PASSED. Not started. | |
| gate-12: Jarvis (last gate) | | | | | | NOT PASSED. Not started. | |

## Gate 2c: Library

**What it checks** (`make gate-2c`, Phase 2c Task 11; SEC-15, SEC-20, SEC-43, SEC-44, SEC-54, SEC-57, and every earlier control again):

1. All of `gate-2b`, so gates 1, 2 and 2b run first, unchanged (a test keeps every gate-2b step inside gate-2c).
2. `lint-imports`; the library, intake, night-window, ops, parser, pipeline and eval tests, plus the exact `doc_id` scope test (`tests/rag/test_retrieve_scope.py`, which replaced the deleted `test_scoped_ask.py`).
3. The `db` tests of the library, intake, parser, RAG and evals, and the `slow` tests (Docling page budgets, pixel rebuild, the local run of the simulation).
4. `make rag-eval` (run by gate-2b) now includes the book evals: recall@5 of each book's own questions, scoped to that book, at least 0.80. When no real models or database are reachable it falls back to the mock evaluator and prints a `WAITING: internet stage` line: that run does not count.
5. `make simulate-2c` (`security/simulate/phase2c.sh`): hostile library files through a temp copy of the inbox intake and the parser's own job loop (Intake Gateway plus the sandboxed parse), inside the parser image with `--network none`, read-only root, no capabilities. Expected results:

   | File | Expected |
   |---|---|
   | `control.docx` (clean) | taken, gateway pass (the gateway does not refuse everything) |
   | `zip_bomb.docx` (250 MB of zeros) | taken, gateway reject: inflates past 200 MB |
   | `ratio_bomb.docx` (ratio about 1000) | taken, gateway reject: compression ratio over 100 |
   | `macro.docx` (`vbaProject.bin`) | taken, gateway quarantine, held 0400 |
   | `entity_bomb.epub` (billion laughs) | taken, gateway reject: `xml_entities` |
   | `playlist.mp4` (M3U) | inbox reject (unsupported type), owner told why |
   | `ftyp_playlist.mp4` (MP4 header, playlist inside) | taken, gateway reject: playlist marker |
   | `pdf_with_js.pdf` | taken, gateway quarantine, held 0400 |
   | `oversized.pdf` (sparse, 301 MB) | inbox reject (too large); written straight into originals: gateway reject at the size step |
   | symlinks in the inbox (file and folder) | skipped, left in place, target untouched; a link in originals: reject |
   | `big_300_pages.pdf` | taken, probe sees 300 pages and 10 chapters; parts 1-25 and 276-300 parse inside 120 s with page markers |

   Then it checks nothing escaped: the job spool is empty, results only, quarantine holds exactly the quarantined files, no media written, no links but the planted ones, no files outside the temp folders, the canary outside the inbox unchanged, and inside the container only `lo`, no route out, no DNS, read-only root. Antivirus answers "clean" in this run (ClamAV is checked by `simulate-2`). Any unexpected result exits non-zero.
6. The compose policy test, the Falco rule and name tests, and the gate wiring test (`tests/security/test_gate_2c.py`: no missing test files, parser timeout still 120 s).

**How to run it** (on the TUF, as the owner, not root, with the images built):

```bash
make gate-2c            # the whole chain, gates 1 to 2c
make simulate-2c        # only the attack simulation (needs the techradar-parser image)
make fixtures-2c        # writes tests/fixtures/library/big_300_pages.pdf (git-ignored)
```

`TR_SIM_PYTHON=.venv/bin/python bash security/simulate/phase2c.sh` runs the same simulation with the repo's Python on any machine (LOCAL MODE: no sandbox checks, no Docling parts). It is a development check only; never sign the gate on it.

**WAITING: internet stage** (printed by the gate; not passed until done):

- Telegram: the Ready message, quarantine notices and the two-step release in the real bot.
- Real models: chapter summaries, the book evals at recall@5 >= 0.80 and `rag-eval` in live mode (the report's `mode` must be `live`).
- Starter-pack downloads through Squid (owner adds the URLs, checked in a browser).

**Owner steps** (plan Task 11 step 2): drop one book you own and one lecture video into the Library folder on the Mac. Expected: the book's Ready message arrives and its chapter summaries appear in Obsidian; a reply to the Ready message answers from that book with page numbers; the video waits as `awaiting_transcription` until phase 6. The plan's "restart `worker-bulk` after 3 parts, no part processed twice" check runs against the real stack only after the owner approves it; until then it is covered by the `db` tests in `tests/library/test_jobs.py` (resume after restart). Sign the row above only when every item here has passed.
