"""Weekly release digest parser, comparison, and formatting."""

import logging
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

import packaging.version
import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class ReleaseItem(BaseModel):
    """Detailed metadata for a discovered or fetched package release."""

    name: str = Field(..., description="Package or artifact name")
    version: str = Field(..., description="Latest release version string")
    previous_version: str | None = Field(
        default=None, description="Currently pinned or previously installed version"
    )
    kind: Literal["major", "minor", "patch", "unknown"] = Field(
        default="unknown", description="SemVer update severity"
    )
    ecosystem: str | None = Field(
        default=None, description="Package ecosystem (pypi, npm, maven, etc.)"
    )
    summary: str | None = Field(default=None, description="Release summary or changelog note")
    url: str | None = Field(default=None, description="Release URL or package page")
    published_at: str | None = Field(default=None, description="Publication timestamp")


class Update(BaseModel):
    """SemVer update recommendation comparing pinned and latest package versions."""

    name: str
    pinned: str
    latest: str
    kind: Literal["major", "minor", "patch"]


def parse_release_payload(data: dict[str, Any]) -> ReleaseItem | None:
    """Parse a package registry JSON response (PyPI, npm, Maven Central, or generic).

    Returns None if the payload does not contain a valid package name and SemVer version.
    """
    if not isinstance(data, dict) or not data:
        return None

    name: str = ""
    version: str = ""
    summary: str | None = None
    ecosystem: str | None = None
    url: str | None = None
    published_at: str | None = None

    # 1. PyPI JSON payload shape
    if "info" in data and isinstance(data["info"], dict):
        info = data["info"]
        name = str(info.get("name") or "").strip()
        version = str(info.get("version") or "").strip()
        summary = info.get("summary")
        ecosystem = "pypi"
        url = info.get("project_url") or info.get("package_url")

    # 2. npm registry JSON payload shape
    elif "dist-tags" in data and isinstance(data["dist-tags"], dict) and "name" in data:
        name = str(data.get("name") or "").strip()
        version = str(data["dist-tags"].get("latest") or "").strip()
        summary = data.get("description")
        ecosystem = "npm"

    # 3. Maven Central search payload shape
    elif "response" in data and isinstance(data["response"], dict) and "docs" in data["response"]:
        docs = data["response"]["docs"]
        if isinstance(docs, list) and docs and isinstance(docs[0], dict):
            g = str(docs[0].get("g") or "")
            a = str(docs[0].get("a") or "")
            name = f"{g}:{a}" if g and a else (a or g)
            version = str(docs[0].get("latestVersion") or docs[0].get("v") or "").strip()
            ecosystem = "maven"

    # 4. Generic / GitHub release payload shape
    else:
        name = str(data.get("name") or data.get("package") or data.get("repo") or "").strip()
        version = str(data.get("version") or data.get("tag_name") or "").strip()
        summary = data.get("summary") or data.get("body") or data.get("description")
        ecosystem = data.get("ecosystem")
        url = data.get("url") or data.get("html_url")
        published_at = data.get("published_at")

    if not name or not version:
        return None

    # Clean leading 'v' or 'V' (e.g. v2.11.0 -> 2.11.0)
    clean_version = version
    if (
        clean_version.startswith(("v", "V"))
        and len(clean_version) > 1
        and clean_version[1].isdigit()
    ):
        clean_version = clean_version[1:]

    try:
        parsed_ver = packaging.version.parse(clean_version)
    except packaging.version.InvalidVersion:
        return None

    # Determine kind if previous_version was supplied
    prev_version = data.get("previous_version")
    kind: Literal["major", "minor", "patch", "unknown"] = "unknown"
    if prev_version:
        clean_prev = str(prev_version).strip()
        if clean_prev.startswith(("v", "V")) and len(clean_prev) > 1 and clean_prev[1].isdigit():
            clean_prev = clean_prev[1:]
        try:
            parsed_prev = packaging.version.parse(clean_prev)
            if parsed_ver.major > parsed_prev.major:
                kind = "major"
            elif parsed_ver.minor > parsed_prev.minor:
                kind = "minor"
            else:
                kind = "patch"
        except packaging.version.InvalidVersion:
            kind = "unknown"

    return ReleaseItem(
        name=name,
        version=clean_version,
        previous_version=str(prev_version) if prev_version else None,
        kind=kind,
        ecosystem=ecosystem,
        summary=str(summary) if summary else None,
        url=str(url) if url else None,
        published_at=str(published_at) if published_at else None,
    )


def format_release_digest(releases: Sequence[ReleaseItem | Update]) -> str:
    """Format release updates into a clean Telegram-friendly digest message.

    Returns an empty string if there are no releases to display.
    """
    if not releases:
        return ""

    lines = ["🆕 Releases this week:"]
    for r in releases:
        if isinstance(r, Update):
            lines.append(f"• {r.name} {r.latest} (you have {r.pinned}, {r.kind})")
        else:
            if r.previous_version:
                kind_str = f", {r.kind}" if r.kind != "unknown" else ""
                lines.append(f"• {r.name} {r.version} (you have {r.previous_version}{kind_str})")
            else:
                lines.append(f"• {r.name} {r.version}")

    return "\n".join(lines)


def render_digest(updates: Sequence[Update]) -> str:
    """Render digest from a sequence of Updates per Phase 10 task specification."""
    if not updates:
        return ""
    lines = ["🆕 Releases this week:"]
    for u in updates:
        lines.append(f"• {u.name} {u.latest} (you have {u.pinned}, {u.kind})")
    return "\n".join(lines)


def parse_uv_lock(text: str) -> dict[str, str]:
    """Parse uv.lock text and return package name to pinned version mapping."""
    try:
        data = tomllib.loads(text)
    except Exception:
        return {}

    packages = data.get("package", [])
    result: dict[str, str] = {}
    for pkg in packages:
        if isinstance(pkg, dict) and "name" in pkg and "version" in pkg:
            result[str(pkg["name"])] = str(pkg["version"])
    return result


def parse_pnpm_lock(text: str) -> dict[str, str]:
    """Parse pnpm-lock.yaml text and return package name to pinned version mapping."""
    try:
        raw = yaml.safe_load(text)
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    result: dict[str, str] = {}

    def _extract_deps(deps: Any) -> None:
        if not isinstance(deps, dict):
            return
        for pkg_name, pkg_val in deps.items():
            if isinstance(pkg_val, dict):
                ver = str(pkg_val.get("version") or "")
            else:
                ver = str(pkg_val or "")
            clean = ver.split("(")[0].strip()
            if clean:
                result[str(pkg_name)] = clean

    importers = raw.get("importers", {})
    if isinstance(importers, dict):
        root = importers.get(".", {})
        if isinstance(root, dict):
            _extract_deps(root.get("dependencies"))
            _extract_deps(root.get("devDependencies"))

    _extract_deps(raw.get("dependencies"))
    _extract_deps(raw.get("devDependencies"))

    return result


ECOSYSTEMS = ("pypi", "npm", "maven")


class TrackedPackage(BaseModel):
    """An extra package from `infra/digest/tracked.yaml`, with the version in use today."""

    ecosystem: Literal["pypi", "npm", "maven"]
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=64)


class LatestSource(Protocol):
    """Where the newest release of a package comes from.

    WIRING(owner, internet stage): the real source asks the fetcher (job kind `json`, through the
    sandbox and Squid) for pypi.org/pypi/<name>/json (`info.version`), registry.npmjs.org/<name>
    (`dist-tags.latest`) and search.maven.org, and passes the payload through
    `parse_release_payload`. It needs `pypi.org`, `registry.npmjs.org` and `search.maven.org` on
    `infra/squid/allowlist.txt` (owner decision, SEC-05). Until then `NullLatestSource` is used
    and no digest is sent.
    """

    async def latest(self, ecosystem: str, name: str) -> str | None: ...


class NullLatestSource:
    """No registry access: knows no newer version, so the digest stays empty."""

    async def latest(self, ecosystem: str, name: str) -> str | None:
        return None


def load_tracked(path: Path) -> list[TrackedPackage]:
    """Read `tracked.yaml`; a missing file is empty and a malformed entry is skipped."""
    if not path.is_file():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = raw.get("packages") if isinstance(raw, dict) else None
    out: list[TrackedPackage] = []
    for entry in entries if isinstance(entries, list) else []:
        try:
            out.append(TrackedPackage.model_validate(entry))
        except ValidationError:
            continue
    return out


async def build_digest(
    uv_lock: str,
    pnpm_lock: str,
    tracked: Sequence[TrackedPackage],
    source: LatestSource,
) -> str:
    """The weekly digest text ('' when nothing is newer) from lock texts and tracked extras.

    One failing lookup skips that package only. Majors first, at most 10 in all.
    """
    pinned: dict[str, dict[str, str]] = {
        "pypi": parse_uv_lock(uv_lock),
        "npm": parse_pnpm_lock(pnpm_lock),
        "maven": {},
    }
    for t in tracked:
        pinned[t.ecosystem][t.name] = t.version

    updates: list[Update] = []
    for ecosystem in ECOSYSTEMS:
        latest: dict[str, str] = {}
        for name in pinned[ecosystem]:
            try:
                version = await source.latest(ecosystem, name)
            except Exception:
                logger.warning("release lookup failed: %s %s", ecosystem, name)
                continue
            if version:
                latest[name] = version
        updates.extend(compare(pinned[ecosystem], latest))
    priority = {"major": 0, "minor": 1, "patch": 2}
    updates.sort(key=lambda u: (priority[u.kind], u.name))
    return render_digest(updates[:10])


def compare(pinned: Mapping[str, str], latest: Mapping[str, str]) -> list[Update]:
    """Compare pinned packages against latest versions.

    Skips pre-releases and dev releases.
    Sorts major updates first, then minor, then patch.
    Returns at most 10 updates.
    """
    updates: list[Update] = []
    for name, pinned_ver_str in pinned.items():
        if name not in latest:
            continue
        latest_ver_str = latest[name]

        try:
            p_ver = packaging.version.parse(pinned_ver_str)
            l_ver = packaging.version.parse(latest_ver_str)
        except packaging.version.InvalidVersion:
            p_ver = None
            l_ver = None

        if p_ver is None or l_ver is None:
            continue

        if l_ver.is_prerelease or l_ver.is_devrelease:
            continue

        if l_ver > p_ver:
            if l_ver.major > p_ver.major:
                kind: Literal["major", "minor", "patch"] = "major"
            elif l_ver.minor > p_ver.minor:
                kind = "minor"
            else:
                kind = "patch"

            updates.append(
                Update(
                    name=name,
                    pinned=pinned_ver_str,
                    latest=latest_ver_str,
                    kind=kind,
                )
            )

    priority = {"major": 0, "minor": 1, "patch": 2}
    updates.sort(key=lambda u: (priority[u.kind], u.name))
    return updates[:10]
