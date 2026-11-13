# Security Validation Gates

One row per gate from the overview plan (`docs/superpowers/plans/2026-11-07-techradar-00-overview.md`, "Security gates"). A gate is signed only when every check in its definition has passed, with the evidence named here. Columns follow Phase 1 Task 19.

**Reset on 2026-11-12.** The rows recorded on 2026-11-08 (gates 1, 2, 2b, 2c, 3, 4 and 5 marked PASS) are withdrawn. They cited nmap scans and a received heartbeat although the Linux server did not exist yet, the `make gate-N` targets ran far less than the gate definitions, gate 4 was signed before the web UI was committed, and the rows for gates 6 to 14 named phases that are not in the plans (there are no phases 13 or 14). An audit on 2026-11-10 found the database code had never run against Postgres.

| Gate | Date | Commit | nmap LAN | nmap tailnet | Heartbeat | Notes | Signed |
|---|---|---|---|---|---|---|---|
| gate-1: Secure foundation | | | not run | not run | not set up | NOT PASSED. Verified 2026-11-13 on the TUF at `2f8e7a2`: unit and policy tests (814), all 31 db tests on a fresh Postgres 18 volume, all 8 egress tests (denials logged by Squid), compose policy, import contracts; `make security` clean for semgrep, gitleaks, Trivy config, hadolint and shellcheck; `make security-images` passes (bot, migrate, postgres: 0 fixable HIGH/CRITICAL). Open: OSV-Scanner fails on `filelock` 3.32.7 (fix 4.2.1 is blocked by `litellm` requiring <4; owner decision). Added 2026-11-13: host monitoring installed with `infra/host/install_host.sh` (Falco 0.45.2, audit rules, AIDE, timers, alerter running offline); `check_host.sh` passes except disk encryption (accepted), text-mode boot (owner decision) and the heartbeat (Telegram stage); `make simulate-1` 8 of 8 PASS (rules at `81d26fa`; rerun after the pinned exceptions in `328a829`). Missing: restore test; nmap; heartbeat; disk encryption skipped by owner decision (accepted risk, will show as FAIL). | |
| gate-2: Secure ingest and vault | | | | | | NOT PASSED. Verified: the Intake Gateway now runs on every parser job (2026-11-12); end-to-end fake pipeline on Postgres; import contracts; the parser, worker and fetcher images build and import (2026-11-13; before that the parser and worker images could not start). Missing: `clamav` no-network test, parser no-network runtime test, promptfoo on real models, `make guard-eval` (needs the injection model). | |
| gate-2b: Knowledge index and Ask | | | | | | NOT PASSED. Verified: RAG db tests. Missing: poisoned-note tests on the server, `make rag-eval` with real models. | |
| gate-2c: Library | | | | | | NOT PASSED. Most of the plan's tasks are not built yet. | |
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
