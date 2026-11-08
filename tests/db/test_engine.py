"""Unit tests for database engine and model definitions without a live database."""

from pathlib import Path

import pytest
from sqlalchemy import BigInteger, DateTime, Identity, String
from sqlalchemy.dialects.postgresql import JSONB

from techradar.db.engine import database_url, make_engine
from techradar.db.models import AuditEvent, Base
from techradar.settings import SecretError, Settings


@pytest.fixture
def test_secrets_dir(tmp_path: Path) -> Path:
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(mode=0o700)
    for role in ("migrator", "app", "ro"):
        secret_file = secrets_dir / f"tr_{role}_password"
        secret_file.write_text(f"{role}_secret_value\n")
        secret_file.chmod(0o600)
    return secrets_dir


@pytest.fixture
def test_settings(test_secrets_dir: Path) -> Settings:
    return Settings(
        telegram_owner_chat_id=123456,
        db_host="127.0.0.1",
        db_port=5432,
        db_name="techradar_test",
        secrets_dir=test_secrets_dir,
    )


def test_database_url_for_roles(test_settings: Settings) -> None:
    app_url = database_url("app", test_settings)
    assert app_url == "postgresql+psycopg://tr_app:app_secret_value@127.0.0.1:5432/techradar_test"

    migrator_url = database_url("migrator", test_settings)
    assert (
        migrator_url
        == "postgresql+psycopg://tr_migrator:migrator_secret_value@127.0.0.1:5432/techradar_test"
    )

    ro_url = database_url("ro", test_settings)
    assert ro_url == "postgresql+psycopg://tr_ro:ro_secret_value@127.0.0.1:5432/techradar_test"


def test_database_url_invalid_role(test_settings: Settings) -> None:
    with pytest.raises(ValueError, match="Invalid db role"):
        database_url("superuser", test_settings)  # type: ignore[arg-type]


def test_database_url_missing_secret(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty_secrets"
    empty_dir.mkdir(mode=0o700)
    s = Settings(
        telegram_owner_chat_id=123456,
        secrets_dir=empty_dir,
    )
    with pytest.raises(SecretError, match="missing secret file"):
        database_url("app", s)


def test_audit_event_model_metadata() -> None:
    table = AuditEvent.__table__
    assert table.schema == "techradar"
    assert table.name == "audit_log"
    assert "techradar.audit_log" in Base.metadata.tables

    cols = table.columns
    assert isinstance(cols["id"].type, BigInteger)
    assert cols["id"].primary_key
    assert isinstance(cols["id"].identity, Identity)

    assert isinstance(cols["at"].type, DateTime)
    assert cols["at"].type.timezone is True
    assert cols["at"].server_default is not None

    assert isinstance(cols["actor"].type, String)
    assert cols["actor"].type.length == 64

    assert isinstance(cols["action"].type, String)
    assert cols["action"].type.length == 64

    assert isinstance(cols["detail"].type, JSONB)


def test_make_engine_creates_engine(test_settings: Settings) -> None:
    engine = make_engine("app", test_settings)
    assert engine.url.render_as_string(hide_password=False) == database_url("app", test_settings)
    assert engine.sync_engine.pool._pre_ping is True
    engine.sync_engine.dispose()
