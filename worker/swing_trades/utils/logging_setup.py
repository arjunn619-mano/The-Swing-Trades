"""Structured JSON-line logging with enforced rotation (v1 lesson: logs grew to 130 MB
because rotation never purged). backupCount caps the number of files on disk."""
from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class _JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(
    log_dir: str | Path,
    *,
    name: str = "swing_trades",
    level: int = logging.INFO,
    max_bytes: int = 5_000_000,
    backup_count: int = 7,
    also_console: bool = True,
) -> logging.Logger:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()  # idempotent: safe to call repeatedly
    logger.propagate = False

    fmt = _JsonLineFormatter()

    file_handler = RotatingFileHandler(
        log_dir / "scan.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    if also_console:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        logger.addHandler(console)

    return logger
