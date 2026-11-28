"""Doomscroll Together overhead on one computer (loopback; development tool, Brief 008).

Runs a Host and a Guest in this process with a scripted Host browser (confirms each action
after ``--browser-ms``), then measures:

* process CPU (share of all logical cores) while the session is idle (pings only);
* the network round trip reported by the Guest's pings;
* the Guest's confirmation time for shared actions (request -> Host executes -> result).

Loopback has no Wi-Fi or Internet latency: these are the app's own costs, not a two-computer
measurement.

Usage: python scripts/benchmark_coop.py [--idle-s 30] [--actions 20] [--json FILE]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interactive_scrolling.actions.dispatcher import ActionDispatcher  # noqa: E402
from interactive_scrolling.actions.types import (  # noqa: E402
    ActionResult,
    ActionStatus,
    ActionType,
    ControllerCheck,
    ControlMode,
)
from interactive_scrolling.integrations.coop.session import (  # noqa: E402
    CoopGuest,
    CoopGuestController,
    CoopHost,
)


class ScriptedBrowser:
    def __init__(self, delay_s: float) -> None:
        self.delay_s = delay_s

    def check(self, action: ActionType) -> ControllerCheck:
        return ControllerCheck(True)

    def execute(self, action: ActionType, request_id: str, timeout_s: float) -> ActionResult:
        time.sleep(self.delay_s)
        return ActionResult(ActionStatus.SUCCEEDED)

    def cancel_all(self) -> None:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--idle-s", type=float, default=30.0)
    parser.add_argument("--actions", type=int, default=20)
    parser.add_argument("--browser-ms", type=float, default=250.0)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    process = psutil.Process()
    host_dispatcher = ActionDispatcher(ScriptedBrowser(args.browser_ms / 1000))
    host = CoopHost(host_dispatcher, "Host", port=0, bind="127.0.0.1", shared_cooldown_s=0.0)
    code = host.start()
    guest = CoopGuest("Guest")
    guest_dispatcher = ActionDispatcher(None)
    report: dict = {"browser_ms": args.browser_ms}
    try:
        guest.connect("127.0.0.1", host.port, code)
        while not host.status().pending_approval:
            time.sleep(0.05)
        host.approve()
        while not guest.approved:
            time.sleep(0.05)
        host_dispatcher.set_mode(ControlMode.LIVE_CONTROL)
        controller = CoopGuestController(guest)
        process.cpu_percent(None)
        rtts = []
        end = time.monotonic() + args.idle_s
        while time.monotonic() < end:
            time.sleep(1.0)
            if guest.rtt_ms is not None:
                rtts.append(guest.rtt_ms)
        report["idle_cpu_percent_of_machine"] = round(
            process.cpu_percent(None) / psutil.cpu_count(), 2
        )
        report["ping_rtt_ms_median"] = round(statistics.median(rtts), 2) if rtts else None
        confirm, outcomes = [], []
        for _ in range(args.actions):
            t0 = time.perf_counter()
            result = controller.execute(ActionType.TOGGLE_PLAYBACK, uuid.uuid4().hex, 3.0)
            confirm.append((time.perf_counter() - t0) * 1000)
            outcomes.append(result.status.value)
            time.sleep(0.3)
        report["confirm_ms_median"] = round(statistics.median(confirm), 1)
        report["confirm_ms_max"] = round(max(confirm), 1)
        report["overhead_ms_median"] = round(statistics.median(confirm) - args.browser_ms, 1)
        report["outcomes"] = {o: outcomes.count(o) for o in set(outcomes)}
    finally:
        guest.disconnect()
        host.stop()
        host_dispatcher.shutdown()
        guest_dispatcher.shutdown()
    text = json.dumps(report, indent=2)
    print(text)
    if args.json:
        args.json.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
