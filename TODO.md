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
- [ ] **Task 2: Procrastinate `bulk` queue & settling detection** `[Mac Ready]` (In progress: Agent 1)
  - *Files:* `src/techradar/library/bulk.py`, `tests/library/test_bulk.py`
  - *Verify:* `test_partial_sync_file_skipped`, `test_duplicate_book_detected`, `test_bulk_resumes_after_restart`
- [x] **Task 3: Docling 25-page segmented PDF processor & outline parser** `[Mac Ready]` (Done: commit 8149f8d)
- [ ] **Task 4: ffmpeg audio & slide frame extractor sandbox** `[Mac Ready]` (In progress: Agent 1)
  - *Files:* `src/techradar/library/media.py`, `tests/library/test_media.py`
  - *SEC:* SEC-44 (`-protocol_whitelist file`, reject playlists, no network)
- [ ] **Task 5: Chapter summary generator & vault note creator** `[Mac Ready]`
  - *Files:* `src/techradar/library/summarizer.py`, `tests/unit/test_summarizer.py`
- [ ] **Task 6: Starter pack downloader (NCERT, NIOS, RBI, Budget)** `[Mac Ready]`
  - *Files:* `infra/sources/exam_packs.yaml`, `src/techradar/library/starter_packs.py`
  - *SEC:* Downloads only after explicit allowlist approval
- [ ] **Task 7: "Ask this PDF" scoped RAG query engine** `[Mac Ready]`
  - *Files:* `src/techradar/rag/scoped_ask.py`, `tests/unit/test_scoped_ask.py`
- [ ] **Task 8: Phase 2c gate verification (`make gate-2c`)** `[Mac Ready]`

---

### Phase 3: Daily Briefing, Practice & Exam Alerts (`docs/superpowers/plans/2026-11-07-techradar-phase3-briefing-practice.md`)
**Gate Criteria:** First usable MVP (Telegram daily briefing, FSRS flashcard engine, MCQs, website watcher)

- [ ] **Task 1: Morning briefing generator (Tech, India, World, Economy, Science, Daily Life)** `[Mac Ready]` (In progress: Agent 2)
  - *Files:* `src/techradar/briefing/compose.py`, `tests/briefing/test_compose.py`
  - *SEC:* SEC-20 (Politics 3-domain rule, verified stories preferred)
- [ ] **Task 2: "My take" user opinion & prediction tracker** `[Mac Ready]`
  - *Files:* `src/techradar/practice/predictions.py`, `tests/unit/test_predictions.py`
- [x] **Task 3: MCQ generator & 4-option draft schema** `[Mac Ready]` (Done: commit 8222e18)
  - *Files:* `src/techradar/practice/mcq.py`, `tests/practice/test_mcq.py`
  - *SEC:* SEC-20 (Generated strictly from verified facts, deterministic option shuffling)
- [x] **Task 4: FSRS v5 spaced repetition flashcard scheduler** `[Mac Ready]` (Done: commit 8222e18)
  - *Files:* `src/techradar/practice/fsrs.py`, `tests/practice/test_fsrs.py`
  - *SEC:* Daily caps: 10 new cards, 40 reviews (FSRS optimizer)
- [ ] **Task 4b: Dual-model key checker & practice limits** `[Mac Ready]` (In progress: Agent 2)
  - *Files:* `src/techradar/practice/quiz.py`, `tests/practice/test_quiz.py`
  - *SEC:* SEC-20 (Two-model family key agreement, drop on mismatch)
- [ ] **Task 5: "Mark chapter as read" event trigger** `[Mac Ready]`
  - *Files:* `src/techradar/practice/chapter_cards.py`, `tests/unit/test_chapter_cards.py`
- [ ] **Task 6: Mistakes notebook & review loop** `[Mac Ready]`
  - *Files:* `src/techradar/practice/mistakes.py`, `tests/unit/test_mistakes.py`
- [ ] **Task 7: Grammar & vocabulary daily practice generator** `[Mac Ready]`
  - *Files:* `src/techradar/practice/grammar.py`, `tests/unit/test_grammar.py`
- [ ] **Task 8: changedetection.io exam notification watcher integration** `[Mac Ready (Client) / Linux (Container)]`
  - *Files:* `src/techradar/exams/watcher.py`, `tests/unit/test_watcher.py`
- [ ] **Task 9: Bot interactive quiz & card review session handlers** `[Mac Ready]`
  - *Files:* `src/techradar/bot/commands/quiz.py`, `src/techradar/bot/commands/cards.py`
- [ ] **Task 10: Phase 3 gate verification (`make gate-3`)** `[Mac Ready]`

---

### Phase 4: Web Application v1 (`docs/superpowers/plans/2026-11-07-techradar-phase4-web-app.md`)
**Gate Criteria:** Next.js 16 UI over Tailscale HTTPS with streaming answers, CSRF protection, and confirmation tickets

- [ ] **Task 1: FastAPI service & security middleware** `[Mac Ready]` (In progress: Agent 3)
  - *Files:* `src/techradar/api/main.py`, `src/techradar/api/deps.py`, `tests/api/test_auth.py`
  - *SEC:* SEC-27, SEC-51 (TrustedHostMiddleware, MAX_BODY=64KB limit, disabled docs in prod)
- [ ] **Task 2: Service-token and Tailscale owner authentication** `[Mac Ready]` (In progress: Agent 3)
  - *Files:* `src/techradar/api/deps.py`, `tests/api/test_auth.py`
  - *SEC:* SEC-27, SEC-41 (Constant-time token comparison, owner login header check)
- [x] **Task 2b: One-time confirmation ticket system (`pending_actions`)** `[Mac Ready]` (Done: commit 2aac042)
  - *Files:* `src/techradar/api/ticket.py`, `tests/api/test_ticket.py`
  - *SEC:* SEC-56 (60s tap expiry, single action, single use, HMAC replay protection)
- [ ] **Task 3: openapi-typescript client generation pipeline** `[Mac Ready]`
  - *Files:* `apps/web/lib/api/types.ts`
- [ ] **Task 4: Today screen (sectioned cards, "Why it matters", "How it affects me")** `[Mac Ready]`
  - *Files:* `apps/web/app/today/page.tsx`
- [ ] **Task 5: Ask screen with Vercel AI SDK 7 streaming & Streamdown KaTeX/Mermaid** `[Mac Ready]`
  - *Files:* `apps/web/app/ask/page.tsx`
  - *SEC:* SEC-28 (Render Markdown only, block external images)
- [ ] **Task 6: Library screen (chapter view, "Ask this PDF", file upload)** `[Mac Ready]`
  - *Files:* `apps/web/app/library/page.tsx`
  - *SEC:* Decision D48 (Uploads stream to `data/library-uploads`, checked by Intake Gateway)
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
- [ ] **Task 12: Phase 4 gate verification (`make gate-4`)** `[Mac Ready]`

---

### Phase 5: Planner, Progress & Reliability (`docs/superpowers/plans/2026-11-07-techradar-phase5-planner.md`)
- [ ] Daily plan generator matching study blocks to energy levels
- [ ] Revision calendar (+1, +7, +30, and +90 days for exam topics)
- [ ] Study time tracking per goal (GATE, SSC, Bank, Dev, English)
- [ ] Progress dashboard with Recharts streak & mastery visualization
- [ ] Catch-up engine (recovers queued tasks after server offline/reboot)

---

### Phase 6: Voice Coach v1 & English Practice (`docs/superpowers/plans/2026-11-07-techradar-phase6-voice-english.md`)
- [ ] Telegram voice note receiver and faster-whisper transcription
- [ ] LanguageTool `en-GB` grammar analysis
- [ ] CTC Viterbi forced alignment pronunciation scoring
- [ ] Fluency & filler words ("um/uh") frequency counter
- [ ] Web audio waveform session report (wavesurfer.js)
- [ ] Library lecture video transcription with timestamp alignment

---

### Phase 7: World Understanding & Night Writer (`docs/superpowers/plans/2026-11-07-techradar-phase7-world.md`)
- [ ] Night model batch orchestrator (Gemma 4 12B QAT, 01:00–05:00 AM)
- [ ] Foundation pages generator (Economy, Finance, Politics, World, GK)
- [ ] Weekly 20–30 minute deep-dive essay generator
- [ ] Cause-and-effect chain graph builder
- [ ] Dynamic terminology glossary
- [ ] Economy dashboard (RBI rates, GDP, CPI inflation, currency)
- [ ] SearXNG forward fact-checker with Telegram approval gate

---

### Phase 8: Exams Engine (GATE / SSC / Banking) (`docs/superpowers/plans/2026-11-07-techradar-phase8-exams.md`)
- [ ] Complete syllabus tree parser (GATE DA/CS, SSC CGL, Banking)
- [ ] Syllabus coverage tracker (highlights topics with "no source yet")
- [ ] Previous Years Questions (PYQs) bank linked to syllabus nodes
- [ ] Official answer key capture & cutoff PDF extractor
- [ ] Algorithmic aptitude & reasoning drill generator (calculated in code)
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
- [ ] Read-only FastMCP server for Claude Code on macOS (`vault/` search)
- [ ] Tech stack release digest & "Rising fast" tool analyzer
- [ ] Optional cloud fallback toggle with strict spend limits

---

### Phase 11: Feedback & Self-Improvement (`docs/superpowers/plans/2026-11-08-techradar-phase11-feedback.md`)
- [ ] User feedback action buttons (👍, 👎, "Too long", "Wrong fact")
- [ ] Bounded topic and source weights (0.2 to 2.0 with exam floors)
- [ ] Automatic regression test generator (`regression_cases`)
- [ ] "Answers in my way" style profile engine per exam/goal mode
- [ ] Sunday weekly improvement report generator
- [ ] "My Profile" transparency dashboard

---

### Phase 12: Jarvis System-Wide Voice Assistant (`docs/superpowers/plans/2026-11-08-techradar-phase12-jarvis.md`)
- [ ] openWakeWord local wake word detection ("Hey Jarvis")
- [ ] Unified conversational intent router (Qwen3.5-4B)
- [ ] 10-second spoken confirmation ticket evaluator (SEC-56)
- [ ] Self-hearing and echo cancellation suppression (SEC-68)
- [ ] Proactive morning greeting and day plan briefing
- [ ] System-wide voice action executor (read immediate, write confirmed)

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

#### Active Subagent Assignments
- **Subagent 1 (Library & Media Engine):** `src/techradar/library/bulk.py`, `src/techradar/library/media.py`, `tests/library/test_bulk.py`, `tests/library/test_media.py`.
- **Subagent 2 (Practice Engine & Briefing):** `src/techradar/briefing/compose.py`, `src/techradar/practice/quiz.py`, `tests/briefing/test_compose.py`, `tests/practice/test_quiz.py`.
- **Subagent 3 (Web API & Security):** `src/techradar/api/main.py`, `src/techradar/api/deps.py`, `tests/api/test_auth.py`.
- **Subagent 4 (Integration Verification):** Orchestrates boundary validation, end-to-end regression testing, commit gating, and GitHub pushes.

### Integration Checklist

- [ ] **1. Architectural Boundary Isolation (`lint-imports`)**
  - [ ] Contract 1: `techradar.parser` does NOT import `httpx`, `techradar.db`, or `techradar.llm`.
  - [ ] Contract 2: `techradar.pipeline.reader` does NOT import `writer`, `db`, `vault`, `httpx`, or `subprocess`.
  - [ ] Contract 3: `techradar.pipeline.writer` does NOT import `llm` or `httpx`.
  - [ ] Contract 4: `techradar.fetcher` does NOT import `llm`, `pipeline`, or `vault`.
  - [ ] Contract 5: `pipeline`, `worker`, `rag`, `bot`, and `api` do NOT import parser submodules directly (SEC-57 One Door).
  - [ ] Contract 6: `techradar.intake` does NOT import `httpx`, `db`, or `llm`.
  - [ ] Contract 7: `techradar.rag` does NOT import `httpx` or `subprocess`.
  - [ ] New subsystems (`library`, `practice`, `api`) remain strictly decoupled and do not violate existing boundaries.

- [ ] **2. Dependency Allowlist & Policy Audit (SEC-52)**
  - [ ] `scripts/check_deps.py` passes with zero unapproved packages in `pyproject.toml`.
  - [ ] `scripts/check_mcp.py` and `scripts/check_skills.py` confirm zero unvetted plugins/MCP tools.
  - [ ] Every pinned Docker image retains its immutable `@sha256:` digest in `compose.yaml` and `infra/docker/Dockerfile`.

- [ ] **3. Compose Policy & Host Hardening (SEC-01–SEC-07, SEC-55)**
  - [ ] `tests/security/test_compose_policy.py` passes all checks (127.0.0.1 bindings, non-root, read-only, tmpfs, cap_drop ALL).
  - [ ] `tests/security/test_falco_rules.py` validates eBPF process baselines.

- [ ] **4. Subsystem Interoperability & Data Contract Checks**
  - [ ] **Library & Media (Subagent 1):** File settling skips partial syncs; duplicate books detected via SHA-256; restart resumption picks up next unfinished part; ffmpeg commands strictly enforce `-protocol_whitelist file` and reject playlists/remote URLs (SEC-44).
  - [ ] **Practice & Briefing (Subagent 2):** Politics stories require 3+ independent domains; item selection caps at 3/section and 15 total; dual-model key checker drops MCQs when models disagree (SEC-20); daily limits enforce 10 new cards and 40 reviews.
  - [ ] **API & Security (Subagent 3):** `TrustedHostMiddleware` blocks foreign Host headers (SEC-51); body limiter enforces 64KB max (413); `/docs` and `/openapi.json` are hidden in prod; constant-time service token check and owner login check gate all `/v1/*` routes (SEC-27, SEC-41).

- [ ] **5. Code Quality & Formatting Gate**
  - [ ] `make lint` passes 100% clean across all `src/`, `tests/`, `evals/`, and `scripts/`.
  - [ ] `make test` executes all unit test suites without failures.
  - [ ] `make security` runs all automated security audits green.

- [ ] **6. Git Discipline & Push Readiness**
  - [ ] One task, one commit with clear conventional commit messages.
  - [ ] No uncommitted scratch files or untracked debris left in the working tree.
  - [ ] Commits pushed cleanly to `git@github.com:SidduNiharY/Tech-Radar.git` on `main`.

