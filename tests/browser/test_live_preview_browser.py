"""The real extension's live preview in Microsoft Edge, against the local Shorts fixture.

The capture is started with the Chromium test switch that stands in for the user's click on
the extension icon (``TAB_CAPTURE_TEST_ARGS``); everything after that - capture, cropping,
encoding, the loopback transport, privacy rules and preview-tab control - is the real code.

The fixture's video shows the page's wall clock as a black/white bit grid (``clock=1``), so the
received frames give a real page-to-app delay: page drawing, the browser's compositing and
capture, cropping, JPEG encoding and the transfer (not the app's painting).
"""

from __future__ import annotations

import socket
import statistics
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
import pytest

from interactive_scrolling.actions.types import ActionStatus, ActionType
from interactive_scrolling.integrations.youtube.bridge import BridgeServer
from interactive_scrolling.integrations.youtube.controller import YouTubeShortsController
from tests.browser_helpers import (
    TAB_CAPTURE_TEST_ARGS,
    Browser,
    Session,
    find_browser,
    serve_youtube_fixture,
)
from tests.helpers import wait_until

pytestmark = pytest.mark.browser

FIXTURE = (Path(__file__).resolve().parents[1] / "fixtures" / "youtube_shorts.html").read_bytes()
TOKEN = "fixture-preview-token-0123456789"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def stack() -> Iterator[tuple[Browser, BridgeServer, YouTubeShortsController, Session, Session]]:
    executable = find_browser(prefer_extension_support=True)
    if executable is None:
        pytest.skip("Microsoft Edge not installed (needed to load the unpacked extension)")
    port = free_port()
    bridge = BridgeServer(port, TOKEN)
    assert bridge.start()
    controller = YouTubeShortsController(bridge)
    browser = Browser(executable, free_port(), extension=True, extra_args=TAB_CAPTURE_TEST_ARGS)
    try:
        worker = browser.extension_worker()
        worker.eval(
            f"chrome.storage.local.set({{token: '{TOKEN}', port: {port}}}).then(() => connect())"
        )
        assert wait_until(lambda: len(bridge.clients()) == 1, timeout_s=10)
        page = browser.new_tab()
        serve_youtube_fixture(page, {"/shorts/": (FIXTURE, "text/html")})
        page.call("Page.navigate", url="https://www.youtube.com/shorts/aaaaaaaaaa1?clock=1")
        page.wait_for("document.readyState === 'complete' && !!document.querySelector('video')")
        assert wait_until(lambda: controller.status().ready, timeout_s=10), controller.status()
        yield browser, bridge, controller, page, worker
    finally:
        browser.close()
        bridge.stop()


def start_preview(stack) -> None:  # type: ignore[no-untyped-def]
    browser, bridge, controller, page, worker = stack
    if bridge.preview.status().connected:
        return
    browser.activate(page)
    tab_id = controller.status() and bridge.clients()[0].context.shorts.tab_id
    result = worker.eval(f"startPreview({tab_id})")
    assert result == {"ok": True}, result
    assert wait_until(lambda: bridge.preview.latest() is not None, timeout_s=10)


def decode_clock(jpeg: bytes) -> int | None:
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    h, w = image.shape
    value = 0
    for bit in range(16):
        cx = int(((bit % 4) + 0.5) * w / 4)
        cy = int(((bit // 4) + 0.5) * h / 4)
        patch = image[cy - 3 : cy + 4, cx - 3 : cx + 4]
        level = float(patch.mean())
        if 60 < level < 195:
            return None  # a block in transition: not a clean reading
        if level >= 195:
            value |= 1 << bit
    return value


def test_preview_streams_only_the_video_area_with_a_measured_delay(stack) -> None:
    _, bridge, _, _, _ = stack
    start_preview(stack)
    frames, delays = 0, []
    last = None
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        frame = bridge.preview.latest()
        if frame is not None and frame is not last:
            last = frame
            frames += 1
            arrived = time.time() * 1000
            clock = decode_clock(frame.jpeg)
            if clock is not None:
                delays.append((int(arrived) - clock) % 65536)
        time.sleep(0.003)
    image = cv2.imdecode(np.frombuffer(last.jpeg, np.uint8), cv2.IMREAD_COLOR)
    h, w = image.shape[:2]
    # Cropped to the 360x640 video element: the Short's 9:16 shape, not the whole page.
    assert abs(w / h - 360 / 640) < 0.03, (w, h)
    status = bridge.preview.status()
    print(
        f"preview: {frames / 4.0:.1f} fps received, page-to-app delay median "
        f"{statistics.median(delays):.0f} ms (n={len(delays)}), transport "
        f"{status.transport_ms:.1f} ms, frame {w}x{h}"
    )
    assert frames / 4.0 >= 15
    assert len(delays) >= 10
    assert statistics.median(delays) < 250


def test_preview_tab_is_controlled_while_the_app_is_in_front(stack) -> None:
    browser, bridge, controller, page, _ = stack
    start_preview(stack)
    other = browser.new_tab()  # the user switches to another tab in the browser
    try:
        controller.app_in_front = True
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready, timeout_s=5), (
            controller.check(ActionType.NEXT_SHORT)
        )
        result = controller.execute(ActionType.NEXT_SHORT, uuid.uuid4().hex, 3.0)
        assert result.status is ActionStatus.SUCCEEDED, result
        assert page.eval("location.pathname") == "/shorts/bbbbbbbbbb2"
        # Tab switching still needs the browser to be the active window.
        controller.app_in_front = True
        tab = controller.check(ActionType.PREVIOUS_BROWSER_TAB)
        assert tab.ready == bool(bridge.clients()[0].context.browser_focused)
    finally:
        controller.app_in_front = False
        browser.close_tab(other)
        browser.activate(page)


def test_leaving_shorts_hides_the_preview_and_returning_resumes(stack) -> None:
    _browser, bridge, controller, page, _ = stack
    start_preview(stack)
    page.call("Page.navigate", url="https://www.youtube.com/feed/subscriptions")
    assert wait_until(lambda: bridge.preview.status().state == "hidden", timeout_s=5)
    assert bridge.preview.latest() is None
    controller.app_in_front = True
    try:
        # The browser reports the navigation within its next context message; the extension
        # itself refuses a command for a tab that no longer shows a Short in the meantime.
        # Transient refusals ("the Short is changing") come first during the grace period.
        assert wait_until(
            lambda: (
                controller.check(ActionType.NEXT_SHORT).reason
                == "the previewed tab is not showing a YouTube Short"
            ),
            timeout_s=5,
        ), controller.check(ActionType.NEXT_SHORT)
    finally:
        controller.app_in_front = False
    page.call("Page.navigate", url="https://www.youtube.com/shorts/aaaaaaaaaa1?clock=1")
    assert wait_until(lambda: bridge.preview.latest() is not None, timeout_s=10)


def test_stopping_the_preview_revokes_the_tab(stack) -> None:
    _browser, bridge, _controller, _page, _worker = stack
    start_preview(stack)
    tab_id = bridge.clients()[0].context.preview.tab_id
    assert bridge.stop_preview()
    assert wait_until(lambda: not bridge.preview.status().connected, timeout_s=5)
    assert wait_until(lambda: bridge.clients()[0].context.preview is None, timeout_s=5)
    client = bridge.clients()[0]
    refused = bridge.request(client.client_id, uuid.uuid4().hex, "next_short", None, 2.0, tab_id)
    assert refused.outcome == "rejected"
    assert refused.reason == "not the tab shown in the live preview"


def test_closing_the_previewed_tab_ends_the_preview(stack) -> None:
    browser, bridge, _controller, page, worker = stack
    extra = browser.new_tab()
    serve_youtube_fixture(extra, {"/shorts/": (FIXTURE, "text/html")})
    extra.call("Page.navigate", url="https://www.youtube.com/shorts/cccccccccc3")
    extra.wait_for("document.readyState === 'complete' && !!document.querySelector('video')")
    browser.activate(extra)
    assert wait_until(
        lambda: (
            (bridge.clients()[0].context.shorts or None) is not None
            and bridge.clients()[0].context.shorts.video_id == "cccccccccc3"
        ),
        timeout_s=10,
    )
    tab_id = bridge.clients()[0].context.shorts.tab_id
    assert worker.eval(f"startPreview({tab_id})") == {"ok": True}
    assert wait_until(lambda: bridge.preview.latest() is not None, timeout_s=10)
    browser.close_tab(extra)
    assert wait_until(lambda: not bridge.preview.status().connected, timeout_s=5)
    assert wait_until(lambda: bridge.clients()[0].context.preview is None, timeout_s=5)
    browser.activate(page)
