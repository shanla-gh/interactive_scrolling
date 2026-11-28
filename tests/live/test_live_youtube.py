"""The real YouTube Shorts website with the real extension (opt in: ``--live-youtube``).

This test depends on the live site and on how YouTube treats an automated, signed-out
browser; it is a verification aid, not a CI gate. Results are recorded in
docs/milestones/M3_YOUTUBE_INTEGRATION.md.

Runs in a throw-away, signed-out Microsoft Edge profile, so no account is involved and no like
can be registered: liking must be rejected as "not signed in" without clicking. If YouTube
shows its cookie-consent page, the test chooses "Reject all".
"""

from __future__ import annotations

import socket
import time
import uuid

import pytest

from interactive_scrolling.actions.types import ActionStatus, ActionType
from interactive_scrolling.integrations.youtube.bridge import BridgeServer
from interactive_scrolling.integrations.youtube.controller import YouTubeShortsController
from tests.browser_helpers import Browser, find_browser
from tests.helpers import wait_until

pytestmark = pytest.mark.live_youtube
TOKEN = "live-test-pairing-token-0123456789"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


DIAGNOSTICS = """JSON.stringify({
  path: location.pathname + location.search,
  visibility: document.visibilityState,
  focused: document.hasFocus(),
  reels: document.querySelectorAll("ytd-reel-video-renderer").length,
  active: document.querySelectorAll("ytd-reel-video-renderer[is-active]").length,
  dialogs: [...document.querySelectorAll("[role=dialog], tp-yt-paper-dialog")]
    .filter(e => e.getClientRects().length && (e.innerText || "").trim())
    .map(e => (e.innerText || "").trim().slice(0, 80)).slice(0, 3),
  down: (() => { const h = document.querySelector("#navigation-button-down");
    const b = h && h.querySelector("button");
    return b ? {disabled: b.disabled, aria: b.getAttribute("aria-disabled"),
      hidden: h.getAttribute("aria-hidden"), vis: getComputedStyle(h).visibility} : null; })(),
  video: (() => { const v = document.querySelector("ytd-reel-video-renderer[is-active] video")
    || document.querySelector("#shorts-player video");
    return v ? {ready: v.readyState, paused: v.paused, t: Math.round(v.currentTime * 10) / 10}
      : null; })(),
})"""


def diagnose(page, action: ActionType) -> None:  # type: ignore[no-untyped-def]
    """On a failed navigation: page state now and after a further second, plus a screenshot
    (kept locally in reports/, never committed)."""
    import base64
    from pathlib import Path

    print(f"DIAGNOSTICS {action.value} now: {page.eval(DIAGNOSTICS)}")
    time.sleep(1.0)
    print(f"DIAGNOSTICS {action.value} +1 s: {page.eval(DIAGNOSTICS)}")
    shot = page.call("Page.captureScreenshot", format="png")
    out = Path("reports") / f"live_failure_{action.value}_{int(time.time())}.png"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(base64.b64decode(shot["data"]))
    print(f"DIAGNOSTICS screenshot {out}")


def test_real_youtube_shorts_end_to_end() -> None:
    executable = find_browser(prefer_extension_support=True)
    # Headless Edge sometimes never loads YouTube's video (observed Nov 2026); the controller
    # then correctly reports "still loading". A visible window placed off-screen is reliable.
    if executable is None:
        pytest.skip("Microsoft Edge not installed")
    bridge = BridgeServer(free_port(), TOKEN)
    assert bridge.start()
    controller = YouTubeShortsController(bridge)
    browser = Browser(executable, free_port(), extension=True)
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

        def shorts_in_front() -> bool:
            # A fresh Edge profile opens its own first-run tabs and may bring them to the front
            # at any time, even in the middle of an action (Brief 008 diagnostics: the Shorts
            # page was "hidden" when a navigation failed). A real user's browser does not do
            # that: close every other tab and keep the Shorts tab in front. After the consent
            # page YouTube lands on /shorts?cbrd=1 (no video id yet), so match /shorts too.
            worker.eval(
                "chrome.tabs.query({}).then(ts => {"
                " const shorts = ts.filter(t => (t.url || '').startsWith("
                "'https://www.youtube.com/shorts'));"
                " if (!shorts.length) return;"
                " const others = ts.filter(t => !shorts.includes(t)).map(t => t.id);"
                " if (others.length) chrome.tabs.remove(others);"
                " if (!shorts[0].active) chrome.tabs.update(shorts[0].id, {active: true}); })"
            )
            status = controller.status()
            return status.ready and status.signed_in is not None

        assert wait_until(shorts_in_front, timeout_s=45, step_s=0.5), (
            controller.status(),
            page.eval("location.href"),
            worker.eval(
                "chrome.tabs.query({}).then(ts => JSON.stringify(ts.map(t => "
                "[t.active, (t.url || '').slice(0, 60)])))"
            ),
        )
        assert controller.status().signed_in is False

        def run(action: ActionType):
            # Edge may bring one of its own startup tabs to the front at any time during the
            # automated session; a real user's Shorts tab stays in front.
            wait_until(shorts_in_front, timeout_s=10, step_s=0.3)
            assert wait_until(lambda: controller.check(action).ready, timeout_s=10), (
                controller.check(action),
                worker.eval(
                    "chrome.tabs.query({}).then(ts => JSON.stringify(ts.map(t => "
                    "[t.active, (t.url || '').slice(0, 60)])))"
                ),
            )
            started = time.perf_counter()
            result = controller.execute(action, uuid.uuid4().hex, 3.0)
            print(
                f"{action.value}: {result.status.value} {result.reason} {result.detail} "
                f"({(time.perf_counter() - started) * 1000:.0f} ms)"
            )
            if result.status is not ActionStatus.SUCCEEDED and action is not ActionType.LIKE_SHORT:
                diagnose(page, action)
            return result

        first_id = page.eval("location.pathname")
        assert run(ActionType.NEXT_SHORT).status is ActionStatus.SUCCEEDED
        assert page.eval("location.pathname") != first_id
        time.sleep(1.0)
        assert run(ActionType.PREVIOUS_SHORT).status is ActionStatus.SUCCEEDED
        assert page.eval("location.pathname") == first_id
        time.sleep(1.0)
        paused = run(ActionType.TOGGLE_PLAYBACK)
        assert paused.status is ActionStatus.SUCCEEDED and paused.detail == "paused"
        resumed = run(ActionType.TOGGLE_PLAYBACK)
        assert resumed.status is ActionStatus.SUCCEEDED and resumed.detail == "playing"
        like = run(ActionType.LIKE_SHORT)
        assert like.status is ActionStatus.REJECTED
        assert "not signed in" in like.reason
    finally:
        browser.close()
        bridge.stop()
