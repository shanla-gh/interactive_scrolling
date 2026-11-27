"""The Director's five failed actions and the quick-repeat rejections (Brief 004).

* At the first Short of a feed YouTube hides the previous button without disabling it; every
  "previous" waited 3 s and failed. The page now reports can_previous and the controller
  refuses at once.
* After a navigation the page state was briefly missing (and the app still held the previous
  Short's id), so a quick next gesture was refused; these states are now transient and waited
  for by the dispatcher.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from interactive_scrolling.actions.types import ActionStatus, ActionType
from interactive_scrolling.integrations.youtube.bridge import BridgeServer
from interactive_scrolling.integrations.youtube.controller import YouTubeShortsController
from tests.helpers import wait_until
from tests.integration.test_youtube_bridge import TOKEN, FakeExtension, execute, free_port


@pytest.fixture
def server() -> Iterator[tuple[BridgeServer, YouTubeShortsController, list[bool]]]:
    sessions: list[bool] = []
    bridge = BridgeServer(free_port(), TOKEN)
    controller = YouTubeShortsController(bridge, on_shorts_session=sessions.append)
    bridge.set_change_listener(controller.refresh)
    assert bridge.start()
    yield bridge, controller, sessions
    bridge.stop()


def test_previous_at_the_first_short_is_refused_immediately(server) -> None:
    """Regression (Director test, Nov 2026): at the first Short of a feed YouTube hides the
    previous button without disabling it; every "previous" waited 3 s and failed."""
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    try:
        ext.context(can_previous=False)
        assert wait_until(
            lambda: (
                controller.check(ActionType.PREVIOUS_SHORT).reason == "already at the first Short"
            )
        )
        check = controller.check(ActionType.PREVIOUS_SHORT)
        assert not check.ready and not check.transient
        assert controller.check(ActionType.NEXT_SHORT).ready
        ext.context(can_previous=True)
        assert wait_until(lambda: controller.check(ActionType.PREVIOUS_SHORT).ready)
    finally:
        ext.close()


def test_short_disappearing_during_navigation_is_transient(server) -> None:
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    try:
        ext.context()
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready)
        ext.context(shorts=False)
        assert wait_until(lambda: not controller.check(ActionType.NEXT_SHORT).ready)
        check = controller.check(ActionType.NEXT_SHORT)
        assert check.transient and check.reason == "the Short is changing"
        ext.context(loaded=False)
        assert wait_until(
            lambda: controller.check(ActionType.LIKE_SHORT).reason == "the Short is still loading"
        )
        assert controller.check(ActionType.LIKE_SHORT).transient
    finally:
        ext.close()


def test_command_after_a_navigation_waits_for_the_new_short_report(server) -> None:
    """Regression (fixture test of quick repeated gestures): right after a confirmed
    navigation the app still held the previous Short's id; the next command carried it and
    the page refused it as "the active Short changed before the action"."""
    bridge, controller, _ = server
    ext = FakeExtension(bridge.port)
    try:
        ext.context()
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready)
        assert execute(controller).status is ActionStatus.SUCCEEDED  # -> bcdefghijkl
        check = controller.check(ActionType.NEXT_SHORT)
        assert not check.ready and check.transient
        assert check.reason == "the Short is changing"
        ext.context(video_id="bcdefghijkl")
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready)
    finally:
        ext.close()


def test_shorts_session_does_not_end_while_the_short_changes(server) -> None:
    """The Director's log showed the Shorts session ending and starting again around every
    navigation; a briefly missing page state is transient and keeps the session."""
    bridge, controller, sessions = server
    ext = FakeExtension(bridge.port)
    try:
        ext.context()
        assert wait_until(lambda: sessions == [True])
        ext.context(shorts=False)
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).transient)
        controller.refresh()
        ext.context(video_id="bcdefghijkl")
        assert wait_until(lambda: controller.check(ActionType.NEXT_SHORT).ready)
        assert sessions == [True]
    finally:
        ext.close()
