"""Process resource measurements for the diagnostics display and benchmarks."""

from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass(frozen=True, slots=True)
class ResourceSample:
    cpu_percent_of_machine: float
    """Process CPU time as a share of the whole machine (all logical cores = 100 %)."""
    cpu_percent_of_core: float
    """Process CPU time where one fully busy logical core = 100 % (may exceed 100 %)."""
    rss_mb: float
    thread_count: int


class ResourceMonitor:
    """Samples the current process's CPU and memory use.

    CPU usage is measured between consecutive calls to :meth:`sample`; the first call
    establishes the baseline and reports 0 %.
    """

    def __init__(self) -> None:
        self._process = psutil.Process()
        self._cores = psutil.cpu_count(logical=True) or 1
        self._process.cpu_percent(None)

    @property
    def logical_cores(self) -> int:
        return self._cores

    def sample(self) -> ResourceSample:
        per_core = self._process.cpu_percent(None)
        with self._process.oneshot():
            rss = self._process.memory_info().rss
            threads = self._process.num_threads()
        return ResourceSample(
            cpu_percent_of_machine=per_core / self._cores,
            cpu_percent_of_core=per_core,
            rss_mb=rss / (1024 * 1024),
            thread_count=threads,
        )
