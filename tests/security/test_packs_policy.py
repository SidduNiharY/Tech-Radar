"""Starter packs policy (Phase 2c Task 9; SEC-05, SEC-25, SEC-57).

- The fetcher (the only service with internet) writes downloads into the packs folder and
  nothing else of the library; it never sees the library or its inbox.
- The packs file in the repo loads strictly against the real Squid allowlist, and an
  approved pack never contains a blocked item (each URL is checked by the owner first).
- The pack downloader never lets httpx follow redirects by itself.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

from techradar.library.packs import load_packs, trust_for
from techradar.security.urls import load_allowlist

PACKS = Path("infra/sources/exam_packs.yaml")
ALLOWLIST = Path("infra/squid/allowlist.txt")


def _mounts(svc: dict) -> tuple[set[str], set[str]]:
    rw, ro = set(), set()
    for v in svc["volumes"]:
        parts = v.split(":")
        (ro if len(parts) > 2 and "ro" in parts[2].split(",") else rw).add(parts[1])
    return rw, ro


def test_fetcher_writes_only_raw_jobs_and_packs():
    svc = yaml.safe_load(Path("compose.yaml").read_text())["services"]["fetcher"]
    rw, ro = _mounts(svc)
    assert rw == {"/data/raw", "/data/parse-jobs", "/data/library-packs"}
    assert {"/etc/techradar/exam_packs.yaml", "/etc/squid/allowlist.txt"} <= ro
    every = rw | ro
    assert not any(m.startswith(("/data/library/", "/data/library-inbox")) for m in every)
    assert "/data/library" not in every


def test_repo_packs_file_loads_and_approved_packs_are_clean():
    packs = load_packs(PACKS, load_allowlist(ALLOWLIST))
    for pack in packs:
        if pack.approved:
            assert pack.items, f"{pack.name}: approved with no items"
            blocked = [(i.url, i.refused) for i in pack.items if i.refused]
            assert not blocked, f"{pack.name}: approved pack has blocked items {blocked}"
            assert all(trust_for(i.host) for i in pack.items)


def test_every_listed_url_is_https_on_an_allowlisted_host():
    allowed = load_allowlist(ALLOWLIST)
    for pack in load_packs(PACKS, allowed):
        for item in pack.items:
            assert item.url.startswith("https://"), item.url
            assert item.refused != "host not in the Squid allowlist", item.url


def test_pack_downloader_never_follows_redirects_itself():
    tree = ast.parse(Path("src/techradar/library/packs.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "follow_redirects":
            assert isinstance(node.value, ast.Constant) and node.value.value is False


NET_MODULES = {"socket", "ssl", "requests", "aiohttp", "urllib3", "http", "urllib.request"}


def test_pack_downloader_only_uses_the_fetchers_client():
    # SEC-05: a pack download goes out only through the fetcher's own client (FetchDeps,
    # proxied through Squid). packs.py never opens a socket or builds an HTTP client.
    tree = ast.parse(Path("src/techradar/library/packs.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in NET_MODULES, alias.name
                assert alias.name.split(".")[0] not in {"socket", "ssl", "requests", "aiohttp"}
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") not in NET_MODULES, node.module
            assert not (node.module or "").startswith(("http.", "urllib.request"))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            # No httpx.AsyncClient(...), httpx.get(...), httpx.stream(...) and so on.
            assert not (isinstance(owner, ast.Name) and owner.id == "httpx"), ast.unparse(node)
        if isinstance(node, ast.Attribute) and node.attr == "client":
            assert isinstance(node.value, ast.Name) and node.value.id == "deps", ast.unparse(node)


def test_fetchers_client_goes_through_squid_and_ignores_the_environment():
    tree = ast.parse(Path("src/techradar/fetcher/main.py").read_text())
    clients = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("AsyncClient", "Client")
    ]
    assert clients, "the fetcher builds its HTTP client in fetcher/main.py"
    for call in clients:
        kw = {k.arg: k.value for k in call.keywords}
        assert ast.unparse(kw["proxy"]) == "settings.https_proxy"
        assert isinstance(kw["trust_env"], ast.Constant) and kw["trust_env"].value is False


def test_pack_cycle_runs_only_in_the_fetcher_with_its_deps():
    # The pack cycle gets the fetcher's FetchDeps (its proxied client); nothing else calls it.
    callers = [
        p
        for p in Path("src/techradar").rglob("*.py")
        if "run_pack_cycle(" in p.read_text() and p.name != "packs_cycle.py"
    ]
    assert [p.as_posix() for p in callers] == ["src/techradar/fetcher/main.py"]
    callers = [
        p
        for p in Path("src/techradar").rglob("*.py")
        if "download_pack_items(" in p.read_text() or "fetch_pack_file(" in p.read_text()
    ]
    assert sorted(p.name for p in callers) == ["packs.py", "packs_cycle.py"]
    assert all(p.parent.name in ("library", "fetcher") for p in callers)
