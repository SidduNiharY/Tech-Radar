"""Application configuration and strict secret loading."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecretError(Exception):
    """Raised when a secret file is missing, invalid, or insecure."""


def read_secret(name: str, secrets_dir: Path = Path("/run/secrets")) -> str:
    """Read a secret file securely.

    Enforces that the secret:
    1. exists and is a regular file
    2. is not a symlink
    3. is readable only by the owner (mode 0600 or 0400, no group/world bits)
    4. is non-empty after stripping whitespace
    """
    path = Path(secrets_dir) / name

    if not path.exists() and not path.is_symlink():
        raise SecretError(f"missing secret file: {path}")
    if path.is_symlink():
        raise SecretError(f"symlink secret file rejected: {path}")
    if not path.is_file():
        raise SecretError(f"missing secret file: {path}")
    if path.stat().st_mode & 0o077 != 0:
        raise SecretError(
            f"permissions too open on {path}: mode must not have group or world permissions"
        )

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise SecretError(f"empty secret file: {path}")

    return content


class Settings(BaseSettings):
    """Global configuration settings for TechRadar Brain."""

    model_config = SettingsConfigDict(
        env_prefix="TR_",
        env_file=".env",
        extra="ignore",
    )

    env: Literal["dev", "prod"] = "dev"
    tz: str = "Asia/Kolkata"
    data_dir: Path = Path("/data")
    vault_dir: Path = Path("/data/vault")
    secrets_dir: Path = Path("/run/secrets")
    db_host: str = "postgres"
    db_port: int = 5432
    db_name: str = "techradar"
    telegram_owner_chat_id: int
    allow_cloud_llm: bool = False
    ollama_base_url: str = "http://ollama:11434"
    https_proxy: str = "http://squid:3128"
    fetch_interval_min: int = 120
    per_domain_delay_s: float = 5.0
    max_fetch_bytes: int = 5_000_000
    fetch_timeout_s: float = 20.0
    parse_timeout_s: int = 120
    max_doc_chars: int = 100_000
    dedupe_threshold: float = 0.90
    relevance_min: float = 0.30
    retention_days: int = 7
    briefing_time: str = "06:30"
    misfire_grace_s: int = 21600
    user_agent: str = "TechRadarBrain/0.1 (personal, non-commercial)"
    alert_chat_id: int | None = None
    containment: Literal["alert-only", "on"] = "alert-only"
    heartbeat_time: str = "06:25"
    quiet_hours: str = "23:00-06:00"
    alert_log: Path = Path("/var/lib/techradar-alerter/alerts.jsonl")
    incidents_dir: Path = Path("data/incidents")
    evidence_pubkey: Path = Path("infra/host/evidence.pub")
    index_skip: list[str] = []
    rag_min_score: float = 0.30
    rag_k_candidates: int = 30
    rag_k_final: int = 6
    max_question_chars: int = 500
    reranker_path: Path = Path("/opt/models/reranker")
    reranker_device: Literal["cpu", "cuda"] = "cpu"
    library_dir: Path = Path("/data/library")
    owner_login: str = "owner@local"
    library_inbox: Path = Path("/data/library-inbox")
    library_packs_dir: Path = Path("/data/library-packs")
    library_part_pages: int = 25
    max_video_s: int = 14_400
    pack_max_bytes: int = 200_000_000
    night_start: str = "01:00"
    night_end: str = "05:00"

    @field_validator("index_skip", mode="before")
    @classmethod
    def _parse_index_skip(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v or []


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
