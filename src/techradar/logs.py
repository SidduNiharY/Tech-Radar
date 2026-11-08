"""JSON logging with secret and token redaction."""

import json
import logging
import re
import sys
import traceback
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, TextIO

REDACTED: str = "[REDACTED]"

_TELEGRAM_TOKEN_PATTERN = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")
_DB_URL_PATTERN = re.compile(r"(://[^:/@\s]+):[^@\s]+@")

__all__ = ["REDACTED", "JsonFormatter", "RedactingFilter", "configure_logging"]


class RedactingFilter(logging.Filter):
    """Logging filter that scrubs sensitive secrets, tokens, and database passwords."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        raw_secrets = secrets if secrets is not None else ()
        self.secrets: list[str] = sorted(
            {s for s in raw_secrets if s},
            key=len,
            reverse=True,
        )

    def redact(self, text: str) -> str:
        """Redact known secrets, Telegram bot tokens, and database credentials."""
        if not isinstance(text, str):
            return text
        for secret in self.secrets:
            text = text.replace(secret, REDACTED)
        text = _TELEGRAM_TOKEN_PATTERN.sub(REDACTED, text)
        text = _DB_URL_PATTERN.sub(r"\1:" + REDACTED + "@", text)
        return text

    def _redact_value(self, val: Any) -> Any:
        if isinstance(val, str):
            return self.redact(val)
        if isinstance(val, tuple):
            return tuple(self._redact_value(v) for v in val)
        if isinstance(val, list):
            return [self._redact_value(v) for v in val]
        if isinstance(val, dict):
            return {k: self._redact_value(v) for k, v in val.items()}
        return val

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact record msg, format args, and exception text in place."""
        if isinstance(record.msg, str):
            record.msg = self.redact(record.msg)
        if record.args:
            record.args = self._redact_value(record.args)
        if record.exc_info and not record.exc_text:
            if isinstance(record.exc_info, tuple) and record.exc_info[0] is not None:
                record.exc_text = "".join(traceback.format_exception(*record.exc_info)).rstrip("\n")
            elif isinstance(record.exc_info, BaseException):
                record.exc_text = "".join(traceback.format_exception(record.exc_info)).rstrip("\n")
        if record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        return True


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects with standard fields."""

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        ts = datetime.fromtimestamp(record.created, tz=UTC).isoformat().replace("+00:00", "Z")
        payload: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.message,
        }
        has_exc = False
        if record.exc_info:
            if isinstance(record.exc_info, tuple) and record.exc_info[0] is not None:
                has_exc = True
            elif isinstance(record.exc_info, BaseException):
                has_exc = True
        if has_exc:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            payload["exc"] = record.exc_text
        elif record.exc_text:
            payload["exc"] = record.exc_text

        return json.dumps(payload)


def configure_logging(
    level: str | int = "INFO",
    secrets: Iterable[str] = (),
    stream: TextIO | None = None,
) -> None:
    """Configure the root logger with JsonFormatter and RedactingFilter."""
    if isinstance(level, str):
        numeric_level = getattr(logging, level.upper(), logging.INFO)
    else:
        numeric_level = level

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.filters.clear()

    redacting_filter = RedactingFilter(secrets)

    target_stream = stream if stream is not None else sys.stderr
    handler = logging.StreamHandler(target_stream)
    handler.setLevel(numeric_level)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(redacting_filter)

    root.addHandler(handler)
