
from __future__ import annotations

import platform
import re
import time
import subprocess
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple, Callable, Deque

#  Sleep state
_sleep_state: bool = False
_sleep_state_getter: Optional[Callable[[], bool]] = None


def set_sleep_state_getter(getter: Callable[[], bool]) -> None:
    """Register a callback that returns the live hamster sleep state."""
    global _sleep_state_getter
    _sleep_state_getter = getter


def set_sleeping(is_sleeping: bool) -> None:
    """Update the fallback sleep state when no getter is set."""
    global _sleep_state
    _sleep_state = is_sleeping


def is_sleeping() -> bool:
    """Return True if slack detection should be paused."""
    if _sleep_state_getter is not None:
        try:
            return bool(_sleep_state_getter())
        except Exception:
            return _sleep_state
    return _sleep_state


@dataclass
class SlackDetectionState:
    last_input_time: float = field(default_factory=time.time)
    click_timestamps: Deque[float] = field(default_factory=lambda: deque(maxlen=120))
    scroll_timestamps: Deque[float] = field(default_factory=lambda: deque(maxlen=120))
    key_timestamps: Deque[float] = field(default_factory=lambda: deque(maxlen=120))
    global_input_status: str = "off"
    global_input_events: int = 0
    global_last_input_time: float = 0.0
    active_app: str = ""
    active_title: str = ""
    active_window_started_at: float = field(default_factory=time.time)
    window_seen_at: dict[tuple[str, str], float] = field(default_factory=dict)


def get_active_window_info() -> Tuple[Optional[str], Optional[str]]:
    system = platform.system().lower()
    if system == "windows":
        return _get_active_window_windows()
    if system == "darwin":
        return _get_active_window_macos()
    return _get_active_window_linux()


def _is_periodic(
    timestamps: Sequence[float],
    min_events: int,
    min_period_s: float,
    max_period_s: float,
    max_jitter_ratio: float,
) -> bool:
    print(timestamps)
    if len(timestamps) < min_events:
        return False
    recent = list(timestamps)[-min_events:]
    intervals = [b - a for a, b in zip(recent, recent[1:]) if b > a]
    if len(intervals) < (min_events - 1):
        return False
    mean_interval = sum(intervals) / len(intervals)
    if mean_interval <= 0:
        return False
    if mean_interval < min_period_s or mean_interval > max_period_s:
        return False
    max_deviation = max(abs(interval - mean_interval) for interval in intervals)
    return max_deviation <= (mean_interval * max_jitter_ratio)


def _get_active_window_windows() -> Tuple[Optional[str], Optional[str]]:
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return None, None

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, None

    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    title = buffer.value

    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    handle = kernel32.OpenProcess(0x1000, False, process_id.value)
    app_name = None
    if handle:
        try:
            size = wintypes.DWORD(1024)
            exe_buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(
                handle, 0, exe_buffer, ctypes.byref(size)
            ):
                app_name = exe_buffer.value.split("\\")[-1]
        finally:
            kernel32.CloseHandle(handle)
    return app_name, title


def _get_active_window_macos() -> Tuple[Optional[str], Optional[str]]:
    script = (
        'tell application "System Events"\n'
        "set frontApp to first application process whose frontmost is true\n"
        "set appName to name of frontApp\n"
        'set windowName to ""\n'
        "try\n"
        "set windowName to name of front window of frontApp\n"
        "end try\n"
        'return appName & "||" & windowName\n'
        "end tell"
    )
    result = _run_command(["osascript", "-e", script])
    if not result:
        return None, None
    if "||" in result:
        app_name, title = result.split("||", 1)
    else:
        app_name, title = result, ""
    return app_name or None, title or None


def _get_active_window_linux() -> Tuple[Optional[str], Optional[str]]:
    root_output = _run_command(["xprop", "-root", "_NET_ACTIVE_WINDOW"])
    if not root_output:
        return None, None
    match = re.search(r"window id # (0x[0-9a-fA-F]+)", root_output)
    if not match:
        return None, None
    window_id = match.group(1)
    title = _parse_xprop_value(_run_command(["xprop", "-id", window_id, "_NET_WM_NAME"]))
    if title is None:
        title = _parse_xprop_value(_run_command(["xprop", "-id", window_id, "WM_NAME"]))
    app_name = _parse_xprop_value(
        _run_command(["xprop", "-id", window_id, "WM_CLASS"]),
        prefer_last=True,
    )
    return app_name, title


def _run_command(args: Sequence[str]) -> Optional[str]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _parse_xprop_value(output: Optional[str], prefer_last: bool = False) -> Optional[str]:
    if not output or "=" not in output:
        return None
    _, value = output.split("=", 1)
    matches = re.findall(r'"([^"]+)"', value)
    if matches:
        return matches[-1] if prefer_last else matches[0]
    cleaned = value.strip().strip('"')
    return cleaned or None
