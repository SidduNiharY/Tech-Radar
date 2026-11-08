SHELL := /bin/bash
UV ?= /opt/homebrew/bin/uv
UV_PYTHON ?= /opt/homebrew/bin/python3
UV_RUN := UV_PYTHON=$(UV_PYTHON) $(UV) run --no-sync

.PHONY: all lint format test test-db test-egress security simulate-1 simulate-2 guard-eval redteam-live gate-1 gate-2 rag-eval gate-2b gate-2c gate-3 gate-4 gate-5

all: lint test security

lint:
	$(UV_RUN) ruff check src/ tests/ scripts/
	$(UV_RUN) ruff format --check src/ tests/ scripts/

format:
	$(UV_RUN) ruff format src/ tests/ scripts/
	$(UV_RUN) ruff check --fix src/ tests/ scripts/

test:
	$(UV_RUN) pytest -v

test-db:
	$(UV_RUN) pytest -m db tests/ -v

test-egress:
	$(UV_RUN) pytest -m egress tests/ -v

security:
	$(UV_RUN) python scripts/check_deps.py
	$(UV_RUN) python scripts/check_mcp.py
	$(UV_RUN) python scripts/check_skills.py
	$(UV_RUN) pytest tests/security/test_compose_policy.py tests/security/test_falco_rules.py -v
	@echo "All security policy gates passed."

simulate-1:
	bash security/simulate/phase1.sh

gate-1: lint test security
	$(UV_RUN) pytest tests/hostsec -v
	bash -n infra/backup/*.sh
	bash -n infra/host/*.sh
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
	$(UV_RUN) pytest tests/intake -v
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

gate-2c: gate-2b
	$(UV_RUN) lint-imports
	$(UV_RUN) pytest tests/library tests/rag/test_scoped_ask.py -v
	@echo "GATE 2c: automated checks passed. Sign docs/security/gates.md."

gate-3:
	$(UV_RUN) pytest tests/briefing tests/practice tests/exams/test_watcher.py tests/bot -v
	@echo "GATE 3: automated checks passed. Sign docs/security/gates.md."

gate-4:
	$(UV_RUN) pytest tests/api -v
	@echo "GATE 4: automated checks passed. Sign docs/security/gates.md."

gate-5:
	$(UV_RUN) pytest tests/planner tests/ops -v
	@echo "GATE 5: automated checks passed. Sign docs/security/gates.md."



