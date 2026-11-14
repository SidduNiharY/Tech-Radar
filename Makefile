SHELL := /bin/bash
# Portable: uv from PATH; Python as pinned in .python-version / requires-python.
UV ?= uv
UV_PYTHON ?= 3.14.5
UV_RUN := UV_PYTHON=$(UV_PYTHON) $(UV) run --no-sync
SEMGREP := $(UV) tool run --from semgrep==1.184.0 semgrep
SHELL_SCRIPTS := $(shell git ls-files '*.sh')
# Images built from this repo that Trivy scans (gate-1).
IMAGES := techradar-bot techradar-migrate techradar-postgres

.PHONY: all lint format test test-db test-egress security security-images simulate-1 simulate-2 simulate-2c fixtures-2c guard-eval redteam-live gate-1-mac gate-1 gate-2 rag-eval gate-2b gate-2c gate-3 gate-4 gate-5

all: lint test security

lint:
	$(UV_RUN) ruff check src/ tests/ scripts/
	$(UV_RUN) ruff format --check src/ tests/ scripts/

format:
	$(UV_RUN) ruff format src/ tests/ scripts/
	$(UV_RUN) ruff check --fix src/ tests/ scripts/

test:
	$(UV_RUN) pytest -v

# The db fixtures empty the test tables; never point this at real notes.
test-db:
	TR_DB_TESTS_MAY_WIPE=1 $(UV_RUN) pytest -m db tests/ -v

test-egress:
	$(UV_RUN) pytest -m egress tests/ -v

# Scanners come from scripts/install_security_tools.sh (pinned, checksummed).
security:
	$(UV_RUN) python scripts/check_deps.py
	$(UV_RUN) python scripts/check_mcp.py
	$(UV_RUN) python scripts/check_skills.py
	$(UV_RUN) pytest tests/security/test_compose_policy.py tests/security/test_falco_rules.py -v
	$(SEMGREP) --test security/semgrep
	$(SEMGREP) scan --error --config security/semgrep/rules.yaml src
	gitleaks git --redact --no-banner .
	osv-scanner scan source -L uv.lock
	trivy config --exit-code 1 --severity HIGH,CRITICAL --ignorefile .trivyignore.yaml .
	hadolint infra/docker/Dockerfile infra/postgres/Dockerfile
	shellcheck $(SHELL_SCRIPTS)
	@echo "All security policy gates passed."

security-images:
	for img in $(IMAGES); do trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed "$$img" || exit 1; done

simulate-1:
	bash security/simulate/phase1.sh

# Runs anywhere (Mac or server). It is only part of gate 1: never sign a gate on it.
gate-1-mac: lint test security
	$(UV_RUN) pytest tests/hostsec -v
	bash -n infra/backup/*.sh
	bash -n infra/host/*.sh
	@echo "gate-1-mac passed. This is NOT gate 1: run make gate-1 on the server."

gate-1: lint test security test-db test-egress security-images
	$(UV_RUN) pytest tests/hostsec -v
	bash -n infra/backup/*.sh
	bash -n infra/host/*.sh
	bash infra/backup/restore_test.sh
	sudo OWNER="$$USER" bash infra/host/check_host.sh
	$(MAKE) simulate-1
	@echo "GATE 1: automated checks passed. Check tomorrow's heartbeat, run the nmap checks and sign docs/security/gates.md."

simulate-2:
	bash security/simulate/phase2.sh

guard-eval:
	$(UV_RUN) python evals/guard/eval.py

redteam-live:
	docker compose --profile test run --rm redteam

gate-2: gate-1
	$(UV_RUN) lint-imports
	$(UV_RUN) pytest tests/security/test_redteam.py -v
	$(UV_RUN) pytest tests/intake tests/parser -v
	$(UV_RUN) pytest tests/pipeline -v
	$(MAKE) guard-eval
	bash security/simulate/phase2.sh
	bash -n security/simulate/*.sh
	@echo "GATE 2: automated checks passed. Sign docs/security/gates.md."

rag-eval:
	$(UV_RUN) python evals/rag/run.py

gate-2b: gate-2
	$(UV_RUN) pytest tests/rag tests/security/test_rag_redteam.py -v
	$(MAKE) rag-eval
	@echo "GATE 2b: automated checks passed. Sign docs/security/gates.md."

# Library attacks in the parser image (--network none), on a temp folder only.
simulate-2c:
	bash security/simulate/phase2c.sh

# The 300-page test book (git-ignored); the simulation builds its own copy.
fixtures-2c:
	$(UV_RUN) python scripts/make_big_pdf.py

# gate-2b already ran rag-eval (book evals included; see evals/rag/run.py) and
# the db tests. The internet stage is printed as WAITING, never counted as passed.
gate-2c: gate-2b
	$(UV_RUN) lint-imports
	$(UV_RUN) pytest tests/library tests/intake tests/night tests/ops tests/parser tests/pipeline tests/evals tests/rag/test_retrieve_scope.py -v
	TR_DB_TESTS_MAY_WIPE=1 $(UV_RUN) pytest -m db tests/library tests/intake tests/parser tests/rag tests/evals -v
	$(UV_RUN) pytest -m slow tests/library tests/intake tests/parser tests/security/test_gate_2c.py -v
	$(MAKE) simulate-2c
	$(UV_RUN) pytest tests/security/test_compose_policy.py tests/security/test_falco_rules.py tests/security/test_falco_names.py tests/security/test_gate_2c.py -v
	@echo "WAITING: internet stage: Telegram Ready message and notices (needs the bot online)"
	@echo "WAITING: internet stage: real chapter summaries and book-eval recall@5 >= 0.80 with real models (rag-eval above says if it ran in mock mode)"
	@echo "WAITING: internet stage: starter-pack downloads through Squid"
	@echo "WAITING: owner: real book and lecture video in the Library folder (plan Task 11 step 2)"
	@echo "GATE 2c: automated checks passed; the WAITING items above are not. Sign docs/security/gates.md only when they pass."

gate-3: gate-2c
	$(UV_RUN) pytest tests/briefing tests/practice tests/exams/test_watcher.py tests/bot -v
	@echo "GATE 3: automated checks passed. Sign docs/security/gates.md."

gate-4: gate-3
	$(UV_RUN) pytest tests/api -v
	@echo "GATE 4: automated checks passed. Sign docs/security/gates.md."

gate-5: gate-4
	$(UV_RUN) pytest tests/planner tests/ops -v
	@echo "GATE 5: automated checks passed. Sign docs/security/gates.md."
