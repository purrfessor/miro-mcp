"""Logging helpers for consistent structured output."""

from __future__ import annotations

import json
import logging
from typing import Any

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging() -> None:
    """Configure application logging once."""
    logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)


def format_log(message: str, **context: Any) -> str:
    """Render a log line with structured JSON context."""
    if not context:
        return message
    safe_context = json.dumps(context, default=str, sort_keys=True)
    return f"{message} | context={safe_context}"
