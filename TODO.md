# TechRadar Brain: TODO

**Status date:** 2026-11-24 · **Branch:** `fix/b5-real-gates` at `30fd052`+ (pushed; never merge to `main` without the owner) · **Rough progress:** about half of the whole project.

This file is the tracker. The task details are in the phase plans under `docs/superpowers/plans/`. The brief for Antigravity is [`implementations.md`](implementations.md). Server steps are in `TODO_TUF_AND_MAC.md`; gate sign-offs are in `docs/security/gates.md`.

The tick list this file held until 2026-11-12 is gone on purpose: a tick there meant only "a small module with fake-based tests exists", often under a different name than the plan. It is still in git (`git show f2631a7:TODO.md`).

---

## 1. Who does what

| Who | Does |
|---|---|
| **Antigravity** | The basic work of phases 3 to 12: plain logic, data shapes, message text, database models and migrations, unit tests. Exactly as [`implementations.md`](implementations.md) says, on its own branch. |
| **Claude** | Phase 2c to the end; then, for every phase Antigravity hands back: review, wiring (jobs, bot handlers, API, containers), every security task, the database tests on the TUF, the gaps. |
| **Owner** | Sudo and secrets on the TUF, approvals (dependencies, URLs), the checks only a person can do (50 MCQs, real book, nmap), signing gates. |

## 2. Status by phase

Three levels, in this order. A phase is done only when all three are "yes" and its gate is signed.

- **Basic**: the plan's modules exist under the plan's names, with unit tests.
- **Wired**: migrations, jobs, bot handlers and API routes call them, so it runs inside the app.
- **On TUF**: its database, egress and end-to-end tests have passed on the server.

| Phase | Basic | Wired | On TUF | Next step, and whose |
|---|---|---|---|---|
| 1 Foundation | yes | yes | partly | Owner: nmap from the Mac, Telegram stage (heartbeat), `filelock` decision. Then sign gate 1. |
| 2 Ingest | yes | partly | partly | Internet stage: real feeds, real models, `guard-eval`, red-team. |
| 2b RAG and Ask | yes | partly | partly | Internet stage: `rag-eval` in live mode. |
| 2c Library | yes (11 of 11) | yes | db tests pass | Claude: `make simulate-2c`, `make gate-2c`, OCR timing on the TUF. Owner: pack URLs, bot database role. |
| 3 Briefing and practice | yes | yes, except Task 3 | db tests pass | Claude (Opus): Task 3 intake (links, PDFs, pasted text); gate 3. Owner: changedetection image, exam hosts. |
| 4 Web app | yes (tables, schemas) | API Tasks 1, 2, 2b | db tests pass | Claude: Task 5b API routes. Owner: approve the web stack, then scaffold, screens, containers, gate 4. |
| 5 Planner | yes | yes | db tests pass | Owner: compose mounts (`data/status` for the worker, vault for `/skill`); backup script writes `backup.json`. Claude: gate 5. |
| 6 Voice and English | yes | no | 1 db test fails | Claude: wire English practice; fix `voice/feedback.py` (wrong `complete` call). Owner: approve whisper, Kokoro, wav2vec2, LanguageTool image. |
| 7 World | yes | yes, except fetch and Task 8 | db tests pass | Claude (Opus): Task 8 fact-checker. Owner: Wikipedia and World Bank domains, SearXNG image, a separate night worker or not. |
| 8 Exams | yes | yes, except intake | db tests pass | Claude (Opus): past papers, screenshots, answer keys, cutoffs folder reading. |
| 9 Live voice and group | small parts | no | no | Claude: group mode (Opus). Owner: Pipecat, `sympy`. |
| 10 Models and extras | small parts | no | no | Claude: registry, switch, rollback, bench, digest jobs. Owner: `fastmcp`. |
| 11 Feedback | yes | no | db tests pass | Claude: buttons, jobs, rules, reports. |
| 12 Jarvis | small parts | no | db tests pass | Claude: router, permission levels, tickets (Opus). Owner: `onnxruntime-web`. |

"Old code" means the modules from the first Antigravity run. They sit under other names and keep data in memory instead of the database, so nothing can call them. `implementations.md` section 6 says what replaces each one.

Migrations today: `0001` to `0004b`. The plans need `0005` to `0014`.

## 3. State of the tree (2026-11-24)

- Antigravity's `basic/phases-3-12` was merged on 2026-11-22. Phases 2c, 3, 4 (API), 5, 7 and 8 were reviewed and wired by worktree agents (Opus for security, Sonnet for the rest) and merged through `integrate/wave1`. Order and rules: `docs/superpowers/plans/2026-11-22-phases3-12-wiring-order.md`.
- `make lint test`: 2160 passed on the Mac; 7 import contracts kept. On the TUF all 277 db tests pass except `tests/voice/test_jobs.py::test_audio_deleted_after_24h_unless_kept` (Phase 6 code bug). Migrations `0001` to `0014` upgrade and downgrade on the TUF.
- `tests/test_settings.py::test_settings_requires_owner_chat_id` fails on the TUF only, because the TUF's `.env` sets the owner id.
- Bugs fixed while wiring: every periodic job now accepts procrastinate's `timestamp=` (17 jobs crashed on first run); the worker and bot procrastinate connectors could not open their pool; drill answer keys could be wrong; several `enqueue_message` calls could never send; flagged items fed night prompts.
- Owner decisions found while wiring: the bot connects as the `app` role but compose gives it only `tr_ro_password` (`/quarantine`, `/packs`, practice buttons need writes); the API image needs python-telegram-bot (`messaging/outbox.py`).

## 4. Phase 2c: what is done, what is left

| Plan task | State |
|---|---|
| 1 Tables, schema fields, settings | Done. Database tests pass on the TUF. |
| 2 Library inbox intake | Done. No-follow opens, hash while copying, 50 files a run. |
| 3 Gateway steps 4 to 6 | Done. Zip and Office checks, media probe, pixel rebuild for flagged PDFs. |
| 4 Big PDFs in parts, chapters, night window | Done. Parts are 25 pages; one part took 58 s in the real image. |
| 5 Videos: audio, frames, slides | Done and hardened. Not yet timed with OCR on the TUF. |
| 6 Indexing | Done. |
| 7 Summaries, Ready message, book evals | Done. Retries, give-up after 3 tries, night budget. |
| 8 RAG upgrades | Done (`c2c0666`): reply to a Ready message asks that book; hard questions go to the night model. Its database test has not run on the TUF. |
| 9 Starter packs | **In progress, uncommitted.** |
| 10 Quarantine | Done: notice, `/quarantine`, two-step release, delete. **Compose mounts for it are in progress.** |
| 11 Gate 2c | Wired (`310e75d`, `00823ea`). **Not run on the TUF.** |

Left for Claude, in order:

- [ ] Finish and review Task 9 (starter packs) and the quarantine mounts; commit; push.
- [ ] On the TUF: pull, `make test-db`, `make security` (first shellcheck of `phase2c.sh`), `make simulate-2c`, `make gate-2c`.
- [ ] Time on the TUF: OCR of 20 frames in one media job, and 25 dense PDF pages. Both must stay under 120 s.
- [ ] Decide and fix: a flagged document stays `processing` for ever (the summaries job skips it).
- [ ] Held news and Telegram items cannot be released yet (the bot has no gate); only library documents can.
- [ ] A quarantined video is copied whole once per segment, and every segment job repeats the probe and the antivirus scan. Make it once per file.
- [ ] Retention: when a held library item expires, its original and its row stay.
- [ ] `init: true` for the parser service (it reaps children in code today).
- [ ] The summaries job ends without a retry when the model call raises; two books can overlap if the `llm` queue ever runs more than one job.
- [ ] Remove the old 2c modules once nothing imports them: `library/summarizer.py`, and check `library/models.py` and `library/media.py`.
- [ ] Bring the plan text in line with the code (note folders are `<slug>-<doc_id>`; `ask_night` takes no chat id).
- [ ] Update `HANDOFF.md`, `TODO_TUF_AND_MAC.md` and `docs/security/gates.md` when gate 2c has run.

Waiting on the internet stage (the gate prints these as WAITING): the Ready message and quarantine notices in the real bot, summaries and book evals with real models, pack downloads.

## 5. Phases 3 to 12: task tracker

One row per plan task. **Basic** is Antigravity's column, **Wired** is Claude's. Values: `no`, `old` (old module, to be replaced), `part`, `yes`, `claude` (no basic part: Claude does the whole task). Update the cell and add the commit when it changes.

### Phase 3: Briefing, practice, exam alerts (`0005_practice`)

| Task | Basic | Wired |
|---|---|---|
| 1 Briefing composer and schedule | part (text and selection exist; no tables, no run function) | no |
| 2 "My take" replies | old | no |
| 3 Links, PDFs and pasted text from me | claude | no |
| 4 Facts-first MCQs, two-family check | old | no |
| 5 Quiz, flashcards, mistakes notebook | old | no |
| 5b Mark chapter as read, chapter cards | old | no |
| 6 Grammar set and vocabulary | old | no |
| 7 Exam notification watcher | old (text parts only) | no |
| 8 Monthly capsule and review inbox | no | no |
| 8b Outdated facts retire cards and MCQs | no | no |
| 9 Gate 3 | n/a | no |

### Phase 4: Web app v1 (`0006_web`)

| Task | Basic | Wired |
|---|---|---|
| 1 API service, service token, owner check | claude | part (fails closed since 2026-11-12) |
| 2 API routes and OpenAPI export | part (tables and schemas are Antigravity's) | no |
| 2b Confirmation tickets | claude | no |
| 3 Next.js scaffold, supply chain, headers | claude | no |
| 4 Server-only API client, streaming | claude | no |
| 5 Screens and design system | old (placeholder pages) | no |
| 5b Library, Quarantine, Security screens | old | no |
| 6 Containers, `edge` network, Tailscale Serve, Langfuse | claude | no |
| 6b Cross-site and host hardening | claude | no |
| 6c Uploads from the Library screen | claude | no |
| 7 Web security suite and gate 4 | claude | no |

### Phase 5: Planner, progress, reliability (`0007_planner`)

| Task | Basic | Wired |
|---|---|---|
| 1 Study sessions, 1-7-30 revisions | old | no |
| 2 One-tap energy check-in | no | no |
| 3 Daily plan in the briefing | old | no |
| 4 Progress screen and weekly review | part | no |
| 5 Skill map updates | part | no |
| 6 Failure alerts and health checks | part | no |
| 7 Catch-up test and gate 5 | claude | no |

### Phase 6: Voice Coach v1 and English (`0008_voice`)

| Task | Basic | Wired |
|---|---|---|
| 1 Voice note intake | claude | no |
| 2 `voice-worker` service and transcription | claude (Antigravity: result shapes only) | no |
| 2b Library audio transcription | claude | no |
| 3 Speech metrics in code | old | no |
| 4 LanguageTool grammar checks | old (rule list, not LanguageTool) | no |
| 5 Pronunciation scoring | no | no |
| 6 Fixes, spoken feedback, analysis job, retention | no | no |
| 7 Writing practice | no | no |
| 8 Story bank, reading quiz, listening, reflection | no | no |
| 9 Voice report screen | no | no |
| 9b English practice time | no | no |
| 10 Voice evals and gate 6 | no | no |

### Phase 7: Understanding and World (`0009_world`)

| Task | Basic | Wired |
|---|---|---|
| 1 Night queue | claude | no |
| 2 Wikipedia background, foundation pages | no | no |
| 3 Weekly deep dive | no | no |
| 4 Glossary, timelines, cause-and-effect chains | old | no |
| 5 Politics: facts apart from opinions | no | no |
| 6 Opinions and predictions log | old | no |
| 7 Economy dashboard data | old | no |
| 8 Forward fact-checker with approval | claude (old in-memory list exists) | no |
| 9 World screen | old | no |
| 10 Gate 7 | n/a | no |

### Phase 8: Exams (`0010_exams`)

| Task | Basic | Wired |
|---|---|---|
| 1 Syllabus topics and coverage | old | no |
| 2 GATE past-paper bank | no | no |
| 2b Sources for every syllabus topic | no | no |
| 3 Code-generated drills | old (3 generators) | no |
| 4 Daily drills on Telegram | no | no |
| 5 Mock-test analyser | no | no |
| 6 Cutoffs and topic weightage | no | no |
| 6b Official answer keys | no | no |
| 7 Final 30 days mode | no | no |
| 8 Exams screen | no | no |
| 9 Gate 8 | n/a | no |

### Phase 9: Study smarter and live voice (`0011_live_group`)

| Task | Basic | Wired |
|---|---|---|
| 1 Handwritten notes, safe maths checks | claude | no |
| 2 Study group mode | claude (Antigravity: leaderboard and text) | no |
| 3 The `voice-live` service | claude | no |
| 4 Live voice screen | no | no |
| 5 After-session analysis, shadowing pitch | no | no |
| 6 Interview briefs, "Know yourself" pack | no | no |
| 7 Gate 9 | n/a | no |

### Phase 10: Models admin and tech extras (`0012_models`)

| Task | Basic | Wired |
|---|---|---|
| 1 Model registry, switch, rollback | claude | no |
| 2 Approved models, owner-run downloads | claude | no |
| 3 GPU stats service and fit estimate | old (fit only) | no |
| 4 Test bench | no | no |
| 5 Models screen admin | claude | no |
| 6 Weekly release digest | no | no |
| 7 "Rising fast" trends | no | no |
| 8 Read-only vault MCP server | claude (plain class exists; `fastmcp` not approved) | no |
| 9 Optional cloud fallback | claude, only if the owner wants it | no |
| 10 Gate 10 | n/a | no |

### Phase 11: Feedback and self-improvement (`0013_feedback`)

| Task | Basic | Wired |
|---|---|---|
| 1 Feedback, profile, improvement tables | no | no |
| 2 Feedback buttons and action log | old | no |
| 3 Edits to generated notes | no | no |
| 4 Bounded weights and ranking | old | no |
| 5 Nightly pattern finding | no | no |
| 6 Weekly review and improvement report | claude (rules); Antigravity: report text | no |
| 7 Answers in my way: profiles, mastery, liked examples | no | no |
| 8 Regression cases, search tuning | old | no |
| 9 "Which is better?" pairs, FSRS optimizer | no | no |
| 10 My profile page | no | no |
| 11 Gate 11 | n/a | no |

### Phase 12: Jarvis (`0014_jarvis`)

| Task | Basic | Wired |
|---|---|---|
| 1 Jarvis tables | no | no |
| 2 Skills and the router | claude (old intent matcher exists) | no |
| 3 Permission levels, voice tickets, write limit | claude (old executor exists) | no |
| 4 `jarvis` service, `api-voice` socket | claude | no |
| 5 Jarvis mode in `voice-live`: echo, barge-in, GPU lease | claude | no |
| 6 Wake word in the Mac's Jarvis tab | part (browser code exists) | no |
| 7 Wake-word helper on the server (optional) | claude | no |
| 8 The ten skills | no | no |
| 9 Morning greeting | no | no |
| 10 Conversation memory | claude | no |
| 11 Jarvis screen, orb on every screen | old | no |
| 12 Voice red-team and gate 12 | claude | no |

## 6. Owner's list

- [ ] Tailscale SSH asks for a browser check again from time to time. Approve the link when Claude shows it.
- [ ] Phase 2c: check each starter-pack URL in a browser, then add it; set up the Library folder in Syncthing; on the TUF `mkdir` and `chown 1000:1000` for `data/library-inbox`, `data/library-packs`, `data/library`.
- [ ] Phase 2c: say whether Claude may run the "restart `worker-bulk` after 3 parts" check against the real stack.
- [ ] Gate 1 leftovers: nmap from the Mac, `filelock` decision, text-mode boot decision.
- [ ] Dependencies the later phases need and that are **not approved** yet (`infra/policy/approved_deps.yaml`). Nothing that needs them can be finished until you decide:
  - Phase 3: `fsrs` (py-fsrs), `spacy`, `wordfreq`, the `en_core_web_sm` model wheel.
  - Phase 4: the web stack the plan names (Next.js 16, Tailwind v4, shadcn/ui, AI SDK, Streamdown, Playwright, axe). Today the web folder has Next.js 14 with loose versions and no lock file.
  - Phase 6: `faster-whisper`, Kokoro (ONNX), `transformers` and `torch` for wav2vec2.
  - Phase 9: Pipecat, `sympy`.
  - Phase 10: `fastmcp`. Phase 12: `onnxruntime-web`.
  - Still open from Phase 2: `python-magic`, `yara-python`.
- [ ] Decisions: GATE paper (CS or DA), when to merge the branch, the backup destination.
- [ ] Internet stage, last: the two Telegram bots and their secrets, the alerter, real feeds and models, the heartbeat.

## 7. Where things run

| Thing | Mac (development) | TUF (server, Ubuntu, host `jarvis`) |
|---|---|---|
| Unit tests, lint, import contracts | `make lint test`, `uv run --no-sync lint-imports` | same |
| Database tests (`-m db`) | cannot run | `make test-db` (needs `TR_DB_TESTS_MAY_WIPE=1`, set by the target) |
| Egress tests, attack simulations, gates | cannot run | `make test-egress`, `make simulate-N`, `make gate-N` |
| Images, real models | no | yes |

Code changes happen on the Mac, are pushed, then pulled on the TUF. Nothing is edited on the TUF.
