from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from techradar.security.urls import check_url, load_allowlist


class StarterPackItem(BaseModel):
    """An educational starter pack item for ingestion."""

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    exam: str
    url: str
    approved: bool
    max_bytes: int = Field(default=200_000_000)


class StarterPackManager:
    """Manages curated starter pack items and their validation."""

    def __init__(
        self,
        config_path: Path | None = None,
        allowlist_path: Path | None = None,
    ) -> None:
        self.config_path = config_path or Path("infra/sources/exam_packs.yaml")
        self.allowlist_path = allowlist_path or Path("infra/squid/allowlist.txt")
        self.items: list[StarterPackItem] = []
        if self.config_path.exists():
            self.load_packs()

    def load_packs(self, config_path: Path | None = None) -> list[StarterPackItem]:
        """Load starter pack items from YAML config file."""
        path = config_path or self.config_path
        if not path.exists():
            self.items = []
            return []

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        items: list[StarterPackItem] = []
        if isinstance(data, dict):
            if "packs" in data and isinstance(data["packs"], list):
                for entry in data["packs"]:
                    if isinstance(entry, dict):
                        items.append(StarterPackItem(**entry))
            elif "packs" in data and isinstance(data["packs"], dict):
                for k, v in data["packs"].items():
                    if isinstance(v, dict):
                        items.append(StarterPackItem(id=k, **v))
            else:
                for k, v in data.items():
                    if isinstance(v, dict):
                        items.append(StarterPackItem(id=k, **v))
        elif isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    items.append(StarterPackItem(**entry))

        self.items = items
        return items

    def get_approved_packs(self) -> list[StarterPackItem]:
        """Return only items where approved is True."""
        return [item for item in self.items if item.approved]

    @staticmethod
    def validate_pack_url(url: str, allowlist_path: Path | None = None) -> bool:
        """Ensure URL scheme is https and domain is in Squid allowlist.

        Rejects non-https URLs, unallowlisted domains, and file-sharing sites.
        """
        path = allowlist_path or Path("infra/squid/allowlist.txt")
        if not path.exists():
            return False

        try:
            allowed = load_allowlist(path)
            check_url(url, allowed)
            return True
        except Exception:
            return False

    @staticmethod
    def validate_download_size(size_bytes: int, max_bytes: int = 200_000_000) -> bool:
        """Enforce maximum download size limit (default 200MB)."""
        return 0 <= size_bytes <= max_bytes
