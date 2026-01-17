# handles the mouse input stuff and fwd it to the functions in dabrain file

import time
from pathlib import Path
from typing import Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt5.QtGui import QPainter, QFont, QPixmap
from PyQt5.QtWidgets import QWidget

from PokeForFun.hamster_states import HamsterState, ReactionType
from PokeForFun.hamster_model import HamsterModel
from PokeForFun.hamster_dabrain import on_poke, update

class HamsterWidget(QWidget):
    """
    UI layer:
    - Handles input (drag, scroll, poke)
    - Calls FSM (on_poke / update)
    - Renders hamster PNGs + speech bubble
    """

    def __init__(self, assets_dir: str = "../sprites"):
        super().__init__()

        # --- window setup ---
        self.setWindowTitle("Hamster")
        self.resize(900, 600)

        # --- model ---
        self.ham = HamsterModel()

        # --- assets ---
        self.assets_dir = Path(assets_dir)
        self._load_assets()

        # --- input/drag tracking ---
        self.dragging = False
        self.drag_offset = QPointF(0, 0)
        self.press_pos: Optional[QPointF] = None
        self.click_move_threshold = 5  # px

        # --- scale limits ---
        self.min_scale = 0.4
        self.max_scale = 2.5
        self.scroll_sensitivity = 0.08

        # --- frame timing ---
        self.last_frame_time = time.time()

        # --- update loop ---
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)  # ~60 FPS

    # ------------------------
    # Assets / sprite selection
    # ------------------------
    def _load_assets(self) -> None:
        def load(name: str) -> QPixmap:
            pm = QPixmap(str(self.assets_dir / name))
            if pm.isNull():
                raise FileNotFoundError(f"Could not load {self.assets_dir / name}")
            return pm

        # NOTE: keep your filenames as-is; just ensure they exist.
        self.pm_idle = load("idle.jpg")
        self.pm_angry = load("walk_1.jpg")
        self.pm_suspicious = load("walk_2.png")
        self.pm_pancake = load("pancake.jpg")

    def _current_non_pancake_pixmap(self) -> QPixmap:
        if self.ham.state == HamsterState.SINGLE_REACT:
            if self.ham.reaction == ReactionType.ANGRY:
                return self.pm_angry
            else:
                return self.pm_suspicious
        return self.pm_idle

    def _current_pixmap_and_squash(self) -> Tuple[QPixmap, float, float]:
        if self.ham.state == HamsterState.PANCAKE:
            t = self.ham.pancake_t

            if t < 0.999:
                pm = self.pm_idle
                sx = 1.0 + 0.35 * t
                sy = 1.0 - 0.65 * t
                return pm, sx, sy

            return self.pm_pancake, 1.0, 1.0

        return self._current_non_pancake_pixmap(), 1.0, 1.0

    # ------------------------
    # Geometry / hitbox helpers
    # ------------------------
    def hamster_rect(self) -> QRectF:
        pm, _, _ = self._current_pixmap_and_squash()
        w = pm.width() * self.ham.user_scale
        h = pm.height() * self.ham.user_scale
        return QRectF(self.ham.x - w / 2, self.ham.y - h / 2, w, h)

    def _hit_test(self, pos: QPointF) -> bool:
        return self.hamster_rect().contains(pos)

    # ------------------------
    # Main loop
    # ------------------------
    def _tick(self) -> None:
        now = time.time()
        dt = now - self.last_frame_time
        self.last_frame_time = now

        update(self.ham, dt, now)
        self.update()

    # ------------------------
    # Input events (PyQt5)
    # ------------------------
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return

        pos = QPointF(e.localPos())  # QPointF
        self.press_pos = pos

        if self._hit_test(pos):
            self.dragging = True
            self.drag_offset = QPointF(pos.x() - self.ham.x, pos.y() - self.ham.y)

    def mouseMoveEvent(self, e):
        if not self.dragging:
            return

        pos = QPointF(e.localPos())
        self.ham.x = pos.x() - self.drag_offset.x()
        self.ham.y = pos.y() - self.drag_offset.y()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return

        pos = QPointF(e.localPos())
        self.dragging = False

        if not self._hit_test(pos):
            self.press_pos = None
            return

        if self.press_pos is not None:
            moved = (pos - self.press_pos).manhattanLength()
            if moved <= self.click_move_threshold:
                on_poke(self.ham)

        self.press_pos = None

    def wheelEvent(self, e):
        # e.pos() is QPoint (int) - convert to QPointF for hit test
        cursor = QPointF(e.pos())
        if not self._hit_test(cursor):
            return

        steps = e.angleDelta().y() / 120.0
        factor = 1.0 + steps * self.scroll_sensitivity

        self.ham.user_scale *= factor
        self.ham.user_scale = max(self.min_scale, min(self.max_scale, self.ham.user_scale))

    # ------------------------
    # Rendering
    # ------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        pm, sx, sy = self._current_pixmap_and_squash()

        base_w = pm.width() * self.ham.user_scale
        base_h = pm.height() * self.ham.user_scale

        draw_w = base_w * sx
        draw_h = base_h * sy

        target = QRectF(
            self.ham.x - draw_w / 2,
            self.ham.y - draw_h / 2,
            draw_w,
            draw_h
        )

        # FIX: QRectF target requires QRectF source (not QRect)
        p.drawPixmap(target, pm, QRectF(pm.rect()))

        # speech bubble
        #if self.ham.bubble_text:
           # p.setFont(QFont("Arial", 11))

            #bubble_w = 280
            #bubble_h = 50
            #bubble = QRectF(
                #target.left(),
                #target.top() - bubble_h - 10,
                #bubble_w,
                #bubble_h
            #)

            #p.drawRoundedRect(bubble, 12, 12)
            #p.drawText(
                #bubble.adjusted(10, 6, -10, -6),
                #Qt.AlignLeft | Qt.AlignVCenter,
                #self.ham.bubble_text
            #)
