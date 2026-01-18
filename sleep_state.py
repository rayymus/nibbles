from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets
from pathlib import Path

from hamster_dabrain import enter_state
from hamster_states import HamsterState
from slack_detection import set_sleeping
from utils import play_audio


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
    print("awake")
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

    play_audio("sound_effects/sleep.mp3")

    movie = QtGui.QMovie(str(gif_file))
    label.setMovie(movie)
    label.resize(hamster_widget.size())
    label.show()
    movie.start()

    if hasattr(hamster_widget, "sleeping"):
        hamster_widget.sleeping = True
    set_sleeping(True)
    print("asleep")
    return movie