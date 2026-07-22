import sys

from qtpy import QtWidgets

from .widget import RotateTranslateTrajectoryWidget


def main():
    """Launch the Rotate/Translate-Trajectory tool as a standalone window."""
    app = QtWidgets.QApplication(sys.argv)
    win = RotateTranslateTrajectoryWidget()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
