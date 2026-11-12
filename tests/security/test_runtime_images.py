"""Runtime images must not carry the uv binaries.

uv is only needed to build the .venv. Shipping /bin/uv and /bin/uvx added
12 HIGH/CRITICAL Trivy findings (zip, quinn-proto, rustls-webpki) to every
image, so the Dockerfile builds in a `build` stage and copies only /app.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "infra" / "docker" / "Dockerfile"
SERVICES = ["migrate", "bot", "fetcher", "parser", "worker"]


def stages() -> dict[str, str]:
    text = DOCKERFILE.read_text(encoding="utf-8")
    parts = re.split(r"^FROM\s+", text, flags=re.MULTILINE)[1:]
    out = {}
    for part in parts:
        header, _, body = part.partition("\n")
        name = header.split(" AS ")[-1].strip() if " AS " in header else header.strip()
        out[name] = header + "\n" + body
    return out


def lineage(name: str, all_stages: dict[str, str]) -> list[str]:
    chain = []
    while name in all_stages:
        chain.append(name)
        parent = all_stages[name].split("\n", 1)[0].split(" AS ")[0].strip()
        name = parent
    return chain


def test_service_stages_never_copy_uv():
    all_stages = stages()
    for service in SERVICES:
        for stage in lineage(service, all_stages):
            assert "astral-sh/uv" not in all_stages[stage], f"{service} inherits uv via {stage}"


def test_compose_never_calls_uv():
    for f in ROOT.glob("compose*.yaml"):
        assert '"uv"' not in f.read_text(encoding="utf-8"), f


def test_runtime_stage_drops_pip():
    # The base image's pip vendors old urllib3, msgpack and setuptools (5 HIGH
    # findings). The app never uses pip: uv builds the .venv.
    assert "pip uninstall" in stages()["runtime"]


def test_runtime_stage_pins_debian_security_fixes():
    runtime = stages()["runtime"]
    for pin in ("apt=3.0.4", "libapt-pkg7.0=3.0.4", "zlib1g=1:1.3.dfsg+really1.3.1-1+deb13u1"):
        assert pin in runtime, pin


def test_uv_downloads_are_cached_between_builds():
    # torch and its CUDA libraries are several GB; without a cache mount every
    # rebuild downloads them again. The cache never ends up in an image.
    text = DOCKERFILE.read_text(encoding="utf-8")
    syncs = [ln for ln in text.splitlines() if "uv sync" in ln]
    assert syncs
    for ln in syncs:
        assert "--mount=type=cache,target=/tmp/uv-cache,uid=1000,gid=1000" in ln, ln


PG_DOCKERFILE = ROOT / "infra" / "postgres" / "Dockerfile"


def test_postgres_image_replaces_gosu_and_pins_apt_fixes():
    # gosu is a Go binary whose bundled stdlib carried 26 HIGH/CRITICAL
    # findings; the entrypoint only uses it to switch to the postgres user,
    # which util-linux's setpriv does.
    text = PG_DOCKERFILE.read_text(encoding="utf-8")
    assert "infra/postgres/gosu /usr/local/bin/gosu" in text
    shim = (ROOT / "infra" / "postgres" / "gosu").read_text(encoding="utf-8")
    assert "exec setpriv" in shim and "--init-groups" in shim
    for pin in ("apt=2.6.2", "libapt-pkg6.0=2.6.2"):
        assert pin in text, pin
