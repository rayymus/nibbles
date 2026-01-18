from __future__ import annotations

import time
from typing import Optional

from PyQt5 import QtCore

from . import SlackDetectionState


class InputActivityFilter(QtCore.QObject):
    """Qt event filter for capturing app-local input activity."""

    def __init__(self, state: SlackDetectionState) -> None:
        super().__init__()
        self.state = state

    def eventFilter(self, _obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        now = time.time()
        event_type = event.type()
        if event_type == QtCore.QEvent.MouseButtonPress:
            record_mouse_click(self.state, now)
        elif event_type == QtCore.QEvent.Wheel:
            record_mouse_scroll(self.state, now)
        elif event_type == QtCore.QEvent.KeyPress:
            record_keypress(self.state, now)
        elif event_type == QtCore.QEvent.MouseMove:
            record_mouse_move(self.state, now)
        return False


#  Recording input
def record_mouse_click(state: SlackDetectionState, timestamp: Optional[float] = None) -> None:
    now = time.time() if timestamp is None else timestamp
    state.last_input_time = now
    state.click_timestamps.append(now)


def record_mouse_scroll(
    state: SlackDetectionState,
    timestamp: Optional[float] = None,
    debounce_s: float = 0.25,
) -> None:
    now = time.time() if timestamp is None else timestamp
    state.last_input_time = now
    last_event = getattr(state, "last_scroll_event_time", 0.0)
    if (now - last_event) >= debounce_s:
        state.scroll_timestamps.append(now)
    state.last_scroll_event_time = now


def record_keypress(state: SlackDetectionState, timestamp: Optional[float] = None) -> None:
    now = time.time() if timestamp is None else timestamp
    state.last_input_time = now
    state.key_timestamps.append(now)


def record_mouse_move(state: SlackDetectionState, timestamp: Optional[float] = None) -> None:
    now = time.time() if timestamp is None else timestamp
    state.last_input_time = now
