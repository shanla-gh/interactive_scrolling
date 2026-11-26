"""Composition of the gesture-control services (no Qt).

``ControlServices`` owns the gesture engine, the action dispatcher, the YouTube bridge and
controller, the settings store and the analytics store, and wires their events together:

    gesture event -> dispatcher -> controller
                         |-> analytics (gesture confirmed, action outcomes, control sessions)
    controller Shorts-session changes -> analytics

The UI subscribes to the same dispatcher/mode listeners for display.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path

from interactive_scrolling.actions.dispatcher import ActionDispatcher
from interactive_scrolling.actions.types import ActionRecord, ActionStatus, ControlMode
from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.integrations.youtube.bridge import BridgeServer
from interactive_scrolling.integrations.youtube.controller import YouTubeShortsController
from interactive_scrolling.storage.analytics import AnalyticsStore, EventKind
from interactive_scrolling.storage.settings_store import SettingsStore, UserSettings

log = logging.getLogger(__name__)


@dataclass
class ControlServices:
    engine: GestureEngine
    dispatcher: ActionDispatcher
    user_settings: UserSettings
    store: SettingsStore | None = None
    analytics: AnalyticsStore | None = None
    bridge: BridgeServer | None = None
    controller: YouTubeShortsController | None = None

    def __post_init__(self) -> None:
        self.dispatcher.add_record_listener(self._log_record)
        self.dispatcher.add_mode_listener(self._log_mode)

    # ------------------------------------------------------------------ updates from the UI

    def apply_gesture_settings(self, settings: GestureSettings) -> None:
        self.engine.request_settings(settings)
        self._save(replace(self.user_settings, gestures=settings))

    def apply_mapping(self, mapping) -> None:
        self.dispatcher.set_mapping(mapping)
        self._save(replace(self.user_settings, mapping=dict(mapping)))

    def set_analytics_enabled(self, enabled: bool) -> None:
        if self.analytics is not None:
            self.analytics.enabled = enabled
        self._save(replace(self.user_settings, analytics_enabled=enabled))

    def _save(self, settings: UserSettings) -> None:
        self.user_settings = settings
        if self.store is not None and not self.store.save(settings):
            log.error("Settings could not be saved; changes apply until the app closes.")

    # ------------------------------------------------------------------ analytics wiring

    def _log_record(self, record: ActionRecord) -> None:
        analytics = self.analytics
        if analytics is None:
            return
        if record.status in (ActionStatus.QUEUED, ActionStatus.NOT_EXECUTED):
            # The first notification of every record is QUEUED or NOT_EXECUTED.
            analytics.record(
                EventKind.GESTURE_CONFIRMED,
                gesture=record.event.gesture.value,
                event_uid=f"{record.record_id}:gesture",
            )
        if record.status is ActionStatus.DISPATCHED:
            analytics.record(
                EventKind.ACTION_DISPATCHED,
                gesture=record.event.gesture.value,
                action=record.action.value,
                event_uid=f"{record.record_id}:dispatched",
            )
        elif record.status.final:
            analytics.record(
                EventKind.ACTION_RESULT,
                gesture=record.event.gesture.value,
                action=record.action.value,
                outcome=record.status.value,
                reason=record.reason,
                latency_ms=record.action_latency_ms,
                event_uid=f"{record.record_id}:result",
            )

    def _log_mode(self, old: ControlMode, new: ControlMode, reason: str) -> None:
        if self.analytics is None:
            return
        if new is ControlMode.LIVE_CONTROL:
            self.analytics.record(EventKind.CONTROL_SESSION_STARTED)
        elif old is ControlMode.LIVE_CONTROL:
            self.analytics.record(EventKind.CONTROL_SESSION_ENDED, reason=reason or None)

    def _log_shorts_session(self, active: bool) -> None:
        if self.analytics is not None:
            kind = EventKind.SHORTS_SESSION_STARTED if active else EventKind.SHORTS_SESSION_ENDED
            self.analytics.record(kind)

    # ------------------------------------------------------------------ lifecycle

    def shutdown(self) -> None:
        self.dispatcher.shutdown()
        if self.bridge is not None:
            self.bridge.stop()
        if self.analytics is not None:
            self.analytics.close()


def build_services(data_dir: Path | None = None, start_bridge: bool = True) -> ControlServices:
    """Create the production services from the persisted user settings."""
    store = SettingsStore(data_dir / "settings.json" if data_dir else None)
    user = store.load()
    analytics = AnalyticsStore(
        data_dir / "analytics.sqlite3" if data_dir else None, enabled=user.analytics_enabled
    )
    services_box: dict[str, ControlServices] = {}

    def on_session(active: bool) -> None:
        if "services" in services_box:
            services_box["services"]._log_shorts_session(active)

    bridge = BridgeServer(user.bridge_port, user.pairing_token)
    controller = YouTubeShortsController(bridge, on_shorts_session=on_session)
    bridge.set_change_listener(controller.refresh)
    if start_bridge:
        bridge.start()
    services = ControlServices(
        engine=GestureEngine(user.gestures),
        dispatcher=ActionDispatcher(controller, user.mapping),
        user_settings=user,
        store=store,
        analytics=analytics,
        bridge=bridge,
        controller=controller,
    )
    services_box["services"] = services
    return services


def offline_services(settings: GestureSettings | None = None) -> ControlServices:
    """Services without persistence, analytics or browser bridge (tests, tracking-only use)."""
    user = UserSettings(gestures=settings or GestureSettings())
    return ControlServices(
        engine=GestureEngine(user.gestures),
        dispatcher=ActionDispatcher(None, user.mapping),
        user_settings=user,
    )
