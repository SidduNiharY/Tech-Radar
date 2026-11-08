from pathlib import Path

import pytest
from pydantic import ValidationError

from techradar.settings import SecretError, Settings, get_settings, read_secret


def test_read_secret_strips_whitespace(tmp_path: Path) -> None:
    p = tmp_path / "tok"
    p.write_text("abc \r\n")
    p.chmod(0o600)
    assert read_secret("tok", tmp_path) == "abc"


def test_read_secret_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(SecretError, match="missing"):
        read_secret("nope", tmp_path)


def test_read_secret_empty_raises(tmp_path: Path) -> None:
    p = tmp_path / "e"
    p.write_text("\n")
    p.chmod(0o600)
    with pytest.raises(SecretError, match="empty"):
        read_secret("e", tmp_path)


def test_read_secret_rejects_group_or_world_readable(tmp_path: Path) -> None:
    p = tmp_path / "s"
    p.write_text("x")
    p.chmod(0o640)
    with pytest.raises(SecretError, match="permissions"):
        read_secret("s", tmp_path)


def test_read_secret_rejects_symlink(tmp_path: Path) -> None:
    t = tmp_path / "t"
    t.write_text("x")
    t.chmod(0o600)
    (tmp_path / "l").symlink_to(t)
    with pytest.raises(SecretError, match="symlink"):
        read_secret("l", tmp_path)


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TR_TELEGRAM_OWNER_CHAT_ID", "1")
    s = Settings()
    assert (s.allow_cloud_llm, s.tz, s.dedupe_threshold, s.relevance_min) == (
        False,
        "Asia/Kolkata",
        0.90,
        0.30,
    )
    assert s.env == "dev"
    assert s.data_dir == Path("/data")
    assert s.vault_dir == Path("/data/vault")
    assert s.secrets_dir == Path("/run/secrets")
    assert s.db_host == "postgres"
    assert s.db_port == 5432
    assert s.db_name == "techradar"
    assert s.telegram_owner_chat_id == 1
    assert s.ollama_base_url == "http://ollama:11434"
    assert s.https_proxy == "http://squid:3128"
    assert s.fetch_interval_min == 120
    assert s.per_domain_delay_s == 5.0
    assert s.max_fetch_bytes == 5_000_000
    assert s.fetch_timeout_s == 20.0
    assert s.parse_timeout_s == 120
    assert s.max_doc_chars == 100_000
    assert s.retention_days == 7
    assert s.briefing_time == "06:30"
    assert s.misfire_grace_s == 21600
    assert s.user_agent == "TechRadarBrain/0.1 (personal, non-commercial)"
    assert s.alert_chat_id is None
    assert s.containment == "alert-only"
    assert s.heartbeat_time == "06:25"
    assert s.quiet_hours == "23:00-06:00"
    assert s.alert_log == Path("/var/lib/techradar-alerter/alerts.jsonl")
    assert s.incidents_dir == Path("data/incidents")
    assert s.evidence_pubkey == Path("infra/host/evidence.pub")

    get_settings.cache_clear()
    cached = get_settings()
    assert cached.telegram_owner_chat_id == 1
    assert get_settings() is cached
    get_settings.cache_clear()


def test_settings_requires_owner_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TR_TELEGRAM_OWNER_CHAT_ID", raising=False)
    with pytest.raises(ValidationError):
        Settings()
