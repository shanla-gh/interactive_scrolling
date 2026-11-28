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

from interactive_scrolling.actions.dispatcher import ActionDispatcher
from interactive_scrolling.actions.types import ActionRecord, ActionStatus, ActionType, ControlMode
from interactive_scrolling.gestures.types import GestureEvent, GestureType
from interactive_scrolling.integrations.youtube.bridge import BridgeServer
from interactive_scrolling.integrations.youtube.controller import YouTubeShortsController
from interactive_scrolling.vision.landmarks import Handedness
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
    # Wait for the report of *this* page: the previous test's page (possibly at the last Short,
    # where next is unavailable) may still be the latest context for a moment (Brief 009: an
    # intermittent 'no next Short available' on CI).
    assert wait_until(
        lambda: (
            controller.status().ready
            and controller.status().signed_in is ("signed_in=1" in query)
            and _seen_short(controller) == "aaaaaaaaaa1"
            and _seen_can_next(controller) is not False
        ),
        timeout_s=10,
    ), controller.status()


def _context_shorts(controller: YouTubeShortsController):  # type: ignore[no-untyped-def]
    clients = controller.bridge.clients()
    context = clients[0].context if clients else None
    return context.shorts if context else None


def _seen_short(controller: YouTubeShortsController) -> str | None:
    shorts = _context_shorts(controller)
    return shorts.video_id if shorts else None


def _seen_can_next(controller: YouTubeShortsController) -> bool | None:
    shorts = _context_shorts(controller)
    return shorts.can_next if shorts else None


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


@pytest.mark.parametrize("style", ["", "&nav_style=disabled"])
def test_previous_on_first_short_is_rejected_immediately(stack, style) -> None:
    """Regression (Director test, Nov 2026): on the live site the previous button at the first
    Short is hidden but not disabled; clicking it did nothing and every attempt waited 3 s
    before failing."""
    _, _, controller, page = stack
    open_short(page, controller, "?signed_in=1" + style)
    check = controller.check(ActionType.PREVIOUS_SHORT)
    assert not check.ready and check.reason == "already at the first Short"
    # The page refuses it as well if a command arrives anyway (e.g. an older app).
    started = time.perf_counter()
    result = controller.execute(ActionType.PREVIOUS_SHORT, uuid.uuid4().hex, 3.0)
    assert result.status is ActionStatus.REJECTED
    assert result.reason == "already at the first Short"
    assert time.perf_counter() - started < 0.5
    assert current_id(page) == "aaaaaaaaaa1"


def test_rapid_navigation_through_the_dispatcher_executes_every_gesture(stack) -> None:
    """Regression (live probe, Nov 2026): a gesture right after a navigation was rejected with
    "no YouTube Shorts tab is active" while the page reported the new Short."""
    _, _, controller, page = stack
    open_short(page, controller, "?signed_in=1&load_ms=300")
    records: list[ActionRecord] = []
    dispatcher = ActionDispatcher(controller)
    dispatcher.add_record_listener(records.append)
    dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    try:
        outcomes = []
        for _ in range(2):
            gesture = GestureEvent(
                GestureType.INDEX_SWIPE_UP, time.perf_counter_ns(), 1, Handedness.RIGHT
            )
            record = dispatcher.submit(gesture, action=ActionType.NEXT_SHORT)

            def done(rid=record.record_id):
                return [r for r in records if r.record_id == rid and r.status.final]

            assert wait_until(done, timeout_s=6)
            outcomes.append((done()[-1].status, done()[-1].reason))
        assert outcomes == [(ActionStatus.SUCCEEDED, ""), (ActionStatus.SUCCEEDED, "")]
        assert current_id(page) == "cccccccccc3"
        check = controller.check(ActionType.NEXT_SHORT)
        assert wait_until(
            lambda: controller.check(ActionType.NEXT_SHORT).reason == "no next Short available"
        ), check
    finally:
        dispatcher.shutdown()


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
    # A wrong pairing code is refused. The extension retries after its close handler's delay
    # or its 2 s heartbeat, whichever comes first, so wait for the attempt instead of sleeping.
    assert wait_until(lambda: bridge.rejected_connections >= 1, timeout_s=8)
    assert not bridge.clients()
    worker.eval(f"chrome.storage.local.set({{token: '{TOKEN}'}}).then(() => connect())")
    assert wait_until(lambda: len(bridge.clients()) == 1, timeout_s=20)


# ---------------------------------------------------------------------- tab navigation


def active_tab_index(worker: Session) -> int:
    return worker.eval(
        "chrome.windows.getLastFocused({windowTypes: ['normal'], populate: true})"
        ".then(w => w.tabs.find(t => t.active).index)"
    )


def tab_count(worker: Session) -> int:
    return worker.eval(
        "chrome.windows.getLastFocused({windowTypes: ['normal'], populate: true})"
        ".then(w => w.tabs.length)"
    )


def test_tab_navigation_leaves_and_returns_to_shorts(stack) -> None:
    browser, _bridge, controller, page = stack
    worker = browser.extension_worker()
    browser.activate(page)
    open_short(page, controller, "?signed_in=1")
    other = browser.new_tab()  # a non-YouTube tab to the right of the Shorts tab
    try:
        browser.activate(page)
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready, timeout_s=10)
        start = active_tab_index(worker)
        count = tab_count(worker)
        assert start == count - 2

        # Right: leave Shorts for the next tab.
        assert wait_until(lambda: controller.check(ActionType.NEXT_BROWSER_TAB).ready)
        result = controller.execute(ActionType.NEXT_BROWSER_TAB, uuid.uuid4().hex, 2.0)
        assert result.status is ActionStatus.SUCCEEDED, result
        assert active_tab_index(worker) == start + 1
        assert wait_until(lambda: not controller.check(ActionType.NEXT_SHORT).ready)

        # At the last tab: no wrap-around.
        result = controller.execute(ActionType.NEXT_BROWSER_TAB, uuid.uuid4().hex, 2.0)
        assert result.status is ActionStatus.REJECTED
        assert result.reason == "already at the last tab"
        assert active_tab_index(worker) == start + 1

        # Left: back to the Shorts tab, where Shorts control is available again.
        result = controller.execute(ActionType.PREVIOUS_BROWSER_TAB, uuid.uuid4().hex, 2.0)
        assert result.status is ActionStatus.SUCCEEDED, result
        assert active_tab_index(worker) == start
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready, timeout_s=10)
    finally:
        other.close()
        browser.close_tab(other)
        browser.activate(page)


def test_first_tab_is_not_wrapped_around(stack) -> None:
    browser, _bridge, controller, page = stack
    worker = browser.extension_worker()
    first = worker.eval(
        "chrome.windows.getLastFocused({windowTypes: ['normal'], populate: true})"
        ".then(w => chrome.tabs.update(w.tabs[0].id, {active: true})).then(() => true)"
    )
    assert first
    assert active_tab_index(worker) == 0
    assert wait_until(lambda: controller.check(ActionType.PREVIOUS_BROWSER_TAB).ready)
    result = controller.execute(ActionType.PREVIOUS_BROWSER_TAB, uuid.uuid4().hex, 2.0)
    assert result.status is ActionStatus.REJECTED
    assert result.reason == "already at the first tab"
    assert active_tab_index(worker) == 0
    browser.activate(page)


def test_tab_navigation_stays_inside_the_focused_window(stack) -> None:
    browser, _bridge, controller, page = stack
    worker = browser.extension_worker()
    browser.activate(page)
    before = worker.eval(
        "chrome.windows.getAll({populate: true}).then(ws => ws.map(w => "
        "[w.id, w.tabs.findIndex(t => t.active)]))"
    )
    window = browser.new_window()
    try:
        assert wait_until(lambda: controller.check(ActionType.PREVIOUS_BROWSER_TAB).ready)
        focused = worker.eval(
            "chrome.windows.getLastFocused({windowTypes: ['normal']}).then(w => w.id)"
        )
        # The new window has a single tab: nothing to switch to, and the other window's active
        # tab must not change.
        result = controller.execute(ActionType.PREVIOUS_BROWSER_TAB, uuid.uuid4().hex, 2.0)
        assert result.status is ActionStatus.REJECTED
        after = worker.eval(
            "chrome.windows.getAll({populate: true}).then(ws => ws.map(w => "
            "[w.id, w.tabs.findIndex(t => t.active)]))"
        )
        for window_id, index in before:
            assert [window_id, index] in after
        assert focused not in [w for w, _ in before]
    finally:
        browser.close_tab(window)
        browser.activate(page)
