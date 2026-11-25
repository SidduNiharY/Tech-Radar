"""Tests for weekly release digest parsing, version comparison, and formatting."""

from techradar.digest.releases import (
    ReleaseItem,
    TrackedPackage,
    Update,
    compare,
    format_release_digest,
    parse_pnpm_lock,
    parse_release_payload,
    parse_uv_lock,
    render_digest,
)


class FakeLatest:
    def __init__(self, table: dict[tuple[str, str], str]) -> None:
        self.table = table

    async def latest(self, ecosystem: str, name: str) -> str | None:
        return self.table.get((ecosystem, name))


async def test_build_digest_from_locks_and_tracked() -> None:
    from techradar.digest.releases import build_digest

    uv = (
        '[[package]]\nname = "fastapi"\nversion = "0.162.1"\n\n'
        '[[package]]\nname = "x"\nversion = "1.0.0"\n'
    )
    pnpm = (
        "importers:\n  .:\n    dependencies:\n      next:\n"
        "        specifier: 16.0.0\n        version: 16.0.0\n"
    )
    source = FakeLatest(
        {
            ("pypi", "fastapi"): "0.163.0",
            ("pypi", "x"): "1.1.0rc1",  # pre-release: no alert
            ("npm", "next"): "17.0.0",
            ("maven", "org.x:lib"): "2.0.0",
        }
    )
    tracked = [TrackedPackage(ecosystem="maven", name="org.x:lib", version="1.0.0")]
    text = await build_digest(uv, pnpm, tracked, source)
    lines = text.splitlines()
    assert lines[0] == "🆕 Releases this week:"
    assert lines[1:] == [
        "• next 17.0.0 (you have 16.0.0, major)",
        "• org.x:lib 2.0.0 (you have 1.0.0, major)",
        "• fastapi 0.163.0 (you have 0.162.1, minor)",
    ]


async def test_build_digest_nothing_to_say_is_empty() -> None:
    from techradar.digest.releases import NullLatestSource, build_digest

    uv = '[[package]]\nname = "fastapi"\nversion = "0.162.1"\n'
    assert await build_digest(uv, "", [], NullLatestSource()) == ""


async def test_source_errors_skip_the_package() -> None:
    from techradar.digest.releases import build_digest

    class Boom:
        async def latest(self, ecosystem: str, name: str) -> str | None:
            raise RuntimeError("registry down")

    uv = '[[package]]\nname = "fastapi"\nversion = "0.162.1"\n'
    assert await build_digest(uv, "", [], Boom()) == ""


def test_load_tracked(tmp_path) -> None:
    from techradar.digest.releases import load_tracked

    p = tmp_path / "tracked.yaml"
    p.write_text(
        "packages:\n  - {ecosystem: maven, name: 'org.x:lib', version: '1.0'}\n"
        "  - {ecosystem: bad}\n"
    )
    assert [t.name for t in load_tracked(p)] == ["org.x:lib"]
    assert load_tracked(tmp_path / "missing.yaml") == []


def test_real_tracked_yaml_loads() -> None:
    from pathlib import Path

    from techradar.digest.releases import load_tracked

    load_tracked(Path(__file__).resolve().parents[2] / "infra/digest/tracked.yaml")


def test_compare_kinds_and_order() -> None:
    """Test standard comparison order from Phase 10 task specification."""
    u = compare(
        {"fastapi": "0.162.1", "pydantic": "2.11.0"},
        {"fastapi": "0.163.0", "pydantic": "3.0.0"},
    )
    assert [(x.name, x.kind) for x in u] == [("pydantic", "major"), ("fastapi", "minor")]


def test_prereleases_ignored() -> None:
    """Test that alpha/beta/rc pre-releases and dev releases are skipped."""
    assert compare({"x": "1.0.0"}, {"x": "1.1.0rc1"}) == []
    assert compare({"y": "2.0.0"}, {"y": "2.1.0b2"}) == []
    assert compare({"z": "3.0.0"}, {"z": "3.1.0.dev1"}) == []


def test_compare_patch_and_limit() -> None:
    """Test patch classification and max 10 updates limit."""
    pinned = {f"pkg-{i:02d}": "1.0.0" for i in range(15)}
    latest = {f"pkg-{i:02d}": "1.0.1" for i in range(15)}
    u = compare(pinned, latest)
    assert len(u) == 10
    assert all(item.kind == "patch" for item in u)


def test_parse_release_payload_pypi() -> None:
    """Test parsing standard PyPI JSON API response."""
    payload = {
        "info": {
            "name": "pydantic",
            "version": "2.11.0",
            "summary": "Data validation using Python type hints",
            "project_url": "https://pydantic.dev",
        },
        "previous_version": "2.10.0",
    }
    item = parse_release_payload(payload)
    assert item is not None
    assert item.name == "pydantic"
    assert item.version == "2.11.0"
    assert item.previous_version == "2.10.0"
    assert item.kind == "minor"
    assert item.ecosystem == "pypi"


def test_parse_release_payload_npm() -> None:
    """Test parsing npm registry JSON response."""
    payload = {
        "name": "react",
        "dist-tags": {"latest": "19.0.0"},
        "description": "React is a JavaScript library for creating user interfaces",
        "previous_version": "18.3.1",
    }
    item = parse_release_payload(payload)
    assert item is not None
    assert item.name == "react"
    assert item.version == "19.0.0"
    assert item.kind == "major"
    assert item.ecosystem == "npm"


def test_parse_release_payload_maven() -> None:
    """Test parsing Maven Central Search API response."""
    payload = {
        "response": {
            "docs": [
                {
                    "g": "org.springframework.boot",
                    "a": "spring-boot-starter-web",
                    "latestVersion": "3.3.0",
                }
            ]
        },
        "previous_version": "3.2.5",
    }
    item = parse_release_payload(payload)
    assert item is not None
    assert item.name == "org.springframework.boot:spring-boot-starter-web"
    assert item.version == "3.3.0"
    assert item.kind == "minor"
    assert item.ecosystem == "maven"


def test_parse_release_payload_generic_and_cleaning() -> None:
    """Test generic payload and leading 'v' stripping."""
    payload = {
        "name": "ollama",
        "tag_name": "v0.5.1",
        "body": "New model architectures supported",
        "previous_version": "v0.5.0",
    }
    item = parse_release_payload(payload)
    assert item is not None
    assert item.name == "ollama"
    assert item.version == "0.5.1"
    assert item.kind == "patch"


def test_parse_release_payload_invalid() -> None:
    """Test that missing required fields or invalid version strings return None."""
    assert parse_release_payload({}) is None
    assert parse_release_payload({"name": "only-name"}) is None
    assert parse_release_payload({"version": "1.0.0"}) is None
    assert parse_release_payload({"name": "foo", "version": "not-a-version-xyz!!!"}) is None


def test_parse_uv_lock() -> None:
    """Test parsing sample uv.lock text."""
    sample_uv = """
    version = 1
    requires-python = ">=3.14.5"

    [[package]]
    name = "fastapi"
    version = "0.162.1"
    source = { registry = "https://pypi.org/simple" }

    [[package]]
    name = "pydantic"
    version = "2.11.0"
    source = { registry = "https://pypi.org/simple" }
    """
    res = parse_uv_lock(sample_uv)
    assert res == {"fastapi": "0.162.1", "pydantic": "2.11.0"}


def test_parse_pnpm_lock() -> None:
    """Test parsing sample pnpm-lock.yaml text."""
    sample_pnpm = """
    lockfileVersion: '9.0'
    importers:
      .:
        dependencies:
          next:
            specifier: ^15.1.0
            version: 15.1.0(react@19.0.0)
          react:
            specifier: ^19.0.0
            version: 19.0.0
        devDependencies:
          typescript:
            specifier: ^5.7.0
            version: 5.7.2
    """
    res = parse_pnpm_lock(sample_pnpm)
    assert res.get("next") == "15.1.0"
    assert res.get("react") == "19.0.0"
    assert res.get("typescript") == "5.7.2"


def test_format_release_digest_empty() -> None:
    """Test that empty list yields empty digest string."""
    assert format_release_digest([]) == ""
    assert render_digest([]) == ""


def test_format_release_digest_non_empty() -> None:
    """Test rendering digest output with version transitions."""
    items = [
        ReleaseItem(
            name="pydantic",
            version="3.0.0",
            previous_version="2.11.0",
            kind="major",
        ),
        ReleaseItem(
            name="fastapi",
            version="0.163.0",
            previous_version="0.162.1",
            kind="minor",
        ),
    ]
    digest = format_release_digest(items)
    assert "🆕 Releases this week:" in digest
    assert "• pydantic 3.0.0 (you have 2.11.0, major)" in digest
    assert "• fastapi 0.163.0 (you have 0.162.1, minor)" in digest


def test_render_digest_updates() -> None:
    """Test render_digest with Update objects."""
    updates = [
        Update(name="pydantic", pinned="2.11.0", latest="3.0.0", kind="major"),
        Update(name="fastapi", pinned="0.162.1", latest="0.163.0", kind="minor"),
    ]
    rendered = render_digest(updates)
    assert "🆕 Releases this week:" in rendered
    assert "• pydantic 3.0.0 (you have 2.11.0, major)" in rendered
    assert "• fastapi 0.163.0 (you have 0.162.1, minor)" in rendered


def test_release_digest_indian_language_preservation() -> None:
    """Test that Indian language summaries are preserved unchanged."""
    item = ReleaseItem(
        name="indic-nlp-library",
        version="1.0.0",
        summary="भारतीय भाषाओं (हिन्दी, తెలుగు) के लिए प्राकृतिक भाषा संसाधन पुस्तकालय",
    )
    assert "भारतीय भाषाओं" in str(item.summary)
    assert "తెలుగు" in str(item.summary)
