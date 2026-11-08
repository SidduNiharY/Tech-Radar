# Agent Guidelines for TechRadar Brain

## 1. What This Repo Is
TechRadar Brain is a local-first learning system and personal AI second brain that serves five concurrent learning goals (Full-stack AI developer, GATE, Govt/Bank exams, World understanding, and English/Soft skills) through automated ingestion, sandboxed intake parsing, RAG knowledge indexing, active practice, and Jarvis voice assistance. For full architectural details, consult [05_Architecture.md](05_Architecture.md) and the implementation blueprints in [docs/superpowers/plans/2026-11-07-techradar-00-overview.md](docs/superpowers/plans/2026-11-07-techradar-00-overview.md).

## 2. Commands
- `make lint` : Run Ruff linting and formatting verification.
- `make test` : Execute unit test suite with mock protocol fakes.
- `make security` : Run Semgrep custom rules, Gitleaks, and policy audits.
- `make gate-N` : Execute full validation gate for Phase N (e.g., `make gate-1`).

## 3. Non-Negotiable Security Rules
1. **Ports:** Every published port is bound to `"127.0.0.1:<host>:<container>"`. Never bind to `0.0.0.0` or expose public listeners (SEC-02).
2. **Container Baseline:** Not root (`user: "1000:1000"`), `cap_drop: ["ALL"]`, `security_opt: ["no-new-privileges:true"]`, `read_only: true` with `tmpfs` for scratch, memory/CPU/PID limits set, log rotation enabled. Never use `privileged: true`, `network_mode: host` (except `voice-live`), or mount `/var/run/docker.sock`, `/home`, or `/` (SEC-07).
3. **Parser Isolation:** `parser` container runs with `network_mode: none`, `read_only: true`, `tmpfs: ["/tmp"]`, `cap_drop: ["ALL"]`, and a 120-second timeout per job (SEC-06). Never give the parser network access.
4. **Squid Egress:** Outbound HTTP/HTTPS is permitted exclusively through Squid's allowlist (`infra/squid/allowlist.txt`). No other container communicates directly with the internet (SEC-05).
5. **Telegram Bot Authorization:** The Telegram bot responds exclusively to `TR_TELEGRAM_OWNER_CHAT_ID` (and approved study groups from Phase 9). Strangers get zero response (SEC-26).
6. **Secrets Handling:** Secrets reside exclusively as files in `secrets/`, mode `0600`, mounted as Docker secrets. Never read, print, log, or commit files in `secrets/` (SEC-10).
7. **Pinned Immutability:** Pinned exact versions for packages, Docker base images pinned by immutable SHA-256 digest (`name:version@sha256:...`), and GitHub Actions pinned to full 40-character commit SHAs (SEC-08, SEC-33, SEC-55).
8. **Approved Model Formats:** Models only from Ollama library or approved Hugging Face orgs in GGUF or safetensors format. `trust_remote_code` disabled; no pickle/`torch.load` of untrusted files (SEC-23).
9. **Reader Isolation:** The reader model has zero tool bindings; the writer is plain deterministic code and never directly processes raw untrusted text (SEC-16, SEC-22).
10. **Compose Policy Gate:** Every new or modified Compose service must pass `tests/security/test_compose_policy.py`.
11. **Dependency Gate:** Never add a dependency to `pyproject.toml` or `package.json` without pre-approval in `infra/policy/approved_deps.yaml` (SEC-52).
12. **Agent Capability Restriction:** Use only the MCP servers, skills, and plugins listed in the allowlists below, pinned to exact versions or commits (SEC-53). Never install unvetted tools.
13. **Integrity:** Never disable, bypass, or weaken a security test to make it pass.

## 4. Workflow
One task, one commit. Always run `make lint test` before committing.

## 5. Allowed MCP Servers
<!-- mcp-allowlist:start -->
| Name | Command | Version | Access | Why |
|---|---|---|---|---|
<!-- mcp-allowlist:end -->

## 6. Allowed Skills and Plugins
<!-- skills-allowlist:start -->
| Name | Kind | Source | Commit | SHA256 | Why |
|---|---|---|---|---|---|
| `using-agent-skills` | skill | local | pinned | - | Meta-skill for skill discovery and discipline |
| `dispatching-parallel-agents` | skill | local | pinned | - | Parallel execution for independent problem domains |
| `subagent-driven-development` | skill | local | pinned | - | Plan execution with task isolation |
| `executing-plans` | skill | local | pinned | - | Systematic TDD plan execution |
| `test-driven-development` | skill | local | pinned | - | RED-GREEN-REFACTOR execution rigor |
<!-- skills-allowlist:end -->
