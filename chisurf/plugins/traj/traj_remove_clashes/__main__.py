import sys

from qtpy import QtWidgets

from .widget import RemoveClashedFrames


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = RemoveClashedFrames()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
