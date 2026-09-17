import sys

from qtpy.QtWidgets import QApplication

from .widget import MDConverter


def main():
    app = QApplication(sys.argv)
    gui = MDConverter()
    gui.show()
    app.exec_()


if __name__ == "__main__":
    main()
