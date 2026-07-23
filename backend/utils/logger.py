"""
logger.py
Central logging configuration. Every module imports get_logger(__name__)
instead of calling logging.getLogger directly so log format stays consistent
across the whole backend.
"""

import logging
import os
import sys

from config import LOG_DIR

_LOG_FILE = os.path.join(LOG_DIR, "app.log")
_configured = False


def _configure_root_logger():
    """Attach a file handler and a stdout handler to the root logger once."""
    global _configured
    if _configured:
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger, configuring the root logger on first use."""
    _configure_root_logger()
    return logging.getLogger(name)
