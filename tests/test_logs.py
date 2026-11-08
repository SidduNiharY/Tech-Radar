import io
import json
import logging

import pytest

from techradar.logs import REDACTED, JsonFormatter, RedactingFilter, configure_logging


@pytest.fixture
def caplog_json():
    stream = io.StringIO()
    configure_logging(level="INFO", secrets=["s3cr3t-value"], stream=stream)
    try:
        yield stream.getvalue
    finally:
        logging.getLogger().handlers.clear()


def test_exact_secret_redacted(caplog_json):
    logging.getLogger("t").info("token=%s", "s3cr3t-value")
    assert "s3cr3t-value" not in caplog_json() and "[REDACTED]" in caplog_json()


def test_telegram_like_token_redacted(caplog_json):
    logging.getLogger("t").info("bot 1234567890:AAEhBP0av28AAAAAAAAAAAAAAAAAAAAAAAA")
    assert "AAEhBP0av28" not in caplog_json()


def test_db_url_password_redacted(caplog_json):
    logging.getLogger("t").info("postgresql+psycopg://tr_app:hunter2@postgres:5432/techradar")
    assert "hunter2" not in caplog_json() and "tr_app:[REDACTED]@" in caplog_json()


def test_output_is_json_with_keys(caplog_json):
    logging.getLogger("t").warning("hi")
    assert {"ts", "level", "logger", "msg"} <= json.loads(caplog_json().splitlines()[-1]).keys()


def test_exception_text_redacted(caplog_json):
    try:
        raise ValueError("pw s3cr3t-value")
    except ValueError:
        logging.getLogger("t").exception("boom")
    assert "s3cr3t-value" not in caplog_json()


def test_redacted_constant():
    assert REDACTED == "[REDACTED]"


def test_redacting_filter_direct():
    rf = RedactingFilter(secrets=["my_token_secret"])
    record = logging.LogRecord(
        "test", logging.INFO, "test.py", 1, "my_token_secret in msg", (), None
    )
    assert rf.filter(record) is True
    assert record.msg == "[REDACTED] in msg"


def test_json_formatter_keys():
    formatter = JsonFormatter()
    record = logging.LogRecord("test", logging.WARNING, "test.py", 10, "hello world", (), None)
    formatted = formatter.format(record)
    data = json.loads(formatted)
    assert data["level"] == "WARNING"
    assert data["logger"] == "test"
    assert data["msg"] == "hello world"
    assert "ts" in data
    assert "exc" not in data
