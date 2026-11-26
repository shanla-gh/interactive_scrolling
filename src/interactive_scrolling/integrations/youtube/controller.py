"""YouTube Shorts controller: context validation and confirmed execution via the extension.

Target policy (deterministic)
-----------------------------
A browser connection is a candidate when its latest context (at most ``CONTEXT_MAX_AGE_S``
old) reports that the active tab of its last focused window is a YouTube Shorts page that is
visible and shows a video. With several candidates (e.g. Chrome and Edge both showing Shorts)
the one whose window was focused most recently is chosen; if that is undecidable the action is
rejected. A command is sent to exactly one tab and carries the expected video id, so it is
rejected if the user scrolled in the meantime.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from interactive_scrolling.actions.types import (
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

    # ------------------------------------------------------------------ target selection

    def _target(self) -> tuple[ClientInfo | None, str]:
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
        with_shorts = [c for c in fresh if c.context.shorts is not None]  # type: ignore[union-attr]
        if not with_shorts:
            return None, "no YouTube Shorts tab is active in the browser"
        ready = [
            c
            for c in with_shorts
            if c.context.shorts.visible and c.context.shorts.has_video  # type: ignore[union-attr]
        ]
        if not ready:
            return None, "the Shorts tab is not visible or has no video"
        loaded = [c for c in ready if c.context.shorts.video_ready is not False]  # type: ignore[union-attr]
        if not loaded:
            return None, "the Short is still loading"
        ready = loaded
        ready.sort(key=lambda c: c.context.focus_ts, reverse=True)  # type: ignore[union-attr]
        if len(ready) > 1 and ready[0].context.focus_ts == ready[1].context.focus_ts:  # type: ignore[union-attr]
            return None, "several browsers show Shorts; click the one to control"
        return ready[0], ""

    def check(self, action: ActionType) -> ControllerCheck:
        if not action.available:
            return ControllerCheck(False, "action not supported by the YouTube controller")
        client, reason = self._target()
        self._update_session(client is not None)
        return ControllerCheck(client is not None, reason)

    def status(self) -> YouTubeStatus:
        client, reason = self._target()
        self._update_session(client is not None)
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
        )

    # ------------------------------------------------------------------ execution

    def execute(self, action: ActionType, request_id: str, timeout_s: float) -> ActionResult:
        client, reason = self._target()
        if client is None:
            return ActionResult(ActionStatus.REJECTED, reason)
        shorts = client.context.shorts  # type: ignore[union-attr]
        response = self.bridge.request(
            client.client_id, request_id, action.value, shorts.video_id, timeout_s
        )
        if isinstance(response, str):
            # No confirmation: the command may or may not have taken effect.
            return ActionResult(ActionStatus.UNKNOWN, response)
        return self._to_result(response)

    @staticmethod
    def _to_result(response: CommandResult) -> ActionResult:
        status = _OUTCOMES[response.outcome]
        detail = ""
        if response.video_id_after and response.video_id_before:
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
        client, _ = self._target()
        self._update_session(client is not None)

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
