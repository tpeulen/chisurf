import sys

from chisurf.gui import QtWidgets

from . import gui


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = gui.Structure2Transfer()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
