from pathlib import Path

import pytest

from techradar.fetcher.sources import load_sources
from techradar.security.urls import UrlRejected, load_allowlist

A = frozenset({"pib.gov.in", ".github.com"})


def test_repo_sources_file_valid():
    sources_path = Path("infra/sources/sources.yaml")
    allowlist_path = Path("infra/squid/allowlist.txt")
    if sources_path.exists() and allowlist_path.exists():
        sources = load_sources(sources_path, load_allowlist(allowlist_path))
        assert len(sources) > 0


def test_load_sources_rejects_non_allowlisted(tmp_path):
    (tmp_path / "s.yaml").write_text(
        "- {name: x, url: 'https://evil.example/feed', section: tech, trust_tier: news}\n"
    )
    with pytest.raises(UrlRejected):
        load_sources(tmp_path / "s.yaml", A)
