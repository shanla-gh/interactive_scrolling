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
            # Edge may open its own startup tabs on top of ours; keep the Shorts tab in front
            # the way a user would. Sign-in status is known once the masthead has rendered.
            worker.eval(
                "chrome.tabs.query({}).then(ts => ts.filter(t => (t.url || '').startsWith("
                "'https://www.youtube.com/shorts/'))).then(ts => ts.length && !ts[0].active && "
                "chrome.tabs.update(ts[0].id, {active: true}))"
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
            assert wait_until(lambda: controller.check(action).ready, timeout_s=10)
            started = time.perf_counter()
            result = controller.execute(action, uuid.uuid4().hex, 3.0)
            print(
                f"{action.value}: {result.status.value} {result.reason} {result.detail} "
                f"({(time.perf_counter() - started) * 1000:.0f} ms)"
            )
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
