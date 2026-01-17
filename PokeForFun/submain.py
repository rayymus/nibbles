import sys
from PyQt5.QtWidgets import QApplication
from PokeForFun.hamster_action import HamsterWidget

def main():
    app = QApplication(sys.argv)

    w = HamsterWidget()
    w.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
