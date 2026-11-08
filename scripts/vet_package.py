#!/usr/bin/env python3
"""Vet a package before approving it into the dependency policy."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_deps import lookalikes, normalize  # noqa: E402

USER_AGENT = "TechRadar-Package-Vetter/1.0"


def _fetch_json(url: str, post_data: dict | None = None) -> dict | None:
    """Fetch JSON from a URL with standard timeout and user agent."""
    if not url.startswith("https://"):
        return None
    headers = {"User-Agent": USER_AGENT}
    data_bytes = None
    if post_data is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(post_data).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=10) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _check_osv(ecosystem: str, name: str) -> str:
    """Query OSV for known vulnerabilities."""
    eco_name = "PyPI" if ecosystem.lower() == "pypi" else "npm"
    payload = {"package": {"name": name, "ecosystem": eco_name}}
    data = _fetch_json("https://api.osv.dev/v1/query", post_data=payload)
    if data is None:
        return "unable to query OSV"
    vulns = data.get("vulns", [])
    if not vulns:
        return "0 found (clean)"
    ids = [v.get("id", "unknown") for v in vulns]
    return f"{len(vulns)} found: {', '.join(ids)}"


def vet_pypi(name: str, popular: list[str]) -> int:
    norm_name = normalize(name)
    url = f"https://pypi.org/pypi/{norm_name}/json"
    data = _fetch_json(url)
    if not data:
        print(f"Error: package '{name}' not found on PyPI", file=sys.stderr)
        return 1

    info = data.get("info", {})
    releases = data.get("releases", {})

    # Earliest release
    earliest_dt: datetime | None = None
    for rel_files in releases.values():
        for f in rel_files:
            upload_time = f.get("upload_time_iso_8601") or f.get("upload_time")
            if upload_time:
                try:
                    dt = datetime.fromisoformat(upload_time.replace("Z", "+00:00"))
                    if earliest_dt is None or dt < earliest_dt:
                        earliest_dt = dt
                except ValueError:
                    continue

    now = datetime.now(UTC)
    if earliest_dt:
        age_days = (now - earliest_dt).days
        date_str = earliest_dt.strftime("%Y-%m-%d")
        if age_days < 90:
            age_display = f"{date_str} ({age_days} days - needs a reason: under 90 days)"
        else:
            age_display = f"{date_str} ({age_days} days)"
    else:
        age_display = "unknown"

    # Lookalikes
    looks = lookalikes(norm_name, popular)
    looks_display = ", ".join(looks) if looks else "none"

    # Monthly downloads
    dl_data = _fetch_json(f"https://pypistats.org/api/packages/{norm_name}/recent")
    downloads = dl_data.get("data", {}).get("last_month") if dl_data else "unknown"

    # Repository & Maintainers
    project_urls = info.get("project_urls") or {}
    repo_url = (
        project_urls.get("Source")
        or project_urls.get("Source Code")
        or project_urls.get("Repository")
        or project_urls.get("GitHub")
        or project_urls.get("Homepage")
        or info.get("home_page")
        or "unknown"
    )
    maintainer = (
        info.get("maintainer") or info.get("author") or info.get("author_email") or "unknown"
    )

    # OSV
    osv_result = _check_osv("pypi", norm_name)

    print(f"Package: {norm_name} (PyPI)")
    print(f"First release: {age_display}")
    print(f"Look-alikes: {looks_display}")
    print(f"Monthly downloads: {downloads}")
    print(f"Repository: {repo_url}")
    print(f"Maintainers: {maintainer}")
    print(f"OSV vulnerabilities: {osv_result}")
    return 0


def vet_npm(name: str, popular: list[str]) -> int:
    norm_name = normalize(name)
    url = f"https://registry.npmjs.org/{norm_name}"
    data = _fetch_json(url)
    if not data:
        print(f"Error: package '{name}' not found on npm", file=sys.stderr)
        return 1

    time_data = data.get("time", {})
    created_str = time_data.get("created")
    now = datetime.now(UTC)
    if created_str:
        try:
            dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            age_days = (now - dt).days
            date_str = dt.strftime("%Y-%m-%d")
            if age_days < 90:
                age_display = f"{date_str} ({age_days} days - needs a reason: under 90 days)"
            else:
                age_display = f"{date_str} ({age_days} days)"
        except ValueError:
            age_display = created_str
    else:
        age_display = "unknown"

    looks = lookalikes(norm_name, popular)
    looks_display = ", ".join(looks) if looks else "none"

    dl_data = _fetch_json(f"https://api.npmjs.org/downloads/point/last-month/{norm_name}")
    downloads = dl_data.get("downloads") if dl_data else "unknown"

    repo_obj = data.get("repository", {})
    repo_url = repo_obj.get("url") if isinstance(repo_obj, dict) else str(repo_obj) or "unknown"
    maintainers = data.get("maintainers", [])
    m_names = [m.get("name") for m in maintainers if isinstance(m, dict) and m.get("name")]
    maintainer_str = ", ".join(m_names) if m_names else "unknown"

    osv_result = _check_osv("npm", norm_name)

    print(f"Package: {norm_name} (npm)")
    print(f"First release: {age_display}")
    print(f"Look-alikes: {looks_display}")
    print(f"Monthly downloads: {downloads}")
    print(f"Repository: {repo_url}")
    print(f"Maintainers: {maintainer_str}")
    print(f"OSV vulnerabilities: {osv_result}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Vet a package from PyPI or npm.")
    parser.add_argument(
        "ecosystem", choices=["pypi", "npm"], help="Package ecosystem (pypi or npm)"
    )
    parser.add_argument("name", help="Package name")
    args = parser.parse_args()

    popular_path = REPO_ROOT / "infra" / "policy" / "popular_packages.txt"
    popular: list[str] = []
    if popular_path.is_file():
        with popular_path.open("r", encoding="utf-8") as f:
            popular = [line.strip() for line in f if line.strip()]

    if args.ecosystem == "pypi":
        return vet_pypi(args.name, popular)
    else:
        return vet_npm(args.name, popular)


if __name__ == "__main__":
    sys.exit(main())
