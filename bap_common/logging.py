"""Logging helpers that keep secrets and sensor payloads out of logs."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_SENSITIVE_KEYS = {
    "access_token",
    "database_credential",
    "imu_payload",
    "password",
    "refresh_token",
    "secret",
    "token",
}
_VALUE_PATTERN = re.compile(
    r"(?i)\b(password|access[_ -]?token|refresh[_ -]?token|secret|database[_ -]?credential|imu[_ -]?payload)\s*[:=]\s*([^\s,;]+)"
)


def _redact_text(value: str) -> str:
    return _VALUE_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


class SensitiveDataFilter(logging.Filter):
    """Best-effort protection for accidental sensitive key/value logging."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_text(str(record.msg))
        if record.args:
            if isinstance(record.args, Mapping):
                record.args = {
                    key: "[REDACTED]" if str(key).lower() in _SENSITIVE_KEYS else value
                    for key, value in record.args.items()
                }
            else:
                record.args = tuple(_redact_text(str(value)) for value in record.args)
        return True


def configure_logging(
    *,
    name: str = "bap",
    log_file: Path | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """Create an idempotent BAP logger with the redaction filter installed."""

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler: logging.Handler
        if log_file is None:
            handler = logging.StreamHandler()
        else:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)
    return logger


def safe_log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Log structured metadata while dropping fields that may contain secrets/data."""

    safe_fields = {
        key: value
        for key, value in fields.items()
        if key.lower() not in _SENSITIVE_KEYS
    }
    suffix = " ".join(f"{key}={value}" for key, value in sorted(safe_fields.items()))
    logger.info("%s%s", event, f" {suffix}" if suffix else "")
