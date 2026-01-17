from __future__ import annotations

from dataclasses import dataclass
import platform
import re
import time
import math
import random
import subprocess
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

from PyQt5 import QtCore, QtGui, QtWidgets

from poke_for_fun.hamster_dabrain import enter_state
from poke_for_fun.hamster_states import HamsterState
from slack_detection import get_active_window_info, set_sleeping
from CONFIG import *
from utils import play_audio


SizeLike = Union[QtCore.QSize, Tuple[int, int]]


@dataclass
class WindowInfo:
    window_id: str
    title: str
    app_name: Optional[str]
    rect: QtCore.QRect


@dataclass
class BiteSession:
    overlay: "BiteOverlay"
    timer: QtCore.QTimer
    window_id: str


class BiteOverlay(QtWidgets.QWidget):
    def __init__(self) -> None:
        flags = (
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Window
        )
        super().__init__(None, flags)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setWindowFlag(QtCore.Qt.WindowDoesNotAcceptFocus, True)
        self._bite_rect = QtCore.QRect()
        self._bite_color = QtGui.QColor(0, 0, 0, 255)

    def update_target_window(self, window: WindowInfo) -> None:
        rect = window.rect
        if rect.width() <= 0 or rect.height() <= 0:
            return
        self.setGeometry(rect)
        self._bite_rect = _bite_rect_for_window(window)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        if self._bite_rect.isNull():
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        path = _build_bite_path(self._bite_rect)
        painter.fillPath(path, self._bite_color)


def bite( #  Should only be run if active window is slacking window
    hamster_widget: QtWidgets.QWidget,
    poll_interval_ms: int = 20,
) -> Optional[BiteSession]:
    """Overlay a bite mask over a slacking browser window until the tab changes."""
    existing = getattr(hamster_widget, "_bite_session", None)
    if existing is not None and existing.timer.isActive():
        return existing
    window = _find_slacking_window(SLACKING_TITLE_KEYWORDS)
    if window is None:
        print("bite: Couldn't find window")
        return None

    print("bite: trying bite overlay")
    """to add: change sprite to bite"""
    hamster_widget.flip_direction()
    hamster_widget.rotate(20)
    play_audio("sound_effects/bite.mp3")
    overlay = BiteOverlay()
    overlay.update_target_window(window)
    overlay.show()
    overlay.raise_()
    _position_hamster_centered_rect(hamster_widget, _bite_rect_for_window(window))
    hamster_widget.raise_()
    print("bite: overlay")

    timer = QtCore.QTimer(overlay)
    timer.setInterval(max(20, int(poll_interval_ms)))

    def tick() -> None:
        active_app, active_title = get_active_window_info()
        if not _is_slacking_window(active_app, active_title, SLACKING_TITLE_KEYWORDS):
            timer.stop()
            hamster_widget.move_to_bottom_right()
            hamster_widget.flip_direction()
            overlay.close()
            overlay.deleteLater()
            setattr(hamster_widget, "_bite_session", None)
            return
        updated = _find_window_by_id(window.window_id)
        overlay.update_target_window(updated)

    timer.timeout.connect(tick)
    timer.start()

    session = BiteSession(overlay=overlay, timer=timer, window_id=window.window_id)
    setattr(hamster_widget, "_bite_session", session)
    return session


def make_window_smaller( #  Can only be used if active window is slacking.
    hamster_widget: QtWidgets.QWidget,
    shrink_by: SizeLike = (160, 120),
    step_px: int = 4,
    interval_ms: int = 8,
    min_size: Optional[SizeLike] = None,
    duration_ms: Optional[int] = 240,
) -> Optional[QtCore.QTimer]:
    """Gradually shrink the slacking window from bottom-right while anchoring hamster there."""
    if not _macos_accessibility_trusted():
        print(
            "make_window_smaller: Accessibility permission not granted for this process."
        )
        return None

    window = _find_slacking_window(SLACKING_TITLE_KEYWORDS)
    if window is None:
        print("make_window_smaller: Couldn't find slacking window")
        return None

    shrink_size = _to_size(shrink_by)
    minimum_size = _to_size(min_size) if min_size is not None else QtCore.QSize(240, 180)

    current_size = window.rect.size()
    target_width = max(minimum_size.width(), current_size.width() - max(0, shrink_size.width()))
    target_height = max(minimum_size.height(), current_size.height() - max(0, shrink_size.height()))
    target_size = QtCore.QSize(target_width, target_height)
    start_rect = window.rect
    start_width = start_rect.width()
    start_height = start_rect.height()
    duration_s = (duration_ms or 0) / 1000.0

    step = max(1, int(step_px))
    _position_hamster_bottom_right_rect(hamster_widget, window.rect)

    timer = QtCore.QTimer(hamster_widget)
    timer.setInterval(max(1, int(interval_ms)))
    start_time = time.time()
    shrink_complete = False

    def revert() -> None:
        updated = _find_window_by_id(window.window_id)
        target = updated or window
        if not _set_window_rect(target, start_rect):
            print("make_window_smaller: revert failed")
        hamster_widget.move_to_bottom_right()

    def tick() -> None:
        active_app, active_title = get_active_window_info()
        if not _is_slacking_window(active_app, active_title, SLACKING_TITLE_KEYWORDS):
            revert()
            timer.stop()
            return
        updated = _find_window_by_id(window.window_id)
        if updated is None or not _is_slacking_window(updated.app_name, updated.title, SLACKING_TITLE_KEYWORDS):
            revert()
            timer.stop()
            return
        nonlocal shrink_complete
        new_rect = None
        if not shrink_complete:
            if duration_s > 0:
                elapsed = time.time() - start_time
                t = min(1.0, elapsed / duration_s)
                eased = 1.0 - (1.0 - t) ** 3
                new_width = int(round(start_width - (start_width - target_width) * eased))
                new_height = int(round(start_height - (start_height - target_height) * eased))
                new_width = max(target_width, new_width)
                new_height = max(target_height, new_height)
                if t >= 1.0:
                    shrink_complete = True
            else:
                size_now = updated.rect.size()
                if size_now.width() <= target_size.width() and size_now.height() <= target_size.height():
                    shrink_complete = True
                else:
                    new_width = max(target_size.width(), size_now.width() - step)
                    new_height = max(target_size.height(), size_now.height() - step)
            if shrink_complete:
                new_rect = QtCore.QRect(updated.rect.topLeft(), target_size)
            else:
                new_rect = QtCore.QRect(updated.rect.topLeft(), QtCore.QSize(new_width, new_height))
            if not _set_window_rect(updated, new_rect):
                print(
                    "make_window_smaller: Failed to resize window. "
                    "On macOS this requires Accessibility permission."
                )
                timer.stop()
                return
        refreshed = _find_window_by_id(window.window_id)
        anchor_rect = refreshed.rect if refreshed is not None else (new_rect or updated.rect)
        _position_hamster_bottom_right_rect(hamster_widget, anchor_rect)

    timer.timeout.connect(tick)
    timer.start()
    return timer

def slap_cursor(
    hamster_widget: QtWidgets.QWidget,
    moves: int = 6,
    interval_ms: int = 45,
    distance_px: int = 220,
) -> QtCore.QTimer:
    """Jolt the mouse cursor around to 'slap' it away from where it currently is."""
    timer = QtCore.QTimer(hamster_widget)
    timer.setInterval(max(1, int(interval_ms)))
    remaining = max(1, int(moves))

    def clamp_to_screen(point: QtCore.QPoint, screen: Optional[QtGui.QScreen]) -> QtCore.QPoint:
        if screen is None:
            return point
        geo = screen.availableGeometry()
        x = max(geo.left(), min(geo.right() - 1, point.x()))
        y = max(geo.top(), min(geo.bottom() - 1, point.y()))
        return QtCore.QPoint(x, y)

    def tick() -> None:
        nonlocal remaining
        if remaining <= 0:
            timer.stop()
            return
        remaining -= 1
        cursor_pos = QtGui.QCursor.pos()
        angle = random.random() * math.tau
        offset = QtCore.QPoint(
            int(distance_px * math.cos(angle)),
            int(distance_px * math.sin(angle)),
        )
        target = cursor_pos + offset
        screen = QtGui.QGuiApplication.screenAt(cursor_pos) or QtGui.QGuiApplication.primaryScreen()
        QtGui.QCursor.setPos(clamp_to_screen(target, screen))

    timer.timeout.connect(tick)
    play_audio("sound_effects/slap.mp3")
    """"to add: move nibbles to mouse pos and change sprite to hold mouse"""
    tick()  # fire once immediately
    timer.start()
    return timer

def _to_size(value: SizeLike) -> QtCore.QSize:
    if isinstance(value, QtCore.QSize):
        return value
    return QtCore.QSize(int(value[0]), int(value[1]))

def drag(
    hamster_widget: QtWidgets.QWidget,
    poll_interval_ms: int = 16,
) -> QtCore.QTimer:
    timer = QtCore.QTimer(hamster_widget)
    timer.setInterval(max(1, int(poll_interval_ms)))

    def tick() -> None:
        pos = QtGui.QCursor.pos()
        hamster_widget.move(pos.x(), pos.y())

    timer.timeout.connect(tick)
    timer.start()
    return timer

def wake_up(hamster_widget: QtWidgets.QWidget) -> None:
    """Stop the sleep animation and return the hamster to idle."""
    label = getattr(hamster_widget, "_sleep_label", None)
    if label is not None:
        movie = label.movie()
        if movie is not None:
            movie.stop()
        label.hide()
    if hasattr(hamster_widget, "sleeping"):
        hamster_widget.sleeping = False
    set_sleeping(False)
    ham = getattr(hamster_widget, "ham", None)
    if ham is not None:
        enter_state(ham, HamsterState.IDLE)
    hamster_widget.update()
    
def sleep(
    hamster_widget: QtWidgets.QWidget,
    gif_path: Optional[str] = None,
) -> QtGui.QMovie:
    gif_file = Path(gif_path) if gif_path else Path(__file__).parent / "sprites" / "sleepy.gif"

    label = getattr(hamster_widget, "_sleep_label", None)
    if label is None:
        label = QtWidgets.QLabel(hamster_widget)
        label.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        label.setAlignment(QtCore.Qt.AlignCenter)
        setattr(hamster_widget, "_sleep_label", label)

    movie = QtGui.QMovie(str(gif_file))
    label.setMovie(movie)
    label.resize(hamster_widget.size())
    label.show()
    movie.start()

    if hasattr(hamster_widget, "sleeping"):
        hamster_widget.sleeping = True
    set_sleeping(True)
    return movie


def _to_size(value: SizeLike) -> QtCore.QSize:
    if isinstance(value, QtCore.QSize):
        return value
    return QtCore.QSize(int(value[0]), int(value[1]))


def _position_hamster_bottom_right_rect(
    hamster_widget: QtWidgets.QWidget,
    rect: QtCore.QRect,
) -> None:
    hamster_size = hamster_widget.frameGeometry().size()
    x = rect.right() - hamster_size.width() + 1
    y = rect.bottom() - hamster_size.height() + 1
    pos = QtCore.QPoint(x, y)
    clamp = getattr(hamster_widget, "_clamp_to_screen", None)
    if callable(clamp):
        pos = clamp(pos)
    hamster_widget.move(pos)


def _position_hamster_centered_rect(
    hamster_widget: QtWidgets.QWidget,
    rect: QtCore.QRect,
) -> None:
    hamster_size = hamster_widget.frameGeometry().size()
    x = rect.center().x() - hamster_size.width() // 2
    y = rect.center().y() - hamster_size.height() // 2
    pos = QtCore.QPoint(x, y)
    clamp = getattr(hamster_widget, "_clamp_to_screen", None)
    if callable(clamp):
        pos = clamp(pos)
    hamster_widget.move(pos)


def _bite_rect_for_window(window: WindowInfo) -> QtCore.QRect:
    rect = window.rect
    width = max(1, rect.width())
    height = max(1, rect.height())
    app = (window.app_name or "").casefold()
    title = (window.title or "").casefold()

    def make_rect(x_frac: float, y_frac: float, w_frac: float, h_frac: float) -> QtCore.QRect:
        x = rect.x() + int(width * x_frac)
        y = rect.y() + int(height * y_frac)
        w = max(1, int(width * w_frac))
        h = max(1, int(height * h_frac))
        w = min(w, width)
        h = min(h, height)
        return QtCore.QRect(x, y, w, h)

    if "tiktok" in app or "tiktok" in title:
        return make_rect(0.31, 0.06, 0.38, 0.88)
    if "instagram" in app or "instagram" in title:
        return make_rect(0.33, 0.08, 0.34, 0.84)
    if "youtube" in app or "youtube" in title:
        if "shorts" in title:
            return make_rect(0.31, 0.10, 0.38, 0.80)
        return make_rect(0.05, 0.16, 0.62, 0.52)

    return _default_bite_rect(rect.size()).translated(rect.topLeft())


def _default_bite_rect(window_size: QtCore.QSize) -> QtCore.QRect:
    width = max(1, window_size.width())
    height = max(1, window_size.height())
    bite_width = max(220, int(width * 0.38))
    bite_height = max(260, int(height * 0.60))
    bite_x = max(0, width - bite_width - int(width * 0.10))
    bite_y = max(0, int(height * 0.08))
    bite_width = min(bite_width, width)
    bite_height = min(bite_height, height)
    return QtCore.QRect(bite_x, bite_y, bite_width, bite_height)


def _build_bite_path(rect: QtCore.QRect) -> QtGui.QPainterPath:
    width = rect.width()
    height = rect.height()
    path = QtGui.QPainterPath()
    path.setFillRule(QtCore.Qt.WindingFill)
    base = max(1, min(width, height))

    center = QtCore.QPointF(rect.center())
    oval_w = width * 0.62
    oval_h = height * 0.88
    base_rect = QtCore.QRectF(
        center.x() - oval_w * 0.5,
        center.y() - oval_h * 0.5,
        oval_w,
        oval_h,
    )
    path.addEllipse(base_rect)

    ring_count = 24
    ring_radius = base * 0.20
    a = base_rect.width() * 0.5
    b = base_rect.height() * 0.5
    for i in range(ring_count):
        t = (i / ring_count) * (2 * 3.141592653589793)
        x = center.x() + a * 0.92 * math.cos(t)
        y = center.y() + b * 0.92 * math.sin(t)
        path.addEllipse(QtCore.QPointF(x, y), ring_radius, ring_radius)

    transform = QtGui.QTransform()
    transform.translate(center.x(), center.y())
    transform.rotate(10.0)
    transform.translate(-center.x(), -center.y())
    return transform.map(path)


def _title_matches_slacking(window_title: Optional[str], keywords: Sequence[str]) -> bool:
    title = (window_title or "").casefold()
    for keyword in keywords:
        if keyword and keyword.casefold() in title:
            return True
    return False


def _is_slacking_window(
    app_name: Optional[str],
    window_title: Optional[str],
    title_keywords: Sequence[str],
) -> bool:
    app = (app_name or "").casefold()
    for keyword in SLACKING_APPS:
        if keyword and keyword.casefold() in app:
            return True
    return _title_matches_slacking(window_title, title_keywords)


def _score_active_window_match(
    window: WindowInfo,
    active_app: Optional[str],
    active_title: Optional[str],
) -> int:
    score = 0
    if active_app and window.app_name:
        active = active_app.casefold()
        candidate = window.app_name.casefold()
        if active == candidate:
            score += 3
        elif active in candidate or candidate in active:
            score += 2
    if active_title and window.title:
        active = active_title.casefold()
        candidate = window.title.casefold()
        if active == candidate:
            score += 3
        elif active in candidate or candidate in active:
            score += 1
    return score


def _find_slacking_window(keywords: Sequence[str]) -> Optional[WindowInfo]:
    windows = _list_windows()
    if not windows:
        return None

    active_app, active_title = get_active_window_info()
    if _is_slacking_window(active_app, active_title, keywords):
        best = None
        best_score = 0
        for window in windows:
            score = _score_active_window_match(window, active_app, active_title)
            if score > best_score:
                best = window
                best_score = score
            elif score == best_score and score > 0 and best is not None:
                if (window.rect.width() * window.rect.height()) > (
                    best.rect.width() * best.rect.height()
                ):
                    best = window
        if best is not None and _is_slacking_window(best.app_name, best.title, keywords):
            return best

    windows = [
        w for w in windows
        if _is_slacking_window(w.app_name, w.title, keywords)
    ]
    if not windows:
        return None
    return max(windows, key=lambda w: w.rect.width() * w.rect.height())


def _find_window_by_id(window_id: str) -> Optional[WindowInfo]:
    for window in _list_windows():
        if window.window_id == window_id:
            return window
    return None


def _list_windows() -> list[WindowInfo]:
    system = platform.system().lower()
    if system == "windows":
        return _list_windows_windows()
    if system == "darwin":
        return _list_windows_macos()
    return _list_windows_linux()


def _list_windows_windows() -> list[WindowInfo]:
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return []

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    windows: list[WindowInfo] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    def enum_callback(hwnd: wintypes.HWND, _lparam: wintypes.LPARAM) -> wintypes.BOOL:
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        if not title:
            return True
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
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

        qt_rect = QtCore.QRect(rect.left, rect.top, width, height)
        windows.append(
            WindowInfo(
                window_id=str(hwnd),
                title=title,
                app_name=app_name,
                rect=qt_rect,
            )
        )
        return True

    user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
    return windows


def _list_windows_macos() -> list[WindowInfo]:
    quartz_windows = _list_windows_macos_quartz()
    if quartz_windows:
        return quartz_windows

    script = (
        'tell application "System Events"\n'
        "set appList to application processes whose visible is true\n"
        'set output to ""\n'
        "repeat with proc in appList\n"
        "set appName to name of proc\n"
        "repeat with w in windows of proc\n"
        "set windowName to name of w\n"
        "set windowId to id of w\n"
        "set winPos to position of w\n"
        "set winSize to size of w\n"
        'set output to output & windowId & "||" & appName & "||" & windowName & '
        '"||" & item 1 of winPos & "," & item 2 of winPos & "," & '
        'item 1 of winSize & "," & item 2 of winSize & "\\n"\n'
        "end repeat\n"
        "end repeat\n"
        "return output\n"
        "end tell"
    )
    result = _run_command(["osascript", "-e", script])
    if not result:
        return []
    windows: list[WindowInfo] = []
    for line in result.splitlines():
        parts = line.split("||")
        if len(parts) != 4:
            continue
        window_id, app_name, title, rect_csv = parts
        rect_parts = rect_csv.split(",")
        if len(rect_parts) != 4:
            continue
        try:
            x, y, width, height = (int(val) for val in rect_parts)
        except ValueError:
            continue
        if width <= 0 or height <= 0:
            continue
        windows.append(
            WindowInfo(
                window_id=str(window_id),
                title=title,
                app_name=app_name or None,
                rect=QtCore.QRect(x, y, width, height),
            )
        )
    return windows


def _list_windows_macos_quartz() -> list[WindowInfo]:
    try:
        import Quartz  # type: ignore
    except Exception:
        return []

    options = Quartz.kCGWindowListOptionOnScreenOnly
    window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
    if not window_list:
        return []

    windows: list[WindowInfo] = []
    for window in window_list:
        bounds = window.get("kCGWindowBounds")
        if not bounds:
            continue
        width = int(bounds.get("Width", 0))
        height = int(bounds.get("Height", 0))
        if width <= 0 or height <= 0:
            continue
        title = window.get("kCGWindowName") or ""
        app_name = window.get("kCGWindowOwnerName") or None
        window_id = window.get("kCGWindowNumber")
        if window_id is None:
            continue
        rect = _qt_rect_from_cg_bounds(bounds, width, height)
        windows.append(
            WindowInfo(
                window_id=str(window_id),
                title=title,
                app_name=app_name,
                rect=rect,
            )
        )
    return windows


def _qt_rect_from_cg_bounds(
    bounds: dict,
    width: int,
    height: int,
) -> QtCore.QRect:
    x = int(bounds.get("X", 0))
    y = int(bounds.get("Y", 0))
    y = _macos_flip_y(y, height)
    return QtCore.QRect(x, y, width, height)


def _macos_flip_y(y: int, height: int) -> int:
    app = QtWidgets.QApplication.instance()
    if app is None:
        return y
    screen = app.primaryScreen()
    if screen is None:
        return y
    geo = screen.geometry()
    return geo.y() + geo.height() - (y + height)


def _list_windows_linux() -> list[WindowInfo]:
    root_output = _run_command(["xprop", "-root", "_NET_CLIENT_LIST"])
    if not root_output:
        return []
    ids = re.findall(r"0x[0-9a-fA-F]+", root_output)
    windows: list[WindowInfo] = []
    for window_id in ids:
        title = _parse_xprop_value(
            _run_command(["xprop", "-id", window_id, "_NET_WM_NAME"])
        )
        if title is None:
            title = _parse_xprop_value(
                _run_command(["xprop", "-id", window_id, "WM_NAME"])
            )
        if not title:
            continue
        app_name = _parse_xprop_value(
            _run_command(["xprop", "-id", window_id, "WM_CLASS"]),
            prefer_last=True,
        )
        rect = _xwininfo_rect(window_id)
        if rect is None:
            continue
        windows.append(
            WindowInfo(
                window_id=window_id.lower(),
                title=title,
                app_name=app_name,
                rect=rect,
            )
        )
    return windows


def _xwininfo_rect(window_id: str) -> Optional[QtCore.QRect]:
    output = _run_command(["xwininfo", "-id", window_id])
    if not output:
        return None
    x_match = re.search(r"Absolute upper-left X:\s+(-?\d+)", output)
    y_match = re.search(r"Absolute upper-left Y:\s+(-?\d+)", output)
    w_match = re.search(r"Width:\s+(\d+)", output)
    h_match = re.search(r"Height:\s+(\d+)", output)
    if not (x_match and y_match and w_match and h_match):
        return None
    x = int(x_match.group(1))
    y = int(y_match.group(1))
    width = int(w_match.group(1))
    height = int(h_match.group(1))
    if width <= 0 or height <= 0:
        return None
    return QtCore.QRect(x, y, width, height)


def _set_window_rect(window: WindowInfo, rect: QtCore.QRect) -> bool:
    system = platform.system().lower()
    if system == "darwin":
        return _set_window_rect_macos(window, rect)
    if system == "windows":
        return False
    return False


def _set_window_rect_macos(window: WindowInfo, rect: QtCore.QRect) -> bool:
    if not window.app_name:
        return False
    app_name = _escape_osascript_string(window.app_name)
    title = _escape_osascript_string(window.title or "")
    if title:
        window_selector = f'first window whose name is "{title}"'
    else:
        window_selector = "front window"
    script = (
        'tell application "System Events"\n'
        f'tell process "{app_name}"\n'
        f'set position of {window_selector} to {{{rect.x()}, {rect.y()}}}\n'
        f'set size of {window_selector} to {{{rect.width()}, {rect.height()}}}\n'
        "end tell\n"
        "end tell"
    )
    result = _run_command_with_status(["osascript", "-e", script])
    if result is None:
        return False
    stdout, stderr, code = result
    if code != 0:
        print(f"make_window_smaller: osascript failed: {stderr or stdout}")
        return False
    return True


def _escape_osascript_string(value: str) -> str:
    return value.replace('"', '\\"')


def _run_command_with_status(args: Sequence[str]) -> Optional[tuple[str, str, int]]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def _macos_accessibility_trusted() -> bool:
    if platform.system().lower() != "darwin":
        return True
    try:
        import Quartz  # type: ignore
    except Exception:
        return True
    try:
        return bool(Quartz.AXIsProcessTrusted())
    except Exception:
        return True


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
