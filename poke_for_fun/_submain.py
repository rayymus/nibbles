import sys
from PyQt5.QtWidgets import QApplication
from poke_for_fun._hamster_action import HamsterWidget

def main():
    app = QApplication(sys.argv)

    w = HamsterWidget()
    w.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
