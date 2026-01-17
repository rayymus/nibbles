from __future__ import annotations

import platform
import re
import subprocess
import time
from typing import Optional, Sequence, Tuple

from . import SlackDetectionState, _is_periodic, get_active_window_info
from CONFIG import *


def detect_periodic_clicking(
    state: SlackDetectionState,
    min_events: int,
    min_period_s: float,
    max_period_s: float,
    max_jitter_ratio: float,
) -> bool:
    return _is_periodic(
        state.click_timestamps,
        min_events,
        min_period_s,
        max_period_s,
        max_jitter_ratio,
    )


def detect_periodic_mouse_scrolling(
    state: SlackDetectionState,
    min_events: int,
    min_period_s: float,
    max_period_s: float,
    max_jitter_ratio: float,
) -> bool:
    return _is_periodic(
        state.scroll_timestamps,
        min_events,
        min_period_s,
        max_period_s,
        max_jitter_ratio,
    )


def detect_periodic_mouse_activity(
    state: SlackDetectionState,
    min_events: int,
    min_period_s: float,
    max_period_s: float,
    max_jitter_ratio: float,
) -> bool:
    return detect_periodic_clicking(
        state,
        min_events,
        min_period_s,
        max_period_s,
        max_jitter_ratio,
    ) or detect_periodic_mouse_scrolling(
        state,
        min_events,
        min_period_s,
        max_period_s,
        max_jitter_ratio,
    )


def detect_scrolling(
    state: SlackDetectionState,
    min_events: int,
    min_period_s: float,
    max_period_s: float,
    max_jitter_ratio: float,
) -> bool:
    """Detects if the user is slacking.
    The user is slacking if:
    - User is periodically clicking the mouse or scrolling the mouse, and
    - User has a "slacking window" open, be it in foreground or background
    """
    return detect_periodic_mouse_activity(
        state,
        min_events,
        min_period_s,
        max_period_s,
        max_jitter_ratio
    ) and detect_any_slacking_window()


def detect_inactivity(
    state: SlackDetectionState,
    idle_seconds: float,
    now: Optional[float] = None,
) -> bool:
    current = time.time() if now is None else now
    return (current - state.last_input_time) >= idle_seconds


def detect_active_slacking_window(
    state: SlackDetectionState,
    threshold_seconds: float,
    now: Optional[float] = None,
    active_app: Optional[str] = None,
    active_title: Optional[str] = None,
) -> bool:
    current = time.time() if now is None else now
    if active_app is None or active_title is None:
        fetched_app, fetched_title = get_active_window_info()
        if active_app is None:
            active_app = fetched_app
        if active_title is None:
            active_title = fetched_title
    if active_app is None and active_title is None:
        return False
    if (
        active_app != state.active_app
        or active_title != state.active_title
    ):
        state.active_app = active_app or ""
        state.active_title = active_title or ""
        state.active_window_started_at = current
    if not is_slacking_window(
        state.active_app,
        state.active_title
    ):
        return False
    return (current - state.active_window_started_at) >= threshold_seconds


def detect_any_slacking_window(
    open_windows: Optional[Sequence[Tuple[Optional[str], Optional[str]]]] = None,
) -> bool:
    windows = open_windows or get_open_window_info()
    if not windows:
        return False

    for app_name, title in windows:
        if not is_slacking_window(
            app_name,
            title,
        ):
            continue
        return True
    return False


def is_slacking_window(
    active_app: Optional[str],
    active_title: Optional[str]
) -> bool:
    app_name = (active_app or "").casefold()
    window_title = (active_title or "").casefold()
    for keyword in SLACKING_APPS:
        if keyword and keyword.casefold() in app_name:
            return True
    for keyword in SLACKING_TITLE_KEYWORDS:
        if keyword and keyword.casefold() in window_title:
            return True
    return False


def get_open_window_info() -> Sequence[Tuple[Optional[str], Optional[str]]]:
    system = platform.system().lower()
    if system == "windows":
        return _get_open_windows_windows()
    if system == "darwin":
        return _get_open_windows_macos()
    return _get_open_windows_linux()


def _get_open_windows_windows() -> Sequence[Tuple[Optional[str], Optional[str]]]:
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return []

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    windows: list[tuple[Optional[str], Optional[str]]] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    def enum_callback(hwnd: wintypes.HWND, _lparam: wintypes.LPARAM) -> wintypes.BOOL:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        if not title:
            return True

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
        windows.append((app_name, title))
        return True

    user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
    return windows


def _get_open_windows_macos() -> Sequence[Tuple[Optional[str], Optional[str]]]:
    script = (
        'tell application "System Events"\n'
        "set appList to application processes whose visible is true\n"
        'set output to ""\n'
        "repeat with proc in appList\n"
        "set appName to name of proc\n"
        "set windowNames to {}\n"
        "try\n"
        "set windowNames to name of windows of proc\n"
        "end try\n"
        "if (count of windowNames) is 0 then\n"
        'set output to output & appName & "||" & "" & "\\n"\n'
        "else\n"
        "repeat with w in windowNames\n"
        'set output to output & appName & "||" & w & "\\n"\n'
        "end repeat\n"
        "end if\n"
        "end repeat\n"
        "return output\n"
        "end tell"
    )
    result = _run_command(["osascript", "-e", script])
    if not result:
        return []
    windows = []
    for line in result.splitlines():
        if "||" not in line:
            continue
        app_name, title = line.split("||", 1)
        windows.append((app_name or None, title or None))
    return windows


def _get_open_windows_linux() -> Sequence[Tuple[Optional[str], Optional[str]]]:
    root_output = _run_command(["xprop", "-root", "_NET_CLIENT_LIST"])
    if not root_output:
        return []
    ids = re.findall(r"0x[0-9a-fA-F]+", root_output)
    windows = []
    for window_id in ids:
        title = _parse_xprop_value(
            _run_command(["xprop", "-id", window_id, "_NET_WM_NAME"])
        )
        if title is None:
            title = _parse_xprop_value(
                _run_command(["xprop", "-id", window_id, "WM_NAME"])
            )
        app_name = _parse_xprop_value(
            _run_command(["xprop", "-id", window_id, "WM_CLASS"]),
            prefer_last=True,
        )
        windows.append((app_name, title))
    return windows


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
