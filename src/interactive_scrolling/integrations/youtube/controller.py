"""Browser controller: YouTube Shorts and tab navigation through the companion extension.

Shorts target policy (deterministic)
------------------------------------
A browser connection is a candidate when its latest context (at most ``CONTEXT_MAX_AGE_S``
old) reports that the active tab of its last focused window is a YouTube Shorts page that is
visible and shows a video. With several candidates (e.g. Chrome and Edge both showing Shorts)
the one whose window was focused most recently is chosen; if that is undecidable the action is
rejected. A command is sent to exactly one tab and carries the expected video id, so it is
rejected if the user scrolled in the meantime.

Transient states
----------------
Right after a navigation the page briefly reports no Short (single-page transition) and the new
Short then loads for a few hundred milliseconds. These states are reported as *transient*
(``ControllerCheck.transient``) while a Shorts page was seen less than ``SHORTS_GRACE_S`` ago, so
the dispatcher can wait briefly for the new Short instead of rejecting a quick repeated
gesture (the page itself also waits, bounded, for a loading Short before clicking). At the
first Short the page reports that no previous Short exists and "previous" is refused
immediately.

Tab target policy
-----------------
Tab navigation does not need a Shorts page (the user must be able to leave Shorts and come
back), but it does need the supported browser to be the *active application*: a connection is
a candidate only if its context reports that one of its normal windows has the operating
system focus. The extension then moves to the neighbouring tab of that focused window only
(never another window, never another application, no wrap-around at the first or last tab)
and confirms the newly active tab.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from interactive_scrolling.actions.types import (
    SHORTS_ACTIONS,
    TAB_ACTIONS,
    ActionResult,
    ActionStatus,
    ActionType,
    ControllerCheck,
)
from interactive_scrolling.core.timing import NS_PER_S, Clock, now_ns
from interactive_scrolling.integrations.youtube.bridge import BridgeServer, ClientInfo
from interactive_scrolling.integrations.youtube.protocol import CommandResult

log = logging.getLogger(__name__)

CONTEXT_MAX_AGE_S = 5.0
SHORTS_GRACE_S = 1.5
"""A Shorts page seen this recently makes its absence or loading state transient."""
_OUTCOMES = {
    "succeeded": ActionStatus.SUCCEEDED,
    "no_change": ActionStatus.NO_CHANGE,
    "rejected": ActionStatus.REJECTED,
    "failed": ActionStatus.FAILED,
    "unknown": ActionStatus.UNKNOWN,
}


@dataclass(frozen=True, slots=True)
class YouTubeStatus:
    listening: bool
    bridge_error: str | None
    connections: int
    browsers: tuple[str, ...]
    ready: bool
    reason: str
    target_browser: str | None = None
    signed_in: bool | None = None
    paused: bool | None = None
    liked: bool | None = None
    browser_focused: bool | None = None
    """Whether the target browser has the operating-system focus."""

    @property
    def actively_scrolling(self) -> bool:
        """A loaded Short is playing in the focused browser (see wellbeing.sessions)."""
        return self.ready and self.browser_focused is True and self.paused is False


class YouTubeShortsController:
    def __init__(
        self,
        bridge: BridgeServer,
        on_shorts_session: Callable[[bool], None] | None = None,
        clock: Clock = now_ns,
    ) -> None:
        self.bridge = bridge
        self._clock = clock
        self._on_shorts_session = on_shorts_session
        self._session_active = False
        self._session_lock = threading.Lock()
        self._shorts_seen_ns: int | None = None
        self._arriving: tuple[str, str, int] | None = None
        """(client id, video id, time) of the Short a confirmed navigation moved to, until the
        browser reports it."""

    # ------------------------------------------------------------------ target selection

    def _target(self, action: ActionType | None = None) -> tuple[ClientInfo | None, str]:
        client, reason, _ = self._shorts_target(action)
        return client, reason

    def _recently_seen(self, now: int) -> bool:
        seen = self._shorts_seen_ns
        return seen is not None and now - seen <= int(SHORTS_GRACE_S * NS_PER_S)

    def _shorts_target(self, action: ActionType | None) -> tuple[ClientInfo | None, str, bool]:
        """(client, refusal reason, whether the refusal is transient)."""
        if not self.bridge.listening:
            return None, self.bridge.error or "browser bridge not running", False
        clients = self.bridge.clients()
        if not clients:
            return None, "browser extension not connected", False
        now = self._clock()
        recent = self._recently_seen(now)
        max_age = int(CONTEXT_MAX_AGE_S * NS_PER_S)
        fresh = [
            c
            for c in clients
            if c.context is not None and c.context_ns is not None and now - c.context_ns <= max_age
        ]
        if not fresh:
            return None, "waiting for the browser to report its state", recent
        with_shorts = [c for c in fresh if c.context.shorts is not None]  # type: ignore[union-attr]
        if not with_shorts:
            if recent:
                return None, "the Short is changing", True
            return None, "no YouTube Shorts tab is active in the browser", False
        ready = [
            c
            for c in with_shorts
            if c.context.shorts.visible and c.context.shorts.has_video  # type: ignore[union-attr]
        ]
        if not ready:
            return None, "the Shorts tab is not visible or has no video", recent
        self._shorts_seen_ns = now
        loaded = [c for c in ready if c.context.shorts.video_ready is not False]  # type: ignore[union-attr]
        if not loaded:
            return None, "the Short is still loading", True
        ready = loaded
        ready.sort(key=lambda c: c.context.focus_ts, reverse=True)  # type: ignore[union-attr]
        if len(ready) > 1 and ready[0].context.focus_ts == ready[1].context.focus_ts:  # type: ignore[union-attr]
            return None, "several browsers show Shorts; click the one to control", False
        client = ready[0]
        shorts = client.context.shorts  # type: ignore[union-attr]
        arriving = self._arriving
        if arriving is not None:
            client_id, video_id, since = arriving
            if client.client_id != client_id or shorts.video_id == video_id:
                self._arriving = None
            elif now - since <= int(SHORTS_GRACE_S * NS_PER_S):
                # The page moved on but its report has not arrived yet: a command now would
                # carry the previous Short's id and be refused by the page.
                return None, "the Short is changing", True
            else:
                self._arriving = None
        if action is ActionType.PREVIOUS_SHORT and shorts.can_previous is False:
            return None, "already at the first Short", False
        if action is ActionType.NEXT_SHORT and shorts.can_next is False:
            return None, "no next Short available", False
        return client, "", False

    def _tab_target(self) -> tuple[ClientInfo | None, str]:
        if not self.bridge.listening:
            return None, self.bridge.error or "browser bridge not running"
        clients = self.bridge.clients()
        if not clients:
            return None, "browser extension not connected"
        now = self._clock()
        max_age = int(CONTEXT_MAX_AGE_S * NS_PER_S)
        fresh = [
            c
            for c in clients
            if c.context is not None and c.context_ns is not None and now - c.context_ns <= max_age
        ]
        if not fresh:
            return None, "waiting for the browser to report its state"
        focused = [c for c in fresh if c.context.browser_focused]  # type: ignore[union-attr]
        if not focused:
            return None, "the browser is not the active window"
        focused.sort(key=lambda c: c.context.focus_ts, reverse=True)  # type: ignore[union-attr]
        if len(focused) > 1 and focused[0].context.focus_ts == focused[1].context.focus_ts:  # type: ignore[union-attr]
            return None, "several browsers report focus; click the one to control"
        client = focused[0]
        if client.protocol < 2:
            return None, "browser extension is outdated; reload it in the extensions page"
        return client, ""

    def _target_for(self, action: ActionType) -> tuple[ClientInfo | None, str]:
        if action in TAB_ACTIONS:
            return self._tab_target()
        return self._target(action)

    def check(self, action: ActionType) -> ControllerCheck:
        if action not in SHORTS_ACTIONS and action not in TAB_ACTIONS:
            return ControllerCheck(False, "action not supported by the browser controller")
        if action in TAB_ACTIONS:
            client, reason = self._tab_target()
            return ControllerCheck(client is not None, reason)
        client, reason, transient = self._shorts_target(action)
        self._update_session(client is not None or transient)
        return ControllerCheck(client is not None, reason, transient=transient)

    def status(self) -> YouTubeStatus:
        client, reason, transient = self._shorts_target(None)
        self._update_session(client is not None or transient)
        clients = self.bridge.clients()
        shorts = client.context.shorts if client and client.context else None
        return YouTubeStatus(
            listening=self.bridge.listening,
            bridge_error=self.bridge.error,
            connections=len(clients),
            browsers=tuple(sorted(c.browser for c in clients)),
            ready=client is not None,
            reason=reason,
            target_browser=client.browser if client else None,
            signed_in=shorts.signed_in if shorts else None,
            paused=shorts.paused if shorts else None,
            liked=shorts.liked if shorts else None,
            browser_focused=client.context.browser_focused if client and client.context else None,
        )

    # ------------------------------------------------------------------ execution

    def execute(self, action: ActionType, request_id: str, timeout_s: float) -> ActionResult:
        client, reason = self._target_for(action)
        if client is None:
            return ActionResult(ActionStatus.REJECTED, reason)
        video_id = None
        if action in SHORTS_ACTIONS:
            video_id = client.context.shorts.video_id  # type: ignore[union-attr]
        response = self.bridge.request(
            client.client_id, request_id, action.value, video_id, timeout_s
        )
        if isinstance(response, str):
            # No confirmation: the command may or may not have taken effect.
            return ActionResult(ActionStatus.UNKNOWN, response)
        if response.outcome == "succeeded" and response.video_id_after:
            self._arriving = (client.client_id, response.video_id_after, self._clock())
        return self._to_result(response)

    @staticmethod
    def _to_result(response: CommandResult) -> ActionResult:
        status = _OUTCOMES[response.outcome]
        detail = ""
        if response.tab_index_after is not None and response.tab_count is not None:
            detail = f"tab {response.tab_index_after + 1} of {response.tab_count} active"
        elif response.video_id_after and response.video_id_before:
            detail = "active Short changed"
        elif response.paused is not None:
            detail = "paused" if response.paused else "playing"
        elif response.liked:
            detail = "liked"
        return ActionResult(status, response.reason, detail)

    def cancel_all(self) -> None:
        self.bridge.cancel_all()

    # ------------------------------------------------------------------ sessions

    def refresh(self) -> None:
        """Re-evaluate the Shorts session state (called on bridge changes and periodically)."""
        client, _, transient = self._shorts_target(None)
        self._update_session(client is not None or transient)

    def _update_session(self, active: bool) -> None:
        with self._session_lock:
            if active == self._session_active:
                return
            self._session_active = active
        if self._on_shorts_session is not None:
            try:
                self._on_shorts_session(active)
            except Exception:
                log.exception("Shorts session listener failed")
