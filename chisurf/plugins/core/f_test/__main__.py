import sys

from chisurf.gui import QtWidgets
from chisurf.plugins.core.f_test.gui.tool import FTestTool


def main():
    """Launch the F-test / χ²-max calculator as a standalone window."""
    app = QtWidgets.QApplication(sys.argv)
    win = FTestTool()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
