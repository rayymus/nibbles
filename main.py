from slack_detection.input_recording import InputActivityFilter
from slack_detection.global_input import start_global_input_monitor
from slack_detection.detection import (
    SlackDetectionState,
    detect_scrolling,
    detect_inactivity,
    detect_active_slacking_window,
)
from slack_detection.__init__ import set_sleep_state_getter, is_sleeping
from annoyed_actions import bite, make_window_smaller, slap_cursor, splat, reset_splat
from sleep_state import wake_up, sleep
from utils import preload_sound_effects
from CONFIG import *

import os
import sys
import time
import random
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets


POKE_DIR = Path(__file__).parent / "poke_for_fun"
if str(POKE_DIR) not in sys.path:
    sys.path.insert(0, str(POKE_DIR))

from hamster_states import HamsterState, ReactionType
from hamster_model import HamsterModel
from hamster_dabrain import on_poke, update


class Nibbles(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Nibbles")
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Window
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setWindowFlag(QtCore.Qt.WindowDoesNotAcceptFocus, True)
        self.setFixedSize(500, 500)
        self.setMouseTracking(True)

        #  Debug text
        self.debug_label = QtWidgets.QLabel(self)
        self.debug_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.debug_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.debug_label.setStyleSheet("QLabel { color: white; font-size: 10pt; }")
        self.debug_label.move(6, 6)
        self.debug_label.resize(self.size())

        # --- hamster model + assets ---
        self.ham = HamsterModel()
        self.ham.user_scale = 0.5
        self.assets_dir = Path(__file__).parent / "sprites"
        self._load_assets()
        self._center_hamster()

        # --- input/drag tracking ---
        self.dragging = False
        self.drag_moved = False
        self.drag_targeted = False
        self.drag_sprite_active = False
        self.drag_offset = QtCore.QPoint()
        self.press_pos: QtCore.QPoint | None = None
        self.click_move_threshold = 5  # px
        self.poke_on_press = False
        self.long_press_triggered = False
        self.long_press_duration_ms = 500
        self.long_press_timer = QtCore.QTimer(self)
        self.long_press_timer.setSingleShot(True)
        self.long_press_timer.timeout.connect(self._trigger_long_press) 

        # --- scale limits ---
        self.min_scale = 0.4
        self.max_scale = 2.5
        self.scroll_sensitivity = 0.08

        self._rotation_deg = 0
        self._flip_x = False

        # --- animation loop ---
        self.last_frame_time = time.time()
        self.anim_timer = QtCore.QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(16)  # ~60 FPS

        self.sleeping = False
        self.slack_state = SlackDetectionState()

        set_sleep_state_getter(lambda: self.sleeping)

        self.input_filter = InputActivityFilter(self.slack_state)
        QtWidgets.QApplication.instance().installEventFilter(self.input_filter)
        self.global_input_stop = start_global_input_monitor(self.slack_state)

        self.slack_check_timer = QtCore.QTimer(self)
        self.slack_check_timer.setInterval(20)
        self.slack_check_timer.timeout.connect(self.check_slacking)
        self.slack_check_timer.start()
        self.last_slap_time = 0.0
        self.slap_cooldown_s = 3.0
        self._debug_last_update = 0.0
        self._debug_interval_s = 0.2

    def check_slacking(self) -> None:
        if is_sleeping(): #  When sleeping, slacking tracking is turned off
            return

        #  Scrolling social media
        scrolling = detect_scrolling(
            self.slack_state,
            min_events=REELS_SCROLLED,
            min_period_s=0.62,
            max_period_s=TIME_PER_REEL+TIME_PER_REEL_DEVIATION,
            max_jitter_ratio=1,
        )

        #  Daydreaming
        idle = detect_inactivity(self.slack_state, idle_seconds=DAYDREAMING_THRESHOLD)

        #  Straight slacking
        window_slack = detect_active_slacking_window(
            self.slack_state,
            threshold_seconds=SLACKING_THRESHOLD,
        )
        if scrolling or idle or window_slack:
            #  Reset
            self.slack_state.click_timestamps.clear() 
            self.slack_state.scroll_timestamps.clear()
            self.slack_state.last_input_time = 0

            if scrolling: #  Active slacking
                print("Scrolling")
                self._slap_cursor_if_ready()
                # possible_actions = ["make_window_smaller", "bite", "slap_cursor", "splat"]
                
            elif idle: 
                print("Idle")
                if detect_active_slacking_window(
                    self.slack_state,
                    threshold_seconds=0
                ):
                    possible_actions = ["make_window_smaller", "bite", "splat"]
                else:
                    splat(self)
            else: #  Active slacking
                print("window slack")
                possible_actions = ["make_window_smaller", "bite", "splat"]

            match random.choice(possible_actions):
                case "make_window_smaller":
                    make_window_smaller(self)
                case "bite":
                    bite(self)
                case "slap_cursor":
                    self._slap_cursor_if_ready()
                case "splat":
                    splat(self)

    def _load_assets(self) -> None:
        def load(name: str) -> QtGui.QPixmap:
            pixmap = QtGui.QPixmap(str(self.assets_dir / name))
            if pixmap.isNull():
                raise FileNotFoundError(f"Could not load {self.assets_dir / name}")
            return pixmap

        self.pm_idle = load("idle.png")
        self.pm_drag = load("drag.png")
        self.pm_angry = load("walk_1.png")
        self.pm_suspicious = load("walk_2.png")
        self.pm_pancake = load("pancake.png")
        self.pm_splat = load("splat.png")
        self.pm_bite = load("bite.png")

    def _center_hamster(self) -> None:
        self.ham.x = self.width() / 2
        self.ham.y = self.height() / 2

    def _current_non_pancake_pixmap(self) -> QtGui.QPixmap:
        if self.ham.state == HamsterState.SINGLE_REACT:
            if self.ham.reaction == ReactionType.ANGRY:
                return self.pm_angry
            return self.pm_suspicious
        if self.ham.state == HamsterState.SPLAT:
            return self.pm_splat
        elif self.ham.state == HamsterState.BITE:
            return self.pm_bite
        return self.pm_idle

    def _current_pixmap_and_squash(self) -> tuple[QtGui.QPixmap, float, float]:
        if self.drag_sprite_active:
            return self.pm_drag, 1.0, 1.0
        if self.ham.state == HamsterState.PANCAKE:
            t = self.ham.pancake_t
            if t < 0.999:
                pm = self.pm_idle
                sx = 1.0 + 0.35 * t
                sy = 1.0 - 0.65 * t
                return pm, sx, sy
            return self.pm_pancake, 1.0, 1.0
        return self._current_non_pancake_pixmap(), 1.0, 1.0

    def hamster_rect(self) -> QtCore.QRectF:
        pm, _, _ = self._current_pixmap_and_squash()
        width = pm.width() * self.ham.user_scale
        height = pm.height() * self.ham.user_scale
        return QtCore.QRectF(
            self.ham.x - width / 2,
            self.ham.y - height / 2,
            width,
            height,
        )

    def _hit_test(self, pos: QtCore.QPoint) -> bool:
        return self.hamster_rect().contains(QtCore.QPointF(pos))

    def _tick(self) -> None:
        now = time.time()
        dt = now - self.last_frame_time
        self.last_frame_time = now
        update(self.ham, dt, now)
        if self.drag_sprite_active and not (QtWidgets.QApplication.mouseButtons() & QtCore.Qt.LeftButton):
            self.drag_sprite_active = False
        clamped = self._clamp_to_screen(self.pos())
        if clamped != self.pos():
            self.move(clamped)
        if now - self._debug_last_update >= self._debug_interval_s:
            self._debug_last_update = now
            self.debug_label.setText(
                "Input: clicks={clicks} scrolls={scrolls} keys={keys} "
                "last={last:.2f}s global={status} g_events={g_events}".format(
                    clicks=len(self.slack_state.click_timestamps),
                    scrolls=len(self.slack_state.scroll_timestamps),
                    keys=len(self.slack_state.key_timestamps),
                    last=now - self.slack_state.last_input_time,
                    status=self.slack_state.global_input_status,
                    g_events=self.slack_state.global_input_events,
                )
            )
        self.update()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.debug_label.resize(self.size())
        self._center_hamster()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.LeftButton:
            super().mousePressEvent(event)
            return
        if self._is_splat_active():
            self.long_press_timer.stop()
            self.long_press_triggered = False
            return
        hit = self._hit_test(event.pos())
        self.press_pos = event.pos()
        self.drag_moved = False
        self.dragging = True
        self.drag_targeted = hit
        self.drag_sprite_active = False
        self.poke_on_press = False
        self.long_press_triggered = False
        self.long_press_timer.stop()
        self.drag_offset = event.globalPos() - self.frameGeometry().topLeft()
        if hit:
            self.long_press_timer.start(self.long_press_duration_ms)
        else:
            self.long_press_timer.stop()
            self.update()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if not (event.buttons() & QtCore.Qt.LeftButton) or not self.dragging:
            super().mouseMoveEvent(event)
            return
        if self._is_splat_active():
            return
        if self.press_pos is not None:
            moved = (event.pos() - self.press_pos).manhattanLength()
            if moved > self.click_move_threshold:
                self.drag_moved = True
                self.long_press_timer.stop()
                if self.drag_targeted and not self.long_press_triggered:
                    self.drag_sprite_active = True
                    self.update()
        if not self.long_press_triggered:
            target_pos = event.globalPos() - self.drag_offset
            self.move(self._clamp_to_screen(target_pos))

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.LeftButton:
            super().mouseReleaseEvent(event)
            return
        if self._is_splat_active():
            self.long_press_timer.stop()
            self.press_pos = None
            return
        pos = event.pos()
        was_click = not self.drag_moved
        self.dragging = False
        self.drag_targeted = False
        self.drag_sprite_active = False
        self.long_press_timer.stop()
        if self.long_press_triggered:
            self.press_pos = None
            return
        
        if is_sleeping(): return
        if was_click and self._hit_test(pos) and not self.poke_on_press:
            on_poke(self.ham)
        self.press_pos = None

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not self._hit_test(event.pos()):
            return
        steps = event.angleDelta().y() / 120.0
        factor = 1.0 + steps * self.scroll_sensitivity
        self.ham.user_scale *= factor
        self.ham.user_scale = max(self.min_scale, min(self.max_scale, self.ham.user_scale))
        self.update()

    def _clamp_to_screen(self, pos: QtCore.QPoint) -> QtCore.QPoint:
        screen = QtGui.QGuiApplication.screenAt(pos)
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return pos
        geo = screen.availableGeometry()
        max_x = geo.right() - self.width() + 1
        max_y = geo.bottom() - self.height() + 1
        x = max(geo.left(), min(max_x, pos.x()))
        y = max(geo.top(), min(max_y, pos.y()))
        return QtCore.QPoint(x, y)

    def _slap_cursor_if_ready(self) -> None:
        now = time.time()
        if now - self.last_slap_time < self.slap_cooldown_s:
            return
        slap_cursor(self)
        self.last_slap_time = now

    def _trigger_long_press(self) -> None:
        if (
            not self.dragging
            or self.drag_moved
            or self.press_pos is None
            or not (QtWidgets.QApplication.mouseButtons() & QtCore.Qt.LeftButton)
        ):
            return
        if self._is_splat_active():
            return
        if not self._hit_test(self.press_pos):
            return
        self.long_press_triggered = True
        if self.sleeping:
            wake_up(self)
        else:
            sleep(self)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton and self._is_splat_active():
            reset_splat(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _is_splat_active(self) -> bool:
        return (
            getattr(self, "_splat_state", None) is not None
            or self.ham.state == HamsterState.SPLAT
        )
        
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        if self.sleeping:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        pm, sx, sy = self._current_pixmap_and_squash()
        base_w = pm.width() * self.ham.user_scale
        base_h = pm.height() * self.ham.user_scale
        draw_w = base_w * sx
        draw_h = base_h * sy

        target = QtCore.QRectF(
            self.ham.x - draw_w / 2,
            self.ham.y - draw_h / 2,
            draw_w,
            draw_h,
        )
        if self._rotation_deg % 360 or self._flip_x:
            painter.save()
            center = target.center()
            painter.translate(center)
            if self._rotation_deg % 360:
                painter.rotate(self._rotation_deg)
            if self._flip_x:
                painter.scale(-1, 1)
            painter.translate(-center)
            painter.drawPixmap(target, pm, QtCore.QRectF(pm.rect()))
            painter.restore()
        else:
            painter.drawPixmap(target, pm, QtCore.QRectF(pm.rect()))

    def move_to_bottom_right(self) -> None:
        # Use the screen under the mouse, fallback to primary
        screen = QtGui.QGuiApplication.screenAt(QtGui.QCursor.pos())
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return

        geo = screen.availableGeometry()  # respects taskbar / dock
        x = geo.right() - self.width() + 1
        y = geo.bottom() - self.height() + 1
        self.move(x, y)

    def rotate(self, degree: float) -> None:
        self._rotation_deg = (self._rotation_deg + degree) % 360
        self.update()

    def flip_direction(self) -> None:
        self._flip_x = not self._flip_x
        self.update()


def main() -> int:
    plugins_path = QtCore.QLibraryInfo.location(QtCore.QLibraryInfo.PluginsPath)
    if plugins_path:
        os.environ.setdefault("QT_PLUGIN_PATH", plugins_path)
        QtCore.QCoreApplication.addLibraryPath(plugins_path)

    app = QtWidgets.QApplication(sys.argv)
    preload_sound_effects()
    pet = Nibbles()
    pet.show()
    pet.move_to_bottom_right()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
