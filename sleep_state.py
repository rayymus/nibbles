from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

from poke_for_fun.hamster_dabrain import enter_state
from poke_for_fun.hamster_states import HamsterState
from slack_detection import set_sleeping
from pathlib import Path


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