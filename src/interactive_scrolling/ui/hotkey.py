"""System-wide emergency hotkey (Windows ``RegisterHotKey``).

The hotkey works while the browser has focus, which is exactly when gesture control is in use.
If registration fails (another program owns the combination, or a non-Windows platform), the
application keeps working with the on-screen Disable button and the Esc shortcut.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QByteArray

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
HOTKEY_ID = 0x4953  # arbitrary, application-unique
DEFAULT_KEY = ord("D")
DEFAULT_LABEL = "Ctrl+Alt+D"


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__()
        self._callback = callback
        self.registered = False
        self.label = ""

    def register(
        self,
        modifiers: int = MOD_CONTROL | MOD_ALT,
        key: int = DEFAULT_KEY,
        label: str = DEFAULT_LABEL,
    ) -> bool:
        if sys.platform != "win32":
            return False
        import ctypes

        user32 = ctypes.windll.user32
        ok = bool(user32.RegisterHotKey(None, HOTKEY_ID, modifiers | MOD_NOREPEAT, key))
        self.registered = ok
        self.label = label if ok else ""
        if ok:
            log.info("Emergency disable shortcut %s is active system-wide.", label)
        else:
            log.warning("Could not register %s (in use by another program).", label)
        return ok

    def unregister(self) -> None:
        if self.registered and sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
            self.registered = False

    def nativeEventFilter(self, event_type: QByteArray | bytes, message: int) -> tuple[bool, int]:
        if self.registered and bytes(event_type) == b"windows_generic_MSG":
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._callback()
                return True, 0
        return False, 0
