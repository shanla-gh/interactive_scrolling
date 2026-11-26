"""The real browser extension in Microsoft Edge, connected to the real bridge and controller.

Requests to https://www.youtube.com are intercepted and answered with a local fixture page
that reproduces the Shorts page structure, so these tests run offline and never touch a real
account. ``tests/live/`` covers the real website (opt-in).
"""

from __future__ import annotations

import socket
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from interactive_scrolling.actions.types import ActionStatus, ActionType
from interactive_scrolling.integrations.youtube.bridge import BridgeServer
from interactive_scrolling.integrations.youtube.controller import YouTubeShortsController
from tests.browser_helpers import Browser, Session, find_browser, serve_youtube_fixture
from tests.helpers import wait_until

pytestmark = pytest.mark.browser

FIXTURE = (Path(__file__).resolve().parents[1] / "fixtures" / "youtube_shorts.html").read_bytes()
TOKEN = "fixture-pairing-token-0123456789"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def stack() -> Iterator[tuple[Browser, BridgeServer, YouTubeShortsController, Session]]:
    executable = find_browser(prefer_extension_support=True)
    if executable is None:
        pytest.skip("Microsoft Edge not installed (needed to load the unpacked extension)")
    port = free_port()
    bridge = BridgeServer(port, TOKEN)
    assert bridge.start()
    controller = YouTubeShortsController(bridge)
    browser = Browser(executable, free_port(), extension=True)
    try:
        worker = browser.extension_worker()
        worker.eval(
            f"chrome.storage.local.set({{token: '{TOKEN}', port: {port}}}).then(() => connect())"
        )
        assert wait_until(lambda: len(bridge.clients()) == 1, timeout_s=10)
        page = browser.new_tab()
        serve_youtube_fixture(page, {"/shorts/": (FIXTURE, "text/html")})
        yield browser, bridge, controller, page
    finally:
        browser.close()
        bridge.stop()


def open_short(page: Session, controller: YouTubeShortsController, query: str = "") -> None:
    page.call("Page.navigate", url=f"https://www.youtube.com/shorts/aaaaaaaaaa1{query}")
    page.wait_for("document.readyState === 'complete' && !!document.querySelector('video')")
    assert wait_until(
        lambda: (
            controller.status().ready and controller.status().signed_in is ("signed_in=1" in query)
        ),
        timeout_s=10,
    ), controller.status()


def run(controller: YouTubeShortsController, action: ActionType):
    check = controller.check(action)
    assert check.ready, check.reason
    return controller.execute(action, uuid.uuid4().hex, 3.0)


def seen_id(bridge: BridgeServer) -> str | None:
    (client,) = bridge.clients()
    return client.context.shorts.video_id if client.context and client.context.shorts else None


def current_id(page: Session) -> str:
    return page.eval("location.pathname.split('/')[2]")


def test_extension_connects_with_fixed_id_and_reports_context(stack) -> None:
    _, bridge, controller, page = stack
    open_short(page, controller, "?signed_in=1")
    (client,) = bridge.clients()
    assert client.browser == "edge"
    assert client.context.shorts.video_id == "aaaaaaaaaa1"
    assert client.context.shorts.visible


def test_next_and_previous_navigate_exactly_one_short(stack) -> None:
    _, bridge, controller, page = stack
    open_short(page, controller, "?signed_in=1")
    result = run(controller, ActionType.NEXT_SHORT)
    assert result.status is ActionStatus.SUCCEEDED
    assert current_id(page) == "bbbbbbbbbb2"
    # Commands carry the Short the app last saw; wait until the new one has been reported,
    # otherwise the extension (correctly) refuses the stale command.
    assert wait_until(lambda: seen_id(bridge) == "bbbbbbbbbb2", timeout_s=5)
    result = run(controller, ActionType.PREVIOUS_SHORT)
    assert result.status is ActionStatus.SUCCEEDED
    assert current_id(page) == "aaaaaaaaaa1"


def test_previous_on_first_short_is_rejected(stack) -> None:
    _, _, controller, page = stack
    open_short(page, controller, "?signed_in=1")
    result = run(controller, ActionType.PREVIOUS_SHORT)
    assert result.status is ActionStatus.REJECTED
    assert "first" in result.reason
    assert current_id(page) == "aaaaaaaaaa1"


def test_navigation_without_effect_is_reported_failed_not_succeeded(stack) -> None:
    _, _, controller, page = stack
    open_short(page, controller, "?signed_in=1&broken_nav=1")
    result = run(controller, ActionType.NEXT_SHORT)
    assert result.status is ActionStatus.FAILED
    assert "did not change" in result.reason


def test_like_sets_liked_state_and_is_confirmed(stack) -> None:
    _, _, controller, page = stack
    open_short(page, controller, "?signed_in=1")
    result = run(controller, ActionType.LIKE_SHORT)
    assert result.status is ActionStatus.SUCCEEDED
    assert (
        page.eval(
            "document.querySelector('like-button-view-model button').getAttribute('aria-pressed')"
        )
        == "true"
    )


def test_like_never_unlikes_an_already_liked_short(stack) -> None:
    _, _, controller, page = stack
    open_short(page, controller, "?signed_in=1&liked=aaaaaaaaaa1")
    result = run(controller, ActionType.LIKE_SHORT)
    assert result.status is ActionStatus.NO_CHANGE
    assert result.reason == "already liked"
    assert (
        page.eval(
            "document.querySelector('like-button-view-model button').getAttribute('aria-pressed')"
        )
        == "true"
    )


def test_like_when_signed_out_is_rejected_without_clicking(stack) -> None:
    _, _, controller, page = stack
    open_short(page, controller)
    page.eval(
        "window.__likeClicks = 0; document.querySelector('like-button-view-model button')"
        ".addEventListener('click', () => window.__likeClicks++)"
    )
    result = run(controller, ActionType.LIKE_SHORT)
    assert result.status is ActionStatus.REJECTED
    assert "not signed in" in result.reason
    assert page.eval("window.__likeClicks") == 0


def test_toggle_playback_pauses_then_resumes(stack) -> None:
    _, _, controller, page = stack
    open_short(page, controller, "?signed_in=1")
    page.wait_for("!document.querySelector('#shorts-player video').paused")
    first = run(controller, ActionType.TOGGLE_PLAYBACK)
    assert first.status is ActionStatus.SUCCEEDED and first.detail == "paused"
    assert page.eval("document.querySelector('#shorts-player video').paused") is True
    second = run(controller, ActionType.TOGGLE_PLAYBACK)
    assert second.status is ActionStatus.SUCCEEDED and second.detail == "playing"


def test_non_shorts_page_is_not_a_valid_context(stack) -> None:
    """Regression: navigating away from Shorts left the tab's stale Shorts state in the
    extension, so the app still considered the tab a valid target."""
    _, _, controller, page = stack
    page.call("Page.navigate", url="https://www.youtube.com/watch?v=abcdefghijk")
    # Transitional states (e.g. "no video" while the old page unloads) may appear first.
    assert wait_until(
        lambda: "no YouTube Shorts tab" in controller.check(ActionType.NEXT_SHORT).reason,
        timeout_s=6,
    )


def test_command_for_a_different_short_is_rejected_by_the_extension(stack) -> None:
    _, bridge, controller, page = stack
    open_short(page, controller, "?signed_in=1")
    (client,) = bridge.clients()
    response = bridge.request(client.client_id, uuid.uuid4().hex, "next_short", "zzzzzzzzzz9", 2.0)
    assert response.outcome == "rejected"
    assert "changed" in response.reason
    assert current_id(page) == "aaaaaaaaaa1"


def test_extension_disconnect_makes_context_unavailable(stack) -> None:
    browser, bridge, controller, page = stack
    open_short(page, controller, "?signed_in=1")
    worker = browser.extension_worker()
    worker.eval(
        "chrome.storage.local.set({token: 'wrong-token-xxxxxxxxxxxx'})"
        ".then(() => { socket && socket.close(); })"
    )
    assert wait_until(lambda: not bridge.clients(), timeout_s=5)
    assert controller.check(ActionType.NEXT_SHORT).reason == "browser extension not connected"
    # A wrong pairing code is refused.
    time.sleep(1.0)
    assert not bridge.clients()
    assert bridge.rejected_connections >= 1
    worker.eval(f"chrome.storage.local.set({{token: '{TOKEN}'}}).then(() => connect())")
    assert wait_until(lambda: len(bridge.clients()) == 1, timeout_s=20)
