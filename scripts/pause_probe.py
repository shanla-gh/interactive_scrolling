"""Machine-wide pause probe (Brief 010, stall investigation).

A separate process (its own interpreter, no Qt, no camera) that sleeps 5 ms in a loop and
records every wake-up that comes more than ``--threshold-ms`` late, with the wall-clock time.
A UI stall in the application that coincides with a late wake-up here was a pause of the whole
machine (or at least of user-mode scheduling), not of the application's UI thread.

Usage: python scripts/pause_probe.py --seconds 3600 --output reports/pauses.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, required=True)
    parser.add_argument("--threshold-ms", type=float, default=50.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pauses: list[dict[str, float]] = []
    end = time.monotonic() + args.seconds
    expected = 0.005
    loops = 0
    while time.monotonic() < end:
        before = time.perf_counter()
        time.sleep(expected)
        late = (time.perf_counter() - before - expected) * 1000
        loops += 1
        if late > args.threshold_ms:
            pauses.append({"wall": round(time.time(), 3), "late_ms": round(late, 1)})
        if loops % 2000 == 0:
            args.output.write_text(json.dumps({"pauses": pauses, "loops": loops}), "utf-8")
    args.output.write_text(json.dumps({"pauses": pauses, "loops": loops, "done": True}), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
