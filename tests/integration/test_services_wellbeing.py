"""Activity accounting and the gesture-scrolling pause wired through the services."""

from __future__ import annotations

import time

from interactive_scrolling.actions.dispatcher import ActionDispatcher
from interactive_scrolling.actions.types import (
    ActionResult,
    ActionStatus,
    ActionType,
    ControllerCheck,
    ControlMode,
)
from interactive_scrolling.config.settings import WellbeingSettings
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.gestures.types import GestureEvent, GestureType
from interactive_scrolling.integrations.youtube.controller import YouTubeStatus
from interactive_scrolling.services import ControlServices
from interactive_scrolling.storage.analytics import AnalyticsStore
from interactive_scrolling.storage.settings_store import UserSettings
from interactive_scrolling.vision.landmarks import Handedness
from tests.helpers import wait_until


class Browser:
    """Fake controller: reports a status and executes everything successfully."""

    def __init__(self) -> None:
        self.playing = True
        self.executed: list[ActionType] = []

    def status(self) -> YouTubeStatus:
        return YouTubeStatus(
            listening=True,
            bridge_error=None,
            connections=1,
            browsers=("edge",),
            ready=True,
            reason="",
            target_browser="edge",
            paused=not self.playing,
            browser_focused=True,
        )

    def check(self, action: ActionType) -> ControllerCheck:
        return ControllerCheck(True)

    def execute(self, action: ActionType, request_id: str, timeout_s: float) -> ActionResult:
        self.executed.append(action)
        return ActionResult(ActionStatus.SUCCEEDED)

    def cancel_all(self) -> None:
        pass


class Clock:
    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now


def make(tmp_path, wellbeing: WellbeingSettings | None = None):
    clock = Clock()
    browser = Browser()
    analytics = AnalyticsStore(tmp_path / "a.sqlite3", wall_clock=clock)
    services = ControlServices(
        engine=GestureEngine(),
        dispatcher=ActionDispatcher(browser),
        user_settings=UserSettings(wellbeing=wellbeing or WellbeingSettings()),
        analytics=analytics,
        controller=browser,  # type: ignore[arg-type]
        wall_clock=clock,
    )
    return services, browser, clock


def event(gesture: GestureType) -> GestureEvent:
    return GestureEvent(gesture, time.perf_counter_ns(), 1, Handedness.RIGHT)


def test_playing_short_in_the_focused_browser_counts_as_scrolling(tmp_path) -> None:
    services, browser, clock = make(tmp_path)
    for _ in range(90):
        services.activity_step(refresh_reports=False)
        clock.now += 1.0
    browser.playing = False  # a paused video is not scrolling
    for _ in range(30):
        services.activity_step(refresh_reports=False)
        clock.now += 1.0
    services.analytics.flush()
    services.refresh_reports()
    assert 88 <= services.report.scrolling_s <= 91
    assert services.report.session_count == 1
    assert 88 <= services.current_session_s() <= 91
    services.shutdown()


def test_reaching_the_limit_pauses_only_gesture_scrolling_and_the_user_can_resume(
    tmp_path,
) -> None:
    settings = WellbeingSettings(enabled=True, session_limit_min=1, pause_at_limit=True)
    services, browser, clock = make(tmp_path, settings)
    notices = []
    services.notice_listeners.append(notices.append)
    for _ in range(65):
        services.activity_step(refresh_reports=False)
        clock.now += 1.0
    assert any(n.title == "Session limit reached" for n in notices)
    assert services.wellbeing.scrolling_paused
    dispatcher = services.dispatcher
    dispatcher.set_mode(ControlMode.LIVE_CONTROL)
    refused = dispatcher.submit(event(GestureType.INDEX_SWIPE_UP))
    assert refused.status is ActionStatus.REJECTED and "session limit" in refused.reason
    liked = dispatcher.submit(event(GestureType.HALF_HEART))  # likes keep working
    assert wait_until(lambda: ActionType.LIKE_SHORT in browser.executed)
    assert liked.status is ActionStatus.QUEUED
    services.pause_scrolling(False)
    assert wait_until(lambda: not dispatcher._busy)
    accepted = dispatcher.submit(event(GestureType.INDEX_SWIPE_UP))
    assert accepted.status is ActionStatus.QUEUED
    assert wait_until(lambda: ActionType.NEXT_SHORT in browser.executed)
    services.shutdown()
