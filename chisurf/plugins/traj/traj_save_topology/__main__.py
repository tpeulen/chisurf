import sys

from qtpy import QtWidgets

from .widget import SaveTopology


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = SaveTopology()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
