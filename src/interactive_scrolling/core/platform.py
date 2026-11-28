"""Operating-system specific process tuning.

Windows 11 may apply *execution speed power throttling* (EcoQoS) to processes it does not
consider latency sensitive: their threads run at reduced clock speeds or on efficiency
cores. For a paced real-time workload that idles between frames this roughly doubled
inference time on the development machine (see docs/architecture/DECISIONS.md, ADR-008).
Opting out uses the documented ``SetProcessInformation(ProcessPowerThrottling)`` API and
affects only this process.

Brief 008: Windows 11 also ignores a process's timer-resolution requests while none of its
windows is visible (``PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION``), which coarsens the
timing of a process running only in the tray (Background Mode). The same call opts out of that
when ``timer_resolution`` is true; on Windows versions without the flag it falls back to the
execution-speed opt-out alone.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

_PROCESS_POWER_THROTTLING = 4  # PROCESS_INFORMATION_CLASS.ProcessPowerThrottling
_PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
_PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
_PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION = 0x4


def disable_power_throttling(timer_resolution: bool = True) -> bool:
    """Opt this process out of execution-speed power throttling on Windows.

    Returns ``True`` if the setting was applied, ``False`` on other platforms or if the
    call failed (e.g. on Windows versions without the API). Never raises.
    """
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    class _PowerThrottlingState(ctypes.Structure):
        _fields_ = (
            ("Version", wintypes.ULONG),
            ("ControlMask", wintypes.ULONG),
            ("StateMask", wintypes.ULONG),
        )

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        set_info = kernel32.SetProcessInformation
    except (OSError, AttributeError) as exc:
        log.info("Power throttling control is not available: %s", exc)
        return False
    set_info.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    set_info.restype = wintypes.BOOL

    def apply(mask: int) -> bool:
        # StateMask 0 with the bits set in ControlMask = these kinds of throttling disabled.
        state = _PowerThrottlingState(_PROCESS_POWER_THROTTLING_CURRENT_VERSION, mask, 0)
        return bool(
            set_info(
                kernel32.GetCurrentProcess(),
                _PROCESS_POWER_THROTTLING,
                ctypes.byref(state),
                ctypes.sizeof(state),
            )
        )

    mask = _PROCESS_POWER_THROTTLING_EXECUTION_SPEED
    if timer_resolution:
        mask |= _PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION
    ok = apply(mask)
    if not ok and timer_resolution:
        ok = apply(_PROCESS_POWER_THROTTLING_EXECUTION_SPEED)
    if ok:
        log.info("Windows power throttling disabled for this process (real-time processing).")
    else:
        log.info("Could not disable power throttling (error %d).", ctypes.get_last_error())
    return ok
