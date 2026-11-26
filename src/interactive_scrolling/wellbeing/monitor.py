"""Anti-Doomscroll: optional reminders and a user-controlled pause of gesture scrolling.

Everything is opt-in and reversible:

* **Reality Check**: every ``reality_check_min`` of active scrolling in a session, a short
  notice with the session's actual duration.
* **Session limit** and **daily budget**: a notice when reached, with a break suggestion if
  break reminders are on.
* **Pause gesture scrolling**: the user can pause next/previous-Short gestures at any time
  (and resume at any time). With ``pause_at_limit`` the pause starts automatically when the
  session limit or daily budget is reached; the user can resume immediately, and the automatic
  pause ends by itself when the session ends. Only gesture navigation between Shorts is
  paused: likes, pause/resume, tab switching, the mouse and the keyboard keep working, and no
  application is opened or closed.

Eye analytics are never used here.
"""

from __future__ import annotations

from dataclasses import dataclass

from interactive_scrolling.config.settings import WellbeingSettings


@dataclass(frozen=True, slots=True)
class Notice:
    key: str
    title: str
    text: str


def _minutes(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


class WellbeingMonitor:
    def __init__(self, settings: WellbeingSettings) -> None:
        self.settings = settings
        self._shown: set[str] = set()
        self.manual_pause = False
        self._auto_pause_reason: str | None = None
        self._auto_pause_key: str | None = None
        self._overridden: set[str] = set()
        """Limits the user chose to continue past (no automatic pause again for them)."""
        self._session_key: str | None = None

    # ------------------------------------------------------------------ pause state

    @property
    def scrolling_paused(self) -> bool:
        return self.manual_pause or self._auto_pause_reason is not None

    @property
    def pause_reason(self) -> str:
        if self.manual_pause:
            return "gesture scrolling paused by you"
        if self._auto_pause_reason is not None:
            return f"gesture scrolling paused: {self._auto_pause_reason}"
        return ""

    def pause(self) -> None:
        self.manual_pause = True

    def resume(self) -> None:
        """Resume gesture scrolling now (also overrides an automatic pause)."""
        self.manual_pause = False
        if self._auto_pause_reason is not None:
            self._overridden.add(self._auto_pause_key or "")
        self._auto_pause_reason = None
        self._auto_pause_key = None

    # ------------------------------------------------------------------ evaluation

    def evaluate(
        self, day: str, session_start: float | None, session_s: float, today_s: float
    ) -> list[Notice]:
        """Return the notices that became due (each is returned once)."""
        s = self.settings
        session_key = f"{day}:{session_start:.0f}" if session_start is not None else None
        if session_key != self._session_key:
            self._session_key = session_key
            if self._auto_pause_key is not None and self._auto_pause_key.startswith("session"):
                self._auto_pause_reason = None  # an automatic session pause ends with the session
                self._auto_pause_key = None
        if not s.enabled:
            return []
        due: list[Notice] = []

        def once(key: str, title: str, text: str) -> None:
            if key not in self._shown:
                self._shown.add(key)
                due.append(Notice(key, title, text))

        if session_key is not None and s.reality_check_min > 0:
            n = int(session_s // (s.reality_check_min * 60))
            if n >= 1:
                once(
                    f"reality:{session_key}:{n}",
                    "Reality Check",
                    f"You have been scrolling Shorts for {_minutes(session_s)} in this session.",
                )
        brk = " Maybe a good moment for a short break?" if s.break_reminders else ""
        if session_key is not None and session_s >= s.session_limit_min * 60:
            key = f"session:{session_key}"
            once(key, "Session limit reached", f"{_minutes(session_s)} in this session.{brk}")
            self._maybe_auto_pause(key, "session limit reached")
        if today_s >= s.daily_budget_min * 60:
            key = f"budget:{day}"
            once(key, "Daily scrolling budget reached", f"{_minutes(today_s)} today.{brk}")
            self._maybe_auto_pause(key, "daily budget reached")
        return due

    def _maybe_auto_pause(self, key: str, reason: str) -> None:
        enabled = self.settings.pause_at_limit and key not in self._overridden
        if enabled and self._auto_pause_reason is None:
            self._auto_pause_reason = reason
            self._auto_pause_key = key
