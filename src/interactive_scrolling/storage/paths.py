"""Location of per-user application data (settings, analytics database)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

DATA_DIR_ENV_VAR = "INTERACTIVE_SCROLLING_DATA_DIR"


def data_dir() -> Path:
    """``%LOCALAPPDATA%\\interactive_scrolling`` on Windows (overridable for tests)."""
    override = os.environ.get(DATA_DIR_ENV_VAR)
    if override:
        return Path(override)
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "interactive_scrolling"
    return Path.home() / ".local" / "share" / "interactive_scrolling"
