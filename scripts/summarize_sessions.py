"""One table row per stability-session report (development tool).

Usage: python scripts/summarize_sessions.py reports/b8_*.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def mean(value) -> str:  # type: ignore[no-untyped-def]
    if isinstance(value, dict):
        value = value.get("mean")
    return f"{value:.1f}" if isinstance(value, int | float) else "-"


def p95(value) -> str:  # type: ignore[no-untyped-def]
    if isinstance(value, dict) and isinstance(value.get("p95"), int | float):
        return f"{value['p95']:.1f}"
    return "-"


def main() -> int:
    print(
        "| Report | Mode | Minutes | Capture / processing fps | Latency mean (p95) ms | "
        "Dropped /min | CPU % | RSS first -> last MB | UI stalls (max ms) | Preview |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name in sys.argv[1:]:
        r = json.loads(Path(name).read_text(encoding="utf-8"))
        minutes = r["measured_seconds"] / 60
        stalls = r.get("ui_stalls") or []
        count = len(stalls)
        worst = round(max(x["duration_ms"] for x in stalls)) if stalls else None
        preview = r.get("preview")
        preview_text = (
            f"{preview['frames_received']} frames, {preview['frames_decoded_by_window']} painted"
            if preview
            else "-"
        )
        mode = r["ui_mode"] + (" +models" if r.get("optional_models") else "")
        mode += " +transparent" if r.get("transparent") else ""
        if r.get("timer_resolution_opt_out") is False:
            mode += " (timer throttling kept)"
        print(
            f"| {Path(name).name} | {mode} | {minutes:.1f} | {mean(r['capture_fps'])} / "
            f"{mean(r['processing_fps'])} | {mean(r['latency_ms'])} ({p95(r['latency_ms'])}) | "
            f"{r['frames_dropped_total'] / minutes:.1f} | {mean(r['cpu_percent_of_machine'])} | "
            f"{r['rss_first_minute_mean']:.0f} -> {r['rss_last_minute_mean']:.0f} | "
            f"{count} ({worst if worst is not None else '-'}) | {preview_text} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
