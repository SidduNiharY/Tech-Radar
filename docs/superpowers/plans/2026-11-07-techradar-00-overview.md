# TechRadar Brain Implementation Plan: Overview

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build TechRadar Brain, a local-first learning system (news radar, notes, library, practice, planner, voice coach, web app, self-improvement and the Jarvis voice assistant), in fourteen phases (1, 2, 2b, 2c and 3–12). Each phase ends with working software and a passed security gate.

**Architecture:** Python services in Docker on a Linux server (ASUS TUF A15, RTX 3060), local models through Ollama, Postgres with pgvector, a Markdown vault synced to Obsidian, a Telegram bot, and later a Next.js web app. Untrusted content is fetched through an allowlisted proxy, checked by the Intake Gateway and parsed in a no-network sandbox, read by a tool-less model, verified, and written by plain code. Host-level detection (Falco, auditd, AIDE, a separate alerter) watches for anything that gets through. Jarvis, the voice assistant, is the front door to every part, and only my own words can make it act.

**Tech Stack:** Python 3.14, uv, Pydantic v2, SQLAlchemy 2, Alembic, psycopg 3, Procrastinate, LangGraph 1.2, LiteLLM 1.106 (library), Ollama 0.40, PostgreSQL 18 + pgvector, Squid, python-telegram-bot, Docling 2.146, trafilatura; later FastAPI 0.162, Next.js 16, faster-whisper, Kokoro, Pipecat.

**Spec:** [01_Idea_and_Daily_Use.md](../../../01_Idea_and_Daily_Use.md) · [02_Tech_Stack_and_Security.md](../../../02_Tech_Stack_and_Security.md) · [03_Local_Models_Research.md](../../../03_Local_Models_Research.md) · [04_Old_vs_New_SLMs.md](../../../04_Old_vs_New_SLMs.md) · [05_Architecture.md](../../../05_Architecture.md) (services, flows and the SEC-01…SEC-68 control catalogue) · [06_Improvements.md](../../../06_Improvements.md) (Parts A–I) · [07_Attack_Types.md](../../../07_Attack_Types.md)

**Written 2026-11-07; updated 2026-11-08** with the improvements in 06 (new phases 2c, 11 and 12; new tasks in phases 1–10; decisions D32–D47). Every phase has a detailed task plan, linked below. Execute them in order. Before starting a phase, re-read its plan and adjust anything that the model tests or earlier phases changed.

| Phase | Plan | Done when |
|---|---|---|
| 1. Secure foundation | [phase1-foundation](2026-11-07-techradar-phase1-foundation.md) | Hardened server and repo, CI security pipeline (with approved dependencies and the allowlist of MCP servers, skills and plugins), database with least-privilege roles, local models tested for fit, owner-only bot answers `/status`, backups restore, intrusion detection with honeytokens and a daily heartbeat. `make gate-1` passes |
| 2. Secure ingest and vault | [phase2-ingest](2026-11-07-techradar-phase2-ingest.md) | Allowlisted sources pass the Intake Gateway and become verified, sourced notes in the vault; outdated facts are superseded; injection red-team passes. `make gate-2` passes |
| 2b. Knowledge index and Ask (RAG) | [phase2b-rag](2026-11-07-techradar-phase2b-rag.md) | Vault and reference library searchable by meaning and keyword; `/ask` answers only from my notes, with citations checked in code; retrieval eval passes. `make gate-2b` passes |
| 2c. Library | [phase2c-library](2026-11-08-techradar-phase2c-library.md) | Big PDFs, DOCX, EPUB and videos from the Library folder become chapters, summaries and searchable chunks with page and timestamp references; starter packs; RAG upgrades for big books. `make gate-2c` passes |
| 3. Briefing, practice, exam alerts | [phase3-briefing-practice](2026-11-07-techradar-phase3-briefing-practice.md) | Daily briefing, "My take", MCQs, flashcards (with chapter cards and daily limits), grammar and vocabulary on Telegram; exam alerts; review inbox. **First usable version** |
| 4. Web app v1 | [phase4-web-app](2026-11-07-techradar-phase4-web-app.md) | Today, Ask, Library, Practice, Security, Settings and a read-only Models screen in Next.js over Tailscale; CSRF and host checks; confirmation tickets |
| 5. Planner, progress, reliability | [phase5-planner](2026-11-07-techradar-phase5-planner.md) | Daily plan, 1–7–30 revision (+90 for exam topics), time tracker, check-in, Progress screen, alerts, verified catch-up |
| 6. Voice Coach v1 and English practice | [phase6-voice-english](2026-11-07-techradar-phase6-voice-english.md) | Telegram voice notes analysed locally with a web report; library videos transcribed; writing, reading, listening, story bank, reflection; English practice time |
| 7. Understanding and World | [phase7-world](2026-11-07-techradar-phase7-world.md) | Night writer, foundation pages, deep dives, glossary, timelines, politics views, predictions, economy dashboard, fact-checker |
| 8. Exams | [phase8-exams](2026-11-07-techradar-phase8-exams.md) | Coverage (with sources per topic and "no source yet"), GATE past papers, answer-key capture, code-generated drills, typing, mock analyser, weightage, final 30 days mode |
| 9. Study smarter and live voice | [phase9-live-voice-group](2026-11-07-techradar-phase9-live-voice-group.md) | Handwritten notes, study group mode, live Voice Coach with the orb, interview pack |
| 10. Models admin and tech extras | [phase10-models-extras](2026-11-07-techradar-phase10-models-extras.md) | Models admin (with tickets), release digest, "Rising fast", read-only MCP server, optional cloud backup |
| 11. Feedback and self-improvement | [phase11-feedback](2026-11-08-techradar-phase11-feedback.md) | Feedback buttons, bounded weights, pattern finding, the weekly improvement report, style profiles, answers in my way, regression cases, the My profile page. `make gate-11` passes |
| 12. Jarvis | [phase12-jarvis](2026-11-08-techradar-phase12-jarvis.md) | One voice assistant for the whole app: wake word, router with a fixed skill list, one-time spoken confirmations, echo handling, morning greeting. **Last gate** |
| Later | not planned | LifeLedger connection (a separate project) |

---

## Decisions this plan takes

These were open or loose in the spec. The plan uses the option below. Change one **before** executing the phase it affects.

| # | Decision | Affects |
|---|---|---|
| D1 | **Repo:** the `TechRadarBrain` folder becomes a Git monorepo. Python package `techradar` in `src/`; the web app in `apps/web` (phase 4) | All |
| D2 | **Agent framework:** LangGraph for multi-step graphs, plain functions plus Pydantic elsewhere. LangChain only if a later task needs it. *Refines 02 §5.3* | 2+ |
| D3 | **LiteLLM runs as a library** (`litellm.Router`) inside the worker and API, not as a proxy service: one less network service, no master key, no port. *Refines 02 §5.3* | 1+ |
| D4 | **Database driver: psycopg 3** for SQLAlchemy and Procrastinate, so there is one driver. *Refines 02 §5.2 (asyncpg)* | 1+ |
| D5 | **Job queue: Procrastinate** on Postgres. Queues `fetch`, `parse`, `llm`, `io`; `llm` runs one job at a time | 2+ |
| D6 | **Model lineup:** worker `qwen3.5:4b` (thinking off), checker `gemma4:e2b-it-qat`, night `gemma4:12b-it-qat`, embed `bge-m3`, vision `qwen3.5:4b`. Gemma 4 E4B is promoted only if the fit test shows 100% on GPU at 8k context and at least 20 tokens/s; then the checker becomes `qwen3.5:4b`. *From 04* | 1+ |
| D7 | **Verification:** verified = 2 or more distinct registrable domains, or 1 official source; politics headlines need 3; MCQs only from verified facts | 2–3 |
| D8 | **Pipeline numbers:** fetch every 120 min; 5 s between requests to one site; 5 MB per download; 20 s timeout; 100,000 characters per document; dedupe cosine 0.90; relevance 0.30; 7-day retention of raw and clean text; User-Agent `TechRadarBrain/0.1 (personal, non-commercial)` | 2 |
| D9 | **Parser sandbox** talks to the rest only through files (no network, no database). Memory raised to `3g` for Docling | 2 |
| D10 | **Model downloads** happen only through a one-off `ollama-pull` Compose profile that I run. The serving `ollama` container has no internet | 1 |
| D11 | **Secrets:** Docker secrets from `secrets/` on the server (mode 600, owner uid 1000). `secrets.example/` holds fake values for development. Coding agents never see real secrets | 1 |
| D12 | **No HTTP API until phase 4.** Phases 1–3 talk only through Telegram and the vault (smaller attack surface) | 1–3 |
| D13 | **GATE paper undecided:** the vault seeds both GATE CS and GATE DA subject lists; delete one when decided | 2 |
| D14 | **Sources start small:** official and RSS sources only. X and LinkedIn are manual; YouTube is channel RSS only, without transcripts. *From 02 §6* | 2 |
| D15 | **Server-only until phase 5.** The Mac fallback route is added in phase 5 | 1–4 |
| D16 | **Runbook assumes Ubuntu LTS** (open decision). Adjust the commands if the distro differs | 1 |
| D17 | **Briefing time 06:30 Asia/Kolkata**, changeable in settings | 3 |
| D18 | **Approval in Telegram** is required before saving web-search results (fact-checker, gap filling) and items flagged as suspicious | 2, 7 |
| D19 | **No Mac fallback for server jobs.** Containers on internal networks can't safely reach the tailnet, so when the server is off or in Windows, jobs wait and catch up. The Mac's Ollama serves Mac-side tools only. *Revises 02 §2 and 05 §4* | 5 |
| D20 | **Publishing the web app:** `web` publishes `127.0.0.1:3000` from a no-egress `edge` bridge (masquerade off), and the host's Tailscale Serve adds HTTPS and identity headers. Ollama uses the same pattern (`edge_llm`) in phase 9 for `voice-live` | 4, 9 |
| D21 | **The API is model-free and returns JSON.** `/v1/ask` queues the worker's `ask` job; Next.js polls and turns the answer into the AI SDK stream. *Refines 02 §5.14* | 4 |
| D22 | **Outbox pattern:** workers never talk to Telegram. They write to `outbox`, and only the bot sends, so the bot token lives in one container | 2b+ |
| D23 | **Bot commands:** `/ask`, `/quiz`, `/cards`, `/grammar`, `/inbox`, `/drill`, `/study`, `/stop`, `/skill`, `/predict`, `/econ`, `/check`, `/polish`, `/story`, `/mock`, `/status`. `/study` replaces the `/start GATE OS` idea, because `/start` is Telegram's greeting command | 2b–8 |
| D24 | **No pickle model files:** Kokoro runs from its ONNX build; wav2vec2 loads with torch ≥ 2.6 (`weights_only` by default) at a pinned revision; every image is checked by `check_model_files.py` | 6 |
| D25 | **Pronunciation alignment is our own CTC Viterbi forced alignment** over wav2vec2 outputs, not Montreal Forced Aligner (no conda). *Refines 02 §5.5* | 6 |
| D26 | **Maths from untrusted input is never passed to `sympify` or `parse_expr`** (both use `eval`); only `parse_latex`, in a child process with a 5 s limit | 9 |
| D27 | **Aptitude, reasoning and speed-maths questions are generated by code**, with computed answers, never by a model | 8 |
| D28 | **Voice audio is deleted 24 hours after analysis** unless I tap Keep; reports keep only waveform peaks and word timings. *Refines 05 §6* | 6, 9 |
| D29 | **Model downloads requested in the web app wait for `make pull-approved`**, which I run; the web app never downloads anything | 10 |
| D30 | **RAG:** a `chunks` index in Postgres (BGE-M3 vectors plus `simple` full-text), reciprocal rank fusion, and `BAAI/bge-reranker-v2-m3` on the CPU (pinned revision, safetensors) | 2b |
| D31 | **LanguageTool uses `en-GB`** (there's no Indian English variant) | 6 |
| D32 | **Phase order and migrations:** 1, 2, 2b, 2c, 3–10, 11, 12. Phase 2c's migration is `0004b_library` (revises 2b's `0004`; phase 3's `0005` then revises `0004b`). Phase 11 adds `0013_feedback`, phase 12 adds `0014_jarvis` | All |
| D33 | **Intake Gateway placement:** it runs inside the parser sandbox. `clamd` runs in its own no-network `clamav` container, reached through a Unix socket; signatures come from `clamav-update` through Squid (`database.clamav.net`). The gateway fails closed: with `clamd` down or signatures older than 3 days, jobs wait. *Refines 05 §3* | 2 |
| D34 | **Gateway thresholds (defaults; 06 F10.1 stays open):** injection flag at score ≥ 0.5 or 1 pattern hit, quarantine at score ≥ 0.98 **and** ≥ 2 pattern hits; injection signals never reject. PDF `/JavaScript`, `/JS`, `/Launch`, `/EmbeddedFile`, `/RichMedia`, `/XFA` → quarantine; `/OpenAction`, `/AA` → flag. Macros → quarantine. Archives other than DOCX and EPUB, and media playlists → reject. Antivirus hit → reject for fetched and pack files, quarantine for files I sent | 2, 2c |
| D35 | **Injection classifier default: Llama Prompt Guard 2 86M** (multilingual), baked into the parser image at a pinned revision through a BuildKit `hf_token` secret (it's a gated model). `make guard-eval` compares it with `protectai/deberta-v3-base-prompt-injection-v2` on my own news and books; the one with fewer false alarms at ≥ 0.9 detection on the red-team set wins (06 F10.3) | 2 |
| D36 | **Pixel rebuild only for flagged documents** (06 F10.2 default) | 2c |
| D37 | **Library layout and limits:** `data/library-inbox` (Syncthing, receive-only on the server), `data/library/originals/<sha>.<ext>`, `data/library/text/<doc_id>/`. Limits: PDF 300 MB, DOCX and EPUB 50 MB, video 4 GB and 4 hours, audio 1 GB. PDFs in 25-page parts on the resumable `bulk` queue (CPU, any time); GPU work (summaries) only in the night window 01:00–05:00 | 2c |
| D38 | **Library videos:** 2c extracts audio and frames and reads slides; transcription arrives with phase 6's `voice-worker` (`transcribe_library_audio`). Until then a video waits as `awaiting_transcription` | 2c, 6 |
| D39 | **Cards and MCQs from chapters:** 10–20 cards per chapter when I mark it read, each quoting its chunk word for word; MCQs from read chapters the same way. Daily limits 10 new cards and 40 reviews (80 in final 30 days mode) | 3 |
| D40 | **Outdated facts:** a `subject_key` exists only for subjects listed in `infra/facts/subjects.yaml`; only an official source can supersede; old cards and MCQs are retired and new ones made from the new fact (no rewording) | 2, 3 |
| D41 | **Detection:** Falco writes JSON alerts to a file that the alerter follows (no Falcosidekick). The alerter runs on the host as my user under systemd sandboxing, with its own bot token and an append-only log. Containment is `alert-only` for the first 14 days, then `on` (`TR_CONTAINMENT`). *Refines 02 §5.17 and 05 §3* | 1 |
| D42 | **Evidence** is encrypted with `age` to my public key (the private key never lives on the server) and kept 90 days (06 H11.3 default). Containment stops only the affected container (06 H11.1 default). Heartbeat at 06:25 Asia/Kolkata (06 H11.2 default) | 1 |
| D43 | **Confirmation tickets** (`pending_actions`) arrive in phase 4 and are reused by phases 10 and 12: voice 10 s from the end of Jarvis's speech, tap 60 s, one open ticket per session | 4, 10, 12 |
| D44 | **Jarvis path:** `voice-live` → `api-voice` (a second instance of the API, listening only on a Unix socket) → the `jarvis` queue, served by its own `jarvis` service. The API stays model-free (D21). Practice answers inside a quiz session I started are recorded without a ticket; every other change needs one | 12 |
| D45 | **Wake word:** the Mac's Jarvis tab first (openWakeWord ONNX models in the browser; the models are CC BY-NC-SA 4.0, fine for this personal app). The server-laptop helper is optional | 12 |
| D46 | **Feedback learning defaults (06 B11 stays open):** a pattern needs 5 signals in 14 days, or over 70% of at least 10 items; weights stay within 0.2–2.0 with a floor of 0.8 for exam topics and a 60-day half-life; only bounded weights change automatically; the weekly report goes out on Sundays at 18:30 | 11 |
| D47 | **SEC-64's GPU checks run in phase 1** (the resource watcher reads NVML on the host), not phase 10. *Refines 05 §10.2* | 1 |
| D48 | **Web uploads** go to their own folder, `data/library-uploads`, never into the Syncthing Library folder. The API only checks the type, size, name and rate, streams the file there and never opens it; the library intake then sends it through the Intake Gateway with origin `upload`. *Refines 05 §6 and §7.11* | 4 |
| D49 | **Langfuse** runs as the Compose project `techradar-langfuse` on the internal `obs` network, with only its web container also on the no-egress `obs_edge` (for `127.0.0.1:3001`), and telemetry off. Falco and the policy tests cover it like the main project; only `worker` sends it traces, and only while tracing is on. *Refines 05 §3* | 4 |

## Global Constraints

Every task in every phase respects these. Values are copied from the spec.

1. Python `>=3.14`; uv; Ruff `>=0.17`; pytest `>=9`; Pydantic v2; SQLAlchemy 2 + Alembic; PostgreSQL 18 with pgvector; LangGraph 1.2; LiteLLM 1.106; Ollama 0.40; Docling 2.146. Phase 4+: FastAPI `>=0.162`, Next.js 16, TypeScript, Tailwind CSS v4, shadcn/ui, Vercel AI SDK 7, pnpm 11, Node.js LTS. (02 §5)
2. Local-only by default: `TR_ALLOW_CLOUD_LLM=false`. Cloud roles don't exist in config unless the flag is true. (02 §1, SEC-35)
3. Ollama: `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, 8k context for daily jobs, 4-bit models only, Qwen thinking off for JSON jobs. (02 §5.4)
4. Every published port is `"127.0.0.1:<host>:<container>"`. (02 §7, SEC-02)
5. Container baseline: not root, `cap_drop: ["ALL"]`, `security_opt: ["no-new-privileges:true"]`, `read_only: true` with `tmpfs` for scratch, `mem_limit`, `cpus` and `pids_limit` set, log `max-size`. Never `privileged`, never `network_mode: host` (except `voice-live` in phase 9), never mount `/var/run/docker.sock`, `/home` or `/`. (02 §8.2, SEC-07)
6. Parser: `network_mode: none`, `read_only: true`, `tmpfs: ["/tmp"]`, `user: "1000:1000"`, `cap_drop: ["ALL"]`, `cpus: "2"`, `mem_limit: 3g`, `pids_limit: 200`, 120 seconds per job. (02 §8, D9, SEC-06)
7. Outbound HTTP only through Squid's allowlist. No other service reaches the internet. (02 §5.9, SEC-05)
8. The bot answers only `TR_TELEGRAM_OWNER_CHAT_ID` (and approved study-group IDs from phase 9). Strangers get no reply. (02 §8.1, SEC-26)
9. Secrets only as files in `secrets/`, mode 600, never committed, mounted as Docker secrets. (02 §8.3, SEC-10)
10. Pin images, packages, models and GitHub Actions (actions to full commit SHAs). Never `:latest`. (02 §8.1, §8.5, SEC-08)
11. Models only from the Ollama library or approved Hugging Face organisations, in GGUF or safetensors. `trust_remote_code` off; no `pickle`/`torch.load` of downloaded files. (02 §8.1, SEC-23)
12. The reader model has no tools; the writer is plain code and never sees raw text; code from sources is never run. (02 §8.1, SEC-16, SEC-22)
13. Facts follow D7. (01, 02 §4, SEC-20)
14. Pipeline numbers follow D8.
15. Timestamps stored as `timestamptz` in UTC; schedules and display in `Asia/Kolkata`.
16. Only fake data in the repo, fixtures and tests: no real chat IDs, tokens, recordings or personal notes.
17. Every input passes the Intake Gateway (D33, SEC-57). Flagged content is never a fact source, an MCQ or a card.
18. Only my own words or clicks trigger actions or learning. Text from content never reaches the Jarvis router or the learning rules. (SEC-45, SEC-48, SEC-49)
19. Images and Dockerfile `FROM` lines are pinned by digest (`name:version@sha256:…`); healthchecks use exec form (`CMD`), never `CMD-SHELL`. (SEC-55, SEC-58)
20. No new direct dependency without an entry in `infra/policy/approved_deps.yaml`; coding agents never add one. MCP servers, skills and plugins only from the `AGENTS.md` allowlists. (SEC-52, SEC-53)
21. Every change made through Jarvis or a confirm step uses a one-time ticket (D43, SEC-56).
22. "My way" changes the form of answers, never the facts. (06 B10)
23. Library files are never deleted by the news retention job. (SEC-43)

## Conventions

- **Layout:** `src/techradar/…`, tests in `tests/` mirroring it. Run everything with `uv run …`.
- **Async:** asyncio throughout; pytest-asyncio with `asyncio_mode = "auto"`.
- **Fakes, not real systems:** external systems sit behind Protocols (`Completer`, `Embedder`, `Resolver`, `Clock`). Unit tests use fakes from `tests/fakes.py` and never call a real model, Telegram or the internet. Integration tests are marked `db`, `egress` or `live` and run on the server.
- **Telegram text** comes from pure `render_*` functions, with the exact text pinned in tests.
- **Enums** are `StrEnum`, stored as their values. IDs are `bigint` identity columns.
- **Security evidence:** every task names the SEC controls it implements; its tests are the evidence a gate relies on.
- **Commits:** one per task: `feat(area): …`, `security(area): …`, `ci: …`, `docs: …`.

---

## Security gates

A gate re-runs every earlier gate plus its own checks. I record each pass in `docs/security/gates.md` with the date, the commit and my sign-off.

| Gate | Adds | Pass line |
|---|---|---|
| `gate-1` | Ruff; unit and security tests; compose policy (including digests and exec-form healthchecks); semgrep (rules and rule tests); OSV-Scanner; gitleaks; Trivy config and images; hadolint; shellcheck; `check_deps.py`; `check_mcp.py`; `check_skills.py`; database role tests; egress tests; restore test; `check_host.sh`; `nmap` from the Mac; detection unit tests; the phase 1 simulated attacks (05 §10.5) | Everything green; `nmap` finds no open TCP port on the server's LAN address; every `check_host.sh` line is PASS; every simulated attack raises its expected alert; the morning heartbeat arrives |
| `gate-2` | import-linter contracts (including "one door"); red-team structure tests; Intake Gateway tests; `clamav` no-network test; fail-closed test; end-to-end fake pipeline; parser no-network runtime test; first promptfoo run on the real models; `make guard-eval` | 0 successful injections; every note has provenance; no network from the parser or `clamav`; a PDF with JavaScript is quarantined; an article about prompt injection is flagged, not rejected; nothing passes with `clamd` stopped |
| `gate-2b` | RAG unit and database tests; poisoned-note tests; clipped pages through the gateway; `make rag-eval` | recall@5 ≥ 0.80 for English and ≥ 0.60 for Hindi and Telugu; 0 invalid citations; at least 9 of 10 out-of-scope questions answered "Not in my notes yet." |
| `gate-2c` | Library tests; a 300-page PDF processed and resumed after a restart; DOCX, EPUB and video fixtures; zip-bomb, macro and playlist fixtures; starter-pack allowlist test; retention-never-touches-library test; per-book evals | Book-eval recall@5 ≥ 0.80; the zip bomb and playlist are rejected; the macro DOCX is quarantined; no library file deleted by retention |
| `gate-3` | MCQ gate (50 items checked by me); FSRS and daily-limit tests; chapter-card quote tests; outdated-fact retirement test; changedetection egress; retention job run | 0 wrong answer keys in 50; 0 cards without a word-for-word quote; alerts only from allowlisted exam sites |
| `gate-4` | Playwright security tests (CSP, raw HTML, external image blocked, identity header required, cross-site POST refused, foreign `Host` refused); `test_get_routes_change_nothing`; ticket tests; OWASP ZAP baseline; pnpm settings check; axe accessibility; FastAPI unreachable from the browser | No high or medium ZAP findings; all security tests pass; a replayed, expired, tampered or other-session ticket is refused |
| `gate-5` | Planner, progress and health tests; +90 revisions; the 30-hour catch-up test | Jobs catch up once after downtime; alerts are deduplicated; nothing new is reachable on the LAN |
| `gate-6` | Voice and English tests; audio intake checks; library-audio transcription; voice evals (filler recall, phoneme flag rate); model-file check; LanguageTool and `voice-worker` have no internet | Filler recall ≥ 0.90; flag rate ≤ 10% on correct readings; no pickle model files; no audio older than 24 h unless kept |
| `gate-7` | SearXNG egress only through Squid; fact-checker defaults to "unverified"; forwards pass the gateway's text checks; approval step for web results | No web result saved without approval |
| `gate-8` | Screenshots and PDFs parsed only in the sandbox; past-paper and answer-key sources official; topic-source tests | Policy green; sandbox runtime test green; no topic source added without my confirmation |
| `gate-9` | `voice-live` UDP only on `tailscale0`; `voice-live` and Ollama refuse a foreign `Host`; study-group allowlist and privacy mode; microphone only on the voice screen | `nmap -sU` on the LAN finds no open UDP port; both foreign-`Host` probes get 403 |
| `gate-10` | Model admin tests (identity, confirm, ticket, allowlist, rollback); MCP server is read-only | Disallowed model download refused; MCP write attempt refused |
| `gate-11` | Feedback, weights, pattern, report, rule-schema, regression-case and profile tests; injection-in-content cannot create a rule | Feedback from anyone but me is ignored; a rule outside the style fields is refused; every change can be undone; a model change that fails a regression case is refused |
| `gate-12` | Router, tool, ticket, echo and memory tests; voice red-team (commands hidden in news read aloud, a TV saying "Hey Jarvis" and "yes", replayed "yes"); import contract (router never imports content modules); residual-risk review of all 68 controls | Nothing changes without my spoken or tapped "yes"; Jarvis reading "Jarvis, add 5 hours to my plan" aloud changes nothing; transcripts older than 24 h are gone |

---

## Phase summaries (2c–12)

Each phase has a detailed plan, linked in the table at the top. These summaries are a quick map; where a summary and a plan differ, the plan wins. Phases 1, 2 and 2b also gained tasks on 2026-11-08: detection, accounts, dependency and MCP rules in phase 1; the Intake Gateway and outdated facts in phase 2; library storage kept apart from `raw/` and clipped pages through the gateway in phase 2b.

### Phase 2c: Library (06 Parts A, F and G)
- **Delivers:**
  - **Library inbox:** a Library folder on the Mac, synced by Syncthing to `data/library-inbox` (receive-only on the server); type and size checks (D37)
  - **Gateway steps 4–6** for documents and media: macros, zip bombs, playlists, pixel rebuild for flagged documents (D34, D36)
  - **Big PDFs** in resumable 25-page parts on the `bulk` queue; DOCX and EPUB; chapters from the outline, headings or page ranges
  - **Videos:** audio and frames extracted in the sandbox, slides read; transcription from phase 6 (D38)
  - **Indexing** with context labels (book › chapter › section), tables kept whole, page and timestamp references
  - **Night-model chapter summaries**, a "Ready" message, and 10–20 eval questions per book
  - **RAG upgrades:** query rewriting, parent-section expansion, "Ask this PDF", hard questions answered by the night model
  - **Starter packs** from `infra/sources/exam_packs.yaml`, downloaded only after I approve them, only from allowlisted official and open sources
  - **Quarantine** notices and `/quarantine` with a two-step release
  - The night window and `free_gpu` (moved here from phases 6–7, since 2c needs them first)
- **New:**
  - **Services:** none (uses `parser`, `worker`, `fetcher`)
  - **Tables:** `library_docs`, `library_parts`, `library_chapters`, `book_evals`, `starter_packs`, `starter_pack_items`; new `chunks` columns
- **Security:** SEC-15, SEC-20, SEC-43, SEC-44, SEC-54, SEC-57.
- **Exit:** `gate-2c`.

### Phase 3: Briefing, practice and exam alerts (build steps 2–4, the first usable version)
- **Delivers:**
  - Morning briefing at 06:30 by section (Tech, India, World, Economy and finance, Science, Daily life), each item with the four questions and exam tags. Politics headlines only with 3+ domains
  - "My take" from my Telegram reply
  - Monthly current-affairs capsule written to the vault
  - Links, PDFs and screenshots I send to the bot go through the phase 2 pipeline
  - MCQs facts-first (D7), checked by the checker model; quiz in Telegram with inline buttons
  - FSRS flashcards (`py-fsrs`) and the mistakes notebook
  - 10 grammar questions a day; vocabulary from my reading (spaCy + wordfreq)
  - Exam watcher: `changedetection` on the official SSC, IBPS, SBI and GATE pages; the worker reads its API and the bot sends the alert
  - Review queue in Telegram for items flagged as suspicious
- **New:**
  - **Services:** `changedetection`
  - **Tables:** `briefings`, `mcqs`, `quiz_attempts`, `flashcards`, `reviews`, `mistakes`, `vocab`, `exam_watches`, `alerts`, `takes`
- **Added 2026-11-08:** chapter cards and MCQs when I mark a chapter as read (D39), daily card limits, cards that point to their source page, outdated facts retiring their cards and MCQs (D40).
- **Security:** SEC-05 (exam sites added to the Squid allowlist), SEC-18 (MCQ schema), SEC-20 (verified facts or quote-checked library text only), SEC-26.
- **Exit:** `gate-3`. I use it for 7 days straight.

### Phase 4: Web app v1
- **Delivers:**
  - **Next.js 16 app** (02 §5.14) with screens Today, Ask, Practice, Settings, and a read-only Models screen (GPU and RAM use, loaded models, job→model map)
  - **FastAPI `api`:** a model-free JSON API; answers come from the worker's `ask` job, and Next.js streams them (D21)
  - **Ask:** retrieval (BGE-M3, then bge-reranker-v2-m3) with citations, "save to vault" through the writer, and "Go deeper"
  - **Answer display:** Streamdown with KaTeX and Mermaid, sources and verified badges
  - **Access:** Tailscale Serve HTTPS; Langfuse on demand
- **New:**
  - **Services:** `api`, `web`, `langfuse` (profile `obs`)
  - **Networks:** `web_internal`
- **Added 2026-11-08:** Library, Quarantine and Security screens; CSRF hardening and host checks in the web app (SEC-51, SEC-54); confirmation tickets (`pending_actions`, D43, SEC-56); file uploads from the Library screen through the Intake Gateway (D48); Langfuse watched and cut off from the internet (D49).
- **Security:** SEC-27, SEC-28, SEC-29, SEC-51, SEC-54, SEC-56; OpenAPI-generated types; identity headers; service token web→api; CSP with `img-src 'self' data: blob:`; `frame-ancestors 'none'`.
- **Exit:** `gate-4`.

### Phase 5: Planner, progress and reliability (build step 5)
- **Delivers:**
  - Daily plan message and Progress screen
  - 1–7–30 revision calendar
  - Study time tracker (`/start <goal> <topic>`, `/stop`)
  - Energy check-in (one tap)
  - Weekly review
  - Skill map status updates
  - Telegram failure alerts for jobs
  - Verified catch-up after downtime (no Mac fallback for server jobs, D19)
- **New:** tables `plans`, `revisions`, `study_sessions`, `checkins`.
- **Added 2026-11-08:** a +90-day revision for exam topics; revisions for chapters I mark as read.
- **Security:** SEC-14, SEC-32.
- **Exit:** `gate-5`; the briefing still arrives on a day the server boots late (catch-up).

### Phase 6: Voice Coach v1 and English practice (build step 6)
- **Delivers:**
  - **Voice notes:** a Telegram voice note goes to `voice-worker`, which produces:
    - a Whisper large-v3-turbo transcript (filler prompt test first)
    - fillers, pace and word variety computed in code
    - LanguageTool grammar checks
    - wav2vec2 phoneme scores with forced alignment
    - feedback text from the worker model
    - Kokoro audio
  - **Session report** in the web app (waveform with marks, trends)
  - **Writing practice:** feedback on "My take", weekly timed essay or letter, story bank (STAR), writing check
  - **Reading and listening practice:** weekly reading-comprehension quiz, listening summaries
  - **Weekly reflection**
- **New:**
  - **Services:** `languagetool`, `voice-worker`
  - **Tables:** `voice_sessions`, `voice_metrics`, `pronunciation_scores`, `writing_feedback`, `stories`
- **Added 2026-11-08:** the gateway's file checks for audio; library-video transcription with timestamps (D38); an English practice time with a reminder (coaching stays on demand).
- **Security:** SEC-15 (audio deleted 24 hours after analysis unless kept, D28), SEC-23 (no pickle model files, D24), SEC-07, SEC-57.
- **Exit:** `gate-6`; the filler test from 03 has passed or a fallback model is chosen.

### Phase 7: Understanding and World (build steps 7–8)
- **Delivers:**
  - **Night-writer jobs** (01:00–05:00): weekly deep dive, foundation pages filled from NCERT, Wikipedia and official sources, glossary, story timelines, cause-and-effect chains (Mermaid)
  - **My opinions:** opinion and prediction log with reminders
  - **Politics:** facts kept separate from opinions
  - **Economy dashboard:** RBI and MOSPI data, plus gold and petrol
  - **Forward fact-checker:** SearXNG plus Gemma; defaults to "unverified"; approval before saving (D18)
  - **World screen**
- **New:**
  - **Services:** `searxng`
  - **Tables:** `deep_dives`, `glossary_terms`, `timelines`, `predictions`, `econ_series`, `fact_checks`
- **Added 2026-11-08:** the night window now comes from phase 2c; forwarded messages pass the gateway's text checks before claims are extracted.
- **Security:** SEC-05, SEC-16, SEC-20, SEC-57, D18.
- **Exit:** `gate-7`.

### Phase 8: Exams (build steps 9–10)
- **Delivers:**
  - **GATE:** syllabus coverage map, past-paper bank from official GATE papers with accuracy per topic, formula flashcards
  - **Daily drills:** timed aptitude set (10 quant + 10 reasoning), speed maths, typing practice for SSC CGL's data entry test
  - **Mock test analyser:** screenshot → parser sandbox OCR → code → cutoff comparison
  - **Topic weightage**
  - **Final 30 days mode**
  - **Exams screen**
- **New:** tables `syllabus_topics`, `pyq_questions`, `mock_results`, `topic_weights`.
- **Added 2026-11-08:** sources linked to each syllabus topic (`topic_sources`, suggested by models, confirmed by me), "no source yet" on the coverage map, official answer keys captured when released.
- **Security:** SEC-06 (screenshots parsed only in the sandbox), SEC-18, SEC-20.
- **Exit:** `gate-8`.

### Phase 9: Study smarter and live voice (build steps 11–12)
- **Delivers:**
  - **Handwritten notes:** Qwen3.5-4B vision in the sandboxed path; maths checked with SymPy; otherwise "unverified"
  - **Study group mode:** group-ID allowlist, privacy mode on, leaderboard, weekly group discussion
  - **Voice Coach v2:** `voice-live` with Pipecat and SmallWebRTC; the orb, captions, read-aloud, shadowing and session reports
  - **Speaking modes:** mock interviews, group-discussion simulator, debate, role plays, and the "Know yourself" pack
- **New:** services `voice-live` (host networking: the documented exception).
- **Added 2026-11-08:** host checks for `voice-live` and the published Ollama port (SEC-51); image re-encoding lives in the gateway.
- **Security:** SEC-03 (UDP only on `tailscale0`), SEC-26 (groups), SEC-28 (microphone only on the voice screen), SEC-51.
- **Exit:** `gate-9`.

### Phase 10: Models admin and tech extras (build step 13)
- **Delivers:**
  - **Models screen admin:** switch, fit check, family rule, test bench, playground, approved-list downloads through `ollama-pull`, history and rollback
  - **Release digest:** PyPI, npm, Maven and GitHub releases
  - **"Rising fast"** trend detection
  - **Read-only vault MCP server** for Claude Code (stdio on the Mac)
  - Optional cloud backup wiring, if decided
- **New:** tables `model_registry`, `model_tests`, `model_changes`.
- **Added 2026-11-08:** model changes also consume a confirmation ticket (D43); gate 10 is no longer the last gate.
- **Security:** SEC-30, SEC-23, SEC-35, SEC-56.
- **Exit:** `gate-10`.

### Phase 11: Feedback and self-improvement (06 Part B)
- **Delivers:**
  - 👍/👎 and other feedback buttons in Telegram and the web app; implicit signals (`action_log`); edits I make to generated notes
  - Topic and source weights within fixed bounds, with fading, exam-topic floors and a 10% "outside your usual" slot (D46)
  - Nightly pattern finding: counting, sequences, repeated confusion, mistake clusters, study times, edit habits
  - A weekly night-model review that proposes at most 3 rules, with evidence checked in code; the Sunday improvement report; approve, ignore and undo
  - Style profiles per mode with a 5-minute setup; topic mastery; liked answers as wrapped style examples ("my way" changes the form, never the facts)
  - Regression cases from every 👎 or "Wrong"; search tuning per book; "Which is better?" pairs; the FSRS optimizer
  - The My profile page
- **New:** tables `feedback`, `edits`, `weights`, `preference_rules`, `regression_cases`, `improvement_log`, `style_profiles`, `topic_mastery`, `liked_examples`, `preference_pairs`, `action_log`, `improvement_reports`.
- **Security:** SEC-48, SEC-49, SEC-56.
- **Exit:** `gate-11`.

### Phase 12: Jarvis (06 Part C)
- **Delivers:**
  - The router: my transcript only, a fixed skill list, schema-checked arguments
  - Tools with three levels (Read, Write with a ticket, Never); big changes also need a tap on the screen; at most 5 writes a minute; everything logged and undoable
  - The `jarvis` service and `api-voice` on a Unix socket (D44)
  - `voice-live` in Jarvis mode: echo filter, wake word paused while Jarvis speaks, barge-in that only stops speech, the GPU lease
  - The wake word in the Mac's Jarvis tab (D45); an optional server-laptop helper
  - Skills: news, ask, teach, quiz, plan, library, exams, progress, coach, status; fast and slow paths
  - The morning greeting with at most 3 suggestions; conversation memory for 24 hours
  - The Jarvis screen and an orb button on every screen
- **New:**
  - **Services:** `jarvis`, `api-voice`
  - **Tables:** `jarvis_sessions`, `jarvis_turns`, `jarvis_writes`, `jarvis_greetings`, `gpu_lease` (`pending_actions` comes from phase 4)
- **Security:** SEC-45, SEC-46, SEC-47, SEC-50, SEC-56, SEC-68.
- **Exit:** `gate-12`, the last gate, with the residual-risk review.

---

## Review Focus (whole program)

These five failure modes cut across phases. Each is pinned by a test in the phase that owns it.

1. **The server is off or in Windows when a job is due.** Jobs must run once on wake, not pile up or be lost. Pinned in phase 1 Task 3 (`test_settings_defaults`, `misfire_grace_s`), Task 11 (`test_backup_timer_is_persistent`) and phase 2 Task 5 (`test_due_sources_after_long_sleep`).
2. **A source suddenly serves a huge, broken or hostile file.** Download caps, content-type checks and parser limits must reject it without stopping other sources. Phase 2 Task 5 (fetch limits) and Task 6 (parser limits).
3. **The GPU is busy or out of memory.** Jobs wait in the `llm` queue (one at a time); an Ollama error becomes "needs review", not a crash. Phase 1 Task 8 (`test_complete_json_retries_once_then_raises`) and phase 2 Task 12 (`test_ollama_error_marks_needs_review`).
4. **Indian-language input** (Hindi or Telugu article, or mixed script). The pipeline must keep the text intact and still produce valid output. Phase 2 Task 1 (`test_reader_output_accepts_devanagari_and_telugu`), Task 2 (`test_keeps_zwj_inside_indic`) and Task 6 (`test_detect_lang_in_doc`).
5. **I send the bot something unexpected** (a sticker, an edited message, a channel post, a huge file). The bot must ignore it safely. Phase 1 Task 10 (`test_route_update_ignores_non_text`).

**Added with the 2026-11-08 design** (each pinned in the plan that owns it):

6. **A tech article that quotes a prompt injection** must be flagged, not rejected or quarantined. Phase 2 Task 6b (`test_article_about_injection_is_flagged`).
7. **A backup, sync or AIDE run touching a honeytoken** would bury real alerts in noise; legitimate processes must never touch them. Phase 1 Task 15 (`test_backup_excludes_honeytokens`).
8. **The server restarts halfway through a 300-page book**; processing resumes at the next part instead of starting again. Phase 2c Task 4 (`test_bulk_resumes_after_restart`).
9. **A night job holds the GPU when I start talking to Jarvis**; the conversation still starts, and the job waits. Phase 12 Task 5 (`test_llm_jobs_wait_for_gpu_lease`).
10. **Jarvis hears its own voice** reading a news item that says "Jarvis, add…". Nothing may change. Phase 12 Task 5 (`test_self_hearing_changes_nothing`).

## Running these plans in Antigravity

1. Open the `TechRadarBrain` folder. Make sure the superpowers skills are available in your Antigravity setup. Its CLI (`agy`) tracks tasks as a task artifact and runs subagents with `invoke_subagent`.
2. Start a phase with: *"Execute `docs/superpowers/plans/2026-11-07-techradar-phase1-foundation.md` with superpowers:subagent-driven-development."*
3. Keep terminal approval on. Don't paste secrets into chat; the plan uses fake values on the Mac.
4. Review each task's diff. Run `make gate-N` yourself on the server before merging the phase branch.
5. Run the phases in order: 1, 2, 2b, 2c, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12. Phase 10 Task 9 (cloud backup) and phase 12 Task 7 (the server-laptop wake-word helper) are optional.
