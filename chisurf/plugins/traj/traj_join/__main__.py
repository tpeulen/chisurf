import sys

from chisurf.gui import QtWidgets

from .widget import JoinTrajectoriesWidget


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = JoinTrajectoriesWidget()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
