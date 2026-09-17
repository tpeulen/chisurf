import sys

from qtpy.QtWidgets import QApplication

from .widget import AlignTrajectoryWidget


def main():
    app = QApplication(sys.argv)
    win = AlignTrajectoryWidget()
    win.show()
    app.exec_()


if __name__ == "__main__":
    main()
