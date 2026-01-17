from __future__ import annotations

import platform
import threading
import time
from typing import Callable, Optional

from . import SlackDetectionState
from .input_recording import (
    record_keypress,
    record_mouse_click,
    record_mouse_move,
    record_mouse_scroll,
)


def start_global_input_monitor(state: SlackDetectionState) -> Optional[Callable[[], None]]:
    """Start a macOS-only global input monitor. Returns a stop callback or None."""
    if platform.system().lower() != "darwin":
        state.global_input_status = "unsupported"
        return None

    try:
        import Quartz  # type: ignore
    except Exception:
        state.global_input_status = "missing pyobjc"
        print("Global input monitor unavailable: install pyobjc for Quartz access.")
        return None

    run_loop_holder: dict[str, object] = {}
    state.global_input_status = "starting"

    def _callback(_proxy, event_type, _event, _refcon):
        now = time.time()
        state.global_input_events += 1
        state.global_last_input_time = now
        if event_type == Quartz.kCGEventScrollWheel:
            record_mouse_scroll(state, now)
        elif event_type in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventRightMouseDown):
            record_mouse_click(state, now)
        elif event_type == Quartz.kCGEventKeyDown:
            record_keypress(state, now)
        elif event_type in (
            Quartz.kCGEventMouseMoved,
            Quartz.kCGEventLeftMouseDragged,
            Quartz.kCGEventRightMouseDragged,
        ):
            record_mouse_move(state, now)
        return _event

    def _run_loop():
        event_mask = (
            (1 << Quartz.kCGEventScrollWheel)
            | (1 << Quartz.kCGEventLeftMouseDown)
            | (1 << Quartz.kCGEventRightMouseDown)
            | (1 << Quartz.kCGEventKeyDown)
            | (1 << Quartz.kCGEventMouseMoved)
            | (1 << Quartz.kCGEventLeftMouseDragged)
            | (1 << Quartz.kCGEventRightMouseDragged)
        )
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGHIDEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            event_mask,
            _callback,
            None,
        )
        if not tap:
            state.global_input_status = "needs accessibility"
            print(
                "Global input monitor failed: enable Accessibility access for this app."
            )
            return
        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        run_loop = Quartz.CFRunLoopGetCurrent()
        run_loop_holder["loop"] = run_loop
        Quartz.CFRunLoopAddSource(run_loop, source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        state.global_input_status = "active"
        Quartz.CFRunLoopRun()

    thread = threading.Thread(target=_run_loop, name="GlobalInputMonitor", daemon=True)
    thread.start()

    def stop() -> None:
        run_loop = run_loop_holder.get("loop")
        if run_loop is not None:
            state.global_input_status = "stopped"
            Quartz.CFRunLoopStop(run_loop)

    return stop
