SHELL := /bin/bash
UV ?= /opt/homebrew/bin/uv
UV_PYTHON ?= /opt/homebrew/bin/python3
UV_RUN := UV_PYTHON=$(UV_PYTHON) $(UV) run --no-sync

.PHONY: all lint format test test-db test-egress security simulate-1 gate-1

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
