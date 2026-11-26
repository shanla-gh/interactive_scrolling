"""Shared helpers for the measurement scripts (environment description, statistics)."""

from __future__ import annotations

import importlib.metadata
import platform
import statistics
from typing import Any

import psutil


def environment() -> dict[str, Any]:
    """Describe the test machine without user names, host names or file paths."""
    packages = {}
    for name in ("mediapipe", "opencv-contrib-python", "numpy", "PySide6", "psutil"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python": platform.python_version(),
        "cpu": platform.processor(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 1024**3, 1),
        "packages": packages,
    }


def summarize(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    ordered = sorted(values)

    def pct(q: float) -> float:
        return ordered[min(len(ordered) - 1, max(0, round(q / 100 * len(ordered)) - 1))]

    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 2),
        "median": round(statistics.median(values), 2),
        "p95": round(pct(95), 2),
        "p99": round(pct(99), 2),
        "max": round(ordered[-1], 2),
        "min": round(ordered[0], 2),
    }
