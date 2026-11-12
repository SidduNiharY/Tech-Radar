"""Every container on the egress network has a fixed address.

The alerter turns a Squid denial's client IP into a service name. Short-lived
containers (an egress probe, `docker compose run`) exit before a runtime
lookup can find them, so the addresses are fixed here and the alerter reads
the map from this file.
"""

import ipaddress
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_egress_services_have_unique_fixed_addresses_in_the_subnet():
    data = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    subnet = ipaddress.ip_network(
        data["networks"]["egress_internal"]["ipam"]["config"][0]["subnet"]
    )
    seen = {}
    for name, svc in data["services"].items():
        nets = svc.get("networks") or {}
        if "egress_internal" not in nets:
            continue
        assert isinstance(nets, dict), f"{name}: use the mapping form to set ipv4_address"
        addr = ipaddress.ip_address((nets["egress_internal"] or {}).get("ipv4_address", ""))
        assert addr in subnet, (name, addr)
        assert addr not in seen, (name, seen.get(addr))
        seen[addr] = name
    assert {"squid", "bot", "fetcher", "clamav-update", "egress-probe"} <= set(seen.values())


def test_dynamic_addresses_never_reuse_a_fixed_one():
    # A container added without a fixed address must not get, say, the
    # fetcher's address while fetcher is down: its denials would be logged as
    # fetcher's, which are only warnings (from the automated review).
    data = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    cfg = data["networks"]["egress_internal"]["ipam"]["config"][0]
    dynamic = ipaddress.ip_network(cfg["ip_range"])
    assert dynamic.subnet_of(ipaddress.ip_network(cfg["subnet"]))
    for name, svc in data["services"].items():
        nets = svc.get("networks") or {}
        if isinstance(nets, dict) and "egress_internal" in nets:
            addr = ipaddress.ip_address(nets["egress_internal"]["ipv4_address"])
            assert addr not in dynamic, name
