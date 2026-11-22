# Phases 3 to 12: review, wiring and security, build order

**Written:** 2026-11-22 · **By:** Claude (Opus) · **Branch:** `fix/b5-real-gates` (Antigravity's `basic/phases-3-12` fast-forwarded in at `e6dc83f`)

Antigravity handed back the basic work of phases 3 to 12 (`implementation_log.md`). This file says in what order Claude reviews it, wires it into the app and does the security tasks, and who may touch which file while agents run in parallel.

## 1. Rules for every agent

- Work in your own git worktree on your own branch `wire/<area>`, started from `fix/b5-real-gates`. Never push, never check out or commit to `main` or `fix/b5-real-gates`; Claude merges your branch.
- Read first: `AGENTS.md`, this file, the phase plan, the phase's rows in `TODO.md` section 5, the phase's entry in `implementation_log.md`, and `implementations.md` section 8 (the "Leave for Claude" column is your list).
- TDD. One task, one commit, staged by explicit path. Before each commit: `set -o pipefail && make lint test` and `uv run --no-sync lint-imports` (7 contracts kept). Messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never read `secrets/`. No new dependency (`infra/policy/approved_deps.yaml`), no `exclude-newer` change. Never weaken a security test. No new Docker image, no new `infra/squid/allowlist.txt` domain: those need the owner (write them under "Owner" in your report).
- Database tests (`pytestmark = pytest.mark.db`) cannot run on the Mac: write them, make sure they collect (`uv run --no-sync pytest -m db --collect-only -q <file>`); Claude runs them on the TUF.
- Do not edit `TODO.md`, `HANDOFF.md`, `docs/security/gates.md` or `implementation_log.md`: Claude updates them after merging. Report instead.
- Models: Sonnet for wiring and plain code; Opus for anything that guards a door (bot owner checks, API auth, tickets, file or URL intake, containers, network, uploads, group access, voice audio intake).

## 2. Step 1 in every phase: check Antigravity's work against the plan

The first Antigravity run built modules nothing could import. Before wiring, check each task's **Files**, **Interfaces → Produces** and **Step 1** test names against the code. Fix names, signatures and missing tests in place (they are unreleased, so a migration of phases 3 to 12 may be edited in place, as `0004b` was). Data must live in Postgres; logic takes an `AsyncSession` and `now`. Delete leftovers of the first run that the plan replaced. Search for `WIRING(claude)` notes.

## 3. Blocked until the owner decides (do not build; list in the report)

- Packages not approved: `fsrs`, `spacy`, `wordfreq`, `en_core_web_sm`, `faster-whisper`, Kokoro, `transformers`, `torch`, Pipecat, `sympy`, `fastmcp`, `onnxruntime(-web)`, `python-magic`, `yara-python`, the Phase 4 web stack (Next.js 16, Tailwind v4, shadcn/ui, AI SDK, Streamdown, Playwright, axe). Keep these behind the Protocols Antigravity wrote.
- New container images (LanguageTool, SearXNG, changedetection, voice-worker, voice-live, jarvis) and new egress domains.
- Web screens (`apps/web/**`) until the pinned scaffold exists.
- Internet stage, last: real Telegram, feeds, models, downloads.

## 4. Waves

| Wave | Area | Model | Branch | Owns these shared files |
|---|---|---|---|---|
| 1 | Phase 2c in-flight: starter packs (Task 9) and quarantine mounts | Opus | main folder | `library/packs.py`, `fetcher/packs_cycle.py`, `bot/packs_command.py`, quarantine hunks |
| 1 | Phase 3 review and wiring (all but Task 3 intake) | Sonnet | `wire/phase3` | jobs, routing, callbacks for Phase 3 |
| 1 | Phase 5 review and wiring | Sonnet | `wire/phase5` | jobs, routing, callbacks for Phase 5 |
| 1 | Phase 4 API service: owner check, routes, OpenAPI, tickets (Tasks 1, 2, 2b) | Opus | `wire/phase4-api` | `src/techradar/api/**` |
| 2 | Phases 7, 8, 11 review and wiring | Sonnet | `wire/phase7`, `wire/phase8`, `wire/phase11` | |
| 2 | Intake doors: Phase 3 Task 3 (links, PDFs, pasted text), Phase 8 past papers and screenshots, Phase 6 Task 1 voice intake | Opus | `wire/intake` | `intake/**`, `parser/**` |
| 3 | Phases 6, 9, 10, 12: the parts not blocked | Sonnet, Opus for group access, tickets, Jarvis permissions | `wire/phase6` ... | |
| 4 | Migrations `0005` to `0014` and all db tests on the TUF; gates that can run offline | Claude | | |

Shared files (`worker/tasks.py`, `bot/routing.py`, `bot/callbacks.py`, `bot/main.py`, `db/models.py`, `compose.yaml`) are edited by several branches. Keep every edit additive and in your phase's own block (a comment banner such as `# --- Phase 3: practice ---`), so merges stay simple.
