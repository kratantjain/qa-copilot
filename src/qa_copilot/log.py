"""Logging setup. Control with QA_COPILOT_LOG=DEBUG|INFO|WARNING (default INFO)."""
from __future__ import annotations

import logging
import os

log = logging.getLogger("qa_copilot")


def setup() -> None:
    level = os.getenv("QA_COPILOT_LOG", "INFO").upper()
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.WARNING,
                            format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    log.setLevel(getattr(logging, level, logging.INFO))
