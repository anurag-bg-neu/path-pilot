"""Structured, PII-free JSON logger shared across all PathPilot agents."""
import json
import logging
import sys
from typing import Any


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        try:
            body: dict[str, Any] = json.loads(msg)
        except (json.JSONDecodeError, TypeError):
            body = {"msg": msg}
        payload: dict[str, Any] = {"level": record.levelname, "logger": record.name, **body}
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _build() -> logging.Logger:
    logger = logging.getLogger("pathpilot")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


log = _build()


def slog(level: str = "info", **fields: Any) -> None:
    """Emit a structured log record. Pass only non-PII fields."""
    getattr(log, level)(json.dumps(fields))
