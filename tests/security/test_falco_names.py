"""Falco rules must match the container names Compose really creates.

Every TechRadar Falco rule matches `container.name startswith "techradar-..."`.
Compose names containers `<project>-<service>-<n>`, and without a `name:` the
project is the folder name, so the containers were `techradarbrain-bot-1`
and no rule could ever fire. compose.yaml pins the project name.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))


def test_compose_pins_the_project_name():
    assert compose().get("name") == "techradar"


def test_every_falco_service_prefix_names_a_real_container():
    data = compose()
    containers = [f"{data.get('name')}-{svc}-1" for svc in data["services"]]
    text = "\n".join(
        (ROOT / "infra/falco" / f).read_text(encoding="utf-8")
        for f in ["techradar_rules.yaml", "generated_lists.yaml"]
    )
    prefixes = set(re.findall(r'container\.name startswith "([^"]+)"', text))
    assert "techradar-" in prefixes
    # Services planned for later phases have no container yet.
    later = {"jarvis", "api", "voice-worker", "changedetection", "searxng", "zap"}
    for prefix in prefixes:
        svc = prefix.removeprefix("techradar-")
        if svc in later:
            continue
        assert any(c.startswith(prefix) for c in containers), prefix


def test_scanned_images_use_the_project_name():
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    images = re.search(r"^IMAGES := (.+)$", makefile, re.MULTILINE).group(1).split()
    assert images and all(i.startswith("techradar-") for i in images), images


def test_every_program_list_is_used_by_the_rules():
    # Real Falco (0.45.2) reported five lists no rule referred to: fetcher,
    # parser, worker, clamav and clamav-update were not covered by the
    # "unexpected program" and "secret read" rules.
    lists = (ROOT / "infra/falco/generated_lists.yaml").read_text(encoding="utf-8")
    rules = (ROOT / "infra/falco/techradar_rules.yaml").read_text(encoding="utf-8")
    names = re.findall(r"^- list: (\S+)$", lists, re.MULTILINE)
    assert names
    for name in names:
        assert rules.count(f"({name})") >= 2, name


def test_rules_avoid_fields_real_falco_rejects():
    rules = (ROOT / "infra/falco/techradar_rules.yaml").read_text(encoding="utf-8")
    assert "evt.flags" not in rules  # no such field; use evt.is_open_write
    assert "evt.dir" not in rules  # deprecated, always true
    assert "fd.rip in (" not in rules  # networks need fd.rnet


def test_clamav_prefix_never_catches_the_updater():
    # "techradar-clamav" is also a prefix of "techradar-clamav-update-1",
    # which runs freshclam and uses the network on purpose.
    rules = (ROOT / "infra/falco/techradar_rules.yaml").read_text(encoding="utf-8")
    for line in rules.splitlines():
        if 'startswith "techradar-clamav"' in line:
            assert 'not container.name startswith "techradar-clamav-update"' in line, line


def test_write_rule_allowlist_is_narrow():
    text = (ROOT / "infra/falco/techradar_rules.yaml").read_text(encoding="utf-8")
    rules = yaml.safe_load(text)
    cond = next(r for r in rules if r.get("rule") == "TR write outside tmpfs or volumes")[
        "condition"
    ]
    prefixes = re.findall(r'fd\.name startswith "([^"]+)"', cond)
    assert prefixes
    for prefix in prefixes:
        assert prefix.endswith("/"), prefix  # "/run" would also allow "/run-evil"
        assert not "/run/secrets/".startswith(prefix), prefix  # secrets stay watched
    # Service-only paths are allowed only for that service's containers.
    for service, path in [("ollama", "/root/.ollama/"), ("squid", "/var/spool/squid/")]:
        pattern = (
            rf'container\.name startswith "techradar-{service}" and'
            rf'\s+\(?[^)]*fd\.name startswith "{path}"'
        )
        assert re.search(pattern, cond), service


def _rule(name: str) -> dict:
    rules = yaml.safe_load((ROOT / "infra/falco/techradar_rules.yaml").read_text(encoding="utf-8"))
    return next(r for r in rules if r.get("rule") == name)


def test_peer_rule_only_looks_at_network_sockets():
    # 2026-11-13: failed local-socket connects (no address) from postgres
    # raised a CRITICAL every 5 seconds.
    assert "fd.type in (ipv4, ipv6)" in _rule("TR connection outside allowed peers")["condition"]


def test_container_rules_skip_docker_runtime_setup():
    # runc's setup steps (seen on every health check) are not the service.
    for name in [
        "TR unexpected program",
        "TR write outside tmpfs or volumes",
        "TR secret read by unexpected program",
    ]:
        assert "not tr_runtime_setup" in _rule(name)["condition"], name


def _macro(name: str) -> str:
    rules = yaml.safe_load((ROOT / "infra/falco/techradar_rules.yaml").read_text(encoding="utf-8"))
    return next(r for r in rules if r.get("macro") == name)["condition"]


def test_runtime_setup_exception_cannot_be_faked_from_a_container():
    # A process can rename itself (automated review): the exception is keyed
    # on the host runc binary, which our images do not contain, run from
    # outside the container's writable layer.
    cond = _macro("tr_runtime_setup")
    assert "proc.exepath = /usr/bin/runc" in cond
    # runc's init stage runs as /runc with the host runc as its parent (seen
    # on the TUF 2026-11-13); /runc alone is not trusted.
    assert "proc.exepath = /runc and proc.pexepath = /usr/bin/runc" in cond
    assert "proc.is_exe_upper_layer = false" in cond
    assert "proc.name" not in cond and "proc.cmdline" not in cond


def test_default_rule_exceptions_are_pinned_to_real_executables():
    rules = yaml.safe_load((ROOT / "infra/falco/techradar_rules.yaml").read_text(encoding="utf-8"))
    overrides = {r["rule"]: r for r in rules if "override" in r}
    for r in overrides.values():
        assert r["override"] == {"condition": "append"}
    sensitive = overrides["Read sensitive file untrusted"]["condition"]
    # pg_isready (Debian's Perl wrapper) only as the health check docker runs
    assert "proc.pexepath = /usr/bin/containerd-shim-runc-v2" in sensitive
    assert "proc.exepath = /usr/bin/perl" in sensitive
    assert 'proc.cmdline = "pg_isready /usr/bin/pg_isready -U postgres"' in sensitive
    # Lynis only for the shadow files, only as the audit the timer runs
    assert "fd.name in (/etc/shadow, /etc/gshadow)" in sensitive
    memfd = overrides["Fileless execution via memfd_create"]["condition"]
    assert "proc.pexepath = /usr/bin/nvidia-cdi-hook" in memfd
    # It runs inside the new container, so it must not be limited to the host.
    assert 'proc.exepath = "memfd:runc_cloned:ldconfig"' in memfd
    assert "container.id = host" not in memfd
    for cond in (sensitive, memfd):
        assert "proc.pname" not in cond


def test_tr_rule_outputs_show_the_executables_for_tuning():
    for name in [
        "TR unexpected program",
        "TR write outside tmpfs or volumes",
        "TR secret read by unexpected program",
    ]:
        out = _rule(name)["output"]
        assert "%proc.exepath" in out and "%proc.pexepath" in out, name
