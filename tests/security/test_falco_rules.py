"""Tests for Falco rules and generated lists."""

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_falco_lists import build_lists  # noqa: E402

EXPECTED_PATH = REPO_ROOT / "infra/falco/expected_programs.yaml"
GENERATED_PATH = REPO_ROOT / "infra/falco/generated_lists.yaml"
RULES_PATH = REPO_ROOT / "infra/falco/techradar_rules.yaml"
COMPOSE_PATH = REPO_ROOT / "compose.yaml"

REQUIRED_RULES = {
    "TR shell or package manager in container": "CRITICAL",
    "TR network tool in container": "CRITICAL",
    "TR unexpected program": "WARNING",
    "TR connection from no-network service": "CRITICAL",
    "TR connection outside allowed peers": "CRITICAL",
    "TR outbound not via squid": "CRITICAL",
    "TR secret read by unexpected program": "CRITICAL",
    "TR write outside tmpfs or volumes": "WARNING",
    "TR new root process": "CRITICAL",
    "TR docker socket access": "CRITICAL",
}


def test_every_compose_service_has_expected_programs() -> None:
    expected = yaml.safe_load(EXPECTED_PATH.read_text())
    compose_services = set(yaml.safe_load(COMPOSE_PATH.read_text())["services"])
    configured = set(expected.get("services", {})) | set(expected.get("excluded_profiles", []))
    assert compose_services - configured == set()


def test_generated_lists_up_to_date() -> None:
    expected = yaml.safe_load(EXPECTED_PATH.read_text())
    assert build_lists(expected) == GENERATED_PATH.read_text()


def test_rules_file_has_required_rules() -> None:
    rules_data = yaml.safe_load(RULES_PATH.read_text())
    rules_by_name = {
        item["rule"]: item
        for item in rules_data
        if isinstance(item, dict) and "rule" in item
    }

    for name, priority in REQUIRED_RULES.items():
        assert name in rules_by_name, f"Missing rule: {name}"
        rule = rules_by_name[name]
        actual_priority = rule.get("priority")
        assert actual_priority == priority, (
            f"Priority mismatch for {name}: {actual_priority} != {priority}"
        )
        assert "condition" in rule, f"Missing condition for rule: {name}"
        assert "output" in rule, f"Missing output for rule: {name}"
