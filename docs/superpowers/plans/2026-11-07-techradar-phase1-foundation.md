# TechRadar Brain Phase 1: Secure Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A hardened server and repository where every later phase can be built safely. This means a CI security pipeline, settings and secrets handling, hardened Docker Compose with a policy test, an allowlisted outbound proxy, a database with least-privilege roles, a local model router with tested models, an owner-only Telegram bot with `/status`, backups with a restore test, and a host check. Added 2026-11-08: approved dependencies and the MCP allowlist, images pinned by digest, and intrusion detection (an alerter with its own bot and a daily heartbeat, Falco, integrity checks, honeytokens, host and database auditing, a resource watcher, account hardening). It ends with `make gate-1`.

**Architecture:** One Python package (`techradar`) built into small hardened images. Postgres, Ollama and Squid run on internal Docker networks; only Squid reaches the internet, through an allowlist. Nothing listens on the LAN. Detection runs on the host, outside Docker: Falco, auditd, AIDE and the timers feed one alerter, which writes an append-only log and messages me through its own bot, so a compromised container or database can't hide an alert.

**Tech Stack:** Python 3.14, uv, Ruff, pytest, pydantic-settings, SQLAlchemy 2, Alembic, psycopg 3, LiteLLM 1.106 (library), Ollama 0.40, PostgreSQL 18 + pgvector, Squid, python-telegram-bot, semgrep, gitleaks, OSV-Scanner, Trivy, hadolint, shellcheck, restic, Falco (modern eBPF), auditd, AIDE, pgaudit, Lynis, age.

**Spec:** [05_Architecture.md](../../../05_Architecture.md) (services, SEC controls, §7.19, §10.5) · [02_Tech_Stack_and_Security.md](../../../02_Tech_Stack_and_Security.md) §5, §5.17, §7–9 · [04_Old_vs_New_SLMs.md](../../../04_Old_vs_New_SLMs.md) · [06_Improvements.md](../../../06_Improvements.md) Parts E (E2, E3, E5), H and I · decisions D1–D18, D41, D42, D47 in the [overview](2026-11-07-techradar-00-overview.md)

## Global Constraints

The overview's Global Constraints 1–16 apply to every task. The ones this phase leans on most:

- Every published port is `"127.0.0.1:<host>:<container>"` (SEC-02).
- Container baseline: not root, `cap_drop: ["ALL"]`, `security_opt: ["no-new-privileges:true"]`, `read_only: true` + `tmpfs`, `mem_limit`, `cpus`, `pids_limit`, log `max-size`. Never `privileged`, host networking, `/var/run/docker.sock`, `/home` or `/` mounts (SEC-07).
- Images pinned to exact versions, never `:latest`; GitHub Actions pinned to full commit SHAs (SEC-08, SEC-33).
- Secrets only as files in `secrets/`, mode 600, mounted as Docker secrets; `secrets.example/` holds fake values (SEC-10).
- Ollama: `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, 8k context; Qwen thinking off.
- `TR_ALLOW_CLOUD_LLM=false` (SEC-35). The bot answers only `TR_TELEGRAM_OWNER_CHAT_ID` (SEC-26).
- Only fake data in the repo and tests.
- **Digests:** every `image:` and every Dockerfile `FROM` is pinned as `name:version@sha256:<64 hex>`; healthchecks use exec form (`CMD`) (SEC-55, SEC-58).
- **Dependencies:** every direct dependency is listed in `infra/policy/approved_deps.yaml` (SEC-52).
- **Alerts:** the alerter uses its own bot token (`alerter_bot_token`), never the main bot's. Containment stays `alert-only` for the first 14 days (D41).
- **Honeytokens** are planted on the server by a script, never committed, and kept out of sync, backups and AIDE (SEC-61).
- **Detection order (06 I4):** quiet alarms first (Task 14: the alerter, the heartbeat and Squid denials), then integrity checks, honeytokens and auditing (Task 15), and Falco last (Task 16).

## Review Focus

1. **A secret file with Windows line endings or trailing spaces** must still work: `read_secret` strips them. Pinned in Task 3 by `test_read_secret_strips_whitespace`.
2. **Stickers, edited messages and channel posts sent to the bot** are ignored silently. Pinned in Task 10 by `test_route_update_ignores_non_text`.
3. **Ollama down when `/status` runs** shows "Models: down" instead of crashing. Pinned in Task 10 by `test_status_ollama_down`.
4. **Disk almost full** shows "(low)" below 15% free. Pinned in Task 10 by `test_render_status_low_disk`.
5. **The server is off at backup time** must not lose the backup: the timer runs it at the next boot. Pinned in Task 11 by `test_backup_timer_is_persistent`.

Also pinned on 2026-11-08:
- **A backup or AIDE run touching a honeytoken** would bury real alerts in noise. Task 15 `test_backup_excludes_honeytokens` and `test_aide_config_excludes_honeytokens`.
- **Twenty identical warnings in an hour** arrive as one message, not twenty. Task 14 `test_warnings_grouped_per_hour`.

---

### Task 1: Repository skeleton, tooling and agent rules

**SEC:** SEC-11, SEC-34

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore`, `.pre-commit-config.yaml`, `AGENTS.md`, `README.md`, `.env.example`, `secrets.example/README.md`, `src/techradar/__init__.py`, `tests/test_smoke.py`

**Interfaces:**
- Produces: package `techradar` with `__version__ = "0.1.0"`; pytest markers `db`, `egress`, `live`, `slow`; dependency extras `bot`, `fetcher`, `parser`, `worker`.

- [ ] **Step 1: Initialise Git and write the failing smoke test**

Run `git init -b main` in `TechRadarBrain/`.

```python
# tests/test_smoke.py
def test_version():
    from techradar import __version__
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: FAIL (no `pyproject.toml` / module `techradar` not found)

- [ ] **Step 3: Create the project files**

- `pyproject.toml`:
  - **Project:** name `techradar`, version `0.1.0`, `requires-python = ">=3.14"`, src layout.
  - **Base dependencies:** `pydantic>=2`, `pydantic-settings`, `sqlalchemy>=2`, `psycopg[binary]>=3`, `alembic`, `pyyaml`.
  - **Extras:** `bot = ["python-telegram-bot"]`, `fetcher = ["httpx", "tldextract"]`, `parser = ["trafilatura", "feedparser", "docling>=2.146"]`, `worker = ["litellm>=1.106", "langgraph>=1.2", "procrastinate", "pgvector", "jinja2", "tldextract"]`.
  - **Dev group:** `pytest>=9`, `pytest-asyncio`, `ruff>=0.17`, `respx`, `import-linter`, `pre-commit`.
  - **Ruff:** line length 100, target `py314`, select `["E","F","I","UP","B","ASYNC","S"]`; `S` is the security (bandit) rule set. Per-file ignores for `tests/**`: `S101`, `S603`, `S607`. `extend-exclude = ["security/semgrep/rules.py"]`, because that file is deliberately unsafe test input for the semgrep rules.
  - **pytest:** `asyncio_mode = "auto"`, `testpaths = ["tests"]`, markers `db`, `egress`, `live`, `slow`, and `addopts = "-m 'not db and not egress and not live and not slow'"`.
- `.python-version`: `3.14`.
- `.gitignore`: `secrets/`, `data/`, `.env`, `.env.production` (a honeytoken, Task 15), `.venv/`, `__pycache__/`, `evals/fit/results/*.tmp`, `apps/web/node_modules/`, `infra/host/evidence.pub`.
- `.pre-commit-config.yaml`: Ruff (lint and format) and gitleaks hooks, each pinned to an exact `rev`.
- `.env.example`: `TR_TELEGRAM_OWNER_CHAT_ID=123456789` and `TR_ENV=dev` (fake values).
- `secrets.example/README.md`: explains that `secrets/` holds one file per secret, mode 600, owned by uid 1000, and lists the file names used in this phase:
  - `pg_superuser_password`
  - `tr_migrator_password`, `tr_app_password`, `tr_ro_password`
  - `telegram_bot_token`
  - `alerter_bot_token` (the separate alert bot, Task 14)
  - `restic_password`

  Add one fake-value file per name (for example `dev-only-not-a-secret`).
- `src/techradar/__init__.py`: `__version__ = "0.1.0"`.
- `AGENTS.md` sections, in this order:
  1. **What this repo is:** one paragraph, with links to `05_Architecture.md` and the plans.
  2. **Commands:** `make lint`, `make test`, `make security`, `make gate-N`.
  3. **Non-negotiable security rules:**
     - Overview Global Constraints 4–12, verbatim.
     - Never read, print or copy files in `secrets/`.
     - Never give the parser network access.
     - Every new Compose service must pass `tests/security/test_compose_policy.py`.
     - Never add a dependency. If one is needed, name it and say why in your summary; I vet and approve it (SEC-52, Task 13).
     - Use only the MCP servers, skills and plugins in the "Allowed MCP servers" and "Allowed skills and plugins" sections, pinned to exact versions or commits (SEC-53, Task 13). Never install one from a marketplace or a link.
     - Never disable a security test to make it pass.
  4. **Workflow:** one task, one commit; run `make lint test` before each commit.
  5. **Allowed MCP servers:** a table between `<!-- mcp-allowlist:start -->` and `<!-- mcp-allowlist:end -->` with columns `name`, `command`, `version`, `access`, `why`. It starts empty; phase 10 adds the read-only vault server.
  6. **Allowed skills and plugins:** a table between `<!-- skills-allowlist:start -->` and `<!-- skills-allowlist:end -->` with columns `name`, `kind` (`skill` or `plugin`), `source` (repository URL), `commit` (full SHA), `sha256` (of the skill's files, for skills kept in the repo; otherwise `-`) and `why`. It starts with the skills I use to build this project, each read before it's listed.
- `README.md`: two paragraphs, with links to `AGENTS.md`, `05_Architecture.md` and the overview plan.

- [ ] **Step 4: Run the test and Ruff**

Run: `uv sync && uv run pytest -v && uv run ruff check .`
Expected: `1 passed`; `All checks passed!`

- [ ] **Step 5: Prove gitleaks blocks a token**

Run: `printf '1234567890:AAEhBP0av28AAAAAAAAAAAAAAAAAAAAAAAA\n' > tmp_leak.txt && uv run pre-commit run gitleaks --files tmp_leak.txt; rm tmp_leak.txt`
Expected: gitleaks reports a leak and the hook fails.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "chore: repo skeleton, tooling and agent rules"
```

### Task 2: CI security pipeline and custom semgrep rules

**SEC:** SEC-22, SEC-23, SEC-33

**Files:**
- Create: `security/semgrep/rules.yaml`, `security/semgrep/rules.py` (rule tests), `.github/workflows/ci.yml`, `.github/dependabot.yml`

**Interfaces:**
- Produces: semgrep rule IDs `tr-no-trust-remote-code`, `tr-no-torch-load`, `tr-no-pickle-load`, `tr-no-yaml-load`, `tr-no-shell-true`, `tr-no-eval`, `tr-no-verify-false`, used by `make security` in Task 19.

- [ ] **Step 1: Write the rule tests first**

`security/semgrep/rules.py` contains one `# ruleid: <id>` case and one `# ok: <id>` case per rule:
- `AutoModel.from_pretrained("x", trust_remote_code=True)` versus `trust_remote_code=False`
- `torch.load(path)`
- `pickle.loads(b)`
- `yaml.load(s)` versus `yaml.safe_load(s)`
- `subprocess.run(cmd, shell=True)` versus `subprocess.run(["ls"])`
- `eval(x)` and `exec(x)`
- `httpx.Client(verify=False)` versus `httpx.Client()`

- [ ] **Step 2: Run them to see them fail**

Run: `uvx semgrep --test security/semgrep`
Expected: FAIL (the rules file is missing or empty)

- [ ] **Step 3: Write `security/semgrep/rules.yaml`**

Seven rules matching the cases above, each with severity `ERROR` and a one-line message naming the SEC control.

- [ ] **Step 4: Run the rule tests**

Run: `uvx semgrep --test security/semgrep`
Expected: all rule tests pass.

- [ ] **Step 5: Write the CI workflow**

`.github/workflows/ci.yml`:
- **Triggers and permissions:** runs on `push` and `pull_request`, with `permissions: contents: read` and no secrets. Every action is pinned to a full commit SHA, with the version in a comment.
- **Jobs:**
  1. `test`: `uv sync --frozen`, then `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest`.
  2. `semgrep`: `semgrep --test security/semgrep`, then `semgrep scan --error --config security/semgrep/rules.yaml --config p/python src`.
  3. `deps`: OSV-Scanner (pinned release) on `uv.lock`; fails on any vulnerability.
  4. `secrets`: gitleaks (pinned release) over the full history, with redaction.
  5. `config`: `trivy config --severity HIGH,CRITICAL --exit-code 1 .`; `hadolint infra/docker/Dockerfile` when the file exists; `shellcheck` on every `*.sh`.

`.github/dependabot.yml`: weekly updates for `uv`, `github-actions`, `docker` and `docker-compose`, so pinned versions and digests get update pull requests (SEC-55). Trivy scans a new image before I merge its update.

- [ ] **Step 6: Verify locally**

Run: `uvx semgrep scan --error --config security/semgrep/rules.yaml src`
Expected: `0 findings`. CI goes green once I push to a private GitHub repo (an owner step; the repo holds code only).

- [ ] **Step 7: Commit**

```bash
git add security .github && git commit -m "ci: security pipeline and custom semgrep rules"
```

### Task 3: Settings and secret files

**SEC:** SEC-10

**Files:**
- Create: `src/techradar/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces:
  - `class SecretError(Exception)`
  - `def read_secret(name: str, secrets_dir: Path = Path("/run/secrets")) -> str`
  - `class Settings(BaseSettings)` with `env_prefix="TR_"` and these fields:

    | Field | Type | Default |
    |---|---|---|
    | `env` | `Literal["dev","prod"]` | `"dev"` |
    | `tz` | `str` | `"Asia/Kolkata"` |
    | `data_dir` | `Path` | `/data` |
    | `vault_dir` | `Path` | `/data/vault` |
    | `secrets_dir` | `Path` | `/run/secrets` |
    | `db_host` | `str` | `"postgres"` |
    | `db_port` | `int` | `5432` |
    | `db_name` | `str` | `"techradar"` |
    | `telegram_owner_chat_id` | `int` | required |
    | `allow_cloud_llm` | `bool` | `False` |
    | `ollama_base_url` | `str` | `"http://ollama:11434"` |
    | `https_proxy` | `str` | `"http://squid:3128"` |
    | `fetch_interval_min` | `int` | `120` |
    | `per_domain_delay_s` | `float` | `5.0` |
    | `max_fetch_bytes` | `int` | `5_000_000` |
    | `fetch_timeout_s` | `float` | `20.0` |
    | `parse_timeout_s` | `int` | `120` |
    | `max_doc_chars` | `int` | `100_000` |
    | `dedupe_threshold` | `float` | `0.90` |
    | `relevance_min` | `float` | `0.30` |
    | `retention_days` | `int` | `7` |
    | `briefing_time` | `str` | `"06:30"` |
    | `misfire_grace_s` | `int` | `21600` |
    | `user_agent` | `str` | `"TechRadarBrain/0.1 (personal, non-commercial)"` |

  - `def get_settings() -> Settings`, cached with `functools.lru_cache`

- [ ] **Step 1: Write the failing tests**

```python
def test_read_secret_strips_whitespace(tmp_path):
    p = tmp_path / "tok"; p.write_text("abc \r\n"); p.chmod(0o600)
    assert read_secret("tok", tmp_path) == "abc"

def test_read_secret_missing_raises(tmp_path):
    with pytest.raises(SecretError, match="missing"): read_secret("nope", tmp_path)

def test_read_secret_empty_raises(tmp_path):
    p = tmp_path / "e"; p.write_text("\n"); p.chmod(0o600)
    with pytest.raises(SecretError, match="empty"): read_secret("e", tmp_path)

def test_read_secret_rejects_group_or_world_readable(tmp_path):
    p = tmp_path / "s"; p.write_text("x"); p.chmod(0o640)
    with pytest.raises(SecretError, match="permissions"): read_secret("s", tmp_path)

def test_read_secret_rejects_symlink(tmp_path):
    t = tmp_path / "t"; t.write_text("x"); t.chmod(0o600); (tmp_path / "l").symlink_to(t)
    with pytest.raises(SecretError, match="symlink"): read_secret("l", tmp_path)

def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("TR_TELEGRAM_OWNER_CHAT_ID", "1")
    s = Settings()
    assert (s.allow_cloud_llm, s.tz, s.dedupe_threshold, s.relevance_min) == (False, "Asia/Kolkata", 0.90, 0.30)
    assert s.misfire_grace_s == 21600
    assert s.user_agent == "TechRadarBrain/0.1 (personal, non-commercial)"

def test_settings_requires_owner_chat_id(monkeypatch):
    monkeypatch.delenv("TR_TELEGRAM_OWNER_CHAT_ID", raising=False)
    with pytest.raises(ValidationError): Settings()
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/test_settings.py -v`
Expected: FAIL (module `techradar.settings` missing)

- [ ] **Step 3: Implement `read_secret`, `Settings` and `get_settings` in `src/techradar/settings.py`**

`read_secret` checks the following in this order, raising `SecretError` with the matching word:
1. **"missing":** the file doesn't exist.
2. **"symlink":** `Path.is_symlink()` is true.
3. **"permissions":** `stat().st_mode & 0o077` is non-zero.
4. **"empty":** the content is empty after `.strip()`.

It returns the stripped content.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_settings.py -v`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/techradar/settings.py tests/test_settings.py && git commit -m "security(settings): settings and strict secret files"
```

### Task 4: JSON logs with secret redaction

**SEC:** SEC-32

**Files:**
- Create: `src/techradar/logs.py`
- Test: `tests/test_logs.py`

**Interfaces:**
- Produces:
  - `REDACTED = "[REDACTED]"`
  - `class RedactingFilter(logging.Filter)`, built with `__init__(self, secrets: Iterable[str] = ())`
  - `class JsonFormatter(logging.Formatter)`, which outputs keys `ts`, `level`, `logger`, `msg`, plus `exc` when there is an exception
  - `def configure_logging(level: str = "INFO", secrets: Iterable[str] = ()) -> None`

- [ ] **Step 1: Write the failing tests**

```python
def test_exact_secret_redacted(caplog_json):            # fixture: configure_logging(secrets=["s3cr3t-value"]) + capture
    logging.getLogger("t").info("token=%s", "s3cr3t-value")
    assert "s3cr3t-value" not in caplog_json() and "[REDACTED]" in caplog_json()

def test_telegram_like_token_redacted(caplog_json):
    logging.getLogger("t").info("bot 1234567890:AAEhBP0av28AAAAAAAAAAAAAAAAAAAAAAAA")
    assert "AAEhBP0av28" not in caplog_json()

def test_db_url_password_redacted(caplog_json):
    logging.getLogger("t").info("postgresql+psycopg://tr_app:hunter2@postgres:5432/techradar")
    assert "hunter2" not in caplog_json() and "tr_app:[REDACTED]@" in caplog_json()

def test_output_is_json_with_keys(caplog_json):
    logging.getLogger("t").warning("hi")
    assert {"ts", "level", "logger", "msg"} <= json.loads(caplog_json().splitlines()[-1]).keys()

def test_exception_text_redacted(caplog_json):
    try: raise ValueError("pw s3cr3t-value")
    except ValueError: logging.getLogger("t").exception("boom")
    assert "s3cr3t-value" not in caplog_json()
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/test_logs.py -v`
Expected: FAIL

- [ ] **Step 3: Implement in `src/techradar/logs.py`**

The filter formats the full message (including args and exception text), then replaces three things with `[REDACTED]`:
- each exact secret
- the regex `\b\d{6,12}:[A-Za-z0-9_-]{30,}\b`
- the password in `://user:pass@` (via `(://[^:/@\s]+):[^@\s]+@` → `\1:[REDACTED]@`)

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_logs.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/techradar/logs.py tests/test_logs.py && git commit -m "security(logs): JSON logs with secret redaction"
```

### Task 5: Hardened Compose baseline and policy test

**SEC:** SEC-02, SEC-06, SEC-07, SEC-08

**Files:**
- Create: `compose.yaml`, `compose.dev.yaml`, `infra/policy/compose_exceptions.yaml`
- Test: `tests/security/test_compose_policy.py`

**Interfaces:**
- Produces:
  - **Compose networks:**
    - `db`, `llm` and `egress_internal`, each with `internal: true`
    - `egress_out`, which is not internal
  - **YAML anchor `x-hardened`:** `cap_drop: ["ALL"]`, `security_opt: ["no-new-privileges:true"]`, `read_only: true`, `tmpfs: ["/tmp"]`, `pids_limit: 200`, and logging `json-file` with `max-size: "10m"`, `max-file: "3"`.
  - **Services:**
    - `postgres`: image `pgvector/pgvector:<exact>-pg18@sha256:<digest>` (replaced by a build with pgaudit in Task 15), network `db`, volume `pgdata`, secrets, healthcheck `["CMD", "pg_isready", "-U", "postgres"]`
    - `ollama`: image `ollama/ollama:0.40.14@sha256:<digest>` (or the exact current tag), network `llm`, no published port, GPU reservation, the three `OLLAMA_*` settings and no `OLLAMA_ORIGINS` (its default allows only local origins, SEC-51), volume `ollama`. Containers on internal networks can't publish ports, so anything that talks to Ollama joins `llm`.
  - **Digests:** get each index digest with `docker buildx imagetools inspect <image>:<tag>` and write `image: <image>:<tag>@sha256:<digest>` (SEC-55).
    - `ollama-pull`: profile `pull`, same image and volume, default network, command `sh -c 'ollama serve & sleep 5 && ollama pull "$MODEL"'`
- Every later service must keep `tests/security/test_compose_policy.py` green.

- [ ] **Step 1: Write the failing policy test**

```python
COMPOSE = yaml.safe_load(Path("compose.yaml").read_text())
EXC = yaml.safe_load(Path("infra/policy/compose_exceptions.yaml").read_text()) or {}
SERVICES = COMPOSE["services"].items()

@pytest.mark.parametrize("name,svc", SERVICES)
def test_ports_bound_to_loopback(name, svc):
    assert all(str(p).startswith("127.0.0.1:") for p in svc.get("ports", []))

@pytest.mark.parametrize("name,svc", SERVICES)
def test_cap_drop_all_and_no_new_privileges(name, svc):
    assert svc.get("cap_drop") == ["ALL"] and "no-new-privileges:true" in svc.get("security_opt", [])

@pytest.mark.parametrize("name,svc", SERVICES)
def test_no_privileged_no_host_network(name, svc):
    assert not svc.get("privileged")
    assert svc.get("network_mode") != "host" or name in EXC.get("host_network", {})

@pytest.mark.parametrize("name,svc", SERVICES)
def test_no_dangerous_mounts(name, svc):
    srcs = [str(v).split(":")[0] for v in svc.get("volumes", [])]
    assert not any(s in {"/", "/home", "/var/run/docker.sock"} or s.startswith("~") for s in srcs)

@pytest.mark.parametrize("name,svc", SERVICES)
def test_limits_present(name, svc):
    assert {"mem_limit", "cpus", "pids_limit"} <= svc.keys()

@pytest.mark.parametrize("name,svc", SERVICES)
def test_read_only_or_excepted(name, svc):
    assert svc.get("read_only") is True or name in EXC.get("writable_root", {})

@pytest.mark.parametrize("name,svc", SERVICES)
def test_non_root_or_excepted(name, svc):
    assert str(svc.get("user", "root")) not in {"root", "0", "0:0"} or name in EXC.get("root_start", {})

@pytest.mark.parametrize("name,svc", SERVICES)
def test_image_pinned_by_digest(name, svc):
    img = svc.get("image")
    assert "build" in svc or (img and re.fullmatch(r"[^:@\s]+:[^:@\s]+@sha256:[0-9a-f]{64}", img)), img

@pytest.mark.parametrize("name,svc", SERVICES)
def test_healthchecks_use_exec_form(name, svc):
    hc = svc.get("healthcheck")
    assert hc is None or (isinstance(hc.get("test"), list) and hc["test"][0] == "CMD"), name

@pytest.mark.parametrize("dockerfile", sorted([*Path("infra").rglob("Dockerfile*"), *Path("apps/web").glob("Dockerfile*")]))
def test_dockerfile_from_pinned_by_digest(dockerfile):
    stages = set()
    for line in dockerfile.read_text().splitlines():
        if line.strip().upper().startswith("FROM "):
            parts = line.split()
            ref = parts[1]
            if ref not in stages:
                assert re.search(r"@sha256:[0-9a-f]{64}$", ref), f"{dockerfile}: {ref}"
            if len(parts) >= 4 and parts[2].upper() == "AS":
                stages.add(parts[3])

@pytest.mark.parametrize("name,svc", SERVICES)
def test_log_size_limited(name, svc):
    assert svc.get("logging", {}).get("options", {}).get("max-size")

def test_parser_has_no_network():
    if "parser" in COMPOSE["services"]:
        assert COMPOSE["services"]["parser"].get("network_mode") == "none"

def test_only_allowed_services_on_internet_networks():
    open_nets = {n for n, cfg in COMPOSE["networks"].items() if not (cfg or {}).get("internal")}
    for name, svc in SERVICES:
        if set(svc.get("networks", [])) & open_nets or not svc.get("networks") and svc.get("network_mode") != "none":
            assert name in {"squid", "ollama-pull"}, name

def test_ollama_origins_not_wildcard():
    env = COMPOSE["services"]["ollama"].get("environment", {})
    text = " ".join(env) if isinstance(env, list) else str(env.get("OLLAMA_ORIGINS", ""))
    assert "*" not in text

def test_exceptions_have_reasons():
    for group in EXC.values():
        for name, entry in group.items():
            assert len(entry["reason"]) >= 20, name
```

The test module imports `re`, `pytest`, `yaml` and `Path`.

- [ ] **Step 2: Run to see it fail**

Run: `uv run pytest tests/security/test_compose_policy.py -v`
Expected: FAIL (`compose.yaml` not found)

- [ ] **Step 3: Write `compose.yaml`, `compose.dev.yaml` and the exceptions file**

- **`compose_exceptions.yaml`:**
  - `root_start`: `postgres`, `squid`, `ollama`, each with a reason. For example, postgres: "official entrypoint starts as root to fix ownership, then drops to the postgres user". Exceptions never relax `cap_drop`.
  - **Capabilities added back:**
    - postgres: `CHOWN`, `SETUID`, `SETGID`, `DAC_OVERRIDE`, `FOWNER`
    - squid: `SETUID`, `SETGID`
- **`compose.dev.yaml`:** on the Mac, removes the GPU reservation. It also attaches postgres to an extra non-internal `dev_host` network and publishes it on `"127.0.0.1:55432:5432"` for tests; internal networks can't publish ports. This file is development only; the policy test checks `compose.yaml`.

- [ ] **Step 4: Run the policy test and validate Compose**

Run: `uv run pytest tests/security/test_compose_policy.py -v && docker compose config -q`
Expected: all pass; `docker compose config` prints nothing.

- [ ] **Step 5: Start the base services on the server**

Run: `docker compose up -d postgres ollama && docker compose ps`
Expected: both `healthy` / `running`.

- [ ] **Step 6: Commit**

```bash
git add compose*.yaml infra/policy tests/security/test_compose_policy.py && git commit -m "security(compose): hardened baseline with policy test"
```

### Task 6: Outbound proxy with allowlist, plus egress tests

**SEC:** SEC-05

**Files:**
- Create: `infra/squid/squid.conf`, `infra/squid/allowlist.txt`
- Modify: `compose.yaml` (add `squid` and the `egress-probe` test service)
- Test: `tests/security/test_egress.py`

**Interfaces:**
- Produces:
  - **`squid` service:** reachable as `http://squid:3128` on `egress_internal`. Its allowlist file is the single list of allowed domains (also mounted read-only into the fetcher in phase 2).
  - **Allowlist after this task:** `api.telegram.org`
  - **`egress-probe` service:** profile `test`, image `curlimages/curl:<exact>`, only on `egress_internal`, with `HTTPS_PROXY=http://squid:3128` and `HTTP_PROXY=http://squid:3128`.

- [ ] **Step 1: Write the failing egress tests**

```python
pytestmark = pytest.mark.egress

def probe(*args):
    return subprocess.run(["docker", "compose", "--profile", "test", "run", "--rm", "egress-probe", *args],
                          capture_output=True, text=True, timeout=60)

def test_allowlisted_https_ok():
    r = probe("-sS", "-o", "/dev/null", "-w", "%{http_code}", "https://api.telegram.org/")
    assert r.returncode == 0 and r.stdout != "000"

def test_not_allowlisted_denied():
    r = probe("-sS", "https://example.com/")
    assert r.returncode != 0 and "403" in r.stderr

@pytest.mark.parametrize("url", ["https://192.168.1.1/", "http://169.254.169.254/", "https://10.0.0.1/", "https://100.100.100.100/"])
def test_private_and_metadata_addresses_denied(url):
    assert probe("-sS", "--max-time", "10", url).returncode != 0

def test_plain_http_denied():
    r = probe("-sS", "-o", "/dev/null", "-w", "%{http_code}", "http://api.telegram.org/")
    assert r.stdout == "403"

def test_no_direct_internet_without_proxy():
    assert probe("-sS", "--max-time", "10", "--noproxy", "*", "https://api.telegram.org/").returncode != 0
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest -m egress tests/security/test_egress.py -v`
Expected: FAIL (no `squid` or `egress-probe` service yet)

- [ ] **Step 3: Write `infra/squid/squid.conf` exactly as below, and the allowlist**

```
http_port 3128
acl SSL_ports port 443
acl CONNECT method CONNECT
acl blocked_dst dst 0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 192.168.0.0/16 224.0.0.0/4 ::1 fc00::/7 fe80::/10
acl allowed_sites dstdomain "/etc/squid/allowlist.txt"
http_access deny blocked_dst
http_access deny CONNECT !SSL_ports
http_access deny !SSL_ports
http_access allow CONNECT allowed_sites
http_access deny all
cache deny all
via off
forwarded_for delete
access_log stdio:/dev/stdout squid
```

`allowlist.txt` contains one line: `api.telegram.org`.

Add `squid` to `compose.yaml`:
- **Image:** `ubuntu/squid:<exact>`
- **Networks:** `egress_internal`, `egress_out`
- **Mounts:** config and allowlist, read-only
- **Writable areas:** `tmpfs` for `/var/run`, `/var/spool/squid` and `/var/log/squid`
- **Logs:** the access log goes to stdout, so `docker compose logs squid` carries every `TCP_DENIED` line for the alerter (Task 14, SEC-59)

- [ ] **Step 4: Run the egress tests on the server**

Run: `docker compose up -d squid && uv run pytest -m egress tests/security/test_egress.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add infra/squid compose.yaml tests/security/test_egress.py && git commit -m "security(egress): squid allowlist proxy with egress tests"
```

### Task 7: Database roles, Dockerfile and first migration

**SEC:** SEC-12

**Files:**
- Create: `infra/postgres/init/01-roles.sh`, `infra/docker/Dockerfile` (stages `base` and `migrate`), `alembic.ini`, `src/techradar/db/__init__.py`, `src/techradar/db/engine.py`, `src/techradar/db/models.py`, `src/techradar/db/migrations/env.py`, `src/techradar/db/migrations/versions/0001_baseline.py`
- Modify: `compose.yaml` (mount the init script; add the `migrate` service), `compose.dev.yaml`
- Test: `tests/db/test_roles.py`

**Interfaces:**
- Consumes: `Settings`, `read_secret` (Task 3).
- Produces:
  - **Database:** `techradar`, with schema `techradar` owned by `tr_migrator`.
  - **Roles:**
    - `tr_migrator` (DDL)
    - `tr_app` (`SELECT`, `INSERT`, `UPDATE`, `DELETE`; sequence `USAGE`)
    - `tr_ro` (`SELECT`)
    - All three have `search_path = techradar`; `CONNECT` and `CREATE` are revoked from `PUBLIC`.
  - **Engine helpers:**
    - `DbRole = Literal["migrator", "app", "ro"]`
    - `def database_url(role: DbRole, s: Settings) -> str` returns `postgresql+psycopg://tr_<role>:<pw>@<host>:<port>/<db>`, reading the secret `tr_<role>_password`
    - `def make_engine(role: DbRole, s: Settings | None = None) -> AsyncEngine` with `pool_pre_ping=True`
  - **Models:** `class Base(DeclarativeBase)` and `class AuditEvent(Base)`, table `techradar.audit_log`:
    - `id` bigint identity primary key
    - `at` timestamptz, default `now()`
    - `actor` varchar(64)
    - `action` varchar(64)
    - `detail` jsonb
  - **Extension:** `vector` installed in `techradar` by the init script (superuser context).
  - **Docker images:**
    - `base` stage: `python:3.14-slim-<debian>@sha256:<digest>` at an exact patch tag, uv copied from `ghcr.io/astral-sh/uv:<exact>@sha256:<digest>`, user `1000:1000`, no shell tools added.
    - `migrate` target: `uv sync --frozen --no-dev`, then `CMD ["alembic", "upgrade", "head"]`.

- [ ] **Step 1: Write the failing role tests**

```python
pytestmark = pytest.mark.db

async def test_app_can_insert_audit_event(app_conn):
    await app_conn.execute(text("INSERT INTO audit_log(actor, action, detail) VALUES ('test','ping','{}')"))

async def test_ro_cannot_insert(ro_conn):
    with pytest.raises(DBAPIError, match="permission denied"):
        await ro_conn.execute(text("INSERT INTO audit_log(actor, action, detail) VALUES ('t','x','{}')"))

async def test_app_cannot_create_table(app_conn):
    with pytest.raises(DBAPIError, match="permission denied"):
        await app_conn.execute(text("CREATE TABLE evil(id int)"))

async def test_app_cannot_drop_table(app_conn):
    with pytest.raises(DBAPIError, match="must be owner"):
        await app_conn.execute(text("DROP TABLE audit_log"))

async def test_vector_extension_installed(ro_conn):
    assert (await ro_conn.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'"))).scalar() == 1
```

The fixtures `app_conn` and `ro_conn` use `make_engine("app")` and `make_engine("ro")`, with `TR_DB_HOST=127.0.0.1`, `TR_DB_PORT=55432` and `TR_SECRETS_DIR=secrets` in dev.

- [ ] **Step 2: Run to see them fail**

Run: `docker compose -f compose.yaml -f compose.dev.yaml up -d postgres && uv run pytest -m db tests/db -v`
Expected: FAIL (roles and tables don't exist)

- [ ] **Step 3: Implement the init script, Dockerfile, engine, model and migration `0001_baseline`**

- **`01-roles.sh`:** reads the passwords from `/run/secrets/tr_*_password`, with `set -euo pipefail` and `psql -v ON_ERROR_STOP=1`. It uses `ALTER DEFAULT PRIVILEGES FOR ROLE tr_migrator IN SCHEMA techradar` so future tables and sequences get the grants automatically.
- **`migrate` service:** target `migrate`, network `db`, secret `tr_migrator_password`, `restart: "no"`, and it waits for `postgres` to be healthy.

- [ ] **Step 4: Recreate the dev database, migrate and run the tests**

Run: `docker compose -f compose.yaml -f compose.dev.yaml down -v && docker compose -f compose.yaml -f compose.dev.yaml up -d postgres && docker compose run --rm migrate && uv run pytest -m db tests/db -v && uv run pytest tests/security/test_compose_policy.py -q`
Expected: migrate logs `Running upgrade -> 0001_baseline`; `5 passed`; policy green.

- [ ] **Step 5: Commit**

```bash
git add infra/postgres infra/docker alembic.ini src/techradar/db compose*.yaml tests/db && git commit -m "security(db): least-privilege roles and baseline migration"
```

### Task 8: Model roles and the LLM client

**SEC:** SEC-09, SEC-23, SEC-35

**Files:**
- Create: `infra/models/roles.yaml`, `src/techradar/llm/__init__.py`, `src/techradar/llm/roles.py`, `src/techradar/llm/client.py`, `tests/fakes.py`
- Test: `tests/llm/test_roles.py`, `tests/llm/test_client.py`, `tests/llm/test_live_smoke.py` (marker `live`)

**Interfaces:**
- Produces:
  - **Roles:**
    - `class Role(StrEnum)`: `WORKER="worker"`, `CHECKER="checker"`, `NIGHT="night"`, `EMBED="embed"`, `VISION="vision"`
    - `class RoleModel(BaseModel)`, `extra="forbid"`, with fields:
      - `ollama_tag: str`, matching `^[a-z0-9][a-z0-9._-]*(:[a-z0-9._-]+)?$`
      - `family: str`
      - `num_ctx: int`, from 1024 to 32768
      - `think: bool`
      - `provider: Literal["ollama"] = "ollama"`
    - `class RoleConfigError(ValueError)`
    - `def load_roles(path: Path, *, allow_cloud: bool) -> dict[Role, RoleModel]`
  - **Completion:**
    - `class Completer(Protocol)`: `async def complete(self, role: Role, messages: list[dict[str, str]], *, json_schema: dict, max_tokens: int, timeout_s: float) -> str`
    - `class Embedder(Protocol)`: `async def embed(self, texts: Sequence[str]) -> list[list[float]]`
    - `class LiteLLMCompleter(Completer)` and `class LiteLLMEmbedder(Embedder)`, both built as `__init__(self, roles: dict[Role, RoleModel], ollama_base_url: str)`. They use `litellm.Router`, with model name = role value and litellm model `ollama_chat/<tag>` (`ollama/<tag>` for embeddings), passing `num_ctx` and `think`.
    - `class LLMOutputError(Exception)`
    - `def strip_thinking(text: str) -> str`
    - `async def complete_json(completer: Completer, role: Role, system: str, user: str, schema: type[T], *, max_tokens: int = 1024, timeout_s: float = 120.0, attempts: int = 2) -> T`
  - **Test fakes (`tests/fakes.py`):** `FakeCompleter(responses: list[str])` with `.calls`, and `FakeEmbedder(dim: int = 4, table: dict[str, list[float]] | None = None)`.

`infra/models/roles.yaml` must contain exactly:

```yaml
worker:  {ollama_tag: "qwen3.5:4b",        family: qwen,  num_ctx: 8192, think: false}
checker: {ollama_tag: "gemma4:e2b-it-qat", family: gemma, num_ctx: 8192, think: false}
night:   {ollama_tag: "gemma4:12b-it-qat", family: gemma, num_ctx: 8192, think: false}
embed:   {ollama_tag: "bge-m3",            family: bge,   num_ctx: 8192, think: false}
vision:  {ollama_tag: "qwen3.5:4b",        family: qwen,  num_ctx: 8192, think: false}
```

- [ ] **Step 1: Write the failing tests**

```python
def test_load_roles_repo_file_ok():
    roles = load_roles(Path("infra/models/roles.yaml"), allow_cloud=False)
    assert roles[Role.WORKER].family != roles[Role.CHECKER].family

def test_same_family_worker_checker_rejected(tmp_path):   # write a yaml where both are qwen
    with pytest.raises(RoleConfigError, match="family"): load_roles(bad, allow_cloud=False)

def test_missing_role_rejected(tmp_path):
    with pytest.raises(RoleConfigError, match="missing"): load_roles(no_vision, allow_cloud=False)

def test_bad_tag_rejected(tmp_path):                      # tag "qwen3.5:4b; rm -rf /"
    with pytest.raises((RoleConfigError, ValidationError)): load_roles(bad_tag, allow_cloud=False)

def test_strip_thinking_removes_block():
    assert strip_thinking("<think>plan</think>\n{\"a\": 1}") == '{"a": 1}'

class Out(BaseModel):
    a: int

async def test_complete_json_returns_model():
    fc = FakeCompleter(['{"a": 1}'])
    assert (await complete_json(fc, Role.WORKER, "sys", "user", Out)).a == 1
    assert "properties" in fc.calls[0]["json_schema"]

async def test_complete_json_retries_once_then_raises():
    fc = FakeCompleter(["not json", '{"a": "x"}'])
    with pytest.raises(LLMOutputError): await complete_json(fc, Role.WORKER, "s", "u", Out)
    assert len(fc.calls) == 2

async def test_complete_json_accepts_think_prefix():
    assert (await complete_json(FakeCompleter(['<think>x</think>{"a": 2}']), Role.WORKER, "s", "u", Out)).a == 2
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/llm -v`
Expected: FAIL

- [ ] **Step 3: Implement `roles.py` and `client.py`**

`load_roles` raises `RoleConfigError` for:
- **"missing":** a role is absent
- **"family":** the worker and checker share a family
- **"provider":** a non-ollama provider while `allow_cloud` is false

`complete_json`:
1. Sends `[{"role": "system", ...}, {"role": "user", ...}]` with `json_schema=schema.model_json_schema()`.
2. Applies `strip_thinking`, then `schema.model_validate_json`.
3. On a validation or JSON error, retries until `attempts` is used up, then raises `LLMOutputError`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/llm -v`
Expected: `8 passed`

- [ ] **Step 5: Write the live smoke test (it runs after Task 9 pulls the models)**

`tests/llm/test_live_smoke.py`, marker `live`: `complete_json(LiteLLMCompleter(...), Role.WORKER, "Return JSON.", "Give a=3", Out)`. It asserts `.a == 3` and that the raw reply has no `<think>`.

- [ ] **Step 6: Commit**

```bash
git add infra/models src/techradar/llm tests/fakes.py tests/llm && git commit -m "feat(llm): model roles with family rule and JSON client"
```

### Task 9: Model downloads and the fit test

**SEC:** SEC-23 (official Ollama library only); decision D6

**Files:**
- Create: `evals/__init__.py`, `evals/fit/__init__.py`, `evals/fit/fit.py`, `evals/fit/results/.gitkeep`, `infra/models/README.md`
- Modify:
  - `infra/docker/Dockerfile`: add a test-only `evals` target (`uv sync --frozen --extra worker --group dev`, copies `src/`, `tests/`, `evals/`)
  - `compose.yaml`: add the `evals` service (profile `test`, network `llm` only, baseline hardening, a writable mount `./evals/fit/results`)
- Test: `tests/evals/test_fit.py`

**Interfaces:**
- Consumes: Ollama API `/api/generate` (with `options.num_ctx=8192`, `stream=false`; it returns `eval_count` and `eval_duration` in nanoseconds) and `/api/ps` (models with `size` and `size_vram`).
- Produces:
  - `class FitResult(BaseModel)`: `tag: str`, `size_bytes: int`, `size_vram_bytes: int`, `fit: Literal["fits","split","mostly_ram"]`, `tokens_per_s: float`
  - `def classify_fit(size: int, size_vram: int) -> Literal["fits","split","mostly_ram"]`: a ratio of at least 0.99 is `fits`, at least 0.5 is `split`, otherwise `mostly_ram`
  - `def ps_sizes(ps_json: dict, tag: str) -> tuple[int, int]`
  - `def choose_worker(results: dict[str, FitResult]) -> tuple[str, str]`: returns `("gemma4:e4b-it-qat", "qwen3.5:4b")` only if that model `fits` and runs at 20 or more tokens/s; otherwise `("qwen3.5:4b", "gemma4:e2b-it-qat")`
  - `async def measure(tag: str, base_url: str, *, prompt_tokens: int = 2000, gen_tokens: int = 256) -> FitResult`
  - CLI `python -m evals.fit.fit --base-url URL TAG...`, which writes `evals/fit/results/<YYYY-MM-DD>.json`

- [ ] **Step 1: Write the failing tests**

```python
def test_classify_fit_thresholds():
    assert classify_fit(100, 100) == "fits"
    assert classify_fit(100, 60) == "split"
    assert classify_fit(100, 10) == "mostly_ram"

def test_ps_sizes_reads_fixture():
    ps = {"models": [{"name": "qwen3.5:4b", "size": 4_000, "size_vram": 4_000}]}
    assert ps_sizes(ps, "qwen3.5:4b") == (4_000, 4_000)

def test_choose_worker_promotes_e4b_only_when_fast_and_fits():
    r = lambda fit, tps: FitResult(tag="gemma4:e4b-it-qat", size_bytes=1, size_vram_bytes=1, fit=fit, tokens_per_s=tps)
    assert choose_worker({"gemma4:e4b-it-qat": r("fits", 25.0)}) == ("gemma4:e4b-it-qat", "qwen3.5:4b")
    assert choose_worker({"gemma4:e4b-it-qat": r("split", 25.0)}) == ("qwen3.5:4b", "gemma4:e2b-it-qat")
    assert choose_worker({"gemma4:e4b-it-qat": r("fits", 12.0)}) == ("qwen3.5:4b", "gemma4:e2b-it-qat")
    assert choose_worker({}) == ("qwen3.5:4b", "gemma4:e2b-it-qat")
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/evals/test_fit.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `evals/fit/fit.py`**

`measure`:
1. Builds a prompt of about `prompt_tokens` words of filler text.
2. Calls `/api/generate` with `num_predict=gen_tokens`.
3. Computes tokens/s as `eval_count / (eval_duration / 1e9)`.
4. Reads `/api/ps` to classify the fit.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/evals/test_fit.py -v`
Expected: `3 passed`

- [ ] **Step 5 (owner): Pull the models through the one-off profile**

`infra/models/README.md` lists these commands and sizes (from the Ollama library on 2026-11-07):
- `qwen3.5:4b`: 3.3–4.0 GB
- `gemma4:e2b-it-qat`: 4.3 GB
- `gemma4:12b-it-qat`: 7.2 GB
- `bge-m3`: about 1.2 GB
- `gemma4:e4b-it-qat`: 6.1 GB, test only

Run, one model at a time: `docker compose stop ollama && docker compose --profile pull run --rm -e MODEL=qwen3.5:4b ollama-pull && docker compose start ollama`
Expected: `success` for each model.

- [ ] **Step 6 (owner): Run the fit test and apply the rule**

Run: `docker compose --profile test run --rm evals python -m evals.fit.fit --base-url http://ollama:11434 qwen3.5:4b gemma4:e2b-it-qat gemma4:12b-it-qat gemma4:e4b-it-qat && docker compose --profile test run --rm -e TR_OLLAMA_BASE_URL=http://ollama:11434 evals pytest -m live tests/llm/test_live_smoke.py -v`
Expected:
- a results table and the chosen worker/checker
- the live smoke test passes
- if `choose_worker` picks E4B, update `roles.yaml` (worker `gemma4:e4b-it-qat`, checker `qwen3.5:4b`, family rule still holds)

- [ ] **Step 7: Commit**

```bash
git add evals infra/models tests/evals && git commit -m "feat(evals): model fit test and worker choice rule"
```

### Task 10: Owner-only Telegram bot with `/status`

**SEC:** SEC-05, SEC-07, SEC-26

**Files:**
- Create: `src/techradar/bot/__init__.py`, `src/techradar/bot/auth.py`, `src/techradar/bot/routing.py`, `src/techradar/bot/render.py`, `src/techradar/bot/main.py`, `src/techradar/ops/__init__.py`, `src/techradar/ops/status.py`
- Modify: `infra/docker/Dockerfile` (add the `bot` target), `compose.yaml` (add the `bot` service)
- Test: `tests/bot/test_auth.py`, `tests/bot/test_routing.py`, `tests/bot/test_render.py`, `tests/ops/test_status.py`

**Interfaces:**
- Consumes: `Settings`, `read_secret`, `configure_logging`, `make_engine("app")`, and `http://squid:3128` (Task 6).
- Produces:
  - `def is_allowed(chat_id: int | None, owner_id: int, group_ids: frozenset[int] = frozenset()) -> bool`
  - `Action = Literal["start", "status", "ignore"]`
  - `def route_update(chat_id: int | None, text: str | None, owner_id: int) -> Action`
  - `START_TEXT = "Hi. TechRadar Brain is running. Send /status to check it."`
  - `class SystemStatus(BaseModel)`: `version: str`, `db_ok: bool`, `ollama_ok: bool`, `loaded_models: list[str]`, `disk_free_pct: float`
  - `async def collect_status(db_check: Callable[[], Awaitable[bool]], ollama_ps: Callable[[], Awaitable[list[str] | None]], disk_free_pct: Callable[[], float]) -> SystemStatus`
  - `def render_status(s: SystemStatus) -> str`
  - `def build_application(settings: Settings, token: str) -> Application`: proxy and get-updates proxy set to `settings.https_proxy`; handles `MESSAGE` updates only
- **Compose `bot` service:**
  - **Image:** target `bot` (`uv sync --frozen --no-dev --extra bot`, `CMD ["python","-m","techradar.bot.main"]`)
  - **Networks:** `db`, `egress_internal`, `llm` (to read Ollama's `/api/ps`)
  - **Secrets:** `telegram_bot_token`, `tr_app_password`
  - **Env:** `TR_TELEGRAM_OWNER_CHAT_ID` from `.env`
  - **Hardening:** the `x-hardened` baseline, `user: "1000:1000"`

- [ ] **Step 1: Write the failing tests**

```python
def test_is_allowed():
    assert is_allowed(42, 42) and not is_allowed(7, 42) and not is_allowed(None, 42)
    assert is_allowed(-100, 42, frozenset({-100}))

def test_route_owner_commands():
    assert route_update(42, "/status", 42) == "status" and route_update(42, "/start", 42) == "start"

def test_route_stranger_ignored():
    assert route_update(7, "/status", 42) == "ignore"

def test_route_update_ignores_non_text():
    assert route_update(42, None, 42) == "ignore" and route_update(42, "hello", 42) == "ignore"

def test_render_status_ok():
    s = SystemStatus(version="0.1.0", db_ok=True, ollama_ok=True, loaded_models=["qwen3.5:4b"], disk_free_pct=72.4)
    assert render_status(s) == "TechRadar Brain v0.1.0\nDatabase: ok\nModels: ok (loaded: qwen3.5:4b)\nDisk free: 72%"

def test_render_status_low_disk():
    s = SystemStatus(version="0.1.0", db_ok=True, ollama_ok=True, loaded_models=[], disk_free_pct=12.0)
    assert render_status(s).splitlines()[2:] == ["Models: ok (none loaded)", "Disk free: 12% (low)"]

async def test_status_ollama_down():
    async def up(): return True
    async def down(): return None
    s = await collect_status(up, down, lambda: 50.0)
    assert not s.ollama_ok and render_status(s).splitlines()[2] == "Models: down"

async def test_status_db_down():
    async def no(): return False
    async def models(): return []
    assert render_status(await collect_status(no, models, lambda: 50.0)).splitlines()[1] == "Database: down"
```

- [ ] **Step 2: Run to see them fail**

Run: `uv run pytest tests/bot tests/ops -v`
Expected: FAIL

- [ ] **Step 3: Implement the modules**

- **`main.py`:**
  1. Calls `configure_logging(secrets=[token])`.
  2. Registers a single `MessageHandler(filters.UpdateType.MESSAGE, ...)` that calls `route_update`.
  3. For `ignore` from a stranger, logs `WARNING "ignored update from chat %s"` and sends nothing.
  4. For `status`, calls `collect_status` with a `SELECT 1` check, `/api/ps` names, and `shutil.disk_usage(settings.data_dir)`.
- **`render_status`:** rounds the disk figure to a whole percent and adds ` (low)` below 15.

- [ ] **Step 4: Run the tests and the policy check**

Run: `uv run pytest tests/bot tests/ops tests/security/test_compose_policy.py -v`
Expected: all pass

- [ ] **Step 5 (owner): Try it on the server**

Run: `docker compose up -d --build bot`
- Send `/status` from my phone. Expected: the four-line reply.
- Send `/status` from a second Telegram account. Expected: no reply.

Run: `docker compose logs bot | grep "ignored update"`
Expected: one line with the second account's chat ID.

- [ ] **Step 6: Commit**

```bash
git add src/techradar/bot src/techradar/ops infra/docker compose.yaml tests/bot tests/ops && git commit -m "feat(bot): owner-only Telegram bot with /status"
```

### Task 11: Backups and the restore test

**SEC:** SEC-14

**Files:**
- Create: `infra/backup/backup.sh`, `infra/backup/restore_test.sh`, `infra/backup/techradar-backup.service`, `infra/backup/techradar-backup.timer`
- Test: `tests/infra/test_backup_units.py`

**Interfaces:**
- Produces:
  - **`backup.sh`:**
    1. Runs with `set -euo pipefail`.
    2. Writes `pg_dump -Fc -U tr_migrator -d techradar` through `docker compose exec -T postgres` to `$BACKUP_DIR/pg/techradar-<UTC timestamp>.dump`, keeping the newest 14.
    3. On Sundays, if the restic repository on the external drive is mounted, runs `restic backup` of `$BACKUP_DIR/pg`, `$VAULT_DIR` and `$SECRETS_DIR` (with `RESTIC_PASSWORD_FILE=$SECRETS_DIR/restic_password`).
    4. Then runs `restic forget --keep-weekly 8 --keep-monthly 12 --prune`.
  - **`restore_test.sh`:**
    1. Restores the newest dump into the scratch database `techradar_restore_test`.
    2. Compares row counts of every table in schema `techradar` against the live database.
    3. Prints `RESTORE OK (<n> tables match)` or exits 1.
    4. Always drops the scratch database.
  - **Timer:** `OnCalendar=*-*-* 02:30:00` and `Persistent=true`; the server's time zone is `Asia/Kolkata`.

- [ ] **Step 1: Write the failing unit-file test**

```python
def test_backup_timer_is_persistent():
    timer = Path("infra/backup/techradar-backup.timer").read_text()
    assert "OnCalendar=*-*-* 02:30:00" in timer and "Persistent=true" in timer
```

- [ ] **Step 2: Run to see it fail**

Run: `uv run pytest tests/infra/test_backup_units.py -v`
Expected: FAIL

- [ ] **Step 3: Write the scripts and systemd units**

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/infra -v && shellcheck infra/backup/*.sh && bash infra/backup/backup.sh && bash infra/backup/restore_test.sh`
Expected: `1 passed`; shellcheck prints nothing; a new dump file; `RESTORE OK (1 tables match)`

- [ ] **Step 5 (owner): Install the timer**

Run: `sudo cp infra/backup/techradar-backup.* /etc/systemd/system/ && sudo systemctl enable --now techradar-backup.timer && systemctl list-timers techradar-backup.timer`
Expected: the next run is listed at 02:30.

- [ ] **Step 6: Commit**

```bash
git add infra/backup tests/infra && git commit -m "feat(backup): nightly dump, weekly restic, restore test"
```

### Task 12: Host runbook and read-only host check

**SEC:** SEC-01, SEC-03, SEC-04, SEC-13, SEC-31, SEC-36

**Files:**
- Create: `infra/host/RUNBOOK.md`, `infra/host/check_host.sh`

**Interfaces:**
- Produces:
  - **`check_host.sh`:** read-only; prints one `PASS`, `FAIL` or `WARN` line per check; exits 1 on any `FAIL`.
  - **`RUNBOOK.md`:** the owner steps that make every check pass.

- [ ] **Step 1: Write `RUNBOOK.md`**

Ubuntu LTS steps, each with its command and expected output:
1. **Time zone:** `timedatectl set-timezone Asia/Kolkata`.
2. **Automatic updates:** `unattended-upgrades` enabled.
3. **Firewall:** `ufw default deny incoming`, `ufw default allow outgoing`, `ufw enable`.
4. **Tailscale:** install, `tailscale up --ssh`. In the admin console: device approval on, key expiry on, Funnel off, and an access rule giving only my devices access to the server.
5. **SSH:** disable `ssh.service`, or bind it to the Tailscale address only.
6. **Docker:** Docker Engine with the Compose plugin. `/etc/docker/daemon.json` = `{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"},"live-restore":true,"no-new-privileges":true}`.
7. **GPU:** NVIDIA driver from the distro, plus the NVIDIA Container Toolkit; check with `nvidia-smi`.
8. **Battery:** `asusctl -c 80`.
9. **Always-on mode only:** `HandleLidSwitch=ignore` and `HandleLidSwitchExternalPower=ignore` in `/etc/systemd/logind.conf`.
10. **Docker group:** only my user in `docker`.
11. **Encryption and boot:** confirm LUKS (`lsblk -o NAME,TYPE`), Secure Boot (`mokutil --sb-state`) and AppArmor (`aa-status`).
12. **Router:** UPnP off, no port forwarding.
13. **Dual boot:** Linux is the default boot entry; Windows is updated with Defender on; a Linux recovery USB is ready.

- [ ] **Step 2: Write `check_host.sh`**

The checks, in order:
1. ufw is active with `deny (incoming)`.
2. `ss -ltnH` shows no TCP listener outside `127.0.0.0/8`, `::1`, `100.64.0.0/10` and `fd7a:115c:a1e0::/48`.
3. `unattended-upgrades` is enabled.
4. `tailscale status` succeeds.
5. The `docker` group members are exactly `$OWNER`.
6. `daemon.json` has `max-size` and `"no-new-privileges": true` (read with `jq`).
7. `aa-status --enabled` succeeds.
8. `lsblk` shows a `crypt` device.
9. `mokutil --sb-state` says enabled; `WARN` otherwise.
10. `timedatectl` shows the time zone is `Asia/Kolkata`.
11. `techradar-backup.timer` is active.
12. `nvidia-smi` succeeds.

- [ ] **Step 3: Verify**

Run: `shellcheck infra/host/check_host.sh && sudo OWNER="$USER" bash infra/host/check_host.sh`
Expected: shellcheck clean; every line `PASS` (Secure Boot may be `WARN`); exit code 0.

- [ ] **Step 4: Commit**

```bash
git add infra/host && git commit -m "docs(host): hardening runbook and read-only host check"
```

### Task 13: Approved dependencies and the allowlists for MCP servers, skills and plugins

**SEC:** SEC-52, SEC-53

**Files:**
- Create: `infra/policy/approved_deps.yaml`, `infra/policy/popular_packages.txt`, `scripts/check_deps.py`, `scripts/vet_package.py`, `scripts/check_mcp.py`, `scripts/check_skills.py`, `tests/security/fixtures/skills_unlisted/shady-skill/SKILL.md`, `tests/security/fixtures/skills_changed/helper/SKILL.md`, `tests/security/fixtures/deps/pyproject_lookalike.toml`, `tests/security/fixtures/deps/mcp_unlisted.json`, `tests/security/fixtures/deps/mcp_latest.json`
- Modify: `AGENTS.md` (the "Allowed MCP servers" and "Allowed skills and plugins" tables, plus the `exclude-newer` rule below), `.github/workflows/ci.yml` (a `policy` job running both checks), `pyproject.toml` (`[tool.uv] exclude-newer = "2026-11-07T00:00:00Z"`)
- Test: `tests/security/test_check_deps.py`, `tests/security/test_check_mcp.py`, `tests/security/test_check_skills.py`

**Interfaces:**
- Produces:
  - **`approved_deps.yaml`:** `python: {<name>: {why: str, approved: date}}` and `npm: {<name>: {…}}`, seeded with every direct dependency from Task 1 (base, extras and the dev group). The `npm` map starts empty; phase 4 adds the web app's packages.
  - `def normalize(name: str) -> str`: PEP 503 (lowercase; runs of `-`, `_`, `.` become `-`)
  - `def direct_python_deps(pyproject: dict) -> set[str]`: `project.dependencies`, every `project.optional-dependencies` list and every `dependency-groups` list, with extras and version specifiers stripped, then normalized
  - `def direct_npm_deps(package_json: dict) -> set[str]`: `dependencies` and `devDependencies` keys
  - `def unapproved(found: set[str], approved: set[str]) -> list[str]`, sorted
  - `def lookalikes(name: str, popular: Sequence[str], max_distance: int = 2) -> list[str]`: popular names at Damerau–Levenshtein distance 1–2 (an exact match isn't a look-alike)
  - **CLI** `python scripts/check_deps.py [--pyproject PATH] [--package-json PATH]… [--approved PATH]`: exit 0 when everything is approved; otherwise exit 1 and print one line per unapproved name, `unapproved: <name> (looks like: <names>)`
  - **`vet_package.py <pypi|npm> <name>`** (runs on the Mac, needs the internet; never edits files) prints:
    - the first release date and age in days, with `needs a reason` under 90 days
    - look-alikes
    - monthly downloads
    - the source repository URL and maintainers
    - OSV vulnerabilities
  - `class AllowedServer(BaseModel)`: `name`, `command`, `version`, `access`, `why`
  - `def read_allowlist(agents_md: str) -> dict[str, AllowedServer]`: the table between `<!-- mcp-allowlist:start -->` and `<!-- mcp-allowlist:end -->`
  - `def mcp_problems(config: dict, allow: Mapping[str, AllowedServer]) -> list[str]`. For each entry in `mcpServers`:
    - `<name>: not allowed` when it isn't in the allowlist
    - `<name>: not pinned` when its args contain `@latest`, or an `npx`/`uvx` package without an exact version
    - `<name>: secret in config` when an env value under a key containing `TOKEN`, `KEY` or `SECRET` isn't a `${…}` placeholder
  - **CLI** `python scripts/check_mcp.py`: scans every committed MCP config that exists (`.mcp.json`, `.cursor/mcp.json`, `.vscode/mcp.json`, `.gemini/settings.json`, `mcp_config.json`); exit 1 on any problem
  - `class AllowedExtension(BaseModel)`: `name`, `kind: Literal["skill","plugin"]`, `source`, `commit`, `sha256: str | None`, `why`
  - `def read_skills_allowlist(agents_md: str) -> dict[str, AllowedExtension]`: the table between `<!-- skills-allowlist:start -->` and `<!-- skills-allowlist:end -->`
  - `def folder_hash(folder: Path) -> str`: SHA-256 over every file's relative path and bytes, in sorted order
  - `def skill_problems(repo: Path, allow: Mapping[str, AllowedExtension]) -> list[str]`:
    - **Skills:** every folder holding a `SKILL.md`, anywhere in the repo except `tests/security/fixtures/`, is a skill named after its folder. It gives `<name>: not allowed` when the skill isn't listed, and `<name>: changed` when `folder_hash` differs from the listed `sha256`.
    - **Plugins:** every plugin enabled in a committed agent settings file (`.claude/settings.json` `enabledPlugins`, and any other agent's settings file the repo adds later) gives `<name>: not allowed` when it isn't listed as a plugin.
  - **CLI** `python scripts/check_skills.py`: exit 1 on any problem. The CI `policy` job runs it with the other two checks.
  - **`AGENTS.md` rule:** "`exclude-newer` in `pyproject.toml` is moved forward only on purpose, when I update dependencies."

- [ ] **Step 1: Write the failing tests**

```python
def test_lookalike_dependency_fails():
    r = run_check_deps("--pyproject", "tests/security/fixtures/deps/pyproject_lookalike.toml")   # adds "reqeusts"
    assert r.returncode == 1 and "unapproved: reqeusts (looks like: requests)" in r.stdout

def test_repo_dependencies_all_approved():
    assert run_check_deps().returncode == 0

def test_normalises_names_and_strips_extras():
    deps = direct_python_deps({"project": {"dependencies": ["psycopg[binary]>=3", "Pydantic_Settings"]}})
    assert deps == {"psycopg", "pydantic-settings"}

def test_lookalikes():
    assert lookalikes("reqeusts", ["requests", "numpy"]) == ["requests"]
    assert lookalikes("requests", ["requests"]) == []

def test_mcp_unlisted_server_fails():
    assert mcp_problems(load("mcp_unlisted.json"), {}) == ["shady-tools: not allowed"]

def test_mcp_latest_fails():
    allow = {"vault": AllowedServer(name="vault", command="uvx", version="1.0.0", access="read", why="notes")}
    assert "vault: not pinned" in mcp_problems(load("mcp_latest.json"), allow)

def test_unlisted_skill_fails():
    assert skill_problems(FIXTURES / "skills_unlisted", {}) == ["shady-skill: not allowed"]

def test_changed_skill_fails():
    allow = {"helper": AllowedExtension(name="helper", kind="skill", source="https://github.com/example/skills", commit="0" * 40, sha256="0" * 64, why="test")}
    assert skill_problems(FIXTURES / "skills_changed", allow) == ["helper: changed"]
```

`run_check_deps(*args)` runs `scripts/check_deps.py` with `subprocess.run([sys.executable, ...], capture_output=True, text=True)`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/security/test_check_deps.py tests/security/test_check_mcp.py tests/security/test_check_skills.py -v`
Expected: FAIL (scripts missing)

- [ ] **Step 3: Implement the four scripts, the skill fixtures, the YAML, the popular-packages list (the top 500 PyPI and top 500 npm names, one per line) and the CI job**

- [ ] **Step 4: Run the tests and both checks**

Run: `uv run pytest tests/security/test_check_deps.py tests/security/test_check_mcp.py tests/security/test_check_skills.py -v && uv run python scripts/check_deps.py && uv run python scripts/check_mcp.py && uv run python scripts/check_skills.py`
Expected: PASS; all three checks exit 0.

- [ ] **Step 5: Commit**

```bash
git add infra/policy scripts tests/security AGENTS.md .github pyproject.toml && git commit -m "security(policy): approved dependencies and allowlists for MCP servers, skills and plugins"
```

### Task 14: Alerter, alert log, containment and the daily heartbeat

**SEC:** SEC-59, SEC-65, SEC-66

**Files:**
- Create: `src/techradar/hostsec/__init__.py`, `src/techradar/hostsec/alerts.py`, `src/techradar/hostsec/sources.py`, `src/techradar/hostsec/contain.py`, `src/techradar/hostsec/alerter.py`, `infra/host/alerter/techradar-alerter.service`, `infra/host/alerter/techradar-heartbeat.service`, `infra/host/alerter/techradar-heartbeat.timer`, `infra/host/evidence.pub.example`
- Modify: `pyproject.toml` (extra `hostsec = ["httpx"]`), `src/techradar/settings.py` (fields below), `infra/host/RUNBOOK.md` (alerter bot, evidence key, install steps)
- Test: `tests/hostsec/test_alerts.py`, `tests/hostsec/test_sources.py`, `tests/hostsec/test_contain.py`

**Interfaces:**
- Consumes: `RedactingFilter` patterns (Task 4); `read_secret` (Task 3).
- Produces:
  - **Settings:**

    | Field | Type | Default |
    |---|---|---|
    | `alert_chat_id` | `int \| None` | `None` (falls back to `telegram_owner_chat_id`) |
    | `containment` | `Literal["alert-only","on"]` | `"alert-only"` |
    | `heartbeat_time` | `str` | `"06:25"` |
    | `quiet_hours` | `str` | `"23:00-06:00"` |
    | `alert_log` | `Path` | `/var/lib/techradar-alerter/alerts.jsonl` |
    | `incidents_dir` | `Path` | `data/incidents` |
    | `evidence_pubkey` | `Path` | `infra/host/evidence.pub` |

  - `class Level(StrEnum)`: `CRITICAL="critical"`, `WARNING="warning"`, `INFO="info"`
  - `class Alert(BaseModel)`:
    - `level: Level`
    - `source: Literal["falco","auditd","journal","pgaudit","squid","aide","integrity","resources","gateway","alerter"]`
    - `rule: str` (≤80)
    - `service: str | None` (`^[a-z0-9-]{1,40}$`, a Compose service name)
    - `summary: str` (≤200)
    - `at: datetime`
  - `def render_alert(a: Alert, action: str) -> str`, exactly `🚨 CRITICAL · <service or "host"> · <rule>\n<summary>\n<HH:MM> · <action>` (`⚠️ WARNING` for warnings). The summary passes the Task 4 redaction patterns first.
  - `def group_key(a: Alert) -> str` returns `f"{a.source}:{a.rule}:{a.service}"`. Warnings with the same key within 60 minutes become one message ending ` (×<n>)`.
  - `def should_send_now(a: Alert, now_local: datetime, quiet: tuple[time, time]) -> bool`:
    - critical: always
    - warning: outside quiet hours; held warnings go out at the end of quiet hours
    - info: never (they appear in the heartbeat counts)
  - `class AlertLog`:
    - `__init__(self, path: Path)`
    - `def append(self, a: Alert) -> None`: opens with `O_APPEND`, mode 0o640; rotates at 10 MB, keeping 12 files
    - `def since(self, t: datetime) -> list[Alert]`
  - `def render_heartbeat(alerts_24h: Sequence[Alert]) -> str`:
    - with no critical alerts: `✅ All quiet: 0 critical, <w> warnings in the last 24 h.`
    - otherwise: `⚠️ <c> critical, <w> warnings in the last 24 h. Check the Security screen or the alert log.`
  - **Source parsers (`sources.py`),** each turning one input line into `Alert | None`:
    - `def from_falco(line: str) -> Alert | None`: Falco JSON. Priorities `Emergency`, `Alert`, `Critical` and `Error` become critical; `Warning` and `Notice` become warnings. `output_fields["container.name"]` `techradar-<service>-<n>` gives the service.
    - `def from_squid(line: str, client_map: Mapping[str, str]) -> Alert | None`: only `TCP_DENIED` lines. The client IP maps to a service through `client_map` (built from `docker network inspect`). `fetcher` gives a warning (rule `squid deny`); any other client gives a critical alert (rule `outbound attempt from <service>`).
    - `def from_journal(entry: dict) -> Alert | None`, by `SYSLOG_IDENTIFIER`:
      - `sudo`: a warning, rule `sudo used`
      - `systemd-logind` "New session": a warning, rule `login`
      - `audit` or `audisp-syslog`: key `tr_honey` critical, `tr_sudoers` critical, `tr_ssh` critical, `tr_secret_change` warning
      - `aide` with "found differences": a warning
      - `techradar-integrity` and `techradar-resources`: lines starting `CRITICAL ` or `WARNING ` keep that level
    - `def from_postgres(line: str, *, migrating: bool) -> Alert | None`:
      - `AUDIT: OBJECT` on `bank_credentials`: critical (rule `honeytoken table read`)
      - `AUDIT: SESSION` with class `ROLE`: critical unless `migrating` (the file `data/run/migrating` exists while `migrate` runs)
      - `password authentication failed for user "admin_backup"`: critical
      - any other failed login: a warning
  - **Containment (`contain.py`):**
    - `class Runner(Protocol)`: `def __call__(self, args: list[str], *, timeout_s: int = 60) -> subprocess.CompletedProcess`. Commands are always lists, never a shell.
    - `class Evidence(BaseModel)`: `dir: Path`, `files: list[str]`
    - `def collect_evidence(service: str, run: Runner, out_root: Path, pubkey: Path, falco_events: Sequence[str], now: datetime) -> Evidence`:
      1. Saves `docker compose logs --no-color --tail 5000 <service>`, `docker inspect`, `docker diff`, the changed files (via `docker cp`, up to 200 MB) and the given Falco events into `out_root/<UTC yyyy-mm-ddThhmm>-<service>/`.
      2. Encrypts each file with `age -R <pubkey>`, deletes the plain copy, and sets each file to mode 0o400.
    - `def contain(service: str, run: Runner) -> list[list[str]]`: `docker network disconnect` from every network the container is on, then `docker compose stop <service>`; returns the commands run
    - `def respond(a: Alert, mode: Literal["alert-only","on"], run: Runner, *, out_root: Path, pubkey: Path, falco_events: Sequence[str], now: datetime | None = None) -> str`:
      - a critical alert with a `service` while `mode == "on"`: evidence first, then `contain`; returns `contained after saving evidence`
      - otherwise: returns `alert only`
  - **`alerter.py`:** follows three streams:
    - `tail -F /var/log/falco/events.json`
    - `journalctl -f -o json` for the identifiers above
    - `docker compose logs -f --no-color squid postgres`

    For each line it runs the matching parser, then `AlertLog.append`, then sends through the Telegram Bot API (`sendMessage` with `alerter_bot_token`, straight from the host with httpx, 10 s timeout, 3 retries), then `respond`. `--heartbeat` sends `render_heartbeat` and exits.
  - **systemd units:**
    - **`techradar-alerter.service`:**
      - `User=<owner>`, `SupplementaryGroups=docker systemd-journal adm`
      - `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateTmp=yes`
      - `ReadWritePaths=/var/lib/techradar-alerter <repo>/data/incidents`
      - `Restart=always`
    - **`techradar-heartbeat.timer`:** `OnCalendar=*-*-* 06:25:00`, `Persistent=true`

- [ ] **Step 1: Write the failing tests**

```python
def test_falco_critical_maps_service():
    a = from_falco(FALCO_SHELL_IN_PARSER)             # fixture: priority Critical, container techradar-parser-1
    assert (a.level, a.service) == (Level.CRITICAL, "parser")

def test_squid_denied_fetcher_is_warning_other_is_critical():
    m = {"172.20.0.5": "fetcher", "172.20.0.9": "worker"}
    assert from_squid(deny_line("172.20.0.5"), m).level is Level.WARNING
    assert from_squid(deny_line("172.20.0.9"), m).level is Level.CRITICAL

def test_honeytoken_audit_is_critical():
    assert from_journal(AUDIT_HONEY_ENTRY).level is Level.CRITICAL

def test_admin_backup_login_is_critical():
    line = 'FATAL:  password authentication failed for user "admin_backup"'
    assert from_postgres(line, migrating=False).level is Level.CRITICAL

def test_role_change_during_migration_is_ignored():
    assert from_postgres(ROLE_AUDIT_LINE, migrating=True) is None

def test_render_alert_redacts_tokens():
    a = alert(summary="token 1234567890:AAEhBP0av28AAAAAAAAAAAAAAAAAAAAAAAA seen")
    assert "AAEhBP0av28" not in render_alert(a, "alert only")

def test_warnings_grouped_per_hour():
    msgs = feed_alerter([warning("squid deny", at=NOW + timedelta(minutes=10 * i)) for i in range(5)])
    assert len(msgs) == 1 and msgs[0].endswith("(×5)")

def test_quiet_hours_hold_warnings_not_criticals():
    q = (time(23), time(6))
    assert should_send_now(critical(), at_local("02:00"), q) and not should_send_now(warning(), at_local("02:00"), q)

def test_heartbeat_texts():
    assert render_heartbeat([]) == "✅ All quiet: 0 critical, 0 warnings in the last 24 h."
    assert render_heartbeat([critical()]).startswith("⚠️ 1 critical, 0 warnings")

def test_alert_log_is_append_only(tmp_path):
    log = AlertLog(tmp_path / "a.jsonl"); log.append(critical()); first = (tmp_path / "a.jsonl").read_text()
    log.append(warning("x")); assert (tmp_path / "a.jsonl").read_text().startswith(first)

def test_evidence_saved_before_stop(fake_runner, tmp_path):
    respond(critical(service="parser"), "on", fake_runner, out_root=tmp_path, pubkey=PUB, falco_events=[])
    calls = fake_runner.calls
    diff_at = next(i for i, c in enumerate(calls) if c[1] == "diff")
    first_disconnect = next(i for i, c in enumerate(calls) if c[1:3] == ["network", "disconnect"])
    assert diff_at < first_disconnect and calls[-1][-2:] == ["stop", "parser"]

def test_alert_only_mode_never_contains(fake_runner, tmp_path):
    assert respond(critical(service="parser"), "alert-only", fake_runner, out_root=tmp_path, pubkey=PUB, falco_events=[]) == "alert only"
    assert not any("stop" in c for c in fake_runner.calls)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/hostsec -v`
Expected: FAIL (package missing)

- [ ] **Step 3: Implement the modules and units**

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/hostsec -v`
Expected: PASS

- [ ] **Step 5 (owner): Create the alert bot and evidence key, then install**

1. In BotFather, create a second bot, "TechRadar Alerts". Save its token as `secrets/alerter_bot_token` (mode 600).
2. On the Mac, run `age-keygen -o ~/techradar-evidence.key`. Copy only the public key line to `infra/host/evidence.pub` on the server. The private key never goes to the server.
3. Install and start: `sudo cp infra/host/alerter/* /etc/systemd/system/ && sudo systemctl enable --now techradar-alerter.service techradar-heartbeat.timer`.
4. Run `sudo systemctl start techradar-heartbeat.service`.

Expected: `✅ All quiet: …` arrives from the alert bot.

- [ ] **Step 6: Commit**

```bash
git add src/techradar/hostsec src/techradar/settings.py infra/host pyproject.toml tests/hostsec && git commit -m "security(hostsec): alerter with its own bot, append-only log, containment and heartbeat"
```

### Task 15: Integrity checks, honeytokens, host and database auditing

**SEC:** SEC-60, SEC-61, SEC-62, SEC-63

**Files:**
- Create: `src/techradar/hostsec/integrity.py`, `scripts/integrity_check.py`, `scripts/plant_honeytokens.py`, `infra/host/audit/techradar.rules`, `infra/host/aide/techradar.conf`, `infra/host/timers/techradar-integrity.{service,timer}`, `infra/host/timers/techradar-aide.{service,timer}`, `infra/host/timers/techradar-lynis.{service,timer}`, `infra/postgres/Dockerfile`, `infra/backup/restic-excludes.txt`
- Modify: `compose.yaml` (`postgres` builds from `infra/postgres/Dockerfile`, with the pgaudit settings below as `command` flags), `infra/postgres/init/01-roles.sh` (role `tr_auditor NOLOGIN`; `CREATE EXTENSION pgaudit`), `infra/backup/backup.sh`, `infra/host/check_host.sh`, `infra/host/RUNBOOK.md`, `infra/falco/expected_programs.yaml` (no change in programs; the build keeps the same entrypoint)
- Test: `tests/hostsec/test_integrity.py`, `tests/hostsec/test_honeytokens.py`, `tests/infra/test_backup_units.py` (add tests), `tests/db/test_audit.py` (marker `db`)

**Interfaces:**
- Produces:
  - `def parse_docker_diff(text: str) -> list[tuple[Literal["A","C","D"], str]]`
  - `def unexpected_changes(changes: Sequence[tuple[str, str]], tmpfs: Sequence[str], volumes: Sequence[str]) -> list[str]`: paths that aren't under any tmpfs or volume mount (and aren't just the mount directory itself)
  - `def digest_mismatches(running: Mapping[str, str], pinned: Mapping[str, str]) -> list[str]`: the services whose running image ID differs from the pin. For built images, the pin is the image ID recorded at build time in `data/run/built-images.json`.
  - **`scripts/integrity_check.py`:** for every running service, prints one of:
    - `CRITICAL <service> unexpected changes: <paths>`
    - `CRITICAL <service> digest mismatch`
    - `OK <service>`

    The timer unit sends the output to the journal with identifier `techradar-integrity`; `--pinned-override <service>=<digest>` exists for the gate's simulation only.
  - **`scripts/plant_honeytokens.py --files --db [--verify]`** (I run it on the server; it prints paths only, never values):
    - `secrets/aws_root_key.txt`: a fake `AKIA…` key (mode 600)
    - `.env.production` in the repo root: a fake `DATABASE_URL` for `admin_backup` with a random password
    - Postgres role `admin_backup LOGIN` with a different random password that is thrown away, and no grants
    - table `techradar.bank_credentials` (owner `tr_migrator`, 5 fake rows), with `GRANT SELECT … TO tr_auditor` so every read is audited
    - `/var/lib/techradar-honey/excludes.txt`: the honey paths, read by restic and AIDE
    - auditd watches with key `tr_honey` for each honey file
    - `--verify` checks that the files exist, the audit rules are loaded and nothing has read them (no `tr_honey` events in the journal)
    - phase 2 adds `--vault`
  - **`infra/host/audit/techradar.rules`:**
    - `-w <repo>/secrets/ -p wa -k tr_secret_change`
    - `-w /etc/sudoers -p wa -k tr_sudoers` and `-w /etc/sudoers.d/ -p wa -k tr_sudoers`
    - `-w /home/<owner>/.ssh/authorized_keys -p wa -k tr_ssh`
    - the audisp syslog plugin turned on, so events reach the journal
  - **AIDE (`techradar.conf`):**
    - **Watches:** `/usr/bin`, `/usr/sbin`, `/etc`, `/etc/systemd/system`, `<repo>/compose.yaml` and `<repo>/infra`.
    - **Skips:** the paths in `/var/lib/techradar-honey/excludes.txt`.
    - **Schedule:** nightly at 03:15. After an approved update I refresh the baseline with `sudo aide --update` (RUNBOOK).
  - **Lynis:** a monthly timer runs `lynis audit system --quick --no-colors` and writes the hardening index to `docs/security/lynis/<YYYY-MM>.txt`.
  - **Postgres build:**
    - `FROM pgvector/pgvector:<exact>-pg18@sha256:<digest>`
    - `RUN apt-get update && apt-get install -y --no-install-recommends postgresql-18-pgaudit=<exact> && rm -rf /var/lib/apt/lists/*`
    - **`command` flags:** `shared_preload_libraries=pgaudit`, `pgaudit.log=role,ddl`, `pgaudit.role=tr_auditor`, `pgaudit.log_relation=on`, `log_connections=on`
  - **`backup.sh` changes:**
    - `pg_dump … --exclude-table-data=techradar.bank_credentials`
    - `restic backup … --exclude-file infra/backup/restic-excludes.txt --exclude-file /var/lib/techradar-honey/excludes.txt`
    - while `migrate` runs, `data/run/migrating` exists (the migrate service's entrypoint creates and removes it)

- [ ] **Step 1: Write the failing tests**

```python
def test_unexpected_changes_ignore_tmpfs_and_volumes():
    ch = parse_docker_diff("C /tmp\nA /tmp/x\nA /usr/bin/evil\nC /data/raw/a\n")
    assert unexpected_changes(ch, ["/tmp"], ["/data/raw"]) == ["/usr/bin/evil"]

def test_digest_mismatch():
    assert digest_mismatches({"postgres": "sha256:aa", "bot": "sha256:cc"}, {"postgres": "sha256:bb", "bot": "sha256:cc"}) == ["postgres"]

def test_backup_excludes_honeytokens():
    sh = Path("infra/backup/backup.sh").read_text()
    assert "--exclude-table-data=techradar.bank_credentials" in sh and "/var/lib/techradar-honey/excludes.txt" in sh

def test_aide_config_excludes_honeytokens():
    assert "/var/lib/techradar-honey/excludes.txt" in Path("infra/host/aide/techradar.conf").read_text()

def test_plant_script_never_prints_values(capsys, tmp_repo, fake_db):
    plant(tmp_repo, fake_db, files=True, db=True)
    out = capsys.readouterr().out
    assert "AKIA" not in out and fake_db.last_password not in out

@pytest.mark.db
async def test_reading_honey_table_is_audited(planted_db, app_conn, pg_log):
    await app_conn.execute(text("SELECT * FROM bank_credentials"))
    assert pg_log.contains("AUDIT: OBJECT") and pg_log.contains("bank_credentials")
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/hostsec tests/infra -v && uv run pytest -m db tests/db/test_audit.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the modules, scripts, rules, configs, Postgres build and units**

- [ ] **Step 4 (owner): Install on the server and plant the honeytokens**

Run:
```bash
sudo cp infra/host/audit/techradar.rules /etc/audit/rules.d/ && sudo augenrules --load
sudo cp infra/host/timers/* /etc/systemd/system/ && sudo systemctl enable --now techradar-integrity.timer techradar-aide.timer techradar-lynis.timer
docker compose build postgres && docker compose up -d postgres
uv run python scripts/plant_honeytokens.py --files --db && uv run python scripts/plant_honeytokens.py --verify
```
Expected: every check prints PASS; `sudo aide --init` has created a baseline; the next backup runs without touching a honeytoken (no `tr_honey` alert).

- [ ] **Step 5: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/techradar/hostsec scripts infra tests compose.yaml && git commit -m "security(hostsec): integrity checks, honeytokens, auditd, pgaudit and Lynis"
```

### Task 16: Falco runtime monitoring

**SEC:** SEC-58

**Files:**
- Create: `infra/falco/techradar_rules.yaml`, `infra/falco/expected_programs.yaml`, `infra/falco/generated_lists.yaml` (generated, committed), `infra/falco/techradar-output.yaml`, `infra/falco/logrotate`, `scripts/build_falco_lists.py`
- Modify: `infra/host/RUNBOOK.md` (install Falco from the falcosecurity apt repository at an exact version, with the `modern_ebpf` driver), `infra/host/check_host.sh` (Falco is active)
- Test: `tests/security/test_falco_rules.py`, `tests/security/test_falco_live.py` (marker `live`)

**Interfaces:**
- Produces:
  - **`expected_programs.yaml`:**
    - **`services`:** each Compose service and the program names it may run. This phase: `bot: [python]`, `migrate: [alembic, python]`, `postgres: [postgres, pg_isready, pg_dump, pg_restore, psql]`, `squid: [squid, log_file_daemon]`, `ollama: [ollama]`. Later phases add their services.
    - **`internal_only`:** services that may connect only to peers on their own Docker networks: `worker`, `jarvis`, `api`, `postgres`, `ollama`, `voice-worker`.
    - **`no_network`:** `parser`, `clamav`.
    - **`root_start`:** the Task 5 exceptions.
    - **`excluded_profiles`:** `ollama-pull`, `egress-probe`, `evals`, `redteam`, `zap`. These run only when I start them.
  - `def build_lists(expected: dict) -> str`: Falco YAML with one `- list: tr_<service>_programs` per service, plus the macro `tr_app_container` (container name starts with `techradar-` and isn't an excluded profile)
  - **Rules in `techradar_rules.yaml`** (from 06 H6), exact names:

    | Rule | Condition, in words | Priority |
    |---|---|---|
    | `TR shell or package manager in container` | a process named `sh`, `bash`, `dash`, `ash`, `zsh`, `apt`, `apt-get`, `dpkg`, `pip`, `pip3`, `npm`, `npx` or `uv` starts in a `tr_app_container` | CRITICAL |
    | `TR network tool in container` | `curl`, `wget`, `nc`, `ncat`, `socat`, `ssh`, `scp` or `telnet` starts in a `tr_app_container` | CRITICAL |
    | `TR unexpected program` | a process outside the service's list starts | WARNING |
    | `TR connection from no-network service` | any `connect` from a `no_network` container | CRITICAL |
    | `TR connection outside allowed peers` | an `internal_only` container connects to an address outside its Docker networks | CRITICAL |
    | `TR outbound not via squid` | `fetcher`, `bot`, `changedetection`, `searxng` or `clamav-update` connects to anything but Squid or its own internal peers | CRITICAL |
    | `TR secret read by unexpected program` | a file under `/run/secrets/` is opened by a program outside the service's list | CRITICAL |
    | `TR write outside tmpfs or volumes` | a write to the container's root filesystem outside its tmpfs and volume paths | WARNING |
    | `TR new root process` | a process with uid 0 starts in a container that isn't in `root_start` | CRITICAL |
    | `TR docker socket access` | `/var/run/docker.sock` is opened from inside a container | CRITICAL |

  - **Output (`techradar-output.yaml`, dropped into `/etc/falco/config.d/`):** `json_output: true`; `file_output` enabled with `filename: /var/log/falco/events.json`; `stdout_output` off; `logrotate` daily, keeping 14 files

- [ ] **Step 1: Write the failing tests**

```python
EXP = yaml.safe_load(Path("infra/falco/expected_programs.yaml").read_text())

def test_every_compose_service_has_expected_programs():
    services = set(yaml.safe_load(Path("compose.yaml").read_text())["services"])
    assert services - set(EXP["services"]) - set(EXP["excluded_profiles"]) == set()

def test_generated_lists_up_to_date():
    assert build_lists(EXP) == Path("infra/falco/generated_lists.yaml").read_text()

def test_rules_file_has_required_rules():
    names = {r["rule"] for r in yaml.safe_load(Path("infra/falco/techradar_rules.yaml").read_text()) if "rule" in r}
    assert {"TR shell or package manager in container", "TR network tool in container",
            "TR connection from no-network service", "TR docker socket access"} <= names

@pytest.mark.live
def test_shell_in_bot_raises_critical_within_60s(alert_log):
    subprocess.run(["docker", "compose", "exec", "-T", "bot", "sh", "-c", "true"], check=True, timeout=30)
    assert alert_log.wait_for(rule="TR shell or package manager in container", service="bot", timeout_s=60)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/security/test_falco_rules.py -v`
Expected: FAIL

- [ ] **Step 3: Write the rules, the expected-programs file, the generator and the output settings; run the generator**

- [ ] **Step 4: Validate on the server and run the live test**

Run: `uv run pytest tests/security/test_falco_rules.py -v && sudo falco --validate infra/falco/techradar_rules.yaml && sudo systemctl restart falco-modern-bpf && uv run pytest -m live tests/security/test_falco_live.py -v`
Expected: PASS; the alert bot reports the shell in `bot` (containment is `alert-only`, so `bot` keeps running).

- [ ] **Step 5: Commit**

```bash
git add infra/falco scripts/build_falco_lists.py infra/host tests/security && git commit -m "security(falco): runtime rules for every container"
```

Every later phase that adds a Compose service also adds it to `expected_programs.yaml` and reruns the generator; `test_every_compose_service_has_expected_programs` fails otherwise.

### Task 17: Resource watcher

**SEC:** SEC-64 (D47)

**Files:**
- Create: `src/techradar/hostsec/resources.py`, `infra/host/timers/techradar-resources.{service,timer}` (every minute)
- Test: `tests/hostsec/test_resources.py`

**Interfaces:**
- Produces:
  - `class GpuApp(BaseModel)`: `pid: int`, `name: str`, `used_mib: int`
  - `def parse_gpu_apps(csv_text: str) -> list[GpuApp]`, from `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits`
  - `def service_of_pid(pid: int, cgroup_text: str, containers: Mapping[str, str]) -> str | None`: the Docker container ID in `/proc/<pid>/cgroup`, then the Compose service through `containers`
  - `GPU_SERVICES = {"ollama", "voice-worker", "voice-live", "evals"}`
  - `def check_gpu(apps: Sequence[GpuApp], services: Mapping[int, str | None]) -> list[str]`: `CRITICAL unknown GPU process <name>` for each process outside `GPU_SERVICES`
  - `def check_gpu_busy(util_last_15min: Sequence[int], loaded_models: Sequence[str], voice_running: bool) -> str | None`: `WARNING GPU busy with no job` when every sample is ≥ 80% while Ollama has no loaded model and no voice service is running
  - `def check_restarts(prev: Mapping[str, tuple[int, datetime]], now: Mapping[str, int], at: datetime) -> list[str]`: `WARNING <service> restarting` when `RestartCount` grew by 3 or more within 10 minutes
  - `def check_outbound_bytes(squid_lines: Sequence[str], client_map: Mapping[str, str], limit_bytes: int = 200_000_000) -> list[str]`: `WARNING <service> sent <n> MB in an hour` above the limit
  - The watcher prints these lines to the journal (identifier `techradar-resources`), and the alerter's `from_journal` turns them into alerts. State lives in `/var/lib/techradar-alerter/resources.json`.

- [ ] **Step 1: Write the failing tests**

```python
def test_parse_gpu_apps():
    assert parse_gpu_apps("4242, ollama, 3200\n") == [GpuApp(pid=4242, name="ollama", used_mib=3200)]

def test_unknown_gpu_process_is_critical():
    assert check_gpu([GpuApp(pid=7, name="xmrig", used_mib=900)], {7: None}) == ["CRITICAL unknown GPU process xmrig"]

def test_gpu_busy_with_no_job():
    assert check_gpu_busy([95] * 15, [], voice_running=False) == "WARNING GPU busy with no job"
    assert check_gpu_busy([95] * 15, ["qwen3.5:4b"], voice_running=False) is None

def test_restart_loop():
    prev = {"bot": (1, NOW)}
    assert check_restarts(prev, {"bot": 4}, NOW + timedelta(minutes=5)) == ["WARNING bot restarting"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/hostsec/test_resources.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the module and timer**

- [ ] **Step 4: Run the tests, then install the timer (owner)**

Run: `uv run pytest tests/hostsec/test_resources.py -v`, then `sudo cp infra/host/timers/techradar-resources.* /etc/systemd/system/ && sudo systemctl enable --now techradar-resources.timer`
Expected: PASS; `journalctl -t techradar-resources` shows runs every minute with no lines while all is normal.

- [ ] **Step 5: Commit**

```bash
git add src/techradar/hostsec/resources.py infra/host/timers tests/hostsec && git commit -m "security(hostsec): GPU, restart and outbound-bytes watcher"
```

### Task 18: Accounts, private network and text-mode boot

**SEC:** SEC-04, SEC-31, SEC-51 (phase 1 part: no browser on the server, strict Ollama origins), SEC-67

**Files:**
- Create: `docs/security/monthly.md`
- Modify: `infra/host/RUNBOOK.md`, `infra/host/check_host.sh`
- Test: `tests/infra/test_check_host_lines.py`

**Interfaces:**
- Produces:
  - **RUNBOOK steps 14–19** (each with its command and expected output):
    14. **Passkeys:** on GitHub and on the account I sign in to Tailscale with; otherwise an authenticator app; never SMS. Recovery codes printed and stored offline.
    15. **Telegram:** 2-step verification with the cloud password.
    16. **Tailnet Lock:** `tailscale lock init` with the Mac and the phone as trusted signing keys. A new device then needs `tailscale lock sign <node-key>` from a trusted device.
    17. **Text mode:**
        - `sudo systemctl set-default multi-user.target`.
        - No browser packages installed: `dpkg -l 'firefox*' 'chromium*' 'google-chrome*' | grep ^ii` prints nothing.
    18. **BIOS/UEFI:** an admin password set in the firmware setup.
    19. **Monthly:** run the checklist in `docs/security/monthly.md`.
  - **`check_host.sh` new checks:**
    13. `systemctl get-default` is `multi-user.target`.
    14. No browser package is installed (`WARN` otherwise).
    15. `tailscale lock status` reports that lock is enabled.
    16. `auditd`, `falco-modern-bpf` and `techradar-alerter` are active.
    17. The timers `techradar-aide`, `techradar-integrity`, `techradar-resources`, `techradar-heartbeat` and `techradar-lynis` are active.
  - **`docs/security/monthly.md`:** a table with a date column for each of:
    - restore test
    - `check_host.sh`
    - `nmap` from the LAN and the tailnet
    - Telegram "Active sessions"
    - Tailscale device list
    - Syncthing device list
    - `plant_honeytokens.py --verify`
    - Lynis score
    - token rotation check
    - skills and plugins installed in the coding agents outside the repo, against the `AGENTS.md` list
    - residual-risk review

- [ ] **Step 1: Write the failing test**

```python
def test_check_host_has_new_checks():
    sh = Path("infra/host/check_host.sh").read_text()
    for needle in ["systemctl get-default", "tailscale lock status", "falco-modern-bpf", "techradar-alerter", "techradar-heartbeat.timer"]:
        assert needle in sh, needle
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/infra/test_check_host_lines.py -v`
Expected: FAIL

- [ ] **Step 3: Write the runbook steps, the checks and the monthly checklist**

- [ ] **Step 4 (owner): Do the account and boot steps, then run the host check**

Run: `shellcheck infra/host/check_host.sh && sudo OWNER="$USER" bash infra/host/check_host.sh`
Expected: every line `PASS` (Secure Boot and the browser check may be `WARN`).

- [ ] **Step 5: Commit**

```bash
git add docs/security/monthly.md infra/host tests/infra && git commit -m "security(host): passkeys, Tailnet Lock, text-mode boot and monthly checklist"
```

### Task 19: Gate 1

**SEC:** all phase 1 controls (SEC-01 to SEC-14, SEC-22, SEC-23, SEC-26, SEC-31 to SEC-36, SEC-51 phase 1 part, SEC-52, SEC-53, SEC-55, SEC-58 to SEC-67)

**Files:**
- Create: `Makefile`, `docs/security/gates.md`, `security/simulate/phase1.sh`
- Test: `tests/security/test_simulate_script.py`

**Interfaces:**
- Produces:
  - **`make lint`:** `ruff check` and `ruff format --check`.
  - **`make test`:** unit tests.
  - **`make security`:**
    - the semgrep rule tests and scan
    - gitleaks
    - OSV-Scanner on `uv.lock`
    - `trivy config`
    - `trivy image` (HIGH and CRITICAL, `--ignore-unfixed`) on the `bot`, `migrate` and `postgres` images
    - hadolint, shellcheck
    - `scripts/check_deps.py`, `scripts/check_mcp.py`, `scripts/check_skills.py`
  - **`make test-db`** and **`make test-egress`:** the marked test suites.
  - **`make simulate-1`:** runs `security/simulate/phase1.sh`, which performs each attack, waits up to 60 s for the expected line in the alert log, and prints `PASS` or `FAIL` per attack:

    | Simulated attack | Expected alert |
    |---|---|
    | `docker compose exec -T bot sh -c true` | critical, `TR shell or package manager in container`, service `bot` |
    | `cat secrets/aws_root_key.txt` | critical, `tr_honey` |
    | `docker compose exec -T -e PGPASSWORD=wrong postgres psql -h 127.0.0.1 -U admin_backup techradar -c 'select 1'` | critical, failed login for `admin_backup` |
    | `docker compose run --rm --entrypoint python migrate -c "import socket; socket.create_connection(('1.1.1.1', 443), 3)"` | critical, `TR connection outside allowed peers` |
    | `docker compose --profile test run --rm egress-probe -sS https://example.com/` | critical, `outbound attempt from egress-probe` (only the fetcher's denies are warnings) |
    | `sudo touch /etc/techradar-aide-test && sudo systemctl start techradar-aide.service` | warning, AIDE differences (the script removes the file and refreshes the baseline afterwards) |
    | `uv run python scripts/integrity_check.py --pinned-override postgres=sha256:0000000000000000000000000000000000000000000000000000000000000000` | critical, `postgres digest mismatch` |
    | `docker run --rm --gpus all <the pinned CUDA image from Task 9> sleep 90` | critical, `unknown GPU process` |

  - **`make gate-1`:**
    1. all of the above
    2. `pytest tests/hostsec`
    3. `restore_test.sh`
    4. `sudo bash infra/host/check_host.sh`
    5. `make simulate-1`
    6. Prints `GATE 1: automated checks passed. Check tomorrow's heartbeat, run the nmap checks and sign docs/security/gates.md.`

- [ ] **Step 1: Write the failing test**

```python
def test_simulate_script_covers_every_phase1_attack():
    sh = Path("security/simulate/phase1.sh").read_text()
    for needle in ["exec -T bot sh", "aws_root_key", "admin_backup", "create_connection", "egress-probe",
                   "techradar-aide", "--pinned-override", "--gpus all"]:
        assert needle in sh, needle
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/security/test_simulate_script.py -v`
Expected: FAIL

- [ ] **Step 3: Write the `Makefile`, the simulation script and `docs/security/gates.md`**

`gates.md` is a table with columns: gate, date, commit, nmap LAN result, nmap tailnet result, heartbeat received, notes, signed.

- [ ] **Step 4: Run the gate on the server**

Run: `make gate-1`
Expected: every step passes, every simulated attack prints `PASS`, and the final line is printed.

- [ ] **Step 5 (owner): Run the exposure scans from the Mac and check the heartbeat**

Run: `nmap -Pn -p- <server-LAN-IP>` and `nmap -Pn -p- <server-tailscale-IP>`
Expected:
- LAN: no open ports.
- Tailscale: only `22/tcp` (Tailscale SSH).
- The next morning's heartbeat arrives from the alert bot and counts the simulated alerts.

Record the results in `gates.md`.

- [ ] **Step 6: Commit**

```bash
git add Makefile docs/security/gates.md security/simulate tests/security && git commit -m "docs(security): gate 1 passed"
```

**After 14 days of alerts-only running:** review the alert log for false alarms, tune `expected_programs.yaml` and the thresholds, then set `TR_CONTAINMENT=on` and record the date in `gates.md` (D41).
