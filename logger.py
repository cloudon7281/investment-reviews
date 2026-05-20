"""Logging configuration for investment-reviews.

Copied from devops-model scaffold/logging_config.py. Conforms to SDI §10.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import warnings
from datetime import datetime, timezone

# Suppress specific RuntimeWarnings from numbers_parser about rounding
warnings.filterwarnings('ignore', message='.*rounded to 15 significant digits', category=RuntimeWarning)
warnings.filterwarnings('ignore', message=r'.*rounded to \d+ significant digits', category=RuntimeWarning)
warnings.filterwarnings('ignore', category=RuntimeWarning, module='numbers_parser')

SERVICE_NAME = "investment-reviews"

_LEVEL_MAP = {
    "WARNING": "WARN",
    "CRITICAL": "FATAL",
}


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        level = _LEVEL_MAP.get(record.levelname, record.levelname)
        ts = (
            datetime.fromtimestamp(record.created, tz=timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{int(record.msecs):03d}Z"
        )
        obj: dict = {
            "ts": ts,
            "level": level,
            "service": SERVICE_NAME,
            "instance": os.environ.get("INSTANCE", "-"),
            "msg": record.getMessage(),
        }
        if record.name and record.name not in ("root", "__main__"):
            obj["component"] = record.name
        if hasattr(record, "event"):
            obj["event"] = record.event
        if record.exc_info:
            obj["err"] = self.formatException(record.exc_info)
        return json.dumps(obj)


def configure_logging(level: int | None = None) -> None:
    """Configure root logger from LOG_FORMAT / LOG_LEVEL env vars."""
    if level is None:
        level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)

    fmt = os.environ.get("LOG_FORMAT", "text").lower()
    handler = logging.StreamHandler(sys.stdout)

    if fmt == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )

    logging.root.handlers = []
    logging.root.addHandler(handler)
    logging.root.setLevel(level)

    # Suppress noisy third-party loggers
    logging.getLogger('pdfminer').setLevel(logging.ERROR)
    logging.getLogger('pdfplumber').setLevel(logging.ERROR)
    logging.getLogger('numbers_parser').setLevel(logging.ERROR)
    logging.getLogger('yfinance').setLevel(logging.ERROR)


def setup_logger(log_level: str = 'INFO') -> logging.Logger:
    """Legacy alias for configure_logging(); kept for call-site compatibility."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    configure_logging(level=level)
    return logging.getLogger()


# Module-level logger for `from logger import logger` call sites
logger = logging.getLogger()
