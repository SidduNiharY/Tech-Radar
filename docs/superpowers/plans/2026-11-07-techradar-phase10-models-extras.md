# TechRadar Brain Phase 10: Models Admin and Tech Extras Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** It ends with `make gate-10` (phases 11 and 12 follow). It delivers:
- full model control from the web app: switch, fit check, test bench, playground, history and rollback
- downloads from an approved list only, pulled by me
- a weekly release digest checked against my lockfiles
- "Rising fast" trend alerts with a "why is everyone talking about this?" answer
- a read-only vault MCP server for Claude Code on the Mac
- optional cloud backup wiring, off by default

**Architecture:**
- **Model registry:** lives in Postgres and replaces `roles.yaml` as the source of truth; `roles.yaml` remains the seed. Changes need a passed test, the family rule, my identity and a typed confirmation. The worker reloads its router on `NOTIFY`.
- **GPU numbers:** come from a tiny read-only `gpu-stats` service.
- **Downloads:** never triggered from the web; requests queue until I run `make pull-approved`.
- **MCP server:** runs on the Mac over stdio and reads only the synced vault files.

**Tech Stack:** Postgres LISTEN/NOTIFY, nvidia-ml-py, packaging, PyYAML, FastMCP 4, Next.js.

**Spec:** [02](../../../02_Tech_Stack_and_Security.md) §5.14 (the Models screen), §5.12 (optional cloud) · [01](../../../01_Idea_and_Daily_Use.md) (release digest, Rising fast, MCP access) · [03](../../../03_Local_Models_Research.md) test plan pass lines · [05](../../../05_Architecture.md) SEC-23, SEC-30, SEC-35 · [overview](2026-11-07-techradar-00-overview.md) D10, D29

## Global Constraints

- The overview's Global Constraints 1–16 apply.
- **Model switches:** need `confirm == "<role>:<tag>"` typed by me, an approved and installed tag, a passed `model_tests` row for that role and tag, and checker family ≠ worker family. Every change is written to `audit_log` with my Tailscale login (SEC-30).
- **Tickets (SEC-56, D43):** every admin action also consumes a one-time ticket from phase 4 (`models.change`, `models.rollback`, `models.delete`), valid for 60 s in the same browser session. A model switch is a big change, so Jarvis can never confirm one by voice (phase 12).
- **Downloads:** only tags in `infra/models/approved.yaml`, pulled by `make pull-approved` through the `ollama-pull` profile (D10, D29).
- **Playground:** prompts up to 2,000 characters, `num_ctx` up to 8192, temperature 0–1; results aren't saved; one run at a time.
- **MCP server:** read-only. Two tools only (`search_notes`, `read_note`); `.md` files inside the vault only, up to 200 KB, no symlinks.
- **Cloud backup:** absent unless `TR_ALLOW_CLOUD_LLM=true`. Only jobs in `CLOUD_ALLOWED_JOBS`; monthly cap `TR_CLOUD_MONTHLY_USD` (default 2).

## Review Focus

1. **Switching to a model that's approved but not yet pulled** is refused with "Pull it first (make pull-approved)". Task 1 `test_switch_requires_installed`.
2. **A bad switch** is undone in one click and the previous model is back. Task 1 `test_rollback_restores_previous`.
3. **A package with no newer release**, or a pre-release only, gets no alert. Task 6 `test_prereleases_ignored`.
4. **A term that's always popular** ("India") isn't flagged as rising. Task 7 `test_steady_term_not_rising`.
5. **Claude Code asking the MCP server for `../../.ssh/id_rsa`** is refused. Task 8 `test_read_note_traversal_refused`.

---

### Task 1: Model registry, switch, rollback and live reload

**SEC:** SEC-23, SEC-30

**Files:**
- Create: `src/techradar/models/__init__.py`, `src/techradar/models/registry.py`, `src/techradar/db/migrations/versions/0012_models.py`
- Modify: `src/techradar/llm/roles.py` (`load_roles_from_db`), `src/techradar/worker/app.py` (LISTEN `model_changed`, rebuild the router)
- Test: `tests/models/test_registry.py` (marker `db`)

**Interfaces:**
- Produces:
  - **Migration `0012_models`:**
    - `model_registry` (`role` primary key, `ollama_tag`, `family`, `updated_at`)
    - `model_changes` (`id`, `role`, `old_tag`, `new_tag`, `test_id` null, `actor`, `reason`, `at`, `rolled_back` bool)
    - `model_tests` (`id`, `role`, `tag`, `metrics` jsonb, `passed` bool, `at`)
    - `model_requests` (`id`, `tag`, `requested_at`, `status` (`pending`, `pulled`, `rejected`), `note`)
    - `playground_runs` (`id`, `role`, `prompt`, `output` null, `status`, `created_at`)
    - `trend_counts` (`day`, `term`, `count`; primary key on `day`, `term`)
  - `class ChangeResult(BaseModel)`: `ok: bool`, `message: str`, `change_id: int | None`
  - `async def set_role_model(session, role: Role, tag: str, family: str, *, test_id: int, actor: str, reason: str, installed: set[str]) -> ChangeResult`. It checks:
    1. The tag is in the installed set (from `/api/tags`); otherwise `Pull it first (make pull-approved)`.
    2. The test passed for this role and tag.
    3. The family rule.

    Then it writes the change and the registry row, and runs `NOTIFY model_changed`.
  - `async def rollback(session, change_id: int, actor: str) -> ChangeResult`
  - `async def load_roles_from_db(session, fallback: Path) -> dict[Role, RoleModel]`: uses `roles.yaml` if the registry is empty

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.db
async def test_switch_requires_installed(session):
    r = await set_role_model(session, Role.WORKER, "qwen3.5:9b", "qwen", test_id=1, actor="me", reason="t", installed={"qwen3.5:4b"})
    assert not r.ok and r.message == "Pull it first (make pull-approved)"

@pytest.mark.db
async def test_switch_requires_passed_test(session): ...
@pytest.mark.db
async def test_family_rule_enforced(session): ...                  # checker gemma → worker gemma refused
@pytest.mark.db
async def test_rollback_restores_previous(session): ...
@pytest.mark.db
async def test_notify_triggers_reload(session, worker_listener): ...
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -m db tests/models/test_registry.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the migration, registry, loader and worker listener**

- [ ] **Step 4: Run the tests**

Run: `docker compose run --rm migrate && uv run pytest -m db tests/models -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar tests/models && git commit -m "feat(models): registry with tested switches, rollback and live reload"
```

### Task 2: Approved models and owner-run downloads

**SEC:** SEC-23, D10, D29

**Files:**
- Create: `infra/models/approved.yaml`, `src/techradar/models/approved.py`, `scripts/pull_approved.py`
- Modify: `Makefile` (add `pull-approved`)
- Test: `tests/models/test_approved.py`

**Interfaces:**
- Produces:
  - **`approved.yaml` entries:** `{tag, family, roles: [..], note}`. Initial list: `qwen3.5:4b`, `qwen3.5:9b`, `gemma4:e2b-it-qat`, `gemma4:e4b-it-qat`, `gemma4:12b-it-qat`, `bge-m3`, and `gemma4:26b-a4b-it-qat` (note: "only after the 32 GB RAM upgrade").
  - `def is_approved(tag: str, role: Role, approved: Sequence[ApprovedEntry]) -> ApprovedEntry | None`
  - `POST /v1/models/requests` takes `{tag, role}`. Approved tags are queued (`pending`); others are refused with `Not on the approved list.`
  - **`make pull-approved`:** lists pending approved requests with their sizes, asks `y/N`, runs the `ollama-pull` profile for each, and marks them `pulled`.

- [ ] **Step 1: Write the failing tests**

```python
def test_unapproved_refused(): assert is_approved("random/model:latest", Role.WORKER, APPROVED) is None
def test_role_must_match(): assert is_approved("bge-m3", Role.WORKER, APPROVED) is None
def test_pull_script_dry_run(tmp_path): ...   # --dry-run prints the pending tags and never runs docker
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/models/test_approved.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the module, route, script and Makefile target**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add infra/models src/techradar scripts Makefile tests && git commit -m "feat(models): approved list and owner-run downloads"
```

### Task 3: GPU stats service and fit estimate

**SEC:** SEC-07

**Files:**
- Create: `src/techradar/gpu_stats/__init__.py`, `src/techradar/gpu_stats/server.py`, `src/techradar/models/fit.py`
- Modify: `compose.yaml` (add `gpu-stats`: GPU reservation `capabilities: [utility]`, network `tools`, read-only, no secrets), `src/techradar/api/routes/models.py` (add GPU data to the status), `infra/falco/expected_programs.yaml` (`gpu-stats: [python]`; rerun the generator)
- Test: `tests/models/test_fit.py`, `tests/gpu_stats/test_server.py`

**Interfaces:**
- Produces:
  - **`gpu-stats`:** `GET /stats` returns `{"name": str, "mem_total": int, "mem_used": int, "temp_c": int, "util_pct": int}` through nvidia-ml-py; a stdlib `http.server` bound to `0.0.0.0:9400` on `tools` only
  - `def kv_estimate(ctx: int) -> int` returns `ctx * 40 * 1024` bytes (a conservative estimate, shown as "estimate" in the UI)
  - `def estimate_fit(model_bytes: int, ctx: int = 8192, vram_bytes: int = 6 * 2**30, headroom: int = 700 * 2**20) -> Literal["fits","split","mostly_ram"]`: `fits` if model + KV cache + headroom ≤ VRAM; `split` if the model alone is ≤ 2 × VRAM; otherwise `mostly_ram`
  - **Measured beats estimated:** if `model_tests` holds a measured fit for the tag, the UI shows that instead.

- [ ] **Step 1: Write the failing tests**

```python
def test_estimate_fit():
    gb = 2**30
    assert estimate_fit(int(3.3 * gb)) == "fits" and estimate_fit(int(7.2 * gb)) == "split" and estimate_fit(16 * gb) == "mostly_ram"

def test_stats_handler_shapes_json(monkeypatch): ...   # fake NVML → keys present, ints
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/models/test_fit.py tests/gpu_stats -v`
Expected: FAIL

- [ ] **Step 3: Implement the service, fit function and route change**

- [ ] **Step 4: Run the tests and the policy check**

Run: same as Step 2, then `uv run pytest tests/security/test_compose_policy.py -q`.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar compose.yaml infra/falco tests && git commit -m "feat(models): GPU stats service and fit estimate"
```

### Task 4: Test bench

**Files:**
- Create: `src/techradar/models/bench.py`, `evals/sets/README.md` (formats), `evals/sets/*.example.yaml`
- Modify: `src/techradar/worker/tasks.py` (add the `bench_job` queue `eval`, concurrency 1, preferring the night window)
- Test: `tests/models/test_bench.py`

**Interfaces:**
- Produces:
  - **Test sets** (my real sets are git-ignored): `tagging.yaml` (100 labelled items), `json_extract.yaml` (50 articles), `mcq_checker.yaml` (50 MCQs, 25 with wrong keys), plus the phase 2b RAG set and the phase 6 voice clips.
  - **Pass lines (from 03):**
    - `def passes_worker(m) -> bool`: `tag_agreement >= 0.90 and json_first_try >= 0.98`
    - `def passes_checker(m) -> bool`: `wrong_key_catch >= 0.90 and false_flag <= 0.05`
    - `def passes_embed(m) -> bool`: the phase 2b RAG thresholds
    - `def passes_night(votes) -> bool`: I prefer the candidate in at least 2 of 3 blind A/B prompts
  - `async def run_role_test(role: Role, tag: str, deps) -> TestResult(metrics: dict, passed: bool)`: stored in `model_tests`
  - **Blind A/B:** `POST /v1/models/ab/{test_id}/vote` takes `{prompt_index, choice: "A"|"B"}`; the A/B order is randomised and stored.

- [ ] **Step 1: Write the failing tests**

```python
def test_pass_lines():
    assert passes_worker({"tag_agreement": 0.91, "json_first_try": 0.99}) and not passes_worker({"tag_agreement": 0.89, "json_first_try": 1.0})
    assert passes_checker({"wrong_key_catch": 0.92, "false_flag": 0.04}) and not passes_checker({"wrong_key_catch": 0.92, "false_flag": 0.06})
    assert passes_night([True, True, False]) and not passes_night([True, False, False])
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/models/test_bench.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the bench, job and vote route**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar evals/sets tests/models && git commit -m "feat(models): role test bench with pass lines and blind A/B"
```

### Task 5: Models screen admin

**SEC:** SEC-27, SEC-28, SEC-30

**Files:**
- Create: `src/techradar/api/routes/models_admin.py`, `apps/web/src/components/models/{SwitchDialog,TestBench,Playground,History}.tsx`, `apps/web/tests/models-admin.spec.ts`
- Modify: `apps/web/src/app/(app)/models/page.tsx` (tabs), `tests/web_mock.py`
- Test: `tests/api/test_models_admin.py` (marker `db`), `apps/web/tests/models-admin.spec.ts`

**Interfaces:**
- Produces:
  - **Routes:**
    - `GET /v1/models/registry`
    - `POST /v1/models/changes` takes `{role, tag, reason}` and returns `{change_id, summary, fit, test: {id, passed} | null}`; nothing is applied yet
    - `POST /v1/models/changes/{id}/confirm` takes `{confirm, token}`:
      - 400 unless `confirm == f"{role}:{tag}"`
      - then `run_confirmed` on the ticket created with the pending change (phase 4 Task 2b), which calls `set_role_model`
      - an expired or replayed ticket gives 409
    - `POST /v1/models/changes/{id}/rollback`
    - `POST /v1/models/playground` takes `{role, prompt ≤2000, think: bool, num_ctx ≤8192, temperature 0–1}` and returns `{run_id}`
    - `GET /v1/models/playground/{run_id}`
  - **Audit:** every admin route writes `audit_log(actor=<Tailscale login>, action, detail)`.
  - **UI:**
    - Rows per role, with a change dropdown (approved and installed tags only) and a fit badge.
    - `SwitchDialog` requires typing `role:tag`.
    - Tabs: Test bench (run, results, A/B voting), Playground, History (rollback).
    - Toast and Telegram alert on failures.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.db
def test_replayed_ticket_refused(client, pending_change, used_ticket):
    assert client.post(f"/v1/models/changes/{pending_change}/confirm", headers=AUTH, json={"confirm": "worker:qwen3.5:9b", "token": used_ticket}).status_code == 409

def test_confirm_text_must_match(client, pending_change):
    assert client.post(f"/v1/models/changes/{pending_change}/confirm", headers=AUTH, json={"confirm": "worker:other"}).status_code == 400

@pytest.mark.db
def test_admin_actions_audited(client, pending_change, session): ...
```

```ts
test("switch requires typed confirmation", async ({ page }) => {
  await page.goto("/models"); await page.getByRole("button", { name: "Change worker" }).click();
  await page.getByRole("option", { name: "qwen3.5:9b" }).click();
  await expect(page.getByRole("button", { name: "Confirm" })).toBeDisabled();
  await page.getByLabel("Type worker:qwen3.5:9b to confirm").fill("worker:qwen3.5:9b");
  await expect(page.getByRole("button", { name: "Confirm" })).toBeEnabled();
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -m db tests/api/test_models_admin.py -v && cd apps/web && pnpm playwright test tests/models-admin.spec.ts`
Expected: FAIL

- [ ] **Step 3: Implement the routes and UI**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/api apps/web tests && git commit -m "feat(web): Models screen admin with typed confirmation and audit"
```

### Task 6: Weekly release digest

**SEC:** SEC-05, SEC-06

**Files:**
- Create: `src/techradar/digest/__init__.py`, `src/techradar/digest/releases.py`, `infra/digest/tracked.yaml`
- Modify: `infra/squid/allowlist.txt` (add `pypi.org`, `registry.npmjs.org`, `search.maven.org`), `src/techradar/worker/tasks.py` (add `digest_job`, Sundays at 09:00)
- Test: `tests/digest/test_releases.py`

**Interfaces:**
- Produces:
  - `def parse_uv_lock(text: str) -> dict[str, str]`: `[[package]]` name and version via `tomllib`
  - `def parse_pnpm_lock(text: str) -> dict[str, str]`: `importers['.'].dependencies` and `devDependencies` versions
  - **`tracked.yaml`:** extra packages to follow (for example Maven artifacts from my Java stack), each `{ecosystem, name}`
  - **Latest versions:** fetched through the fetcher (job kind `json`, through the sandbox) from `https://pypi.org/pypi/<name>/json` (`info.version`), `https://registry.npmjs.org/<name>` (`dist-tags.latest`) and Maven Central search
  - `class Update(BaseModel)`: `name`, `pinned`, `latest`, `kind: Literal["major","minor","patch"]`
  - `def compare(pinned: Mapping[str, str], latest: Mapping[str, str]) -> list[Update]`: uses `packaging.version`, skips pre-releases, majors first, at most 10
  - `def render_digest(updates: Sequence[Update]) -> str`: `🆕 Releases this week:` then `• <name> <latest> (you have <pinned>, <kind>)`. With no updates, nothing is sent.

- [ ] **Step 1: Write the failing tests**

```python
def test_compare_kinds_and_order():
    u = compare({"fastapi": "0.162.1", "pydantic": "2.11.0"}, {"fastapi": "0.163.0", "pydantic": "3.0.0"})
    assert [(x.name, x.kind) for x in u] == [("pydantic", "major"), ("fastapi", "minor")]

def test_prereleases_ignored():
    assert compare({"x": "1.0.0"}, {"x": "1.1.0rc1"}) == []

def test_parse_locks_fixture(): ...
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/digest -v`
Expected: FAIL

- [ ] **Step 3: Implement the module, allowlist entries and job**

- [ ] **Step 4: Run the tests and egress tests**

Run: same as Step 2, then `uv run pytest -m egress tests/security -q`.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/digest infra tests && git commit -m "feat(digest): weekly release digest against my lockfiles"
```

### Task 7: "Rising fast" trends

**SEC:** SEC-37

**Files:**
- Create: `src/techradar/digest/trends.py`
- Modify: `src/techradar/rag/retrieve.py` (`RetrieveFilters.since: date | None`), `src/techradar/worker/tasks.py` (add `trends_job` at 20:00 daily; `trend_counts` updated per processed item)
- Test: `tests/digest/test_trends.py`

**Interfaces:**
- Produces:
  - `def normalise_term(s: str) -> str`
  - `class Rising(BaseModel)`: `term`, `today: int`, `baseline: float`, `ratio: float`
  - `def rising(today: Mapping[str, int], history: Mapping[str, Sequence[int]], *, min_count: int = 5, ratio: float = 3.0, days: int = 14) -> list[Rising]`: the baseline is the mean of the last `days` (0 counts as 1); a term needs `today ≥ min_count` and `today / baseline ≥ ratio`; returns the top 3 by ratio
  - **Card:** `🔥 Rising fast: <Term>, <today> mentions today vs about <baseline>/day usually.` with the button `Why is everyone talking about this?` (`why:<trend_id>`). Tapping it runs the `ask` job with `Why is everyone talking about <term> this week?` and `since = today - 7 days`.

- [ ] **Step 1: Write the failing tests**

```python
def test_rising_detects_spike():
    assert rising({"rust": 40}, {"rust": [5] * 14})[0].term == "rust"

def test_steady_term_not_rising():
    assert rising({"india": 60}, {"india": [55] * 14}) == []

def test_min_count():
    assert rising({"zig": 4}, {"zig": [0] * 14}) == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/digest/test_trends.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the module, filter and job**

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/digest tests/rag -v && uv run pytest -m db tests/rag -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar tests && git commit -m "feat(digest): Rising fast trends with grounded explanation"
```

### Task 8: Read-only vault MCP server for Claude Code

**SEC:** SEC-24, SEC-34

**Files:**
- Create: `mcp/pyproject.toml` (a separate tiny project: `fastmcp` pinned), `mcp/vault_server.py`, `.mcp.json` (project scope; command `uv run --project mcp python -m vault_server`, vault path from `TR_VAULT_PATH` set on the Mac)
- Test: `mcp/tests/test_vault_server.py`

**Interfaces:**
- Produces:
  - `MAX_NOTE_BYTES = 200_000`
  - `def safe_note_path(vault: Path, rel: str) -> Path`: must resolve inside `vault`, end in `.md` and not be a symlink at any level; otherwise `ValueError`
  - **Tool `search_notes(query: str, limit: int = 10) -> list[dict]`:** case-insensitive search over titles, headings and text of synced `.md` files. Title matches rank first. Returns `{path, title, snippet}`; `limit` is capped at 10.
  - **Tool `read_note(path: str) -> str`:** uses `safe_note_path` and the size cap
  - No other tools.

- [ ] **Step 1: Write the failing tests**

```python
def test_only_two_read_tools():
    assert {t.name for t in list_tools(mcp)} == {"search_notes", "read_note"}

def test_read_note_traversal_refused(vault):
    for p in ["../../.ssh/id_rsa", "/etc/passwd", "notes/../../x.md", "notes/a.txt"]:
        with pytest.raises(ValueError): safe_note_path(vault, p)

def test_symlink_refused(vault_with_symlink): ...
def test_size_cap(vault_with_big_note): ...
def test_search_title_first(vault): assert search_notes("repo rate")[0]["title"] == "Repo rate"
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd mcp && uv run pytest -v`
Expected: FAIL

- [ ] **Step 3: Implement the server and the Claude Code config**

- [ ] **Step 4: Run the tests, then try it in Claude Code on the Mac (owner)**

Run: `cd mcp && uv run pytest -v`
Expected: PASS. In Claude Code, `search_notes` returns my notes, and asking it to write a file through MCP isn't possible (no write tool).

- [ ] **Step 5: Commit**

```bash
git add mcp .mcp.json && git commit -m "feat(mcp): read-only vault server for Claude Code"
```

### Task 9 (optional, only if I choose the cloud backup): Capped cloud fallback

**SEC:** SEC-35, SEC-10

**Files:**
- Create: `src/techradar/llm/cloud.py`, `infra/squid/allowlist.cloud.txt`
- Modify: `src/techradar/llm/roles.py` (`provider: Literal["ollama","anthropic"]`, allowed only with the flag), `infra/squid/squid.conf` (includes `allowlist.cloud.txt` only when present), `src/techradar/settings.py`
- Test: `tests/llm/test_cloud.py`

**Interfaces:**
- Produces:
  - `CLOUD_ALLOWED_JOBS = frozenset({"reader", "checker", "deep_dive"})`. Voice, takes, notes and answers about my personal files never go to the cloud.
  - **Models:** `claude-haiku-5-5` (checks) and `claude-sonnet-5-5` (deep dive). Prices from 02 are per million tokens, configurable: Haiku $0.10 in / $0.50 out; Sonnet $2 / $10.
  - `async def cloud_allowed(job: str, session, settings) -> bool`: true only if the flag is on, the job is allowed, and this month's spend is under `cloud_monthly_usd`
  - `async def record_usage(session, model: str, tokens_in: int, tokens_out: int) -> float` returns the running monthly spend
  - **Secret:** `anthropic_api_key`, worker only. `api.anthropic.com` is allowlisted only when `allowlist.cloud.txt` exists.

- [ ] **Step 1: Write the failing tests**

```python
async def test_off_by_default(session): assert not await cloud_allowed("reader", session, Settings(telegram_owner_chat_id=1))
async def test_job_not_allowed(session, cloud_on): assert not await cloud_allowed("voice", session, cloud_on)
async def test_cap_reached(session, cloud_on_spent_2_usd): assert not await cloud_allowed("reader", session, cloud_on_spent_2_usd)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/llm/test_cloud.py -v`
Expected: FAIL

- [ ] **Step 3: Implement it (skip this whole task if I stay fully local)**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/llm infra/squid src/techradar/settings.py tests/llm && git commit -m "feat(llm): optional capped cloud fallback, off by default"
```

### Task 10: Gate 10

**SEC:** the controls so far (the full review of all 68 controls happens at gate 12)

**Files:**
- Modify: `Makefile` (add `gate-10`), `docs/security/gates.md`

**Interfaces:**
- Produces: **`make gate-10`:**
  1. `gate-9`
  2. `pytest tests/models tests/digest tests/gpu_stats` (and `-m db`)
  3. `cd mcp && uv run pytest`
  4. Playwright `models-admin.spec.ts`
  5. An unapproved-download refusal check through the API
  6. The policy test
  7. `check_host.sh`
  8. Print `GATE 10: automated checks passed. Run the nmap scans and sign.`

- [ ] **Step 1: Run the gate on the server**

Run: `make gate-10`
Expected: every step passes.

- [ ] **Step 2 (owner): Review**

1. Run the TCP and UDP `nmap` scans from the Mac and the tailnet.
2. Confirm the monthly checklist in `docs/security/monthly.md` is up to date.

- [ ] **Step 3: Commit and sign**

```bash
git add Makefile docs/security/gates.md && git commit -m "docs(security): gate 10 passed"
```
