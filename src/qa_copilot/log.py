"""Logging setup. Control with QA_COPILOT_LOG=DEBUG|INFO|WARNING (default INFO)."""
from __future__ import annotations

import logging
import os

log = logging.getLogger("qa_copilot")


class _QuietBackgroundedBrowser(logging.Filter):
    """NiceGUI asks the browser a question (e.g. 'is the drawer open?'); when a mobile browser
    is backgrounded it cannot answer and NiceGUI logs a long, harmless traceback. Drop it."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "JavaScript did not respond" not in record.getMessage()


def setup() -> None:
    level = os.getenv("QA_COPILOT_LOG", "INFO").upper()
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.WARNING,
                            format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    log.setLevel(getattr(logging, level, logging.INFO))
    quiet = _QuietBackgroundedBrowser()
    for name in ("", "nicegui"):
        lg = logging.getLogger(name)
        if not any(isinstance(f, _QuietBackgroundedBrowser) for f in lg.filters):
            lg.addFilter(quiet)
        for h in lg.handlers:
            if not any(isinstance(f, _QuietBackgroundedBrowser) for f in h.filters):
                h.addFilter(quiet)
