import re
from pathlib import Path

import pytest
import yaml

COMPOSE_FILE = Path("compose.yaml")
EXC_FILE = Path("infra/policy/compose_exceptions.yaml")


@pytest.fixture(scope="module")
def compose_data():
    if not COMPOSE_FILE.is_file():
        pytest.fail("compose.yaml not found")
    return yaml.safe_load(COMPOSE_FILE.read_text())


@pytest.fixture(scope="module")
def exceptions_data():
    if not EXC_FILE.is_file():
        return {}
    return yaml.safe_load(EXC_FILE.read_text()) or {}


def test_compose_files_exist():
    assert COMPOSE_FILE.is_file(), "compose.yaml must exist"
    assert EXC_FILE.is_file(), "infra/policy/compose_exceptions.yaml must exist"


def test_ports_bound_to_loopback(compose_data):
    for name, svc in compose_data.get("services", {}).items():
        for port in svc.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), f"{name} port {port} not bound to 127.0.0.1"


def test_cap_drop_all_and_no_new_privileges(compose_data):
    for name, svc in compose_data.get("services", {}).items():
        assert svc.get("cap_drop") == ["ALL"], f"{name} must have cap_drop: [ALL]"
        assert "no-new-privileges:true" in svc.get("security_opt", []), (
            f"{name} must have no-new-privileges:true in security_opt"
        )


def test_no_privileged_no_host_network(compose_data, exceptions_data):
    for name, svc in compose_data.get("services", {}).items():
        assert not svc.get("privileged"), f"{name} must not be privileged"
        assert svc.get("network_mode") != "host" or name in exceptions_data.get(
            "host_network", {}
        ), f"{name} must not use host network without exception"


def test_no_dangerous_mounts(compose_data):
    for name, svc in compose_data.get("services", {}).items():
        srcs = [str(v).split(":")[0] for v in svc.get("volumes", [])]
        assert not any(
            s in {"/", "/home", "/var/run/docker.sock"} or s.startswith("~") for s in srcs
        ), f"{name} has dangerous volume mount: {srcs}"


def test_limits_present(compose_data):
    for name, svc in compose_data.get("services", {}).items():
        assert {"mem_limit", "cpus", "pids_limit"} <= svc.keys(), f"{name} missing resource limits"


def test_read_only_or_excepted(compose_data, exceptions_data):
    for name, svc in compose_data.get("services", {}).items():
        assert svc.get("read_only") is True or name in exceptions_data.get("writable_root", {}), (
            f"{name} must be read_only or excepted"
        )


def test_non_root_or_excepted(compose_data, exceptions_data):
    for name, svc in compose_data.get("services", {}).items():
        assert str(svc.get("user", "root")) not in {
            "root",
            "0",
            "0:0",
        } or name in exceptions_data.get("root_start", {}), (
            f"{name} must not run as root without exception"
        )


def test_image_pinned_by_digest(compose_data):
    for name, svc in compose_data.get("services", {}).items():
        img = svc.get("image")
        assert "build" in svc or (
            img and re.fullmatch(r"[^:@\s]+:[^:@\s]+@sha256:[0-9a-f]{64}", img)
        ), f"{name} image {img} must be pinned by sha256 digest"


def test_healthchecks_use_exec_form(compose_data):
    for name, svc in compose_data.get("services", {}).items():
        hc = svc.get("healthcheck")
        assert hc is None or (isinstance(hc.get("test"), list) and hc["test"][0] == "CMD"), (
            f"{name} healthcheck must use exec form ['CMD', ...]"
        )


def test_dockerfile_from_pinned_by_digest():
    dockerfiles = sorted(
        [*Path("infra").rglob("Dockerfile*"), *Path("apps/web").glob("Dockerfile*")]
    )
    for dockerfile in dockerfiles:
        stages = set()
        for line in dockerfile.read_text().splitlines():
            if line.strip().upper().startswith("FROM "):
                parts = line.split()
                ref = parts[1]
                if ref not in stages:
                    assert re.search(r"@sha256:[0-9a-f]{64}$", ref), f"{dockerfile}: {ref}"
                if len(parts) >= 4 and parts[2].upper() == "AS":
                    stages.add(parts[3])


def test_log_size_limited(compose_data):
    for name, svc in compose_data.get("services", {}).items():
        assert svc.get("logging", {}).get("options", {}).get("max-size"), (
            f"{name} must have max-size log limit"
        )


def test_parser_has_no_network(compose_data):
    if "parser" in compose_data.get("services", {}):
        assert compose_data["services"]["parser"].get("network_mode") == "none"


def test_only_allowed_services_on_internet_networks(compose_data):
    open_nets = {
        n for n, cfg in compose_data.get("networks", {}).items() if not (cfg or {}).get("internal")
    }
    for name, svc in compose_data.get("services", {}).items():
        if set(svc.get("networks", [])) & open_nets or (
            not svc.get("networks") and svc.get("network_mode") != "none"
        ):
            assert name in {"squid", "ollama-pull", "egress-probe"}, (
                f"{name} cannot be on non-internal network"
            )


def test_ollama_origins_not_wildcard(compose_data):
    if "ollama" in compose_data.get("services", {}):
        env = compose_data["services"]["ollama"].get("environment", {})
        text = " ".join(env) if isinstance(env, list) else str(env.get("OLLAMA_ORIGINS", ""))
        assert "*" not in text, "Ollama origins must not contain wildcard *"


def test_exceptions_have_reasons(exceptions_data):
    for group_name, group in exceptions_data.items():
        for name, entry in group.items():
            assert len(entry.get("reason", "")) >= 20, (
                f"{group_name}.{name} reason must be >= 20 chars"
            )
