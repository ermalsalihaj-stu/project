"""Minimal logging setup for CLI and pipeline."""
from __future__ import annotations

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configure basic logging to stderr."""
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module name."""
    return logging.getLogger(name)
