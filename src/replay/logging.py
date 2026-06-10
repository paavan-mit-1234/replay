"""Logging setup with a filter that redacts anything shaped like a secret.

This is defense in depth. Secrets should never reach a log call in the first
place, but if one slips through, this masks common provider and Replay key
shapes before the record is emitted.
"""

from __future__ import annotations

import logging
import re

from replay.config import get_settings

# sk-ant-..., sk-..., rpl_..., and long bearer-ish tokens.
_SECRET_RE = re.compile(
    r"(sk-ant-[A-Za-z0-9_\-]+|sk-[A-Za-z0-9_\-]{16,}|rpl_[A-Za-z0-9_\-]+)"
)


class RedactSecretsFilter(logging.Filter):
    """Replace secret-shaped substrings in log messages with a marker."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _SECRET_RE.sub("[redacted]", record.msg)
        if record.args:
            record.args = tuple(
                _SECRET_RE.sub("[redacted]", a) if isinstance(a, str) else a
                for a in record.args
            )
        return True


def configure_logging() -> None:
    """Configure root logging with the redaction filter installed."""
    settings = get_settings()
    handler = logging.StreamHandler()
    handler.addFilter(RedactSecretsFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
