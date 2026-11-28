"""Live Shorts preview measurement on the real YouTube site (development tool, Brief 008).

Starts the bridge, a throw-away signed-out Edge profile with the real extension, opens
YouTube Shorts and starts the tab capture through the extension (with the Chromium test
switch that replaces the user's click on the extension icon). Then it measures, for each
scenario, the received preview frame rate, the browser-to-app transport delay, the frame size
and whether Shorts commands addressed to the preview tab work:

* ``front``: the Shorts tab is the active tab (normal case).
* ``other-tab``: another tab is in front in the browser.
* ``covered``: an always-on-top window covers the browser window completely.
* ``minimized``: the browser window is minimized.

Usage: python scripts/prototype_preview.py [--seconds 8] [--save-frames DIR] [--json FILE]
Saved frames show YouTube content: keep them local (screenshots/ is not committed).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import socket
import statistics
import sys
import time
import uuid
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests.browser_helpers import TAB_CAPTURE_TEST_ARGS, Browser, find_browser  # noqa: E402

from interactive_scrolling.integrations.youtube.bridge import BridgeServer  # noqa: E402
from interactive_scrolling.integrations.youtube.protocol import command_message  # noqa: E402

TOKEN = "preview-prototype-token-0123456789"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait(predicate, timeout_s: float, step_s: float = 0.2):  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(step_s)
    return predicate()


def browser_cpu(browser: Browser) -> list[psutil.Process]:
    root = psutil.Process(browser.process.pid)
    return [root, *root.children(recursive=True)]


def cpu_percent(processes: list[psutil.Process], seconds: float) -> float:
    """Browser CPU as a share of the whole machine (all logical cores) over ``seconds``."""
    for p in processes:
        with contextlib.suppress(psutil.Error):
            p.cpu_percent(None)
    time.sleep(seconds)
    total = 0.0
    for p in processes:
        with contextlib.suppress(psutil.Error):
            total += p.cpu_percent(None)
    return round(total / psutil.cpu_count(), 1)


def measure(bridge: BridgeServer, seconds: float) -> dict:
    feed = bridge.preview
    start = feed.status()
    sizes: list[int] = []
    transport: list[float] = []
    last = None
    t_end = time.monotonic() + seconds
    while time.monotonic() < t_end:
        frame = feed.latest()
        if frame is not None and frame is not last:
            last = frame
            sizes.append(len(frame.jpeg))
            transport.append(time.time() * 1000 - frame.captured_ms)
        time.sleep(0.005)
    end = feed.status()
    frames = end.frames - start.frames
    return {
        "state": end.state,
        "reason": end.reason,
        "fps": round(frames / seconds, 1),
        "transport_ms_median": round(statistics.median(transport), 1) if transport else None,
        "transport_ms_p95": round(sorted(transport)[int(len(transport) * 0.95)], 1)
        if transport
        else None,
        "jpeg_kb_median": round(statistics.median(sizes) / 1024, 1) if sizes else None,
        "skipped_by_browser": end.skipped - start.skipped,
    }


def preview_command(bridge: BridgeServer, action: str) -> dict:
    client = bridge.clients()[0]
    preview = client.context.preview if client.context else None
    if preview is None or preview.shorts is None:
        return {"outcome": "no preview context"}
    started = time.perf_counter()
    result = bridge.request(
        client.client_id, uuid.uuid4().hex, action, preview.shorts.video_id, 3.0, preview.tab_id
    )
    ms = (time.perf_counter() - started) * 1000
    if isinstance(result, str):
        return {"outcome": "error", "reason": result, "ms": round(ms)}
    return {"outcome": result.outcome, "reason": result.reason, "ms": round(ms)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--save-frames", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    executable = find_browser(prefer_extension_support=True)
    if executable is None:
        print("Microsoft Edge not installed")
        return 2
    assert command_message  # imported for the protocol check below
    bridge = BridgeServer(free_port(), TOKEN)
    assert bridge.start()
    browser = Browser(
        executable, free_port(), extension=True, headless=False, extra_args=TAB_CAPTURE_TEST_ARGS
    )
    report: dict = {"browser": executable.name}
    try:
        worker = browser.extension_worker()
        worker.eval(
            f"chrome.storage.local.set({{token: '{TOKEN}', port: {bridge.port}}})"
            ".then(() => connect())"
        )
        page = browser.new_tab()
        page.call("Page.navigate", url="https://www.youtube.com/shorts")
        time.sleep(5)
        if "consent." in page.eval("location.host"):
            page.eval(
                "[...document.querySelectorAll('button')]"
                ".find(b => b.innerText.trim() === 'Reject all').click()"
            )

        def shorts_ready() -> bool:
            browser.activate(page)
            client = bridge.clients()[0] if bridge.clients() else None
            shorts = client.context.shorts if client and client.context else None
            return bool(shorts and shorts.video_ready)

        if not wait(shorts_ready, 45, 0.5):
            report["error"] = "Shorts did not load"
            print(json.dumps(report, indent=2))
            return 1
        tab_id = bridge.clients()[0].context.shorts.tab_id  # type: ignore[union-attr]
        report["browser_cpu_without_preview"] = cpu_percent(browser_cpu(browser), args.seconds)
        browser.activate(page)  # Edge may bring a startup tab to the front meanwhile
        time.sleep(0.5)
        started = worker.eval(f"startPreview({tab_id})")
        report["start"] = started
        if not started or not started.get("ok"):
            print(json.dumps(report, indent=2))
            return 1
        wait(lambda: bridge.preview.status().frames > 3, 10)
        report["front"] = measure(bridge, args.seconds)
        report["browser_cpu_with_preview"] = cpu_percent(browser_cpu(browser), args.seconds)
        if args.save_frames:
            args.save_frames.mkdir(parents=True, exist_ok=True)
            frame = bridge.preview.latest()
            if frame is not None:
                (args.save_frames / "preview_front.jpg").write_bytes(frame.jpeg)
        report["front"]["next"] = preview_command(bridge, "next_short")
        time.sleep(1.5)
        report["front"]["after_next"] = measure(bridge, 2.0)
        report["front"]["toggle"] = preview_command(bridge, "toggle_playback")
        time.sleep(0.5)
        report["front"]["toggle_back"] = preview_command(bridge, "toggle_playback")

        other = browser.new_tab()
        other.call("Page.navigate", url="about:blank")
        time.sleep(1.5)
        report["other_tab"] = measure(bridge, args.seconds / 2)
        report["other_tab"]["next"] = preview_command(bridge, "next_short")
        time.sleep(1.5)
        report["other_tab"]["previous"] = preview_command(bridge, "previous_short")
        client = bridge.clients()[0]
        report["other_tab"]["context_preview"] = repr(client.context.preview)[:300]
        browser.activate(page)
        time.sleep(1.0)

        win = worker.eval("chrome.windows.getLastFocused().then(w => w.id)")
        worker.eval(f"chrome.windows.update({win}, {{state: 'minimized'}})")
        time.sleep(2.0)
        report["minimized"] = measure(bridge, args.seconds / 2)
        report["minimized"]["next"] = preview_command(bridge, "next_short")
        worker.eval(f"chrome.windows.update({win}, {{state: 'normal'}})")
        time.sleep(1.5)

        # Privacy: the previewed tab leaves Shorts (YouTube home, then another site).
        for name, url in (
            ("left_to_youtube_home", "https://www.youtube.com/"),
            ("left_to_other_site", "https://example.com/"),
        ):
            page.call("Page.navigate", url=url)
            time.sleep(2.5)
            status = bridge.preview.status()
            report[name] = {
                "feed_state": status.state,
                "reason": status.reason,
                "picture_available": bridge.preview.latest() is not None,
                "frames_in_2s": measure(bridge, 2.0)["fps"],
            }
        page.call("Page.navigate", url="https://www.youtube.com/shorts")
        returned = wait(lambda: bridge.preview.latest() is not None, 20, 0.3)
        report["back_to_shorts_resumes"] = bool(returned)

        worker.eval("stopPreview('prototype finished')")
        time.sleep(1.0)
        report["after_stop"] = {
            "feed": bridge.preview.status().state,
            "context_preview": repr(bridge.clients()[0].context.preview),
            "command_to_old_tab": preview_command_force(bridge, tab_id),
        }
    finally:
        browser.close()
        bridge.stop()
    text = json.dumps(report, indent=2)
    print(text)
    if args.json:
        args.json.write_text(text, encoding="utf-8")
    return 0


def preview_command_force(bridge: BridgeServer, tab_id: int) -> dict:
    """After the preview stopped, a command addressed to that tab must be refused."""
    client = bridge.clients()[0]
    shorts = client.context.shorts if client.context else None
    result = bridge.request(
        client.client_id,
        uuid.uuid4().hex,
        "next_short",
        shorts.video_id if shorts else None,
        2.0,
        tab_id,
    )
    if isinstance(result, str):
        return {"outcome": "error", "reason": result}
    return {"outcome": result.outcome, "reason": result.reason}


if __name__ == "__main__":
    raise SystemExit(main())
