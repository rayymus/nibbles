from __future__ import annotations

import time
from typing import Optional, Sequence, Tuple

from . import SlackDetectionState, _is_periodic, get_active_window_info
from CONFIG import *
from utils import get_open_window_info


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
