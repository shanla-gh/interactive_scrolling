"""Composition of the gesture-control services (no Qt).

``ControlServices`` owns the gesture engine, the action dispatcher, the YouTube bridge and
controller, the settings store and the analytics store, and wires their events together:

    gesture event -> dispatcher -> controller
                         |-> analytics (gesture confirmed, action outcomes, control sessions)
    controller Shorts-session changes -> analytics

The UI subscribes to the same dispatcher/mode listeners for display.
"""

from __future__ import annotations

import json
import logging
import platform
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path

from interactive_scrolling import __version__
from interactive_scrolling.actions.dispatcher import ActionDispatcher
from interactive_scrolling.actions.types import (
    ActionRecord,
    ActionStatus,
    ActionType,
    ControlMode,
)
from interactive_scrolling.config.settings import (
    GESTURE_ENABLE_FIELDS,
    CalibrationProfile,
    GestureSettings,
    SensitivityPreset,
)
from interactive_scrolling.gestures.calibration import CalibrationCollector
from interactive_scrolling.gestures.diagnostics import GestureDiagnostics, LandmarkRecorder
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.gestures.types import GestureFrame
from interactive_scrolling.integrations.coop.session import (
    CoopGuest,
    CoopGuestController,
    CoopHost,
    CoopStatus,
)
from interactive_scrolling.integrations.youtube.bridge import BridgeServer
from interactive_scrolling.integrations.youtube.controller import YouTubeShortsController
from interactive_scrolling.storage.analytics import AnalyticsStore, EventKind
from interactive_scrolling.storage.settings_store import SettingsStore, UserSettings
from interactive_scrolling.vision.landmarks import TrackingResult
from interactive_scrolling.wellbeing.eyes import Baseline, EyeAnalytics
from interactive_scrolling.wellbeing.monitor import Notice, WellbeingMonitor
from interactive_scrolling.wellbeing.report import (
    DailyReport,
    PerformanceReport,
    daily_report,
    performance_report,
)
from interactive_scrolling.wellbeing.sessions import ActivityEvent, ActivityTracker

SCROLL_NAVIGATION = frozenset({ActionType.NEXT_SHORT, ActionType.PREVIOUS_SHORT})
_ACTIVITY_KINDS = {
    ActivityEvent.STARTED: EventKind.SCROLL_ACTIVE_STARTED,
    ActivityEvent.ENDED: EventKind.SCROLL_ACTIVE_ENDED,
    ActivityEvent.HEARTBEAT: EventKind.SCROLL_HEARTBEAT,
}

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
    wall_clock: Callable[[], float] = time.time
    notice_listeners: list[Callable[[Notice], None]] = field(default_factory=list)
    report: DailyReport | None = None
    """Latest daily report, refreshed on the activity thread (never on the UI thread)."""
    performance: PerformanceReport | None = None

    def __post_init__(self) -> None:
        self.dispatcher.add_record_listener(self._log_record)
        self.dispatcher.add_mode_listener(self._log_mode)
        self.wellbeing = WellbeingMonitor(self.user_settings.wellbeing)
        self.activity = ActivityTracker(self._log_activity)
        self._activity_lock = threading.Lock()
        self._stop = threading.Event()
        self._activity_thread: threading.Thread | None = None
        self.dispatcher.add_admission_check(self._wellbeing_admission)
        self.eyes = EyeAnalytics(self._eye_baseline())
        self._eye_lock = threading.Lock()
        self._eye_flushed = self.wall_clock()
        self.eye_report = None
        self.diagnostics = GestureDiagnostics()
        self.recorder = LandmarkRecorder()
        self.calibration = CalibrationCollector()
        self.dispatcher.add_record_listener(self._diagnose_record)

    # ------------------------------------------------------------------ diagnostics

    def gesture_tap(self, tracking: TrackingResult, frame: GestureFrame) -> None:
        """Every processed frame (processing thread): diagnostics and the opt-in recorder."""
        self.diagnostics.observe(tracking, frame)
        self.recorder.observe(tracking)
        if self.calibration.active:
            self.calibration.observe(tracking)

    def _diagnose_record(self, record: ActionRecord) -> None:
        if record.status.final:
            self.diagnostics.observe_action(
                record.event.gesture.value,
                record.action.value,
                record.status.value,
                record.reason,
                record.action_latency_ms,
            )

    def diagnostics_report(self, performance: dict | None = None) -> dict:
        """Everything needed to analyse a recognition or browser problem, without personal
        data: no pairing code, page addresses, titles, video ids or images."""
        settings = self.user_settings
        gestures = {
            k: (v.value if hasattr(v, "value") else v) for k, v in asdict(settings.gestures).items()
        }
        browser: dict = {"connected": False}
        if self.controller is not None:
            status = self.controller.status()
            browser = {
                "bridge_listening": status.listening,
                "bridge_error": status.bridge_error,
                "connections": status.connections,
                "browsers": list(status.browsers),
                "shorts_ready": status.ready,
                "reason": status.reason,
                "signed_in": status.signed_in,
                "browser_focused": status.browser_focused,
            }
        if self.bridge is not None:
            browser["extensions"] = [
                {"browser": c.browser, "version": c.extension_version, "protocol": c.protocol}
                for c in self.bridge.clients()
            ]
        return {
            "app_version": __version__,
            "created": datetime.now().isoformat(timespec="seconds"),
            "system": f"{platform.system()} {platform.release()}, "
            f"Python {platform.python_version()}",
            "control_mode": self.dispatcher.mode.value,
            "gesture_settings": gestures,
            "mapping": {g.value: a.value for g, a in settings.mapping.items()},
            "browser": browser,
            "performance": performance or {},
            "recognition": self.diagnostics.snapshot(),
        }

    def export_diagnostics(self, folder: Path, performance: dict | None = None) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"diagnostics-{datetime.now():%Y%m%d-%H%M%S}.json"
        path.write_text(
            json.dumps(self.diagnostics_report(performance), indent=2), encoding="utf-8"
        )
        return path

    def save_recording(self, folder: Path) -> Path | None:
        """Stop the landmark recording and save it (landmark numbers only, no images)."""
        content = self.recorder.stop()
        if content is None or not content["frames"]:
            return None
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"gestures_{datetime.now():%Y%m%d_%H%M%S}.json"
        path.write_text(json.dumps(content), encoding="utf-8")
        return path

    # ------------------------------------------------------------------ eye analytics

    def _eye_baseline(self) -> Baseline:
        e = self.user_settings.effects
        if e.eye_baseline_yaw is None or e.eye_baseline_pitch is None:
            return Baseline()
        return Baseline(e.eye_baseline_yaw, e.eye_baseline_pitch, e.eye_baseline_gaze or 0.0)

    def add_face(self, timestamp_s: float, face) -> None:  # type: ignore[no-untyped-def]
        """A face-worker result (worker thread). Ignored unless eye analytics are enabled."""
        if not self.user_settings.effects.eye_analytics_enabled:
            return
        with self._eye_lock:
            self.eyes.add(timestamp_s, face)

    def flush_eyes(self) -> None:
        with self._eye_lock:
            totals = self.eyes.take()
        if totals.samples and self.analytics is not None:
            self.analytics.record_eyes(
                totals.screen_s,
                totals.away_s,
                totals.unknown_s,
                totals.blinks,
                totals.longest_screen_s,
            )

    # ------------------------------------------------------------------ co-op

    def coop_status(self) -> CoopStatus:
        guest = getattr(self, "_coop_guest", None)
        if guest is not None and guest.connected:
            return guest.status()
        host = getattr(self, "_coop_host", None)
        if host is not None:
            return host.status()
        if guest is not None:
            return guest.status()
        return CoopStatus(role="off", state="no session")

    def host_coop(self, name: str, port: int) -> str:
        """Create a co-op session on this computer (this browser is the shared feed)."""
        self.leave_coop()
        host = getattr(self, "_coop_host", None)
        if host is None:
            host = CoopHost(self.dispatcher, name, port)
            self._coop_host = host
        return host.start(name, port)

    def end_coop(self) -> None:
        host = getattr(self, "_coop_host", None)
        if host is not None:
            host.stop()

    def join_coop(self, name: str, address: str, port: int, code: str) -> None:
        """Join a session as Guest (blocking, at most a few seconds; call off the UI thread).
        While joined, this computer's shared gestures go to the Host instead of the local
        browser."""
        self.end_coop()
        self.leave_coop()
        guest = CoopGuest(name)
        guest.connect(address, port, code)
        self._coop_guest = guest
        self._local_controller = self.dispatcher.set_controller(CoopGuestController(guest))

    def leave_coop(self) -> None:
        guest = getattr(self, "_coop_guest", None)
        if guest is None:
            return
        guest.disconnect()
        self._coop_guest = None
        self.dispatcher.set_controller(getattr(self, "_local_controller", None))

    def apply_effects(self, settings) -> None:  # type: ignore[no-untyped-def]
        self.update_settings(effects=settings)
        with self._eye_lock:
            self.eyes.baseline = self._eye_baseline()

    # ------------------------------------------------------------------ activity and reports

    def start_activity(self, interval_s: float = 1.0) -> None:
        """Start the once-per-second activity thread (scrolling sessions, reminders, reports)."""
        if self._activity_thread is not None:
            return
        if self.analytics is not None and self.analytics.enabled:
            today = daily_report(self.analytics, 60.0, 20.0)
            if today is not None:
                self.activity.restore(list(today.sessions), self.wall_clock())
        self._activity_thread = threading.Thread(
            target=self._activity_loop, args=(interval_s,), name="activity", daemon=True
        )
        self._activity_thread.start()

    def _activity_loop(self, interval_s: float) -> None:
        tick = 0
        while not self._stop.wait(interval_s):
            try:
                self.activity_step(refresh_reports=tick % 2 == 0)
            except Exception:
                log.exception("Activity update failed")
            tick += 1

    def activity_step(self, refresh_reports: bool = True) -> list[Notice]:
        """One activity sample (called by the activity thread; public for tests)."""
        now = self.wall_clock()
        status = self.controller.status() if self.controller is not None else None
        active = status is not None and status.actively_scrolling
        with self._activity_lock:
            self.activity.update(now, active)
            session_s = self.activity.current_session_s(now)
            session_start = self.activity.session_start
        if now - self._eye_flushed >= 60.0:
            self._eye_flushed = now
            self.flush_eyes()
        if refresh_reports:
            self.refresh_reports()
        today_s = self.report.scrolling_s if self.report is not None else session_s
        day = datetime.fromtimestamp(now).date().isoformat()
        with self._activity_lock:
            notices = self.wellbeing.evaluate(day, session_start, session_s, today_s)
        for notice in notices:
            log.info("%s: %s", notice.title, notice.text)
            for listener in list(self.notice_listeners):
                try:
                    listener(notice)
                except Exception:
                    log.exception("Notice listener failed")
        return notices

    def refresh_reports(self) -> None:
        if self.analytics is None:
            return
        w = self.user_settings.wellbeing
        self.report = daily_report(self.analytics, w.daily_budget_min, w.session_limit_min)
        self.performance = performance_report(self.analytics)
        self.eye_report = self.analytics.eye_report() if self.analytics.enabled else None

    def current_session(self) -> tuple[float | None, float]:
        """(start wall time, active seconds) of the scrolling session in progress."""
        with self._activity_lock:
            return self.activity.session_start, self.activity.current_session_s(self.wall_clock())

    def current_session_s(self) -> float:
        with self._activity_lock:
            return self.activity.current_session_s(self.wall_clock())

    def _log_activity(self, event: ActivityEvent, ts: float) -> None:
        if self.analytics is not None:
            self.analytics.record(_ACTIVITY_KINDS[event])

    def _wellbeing_admission(self, record: ActionRecord) -> str | None:
        if record.action in SCROLL_NAVIGATION and self.wellbeing.scrolling_paused:
            return self.wellbeing.pause_reason
        return None

    def pause_scrolling(self, paused: bool) -> None:
        """User control: pause or resume gesture scrolling between Shorts."""
        with self._activity_lock:
            if paused:
                self.wellbeing.pause()
            else:
                self.wellbeing.resume()
        log.info("Gesture scrolling %s.", "paused" if paused else "resumed")

    def apply_wellbeing(self, settings) -> None:
        with self._activity_lock:
            self.wellbeing.settings = settings
        self.update_settings(wellbeing=settings)

    # ------------------------------------------------------------------ updates from the UI

    def apply_gesture_settings(self, settings: GestureSettings) -> None:
        self.engine.request_settings(settings)
        self._save(replace(self.user_settings, gestures=settings))

    def apply_calibration(self, settings: GestureSettings, profile: CalibrationProfile) -> None:
        """Use and persist a Quick Calibration result (thresholds and half-heart template)."""
        self.engine.set_profile(profile)
        self.engine.request_settings(settings)
        self._save(replace(self.user_settings, gestures=settings, calibration=profile))

    def reset_calibration(self) -> None:
        """Back to the standard (Balanced) thresholds and shapes; mapping and hand are kept."""
        current = self.user_settings.gestures
        settings = GestureSettings.from_preset(
            SensitivityPreset.BALANCED,
            control_hand=current.control_hand,
            **{name: getattr(current, name) for name in GESTURE_ENABLE_FIELDS},
        )
        self.apply_calibration(settings, CalibrationProfile())

    def apply_mapping(self, mapping) -> None:
        self.dispatcher.set_mapping(mapping)
        self._save(replace(self.user_settings, mapping=dict(mapping)))

    def update_settings(self, **changes: object) -> None:
        """Persist changed sections of the user settings (appearance, creator, ...)."""
        self._save(replace(self.user_settings, **changes))  # type: ignore[arg-type]

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
        self.leave_coop()
        self.end_coop()
        self._stop.set()
        if self._activity_thread is not None:
            self._activity_thread.join(timeout=3)
        with self._activity_lock:
            self.activity.stop(self.wall_clock())
        self.flush_eyes()
        self.dispatcher.shutdown()
        if self.bridge is not None:
            self.bridge.stop()
        if self.analytics is not None:
            self.analytics.close()


def build_services(data_dir: Path | None = None, start_bridge: bool = True) -> ControlServices:
    """Create the production services from the persisted user settings."""
    store = SettingsStore(data_dir / "settings.json" if data_dir else None)
    user = store.load()
    if store.migrations:
        # Persist migrated settings at once, so a migration (and its notice) happens once.
        store.save(user)
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
        engine=GestureEngine(user.gestures, profile=user.calibration),
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
        engine=GestureEngine(user.gestures, profile=user.calibration),
        dispatcher=ActionDispatcher(None, user.mapping),
        user_settings=user,
    )
