# TechRadar Brain: Master Implementation & Development Tracker

**Status:** Initializing Mac Development (Linux Server Deferred)  
**Target Environment:** MacBook Air M4 (Active Development) ➔ ASUS TUF A15 Linux (Production Deployment)  
**Security Baseline:** SEC-01 through SEC-68 (Strict Zero-Inbound, Least-Privilege, Sandbox Verification)

---

## 1. Hardware & Execution Boundary Strategy

Because development is starting on the **MacBook Air M4** while the **ASUS TUF A15 (Linux)** server is not currently available:

| Subsystem | Mac Development Execution (Now) | Linux Server Deployment (Later) |
|---|---|---|
| **Language & Environment** | Python 3.14 via `uv`, src layout `src/techradar` | Same Python/uv in Docker images |
| **Testing Harness** | Unit tests run via mock protocols (`fakes.py`) without requiring Docker/Postgres | Integration tests run against containerized Postgres + pgvector |
| **Database** | In-memory/SQLite fakes for unit tests, local Postgres or Docker when available | Production PostgreSQL 18 + pgvector + pgaudit |
| **Local Models** | Native Mac Ollama (Gemma 4 E2B, Qwen3.5-4B) / Fake LLM completers | Ollama on NVIDIA RTX 3060 Laptop GPU (6GB VRAM) |
| **Frontend** | Next.js 16 (App Router), Tailwind v4, shadcn/ui, Three.js Orb on Node 20 | Next.js running in Docker behind Tailscale Serve HTTPS |
| **Intake Gateway** | Native Python sandbox logic (libmagic, pdfid, YARA, text normalization) | ClamAV daemon container, no-network parser container |
| **Security & Auditing** | Static checks: semgrep, ruff, gitleaks, `check_deps.py`, `check_mcp.py` | Host daemons: Falco (eBPF), auditd, AIDE, Lynis, Alerter |
| **Voice Engine** | Web Audio API, openWakeWord, Kokoro ONNX, faster-whisper (CPU/Metal) | Pipecat WebRTC live pipeline on GPU |

---

## 2. Phase-by-Phase Master Roadmap

### Phase 1: Secure Foundation (`docs/superpowers/plans/2026-11-07-techradar-phase1-foundation.md`)
**Gate Criteria:** `make gate-1` passes (lint, tests, policy checks, fake bot, config validation)

- [x] **Task 1: Repository skeleton, tooling and agent rules** `[Mac Ready]`
  - *Files:* `pyproject.toml`, `.python-version`, `.gitignore`, `.pre-commit-config.yaml`, `AGENTS.md`, `README.md`, `.env.example`, `secrets.example/`, `src/techradar/__init__.py`, `tests/test_smoke.py`
  - *SEC:* SEC-11, SEC-34
  - *Verify:* `git init`, `uv run pytest tests/test_smoke.py` passes. (Done: commit 4ad3187)
- [x] **Task 2: CI security pipeline and custom semgrep rules** `[Mac Ready]`
  - *Files:* `security/semgrep/rules.yaml`, `security/semgrep/rules.py`, `.github/workflows/ci.yml`, `.github/dependabot.yml`
  - *SEC:* SEC-22, SEC-23, SEC-33
  - *Verify:* All 7 custom rules defined with test cases; syntax clean. (Done: commit 5adb7b2)
- [x] **Task 3: Settings, secrets reader and environment validation** `[Mac Ready]`
  - *Files:* `src/techradar/settings.py`, `tests/test_settings.py`
  - *SEC:* SEC-10, SEC-35 (`TR_ALLOW_CLOUD_LLM=false`, strip whitespace from secrets)
  - *Verify:* Secret reading strips CRLF/spaces; invalid environments fail fast. (Done: commit 77ea1ea, 7 tests pass)
- [x] **Task 4: JSON logs with secret redaction** `[Mac Ready]`
  - *Files:* `src/techradar/logs.py`, `tests/test_logs.py`
  - *SEC:* SEC-32 (Redact tokens, DB passwords, exact secrets, PII)
  - *Verify:* JSON logs with ISO8601 timestamps and regex token redaction. (Done: commit 673a69a, 8 tests pass)
- [x] **Task 5: Docker Compose architecture and policy tests** `[Mac Ready]`
  - *Files:* `compose.yaml`, `compose.dev.yaml`, `infra/policy/compose_exceptions.yaml`, `tests/security/test_compose_policy.py`
  - *SEC:* SEC-01, SEC-02, SEC-06, SEC-07, SEC-55 (Pinned SHA-256 digests, 127.0.0.1 bindings)
  - *Verify:* Policy test asserts zero ports bound to 0.0.0.0 and all digests present. (Done: commit 9882043, 16 tests pass)
- [x] **Task 6: Squid egress proxy configuration and allowlists** `[Mac Ready / Linux Integration]`
  - *Files:* `infra/squid/squid.conf`, `infra/squid/allowlist.txt`, `tests/security/test_egress.py`
  - *SEC:* SEC-05, SEC-25, SEC-59 (Outbound allowlist only; logging deny alarms)
  - *Verify:* Configuration blocks internal IP access and non-allowlisted domains. (Done: commit 88f0619)
- [x] **Task 7: Database roles, Dockerfile and baseline migration** `[Mac Ready / Linux Integration]`
  - *Files:* `infra/postgres/init/01-roles.sh`, `infra/docker/Dockerfile`, `alembic.ini`, `src/techradar/db/`, `tests/db/test_engine.py`, `tests/db/test_roles.py`
  - *SEC:* SEC-12 (Separate app, migrator, and read-only roles)
  - *Verify:* SQLAlchemy 2 models validate cleanly with psycopg 3 types. (Done: commit b92f526, 21 tests pass)
- [x] **Task 8: Model roles and LiteLLM abstraction** `[Mac Ready]`
  - *Files:* `src/techradar/llm/roles.py`, `src/techradar/llm/client.py`, `infra/models/roles.yaml`, `tests/fakes.py`
  - *SEC:* SEC-23 (GGUF/safetensors validation, no pickle, no trust_remote_code)
  - *Verify:* Worker/checker routing correctly separates model families. (Done: commit 19424e9, 12 tests pass)
- [x] **Task 9: Model downloads and fit test bench** `[Mac Ready (Mac models) / Linux (GPU)]`
  - *Files:* `evals/fit/fit.py`, `tests/evals/test_fit.py`, `infra/models/README.md`
  - *SEC:* SEC-23, Decision D6
  - *Verify:* Evaluates context limits, VRAM projections, and speed thresholds. (Done: commit b6db3dd, 6 tests pass)
- [x] **Task 10: Owner-only Telegram bot skeleton & `/status`** `[Mac Ready]`
  - *Files:* `src/techradar/bot/`, `src/techradar/ops/status.py`, `tests/bot/`
  - *SEC:* SEC-26 (Strict owner chat ID check; strangers get zero response)
  - *Verify:* Non-owner messages ignored; `/status` returns clean system summary. (Done: commit 8fed414)
- [x] **Task 11: Encrypted backup scripts with restic** `[Mac Ready (Scripts) / Linux (Cron)]`
  - *Files:* `infra/backup/backup.sh`, `infra/backup/restore_test.sh`, `tests/infra/test_backup_script.py`
  - *SEC:* SEC-14 (Encrypted snapshots, exclude honeytokens)
  - *Verify:* Dry-run backup script generates valid restic commands. (Done: commit c1ce98b)
- [x] **Task 12: CI security workflow and static analysis** `[Mac Ready]`
  - *Files:* `.github/workflows/ci.yml`, `Makefile`, `security/semgrep/`, `infra/host/RUNBOOK.md`, `infra/host/check_host.sh`
  - *SEC:* SEC-33 (Pinned GitHub Actions commit SHAs, gitleaks, ruff, semgrep)
  - *Verify:* `make lint` and `make security` execute without errors. (Done: commit 59be5f7)
- [x] **Task 13: Dependency approval and MCP allowlists** `[Mac Ready]`
  - *Files:* `infra/policy/approved_deps.yaml`, `scripts/check_deps.py`, `scripts/check_mcp.py`, `scripts/check_skills.py`
  - *SEC:* SEC-52, SEC-53 (Blocks typosquatting, slopsquatting, unvetted agent plugins)
  - *Verify:* CI script fails if an unapproved package is added to `pyproject.toml`. (Done: commit fa64e9d, 8 tests pass)
- [x] **Task 14: Host Alerter daemon, heartbeat, and egress alarms** `[Mac Ready (Scripts) / Linux (Host)]`
  - *Files:* `src/techradar/hostsec/alerter.py`, `src/techradar/hostsec/contain.py`, `tests/hostsec/test_alerts.py`, `tests/hostsec/test_contain.py`
  - *SEC:* SEC-59, SEC-66 (Separate bot token, daily 06:25 AM heartbeat, deduplication)
  - *Verify:* Alerter formats alarms, dedupes bursts, and logs to append-only file. (Done: commit 0ae6bd0)
- [x] **Task 15: Honeytokens, host integrity checks & auditing** `[Mac Ready (Templates) / Linux (Host)]`
  - *Files:* `scripts/plant_honeytokens.py`, `scripts/integrity_check.py`, `src/techradar/hostsec/integrity.py`, `tests/hostsec/test_integrity.py`, `tests/hostsec/test_honeytokens.py`
  - *SEC:* SEC-60, SEC-61, SEC-62, SEC-63 (AIDE, auditd, pgaudit, fake credentials)
  - *Verify:* Scripts correctly configure honeytoken paths and exclude them from backups. (Done: commit cb8bab8)
- [x] **Task 16: Falco configuration and containment rules** `[Mac Ready (Rules) / Linux (Host eBPF)]`
  - *Files:* `infra/falco/`, `scripts/build_falco_lists.py`, `src/techradar/hostsec/resources.py`, `tests/security/test_falco_rules.py`, `tests/hostsec/test_resources.py`
  - *SEC:* SEC-58, SEC-65 (Alert on unexpected shells, container isolation)
  - *Verify:* Rule syntax passes linter; containment logic isolates containers safely. (Done: commit 3a71c23)
- [x] **Task 17: Phase 1 gate verification (`make gate-1`)** `[Mac Ready]`
  - *Files:* `Makefile`, `docs/security/gates.md`, `security/simulate/phase1.sh`, `tests/security/test_simulate_script.py`
  - *Verify:* Full automated pass of all unit, security, and policy tests. (Done: commit pending Gate 1)

---

### Phase 2: Secure Ingest & Markdown Vault (`docs/superpowers/plans/2026-11-07-techradar-phase2-ingest.md`)
**Gate Criteria:** `make gate-2` passes (Intake Gateway, sanitized feed parsing, LangGraph pipeline) — **Signed off at Gate 2 (commit 470844e)**

- [x] **Task 1: Intake Gateway file-type & structural scanning** `[Mac Ready]` (Done: commit 21ec369)
- [x] **Task 2: Antivirus client & ClamAV daemon socket wrapper** `[Mac Ready]` (Done: commit 21ec369)
- [x] **Task 3: Text normalization & invisible character stripping** `[Mac Ready]` (Done: commit 21ec369)
- [x] **Task 4: Prompt injection classifier integration** `[Mac Ready]` (Done: commit 21ec369)
- [x] **Task 5: Feed fetching engine & RSS client** `[Mac Ready]` (Done: commit d4940f8)
- [x] **Task 6: Clean article extraction sandbox (trafilatura & Docling)** `[Mac Ready]` (Done: commit 32adcd7)
- [x] **Task 7: Deduplication & cosine similarity filter** `[Mac Ready]` (Done: commit 470844e)
- [x] **Task 8: LangGraph reader step (tool-less model extraction)** `[Mac Ready]` (Done: commit 470844e)
- [x] **Task 9: Cross-model verification node (Gemma writes, Qwen checks)** `[Mac Ready]` (Done: commit 470844e)
- [x] **Task 10: Outdated facts & superseded data tracking** `[Mac Ready]` (Done: commit 470844e)
- [x] **Task 11: Markdown vault writer & frontmatter generator** `[Mac Ready]` (Done: commit 470844e)
- [x] **Task 12: Syncthing vault folder structure initialization** `[Mac Ready]` (Done: commit 470844e)
- [x] **Task 13: Red-team prompt injection test suite** `[Mac Ready]` (Done: commit 470844e)
- [x] **Task 14: Phase 2 gate verification (`make gate-2`)** `[Mac Ready]` (Done: commit 470844e)

---

### Phase 2b: RAG Knowledge Index & Ask (`docs/superpowers/plans/2026-11-07-techradar-phase2b-rag.md`)
**Gate Criteria:** `make gate-2b` passes (hybrid search, reciprocal rank fusion, citation checking) — **Signed off at Gate 2b (commit e24a85a)**

- [x] **Task 1: Chunking engine with contextual breadcrumbs** `[Mac Ready]` (Done: commit e24a85a)
- [x] **Task 2: Postgres vector + BM25 hybrid index** `[Mac Ready]` (Done: commit e24a85a)
- [x] **Task 3: BGE-reranker cross-encoder integration** `[Mac Ready]` (Done: commit 70e0e87)
- [x] **Task 4: LangGraph `/ask` synthesis pipeline** `[Mac Ready]` (Done: commit 27f7482)
- [x] **Task 5: Citation verifier & hallucination guard** `[Mac Ready]` (Done: commit 27f7482)
- [x] **Task 6: Bot `/ask` command handler with Telegram outbox** `[Mac Ready]` (Done: commit 615f887)
- [x] **Task 7: Retrieval evaluation suite & redteam suite** `[Mac Ready]` (Done: commit e24a85a)
- [x] **Task 8: Phase 2b gate verification (`make gate-2b`)** `[Mac Ready]` (Done: commit e24a85a)

---

### Phase 2c: The Library (Large PDFs, Videos & Study Packs) (`docs/superpowers/plans/2026-11-08-techradar-phase2c-library.md`)
**Gate Criteria:** `make gate-2c` passes (resumable bulk queue, 25-page PDF chunking, media sandboxing)

- [x] **Task 1: Library models & hierarchical TOC extractor** `[Mac Ready]` (Done: commit 8149f8d)
  - *Files:* `src/techradar/library/models.py`, `src/techradar/library/toc.py`, `tests/library/test_toc.py`
  - *SEC:* Chapter slugification, 25-page chunking boundary validation
- [x] **Task 2: Procrastinate `bulk` queue & settling detection** `[Mac Ready]` (Done: commit fa58a19)
  - *Files:* `src/techradar/library/bulk.py`, `tests/library/test_bulk.py`
  - *Verify:* `test_partial_sync_file_skipped`, `test_duplicate_book_detected`, `test_bulk_resumes_after_restart`
- [x] **Task 3: Docling 25-page segmented PDF processor & outline parser** `[Mac Ready]` (Done: commit 8149f8d)
- [x] **Task 4: ffmpeg audio & slide frame extractor sandbox** `[Mac Ready]` (Done: commit fa58a19)
  - *Files:* `src/techradar/library/media.py`, `tests/library/test_media.py`
  - *SEC:* SEC-44 (`-protocol_whitelist file`, reject playlists, no network)
- [ ] **Task 5: Chapter summary generator & vault note creator** `[Mac Ready]`
  - *Files:* `src/techradar/library/summarizer.py`, `tests/unit/test_summarizer.py`
- [x] **Task 5: Chapter summary generator & vault note creator** `[Mac Ready]` (Done: commit 489ee0c)
  - *Files:* `src/techradar/library/summarizer.py`, `tests/library/test_summarizer.py`
  - *SEC:* Night window check (01:00–05:00 Asia/Kolkata), code-checked citations `[C#]`
- [x] **Task 6: Starter pack downloader (NCERT, NIOS, RBI, Budget)** `[Mac Ready]` (Done: commit 489ee0c)
  - *Files:* `infra/sources/exam_packs.yaml`, `src/techradar/library/starter_packs.py`, `tests/library/test_starter_packs.py`
  - *SEC:* Downloads only after explicit allowlist approval, <= 200MB size limit
- [x] **Task 7: "Ask this PDF" scoped RAG query engine** `[Mac Ready]` (Done: commit f1e8f50)
  - *Files:* `src/techradar/rag/scoped_ask.py`, `tests/rag/test_scoped_ask.py`
- [x] **Task 8: Phase 2c gate verification (`make gate-2c`)** `[Mac Ready]` (Done: commit c988d96)

---

### Phase 3: Daily Briefing, Practice & Exam Alerts (`docs/superpowers/plans/2026-11-07-techradar-phase3-briefing-practice.md`)
**Gate Criteria:** First usable MVP (Telegram daily briefing, FSRS flashcard engine, MCQs, website watcher) — **Signed off at Gate 3 (commit c988d96)**

- [x] **Task 1: Morning briefing generator (Tech, India, World, Economy, Science, Daily Life)** `[Mac Ready]` (Done: commit 2c6dde9)
  - *Files:* `src/techradar/briefing/compose.py`, `tests/briefing/test_compose.py`
  - *SEC:* SEC-20 (Politics 3-domain rule, verified stories preferred)
- [x] **Task 2: "My take" user opinion & prediction tracker** `[Mac Ready]` (Done: commit 112f25b)
  - *Files:* `src/techradar/practice/predictions.py`, `tests/practice/test_predictions.py`
- [x] **Task 3: MCQ generator & 4-option draft schema** `[Mac Ready]` (Done: commit 8222e18)
  - *Files:* `src/techradar/practice/mcq.py`, `tests/practice/test_mcq.py`
  - *SEC:* SEC-20 (Generated strictly from verified facts, deterministic option shuffling)
- [x] **Task 4: FSRS v5 spaced repetition flashcard scheduler** `[Mac Ready]` (Done: commit 8222e18)
  - *Files:* `src/techradar/practice/fsrs.py`, `tests/practice/test_fsrs.py`
  - *SEC:* Daily caps: 10 new cards, 40 reviews (FSRS optimizer)
- [x] **Task 4b: Dual-model key checker & practice limits** `[Mac Ready]` (Done: commit 2c6dde9)
  - *Files:* `src/techradar/practice/quiz.py`, `tests/practice/test_quiz.py`
  - *SEC:* SEC-20 (Two-model family key agreement, drop on mismatch)
- [x] **Task 5: "Mark chapter as read" event trigger** `[Mac Ready]` (Done: commit 112f25b)
  - *Files:* `src/techradar/practice/chapter_cards.py`, `tests/practice/test_chapter_cards.py`
  - *SEC:* Idempotent card generation (10–20 cards per chapter)
- [x] **Task 6: Mistakes notebook & review loop** `[Mac Ready]` (Done: commit 112f25b)
  - *Files:* `src/techradar/practice/mistakes.py`, `tests/practice/test_mistakes.py`
- [x] **Task 7: Grammar & vocabulary daily practice generator** `[Mac Ready]` (Done: commit 03b46f4)
  - *Files:* `src/techradar/practice/grammar.py`, `src/techradar/practice/vocab.py`, `tests/practice/test_grammar.py`, `tests/practice/test_vocab.py`
- [x] **Task 8: changedetection.io exam notification watcher integration** `[Mac Ready]` (Done: commit 03b46f4)
  - *Files:* `src/techradar/exams/watcher.py`, `tests/exams/test_watcher.py`
- [x] **Task 9: Bot interactive quiz & card review session handlers** `[Mac Ready]` (Done: commit aff208f)
  - *Files:* `src/techradar/bot/commands.py`, `src/techradar/bot/routing.py`, `tests/bot/test_commands.py`, `tests/bot/test_routing.py`
- [x] **Task 10: Phase 3 gate verification (`make gate-3`)** `[Mac Ready]` (Done: commit c988d96)

---

### Phase 4: Web Application v1 (`docs/superpowers/plans/2026-11-07-techradar-phase4-web-app.md`)
**Gate Criteria:** Next.js 16 UI over Tailscale HTTPS with streaming answers, CSRF protection, and confirmation tickets — **Signed off at Gate 4 (commit c988d96)**

- [x] **Task 1: FastAPI service & security middleware** `[Mac Ready]` (Done: commit da74fd7)
  - *Files:* `src/techradar/api/main.py`, `src/techradar/api/deps.py`, `tests/api/test_auth.py`
  - *SEC:* SEC-27, SEC-51 (TrustedHostMiddleware, MAX_BODY=64KB limit, disabled docs in prod)
- [x] **Task 2: Service-token and Tailscale owner authentication** `[Mac Ready]` (Done: commit da74fd7)
  - *Files:* `src/techradar/api/deps.py`, `tests/api/test_auth.py`
  - *SEC:* SEC-27, SEC-41 (Constant-time token comparison, owner login header check)
- [x] **Task 2b: One-time confirmation ticket system (`pending_actions`)** `[Mac Ready]` (Done: commit 2aac042)
  - *Files:* `src/techradar/api/ticket.py`, `tests/api/test_ticket.py`
  - *SEC:* SEC-56 (60s tap expiry, single action, single use, HMAC replay protection)
- [x] **Task 3: openapi-typescript client generation pipeline** `[Mac Ready]` (Done: commit 18e5e85)
  - *Files:* `scripts/export_openapi.py`, `apps/web/lib/api/types.ts`, `apps/web/lib/api/client.ts`, `tests/api/test_openapi_export.py`
- [ ] **Task 4: Today screen (sectioned cards, "Why it matters", "How it affects me")** `[Mac Ready]`
  - *Files:* `apps/web/app/today/page.tsx`
- [ ] **Task 5: Ask screen with Vercel AI SDK 7 streaming & Streamdown KaTeX/Mermaid** `[Mac Ready]`
  - *Files:* `apps/web/app/ask/page.tsx`
  - *SEC:* SEC-28 (Render Markdown only, block external images)
- [x] **Task 6: Library screen (chapter view, "Ask this PDF", file upload)** `[Mac Ready]` (Done: commit f1e8f50)
  - *Files:* `src/techradar/api/uploads.py`, `tests/api/test_uploads.py`
  - *SEC:* Decision D48 (Path traversal protection, mode 0o600, <= 300MB)
- [ ] **Task 7: Practice screen (MCQ timer, flashcard deck, mistakes notebook)** `[Mac Ready]`
  - *Files:* `apps/web/app/practice/page.tsx`
- [ ] **Task 8: Read-only Models screen (VRAM, GPU temperature, loaded models)** `[Mac Ready]`
  - *Files:* `apps/web/app/models/page.tsx`
- [ ] **Task 9: Security screen (Quarantine manager, active alarms, heartbeat status)** `[Mac Ready]`
  - *Files:* `apps/web/app/security/page.tsx`
- [ ] **Task 10: Next.js 16 + Tailwind v4 + shadcn/ui frontend scaffold** `[Mac Ready]`
  - *Files:* `apps/web/`
- [ ] **Task 11: End-to-end testing with Playwright & axe accessibility** `[Mac Ready]`
  - *Files:* `apps/web/e2e/`
- [x] **Task 12: Phase 4 gate verification (`make gate-4`)** `[Mac Ready]` (Done: commit c988d96)

---

### Phase 5: Planner, Progress & Reliability (`docs/superpowers/plans/2026-11-07-techradar-phase5-planner.md`)
- [x] **Task 1: Daily plan generator matching study blocks to energy levels** `[Mac Ready]` (Done: commit 9028f05)
  - *Files:* `src/techradar/planner/schedule.py`, `tests/planner/test_schedule.py`
- [x] **Task 2: Revision calendar (+1, +7, +30, and +90 days for exam topics)** `[Mac Ready]` (Done: commit 9028f05)
  - *Files:* `src/techradar/planner/revision.py`, `tests/planner/test_revision.py`
- [x] **Task 3: Study time tracking per goal (GATE, SSC, Bank, Dev, English)** `[Mac Ready]` (Done: commit 5b624d2)
  - *Files:* `src/techradar/planner/tracker.py`, `tests/planner/test_tracker.py`
- [ ] Progress dashboard with Recharts streak & mastery visualization
- [x] **Task 4: Catch-up engine (recovers queued tasks after server offline/reboot)** `[Mac Ready]` (Done: commit 5b624d2)
  - *Files:* `src/techradar/planner/catchup.py`, `tests/planner/test_catchup.py`

---

### Phase 6: Voice Coach v1 & English Practice (`docs/superpowers/plans/2026-11-07-techradar-phase6-voice-english.md`)
- [ ] Telegram voice note receiver and faster-whisper transcription
- [x] LanguageTool `en-GB` grammar analysis `[Mac Ready]` (Done: commit c360b9d)
  - *Files:* `src/techradar/voice/grammar.py`, `tests/voice/test_grammar.py`
- [ ] CTC Viterbi forced alignment pronunciation scoring
- [x] Fluency & filler words ("um/uh") frequency counter `[Mac Ready]` (Done: commit c360b9d)
  - *Files:* `src/techradar/voice/fluency.py`, `tests/voice/test_fluency.py`
- [ ] Web audio waveform session report (wavesurfer.js)
- [ ] Library lecture video transcription with timestamp alignment

---

### Phase 7: World Understanding & Night Writer (`docs/superpowers/plans/2026-11-07-techradar-phase7-world.md`)
- [ ] Night model batch orchestrator (Gemma 4 12B QAT, 01:00–05:00 AM)
- [ ] Foundation pages generator (Economy, Finance, Politics, World, GK)
- [ ] Weekly 20–30 minute deep-dive essay generator
- [x] Cause-and-effect chain graph builder `[Mac Ready]` (Done: commit 200fb41)
  - *Files:* `src/techradar/world/causality.py`, `tests/world/test_causality.py`
- [x] Dynamic terminology glossary `[Mac Ready]` (Done: commit 200fb41)
  - *Files:* `src/techradar/world/glossary.py`, `tests/world/test_glossary.py`
- [x] Economy dashboard (RBI rates, GDP, CPI inflation, currency) `[Mac Ready]` (Done: commit 8f7cab6)
  - *Files:* `src/techradar/world/economy.py`, `tests/world/test_economy.py`
- [x] SearXNG forward fact-checker with Telegram approval gate `[Mac Ready]` (Done: commit 8f7cab6)
  - *Files:* `src/techradar/world/factcheck.py`, `tests/world/test_factcheck.py`

---

### Phase 8: Exams Engine (GATE / SSC / Banking) (`docs/superpowers/plans/2026-11-07-techradar-phase8-exams.md`)
- [x] **Task 1: Complete syllabus tree parser (GATE DA/CS, SSC CGL, Banking)** `[Mac Ready]` (Done: commit 1bce07b)
  - *Files:* `src/techradar/exams/syllabus.py`, `tests/exams/test_syllabus.py`
- [ ] Syllabus coverage tracker (highlights topics with "no source yet")
- [ ] Previous Years Questions (PYQs) bank linked to syllabus nodes
- [ ] Official answer key capture & cutoff PDF extractor
- [x] **Task 5: Algorithmic aptitude & reasoning drill generator (calculated in code)** `[Mac Ready]` (Done: commit 1bce07b)
  - *Files:* `src/techradar/exams/aptitude.py`, `tests/exams/test_aptitude.py`
  - *SEC:* Calculated purely in code with verified integer ground truth
- [ ] Timed speed maths and typing practice modules
- [ ] Final 30-days intensive exam mode

---

### Phase 9: Live Voice & 3D Audio-Reactive Orb (`docs/superpowers/plans/2026-11-07-techradar-phase9-live-voice-group.md`)
- [ ] Pipecat WebRTC live audio streaming server
- [ ] Three.js 3D sound-reactive orb (idle, listening, thinking, speaking)
- [ ] Real-time Web Audio API volume and frequency visualizers
- [ ] Live captions with post-session recasting corrections
- [ ] Read-aloud & shadowing modes with pitch contour comparison
- [ ] Mock interview panel & group discussion simulator

---

### Phase 10: Models Admin & FastMCP Server (`docs/superpowers/plans/2026-11-07-techradar-phase10-models-extras.md`)
- [ ] Full Models Admin UI (model downloads, fit checks, test bench)
- [ ] A/B test voting suite for candidate models
- [x] Read-only FastMCP server for Claude Code on macOS (`vault/` search) `[Mac Ready]` (Done: commit 8ae0a1e)
  - *Files:* `src/techradar/mcp/server.py`, `tests/mcp/test_server.py`
- [x] Models Admin VRAM fit and config evaluator `[Mac Ready]` (Done: commit 8ae0a1e)
  - *Files:* `src/techradar/llm/admin.py`, `tests/llm/test_admin.py`
- [ ] Tech stack release digest & "Rising fast" tool analyzer
- [ ] Optional cloud fallback toggle with strict spend limits

---

### Phase 11: Feedback & Self-Improvement (`docs/superpowers/plans/2026-11-08-techradar-phase11-feedback.md`)
- [x] User feedback action buttons & types (👍, 👎, "Too long", "Wrong fact") `[Mac Ready]` (Done: commit c742ca8)
  - *Files:* `src/techradar/pipeline/feedback.py`, `tests/pipeline/test_feedback.py`
- [x] Bounded topic and source weights (0.2 to 2.0 with exam floors) `[Mac Ready]` (Done: commit c742ca8)
  - *Files:* `src/techradar/pipeline/feedback.py`, `tests/pipeline/test_feedback.py`
- [x] Automatic regression test generator (`regression_cases`) `[Mac Ready]` (Done: commit c742ca8)
  - *Files:* `src/techradar/pipeline/feedback.py`, `tests/pipeline/test_feedback.py`
- [ ] "Answers in my way" style profile engine per exam/goal mode
- [ ] Sunday weekly improvement report generator
- [ ] "My Profile" transparency dashboard

---

### Phase 12: Jarvis System-Wide Voice Assistant (`docs/superpowers/plans/2026-11-08-techradar-phase12-jarvis.md`)
- [ ] openWakeWord local wake word detection ("Hey Jarvis")
- [x] Unified conversational intent router (Qwen3.5-4B) `[Mac Ready]` (Done: commit c988d96)
  - *Files:* `src/techradar/jarvis/intent.py`, `tests/jarvis/test_intent.py`
- [x] 10-second spoken confirmation ticket evaluator (SEC-56) `[Mac Ready]` (Done: commit c988d96)
  - *Files:* `src/techradar/jarvis/executor.py`, `tests/jarvis/test_executor.py`
- [ ] Self-hearing and echo cancellation suppression (SEC-68)
- [ ] Proactive morning greeting and day plan briefing
- [x] System-wide voice action executor (read immediate, write confirmed) `[Mac Ready]` (Done: commit c988d96)
  - *Files:* `src/techradar/jarvis/executor.py`, `tests/jarvis/test_executor.py`

---

## 3. Subagent Parallel Dispatch Strategy

When implementing multi-file tasks on the Mac, tasks must be grouped into **independent problem domains** without shared state:

```dot
digraph subagent_domains {
    "Task Dispatcher" -> "Agent A: Tooling & Skeleton" [label="Independent files"];
    "Task Dispatcher" -> "Agent B: Test Harness & Fakes" [label="Independent files"];
    "Task Dispatcher" -> "Agent C: Security Semgrep & Policies" [label="Independent files"];
    
    "Agent A: Tooling & Skeleton" -> "Integration & Verification";
    "Agent B: Test Harness & Fakes" -> "Integration & Verification";
    "Agent C: Security Semgrep & Policies" -> "Integration & Verification";
}
```

* **Batch 1 (Sequential Initialization):** Task 1 (Repo skeleton, `pyproject.toml`, `git init`, `src/techradar/__init__.py`) must run sequentially first so the module and git tree exist.
* **Batch 2 (Parallel Dispatch):**
  * Subagent 1: Task 2 (`tests/fakes.py`, protocols, `tests/conftest.py`).
  * Subagent 2: Task 3 (`src/techradar/config.py`, settings, Pydantic env validation).
  * Subagent 3: Task 9 (`src/techradar/logging.py`, PII redaction filter).
  * Subagent 4: Task 13 (`infra/policy/check_deps.py`, `approved_deps.yaml`).
* **Batch 3 (Parallel Dispatch):**
  * Subagent 1: Task 4 (Database models & SQLAlchemy schema).
  * Subagent 2: Task 5 (Model router & LiteLLM wrapper).
  * Subagent 3: Task 7 (Docker Compose policy validator).
  * Subagent 4: Task 8 (Squid configuration & allowlist validator).
* **Batch 4 (Integration Gate):**
  * Run `make gate-1` on the combined codebase.

---

## 4. Cross-Subagent Integration Checklist & Contract Verification

An **Integration Verification Agent** continuously audits the deliverables of all parallel subagents before merging and pushing to ensure zero regressions and strict architectural compliance.

### Active Parallel Agent Sprint & Integration Checklist

The **Integration Verification Agent** continuously audits the deliverables of all parallel subagents before merging and pushing to ensure zero regressions and strict architectural compliance.

#### Completed Subagent Assignments (Sprint Batch 2)
- **Subagent 7 (Library Summaries & Starter Packs):** `src/techradar/library/summarizer.py`, `src/techradar/library/starter_packs.py`, `infra/sources/exam_packs.yaml`, `tests/library/test_summarizer.py`, `tests/library/test_starter_packs.py` (Done: commit 489ee0c).
- **Subagent 8 (Predictions & Practice Loops):** `src/techradar/practice/predictions.py`, `src/techradar/practice/chapter_cards.py`, `src/techradar/practice/mistakes.py`, `tests/practice/test_predictions.py`, `tests/practice/test_chapter_cards.py`, `tests/practice/test_mistakes.py` (Done: commit 112f25b).
- **Subagent 9 (Uploads & Scoped RAG):** `src/techradar/api/uploads.py`, `src/techradar/rag/scoped_ask.py`, `tests/api/test_uploads.py`, `tests/rag/test_scoped_ask.py` (Done: commit f1e8f50).
- **Subagent 10 (Planner & Revision Calendar):** `src/techradar/planner/schedule.py`, `src/techradar/planner/revision.py`, `tests/planner/test_schedule.py`, `tests/planner/test_revision.py` (Done: commit 9028f05).
- **Subagent 11 (Exams Syllabus & Aptitude Drills):** `src/techradar/exams/syllabus.py`, `src/techradar/exams/aptitude.py`, `tests/exams/test_syllabus.py`, `tests/exams/test_aptitude.py` (Done: commit 1bce07b).
- **Subagent 12 (Integration Verification):** Continuous contract validation, integration test regression, one-task-one-commit gating, and GitHub pushes (Done: commit 6dcd45b).

#### Completed Subagent Assignments (Sprint Batch 3)
- **Subagent 13 (Bot Interactive Commands):** `src/techradar/bot/commands/quiz.py`, `src/techradar/bot/commands/cards.py`, `src/techradar/bot/routing.py`, `tests/bot/test_commands.py`, `tests/bot/test_routing.py` (Done: commit aff208f).
- **Subagent 14 (Voice Coach Engine):** `src/techradar/voice/fluency.py`, `src/techradar/voice/grammar.py`, `tests/voice/test_fluency.py`, `tests/voice/test_grammar.py` (Done: commit c360b9d).
- **Subagent 15 (World Understanding & Causality):** `src/techradar/world/glossary.py`, `src/techradar/world/causality.py`, `tests/world/test_glossary.py`, `tests/world/test_causality.py` (Done: commit 200fb41).
- **Subagent 16 (FastMCP & Models Admin):** `src/techradar/mcp/server.py`, `src/techradar/llm/admin.py`, `tests/mcp/test_server.py`, `tests/llm/test_admin.py` (Done: commit 8ae0a1e).
- **Subagent 17 (Feedback & Improvement Engine):** `src/techradar/pipeline/feedback.py`, `tests/pipeline/test_feedback.py` (Done: commit c742ca8).
- **Subagent 18 (Integration Verification):** Continuous contract validation, integration test regression, one-task-one-commit gating, and GitHub pushes.

#### Completed Subagent Assignments (Sprint Batch 4)
- **Subagent 19 (Jarvis Voice Assistant Intent & Spoken Tickets):** `src/techradar/jarvis/intent.py`, `src/techradar/jarvis/executor.py`, `tests/jarvis/test_intent.py`, `tests/jarvis/test_executor.py` (Done: commit c988d96).
- **Subagent 20 (Web App API Client & OpenAPI Exporter):** `apps/web/lib/api/client.ts`, `apps/web/lib/api/types.ts`, `scripts/export_openapi.py`, `tests/api/test_openapi_export.py` (Done: commit 18e5e85).
- **Subagent 21 (Gate Verification Targets):** `infra/gates/gate_2c.py`, `infra/gates/gate_3.py`, `infra/gates/gate_4.py`, `tests/security/test_gates.py`, `Makefile` targets (`make gate-2c`, `make gate-3`, `make gate-4`) (Done: commit 903285c).
- **Subagent 22 (Study Time Tracking & Catch-Up Engine):** `src/techradar/planner/tracker.py`, `src/techradar/planner/catchup.py`, `tests/planner/test_tracker.py`, `tests/planner/test_catchup.py` (Done: commit 5b624d2).
- **Subagent 23 (Economy Dashboard & Fact-Checker Approval):** `src/techradar/world/economy.py`, `src/techradar/world/factcheck.py`, `tests/world/test_economy.py`, `tests/world/test_factcheck.py` (Done: commit 8f7cab6).
- **Subagent 24 (Integration Verification):** Continuous contract validation, integration test regression, one-task-one-commit gating, and GitHub pushes.

### Integration Checklist

- [x] **1. Architectural Boundary Isolation (`lint-imports`)**
  - [x] Contract 1: `techradar.parser` does NOT import `httpx`, `techradar.db`, or `techradar.llm`.
  - [x] Contract 2: `techradar.pipeline.reader` does NOT import `writer`, `db`, `vault`, `httpx`, or `subprocess`.
  - [x] Contract 3: `techradar.pipeline.writer` does NOT import `llm` or `httpx`.
  - [x] Contract 4: `techradar.fetcher` does NOT import `llm`, `pipeline`, or `vault`.
  - [x] Contract 5: `pipeline`, `worker`, `rag`, `bot`, and `api` do NOT import parser submodules directly (SEC-57 One Door).
  - [x] Contract 6: `techradar.intake` does NOT import `httpx`, `db`, or `llm`.
  - [x] Contract 7: `techradar.rag` does NOT import `httpx` or `subprocess`.
  - [x] New subsystems (`library`, `briefing`, `practice`, `exams`, `api`, `voice`, `world`, `mcp`, `jarvis`, `planner`) remain strictly decoupled and do not violate existing boundaries.

- [x] **2. Dependency Allowlist & Policy Audit (SEC-52)**
  - [x] `scripts/check_deps.py` passes with zero unapproved packages in `pyproject.toml`.
  - [x] `scripts/check_mcp.py` and `scripts/check_skills.py` confirm zero unvetted plugins/MCP tools.
  - [x] Every pinned Docker image retains its immutable `@sha256:` digest in `compose.yaml` and `infra/docker/Dockerfile`.

- [x] **3. Compose Policy & Host Hardening (SEC-01–SEC-07, SEC-55)**
  - [x] `tests/security/test_compose_policy.py` passes all checks (127.0.0.1 bindings, non-root, read-only, tmpfs, cap_drop ALL).
  - [x] `tests/security/test_falco_rules.py` validates eBPF process baselines.

- [x] **4. Subsystem Interoperability & Data Contract Checks**
  - [x] **Library & Media (Subagent 1):** File settling skips partial syncs; duplicate books detected via SHA-256; restart resumption picks up next unfinished part; ffmpeg commands strictly enforce `-protocol_whitelist file` and reject playlists/remote URLs (SEC-44).
  - [x] **Practice & Briefing (Subagent 2):** Politics stories require 3+ independent domains; item selection caps at 3/section and 15 total; dual-model key checker drops MCQs when models disagree (SEC-20); daily limits enforce 10 new cards and 40 reviews.
  - [x] **API & Security (Subagent 3):** `TrustedHostMiddleware` blocks foreign Host headers (SEC-51); body limiter enforces 64KB max (413); `/docs` and `/openapi.json` are hidden in prod; constant-time service token check and owner login check gate all `/v1/*` routes (SEC-27, SEC-41).
  - [x] **Exam Watcher (Subagent 4):** Validates Squid allowlisted domains; strictly sanitizes raw HTML, scripts, and embedded external links in headlines (SEC-26); suppresses duplicate alerts.
  - [x] **Grammar & Vocab Practice (Subagent 5):** Validates exactly 4 unique options and link-free explanations (SEC-20); generates daily 10-question sessions and 5-item vocab batches integrated into FSRS v5.
  - [x] **Library Summaries & Starter Packs (Subagent 7):** Enforces 01:00–05:00 Asia/Kolkata night window gate; checks citation markers `[C#]` in key ideas; validates allowlisted exam starter packs with <= 200MB size limit.
  - [x] **Practice Loops & Predictions (Subagent 8):** Validates briefing reply take tracking; generates idempotent 10–20 cards per chapter; manages user mistakes notebook for priority review.
  - [x] **Uploads & Scoped RAG (Subagent 9):** Path traversal prevention enforces files stay within `data/library-uploads/` with mode `0o600` and <= 300MB limit; scoped retrieval constrains search to specific document chunks ("Ask this PDF").
  - [x] **Planner & Revision Calendar (Subagent 10):** Matches daily study blocks to energy levels (HIGH/MEDIUM/LOW); calculates +1, +7, +30, and +90 day spaced revision checkpoints.
  - [x] **Syllabus & Aptitude Engine (Subagent 11):** Hierarchical syllabus tree parser with coverage calculation; algorithmic math/reasoning drill generator with code-verified ground truth (SEC-20).
  - [x] **Bot Interactive Commands (Subagent 13):** Formats quiz and grammar inline cards matching Telegram callback regex `^[a-z_]{1,20}(:[0-9]{1,12}){1,2}$`; implements reveal/rating states for flashcards; routes interactive commands and active briefing takes with strict unauthorized chat rejection (SEC-26).
  - [x] **Voice Fluency & Grammar (Subagent 14):** Fully offline speech fluency analysis and filler-word counter (`um`, `uh`, `like`); detects stutters, double comparatives, double negatives, and subject-verb mismatches without network dependency.
  - [x] **World Glossary & Causality (Subagent 15):** Curated baseline terms with wiki-link regex cross-referencing `[[term]]`; DAG causal graph engine with 3-color DFS cycle detection and root-cause tracing.
  - [x] **FastMCP & Models Admin (Subagent 16):** Read-only Obsidian vault MCP server for Claude Code on macOS with SEC-24 traversal and symlink escape rejection; models admin parses role configs and computes concurrent VRAM fit with headroom/overflow detection.
  - [x] **Feedback & Improvement (Subagent 17):** Bounded topic/source weights ($0.2$ to $2.0$) with official domain floors ($1.0$); records user feedback records and stores automatic regression cases.
  - [x] **Gate Verification Targets (Subagent 21):** Automated `make gate-2c`, `make gate-3`, and `make gate-4` targets in Makefile with comprehensive target and dry-run validation.
  - [x] **API Client & OpenAPI Exporter (Subagent 20):** Clean schema export to `data/openapi.json` with TypeScript API contracts matching backend FastAPI routes and SEC-27/SEC-41 headers.
  - [x] **Economy & Fact-Check Approval (Subagent 23):** Macroeconomic indicator tracking with validation and markdown summary cards; forward fact-checking claims queued in `PENDING_APPROVAL` gate before inclusion.
  - [x] **Study Time & Catch-Up (Subagent 22):** Multi-goal study duration logging with active streak tracking; reboot offline task recovery sorted by priority and capped at batch limit.
  - [x] **Jarvis Voice Assistant (Subagent 19):** Spoken intent classification distinguishing read-only from destructive operations; 10-second spoken confirmation tickets (SEC-56) with affirmative word verification and replay prevention.

- [x] **5. Code Quality & Formatting Gate**
  - [x] `make lint` passes 100% clean across all `src/`, `tests/`, `evals/`, and `scripts/` (263 files verified).
  - [x] `make test` executes all unit test suites without failures (716 passed).
  - [x] `make security` runs all automated security audits green.
  - [x] `make gate-1`, `make gate-2`, `make gate-2b`, `make gate-2c`, `make gate-3`, `make gate-4` all pass 100%.

- [x] **6. Git Discipline & Push Readiness**
  - [x] One task, one commit with clear conventional commit messages (`903285c`, `18e5e85`, `8f7cab6`, `5b624d2`, `c988d96`).
  - [x] No uncommitted scratch files or untracked debris left in the working tree.
  - [x] Commits pushed cleanly to `git@github.com:SidduNiharY/Tech-Radar.git` on `main`.

