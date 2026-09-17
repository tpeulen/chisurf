"""A pane for output too long to belong in the scrollback.

``obj?``, ``%history`` and ``%lsmagic`` can each produce hundreds of lines. Left
in the transcript they bury everything you did before them, which is the one
thing a transcript is for. The pager holds that output beside the console until
it is dismissed.
"""

from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.chinsole.theme import ConsoleTheme, stylesheet

__all__ = ["PagerWidget", "MODES"]

#: Where the pager appears. ``none`` sends paged output to the scrollback
#: instead, which is what a user who dislikes the pane will want.
MODES = ("vsplit", "hsplit", "inside", "none")


class PagerWidget(QtWidgets.QWidget):
    """Displays long console output in a dismissable pane.

    Parameters
    ----------
    parent : QtWidgets.QWidget, optional
    theme : ConsoleTheme, optional
    """

    #: Emitted when the pager is dismissed.
    closed = QtCore.Signal()

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        theme: ConsoleTheme | None = None,
    ) -> None:
        super().__init__(parent)
        # A plain QWidget subclass ignores a stylesheet background unless this
        # is set, so the header kept the Qt default light grey against a dark
        # console -- it looked like a strip of a different application.
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(6, 2, 2, 2)
        self._title = QtWidgets.QLabel("")
        self._title.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        close = QtWidgets.QToolButton(self)
        close.setText("✕")
        close.setToolTip("Close (Esc or q)")
        close.setAutoRaise(True)
        close.clicked.connect(self.dismiss)
        header.addWidget(self._title)
        header.addStretch()
        header.addWidget(close)
        layout.addLayout(header)

        self.view = QtWidgets.QTextEdit(self)
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        self.view.installEventFilter(self)
        layout.addWidget(self.view)

        self._find = QtWidgets.QLineEdit(self)
        self._find.setPlaceholderText("Find in this page…  (Enter for next)")
        self._find.returnPressed.connect(self._find_next)
        self._find.hide()
        layout.addWidget(self._find)

        if theme is not None:
            self.apply_theme(theme)
        self.hide()

    def apply_theme(self, theme: ConsoleTheme) -> None:
        """Adopt *theme*.

        Parameters
        ----------
        theme : ConsoleTheme
        """
        # The whole pane, not just the text view: the header sat at the Qt
        # default light grey against a dark console, which read as a piece of a
        # different application.
        self.setStyleSheet(
            f"QWidget {{ background-color: {theme.background}; color: {theme.foreground}; }}"
            f"QToolButton {{ border: none; color: {theme.foreground}; }}"
            f"QToolButton:hover {{ background-color: {theme.selection_bg}; }}"
            f"QLineEdit {{ background-color: {theme.background};"
            f" color: {theme.foreground};"
            f" border: 1px solid {theme.prompt_continuation}; }}"
        )
        self.view.setStyleSheet(stylesheet(theme))
        self._title.setStyleSheet(f"color: {theme.prompt_in}; font-weight: bold;")

    def show_text(self, text: str, *, title: str = "", html: bool = False) -> None:
        """Display *text*.

        Parameters
        ----------
        text : str
        title : str, optional
            Shown in the header, e.g. what was asked about.
        html : bool, optional
        """
        self._title.setText(title or "Output")
        if html:
            self.view.setHtml(text)
        else:
            self.view.setPlainText(text)
        self.view.moveCursor(QtGui.QTextCursor.Start)
        self.show()
        self.view.setFocus()

    def dismiss(self) -> None:
        """Hide the pager and hand focus back."""
        self.hide()
        self._find.hide()
        self.closed.emit()

    def set_font(self, font: QtGui.QFont) -> None:
        """Use *font* for the paged text.

        Parameters
        ----------
        font : QtGui.QFont
        """
        self.view.setFont(font)
        self._find.setFont(font)

    def eventFilter(self, obj, event):  # noqa: N802 - Qt override
        """Handle the pager's keys.

        Parameters
        ----------
        obj : QtCore.QObject
        event : QtCore.QEvent

        Returns
        -------
        bool
        """
        if obj is not self.view or event.type() != QtCore.QEvent.KeyPress:
            return super().eventFilter(obj, event)

        key = event.key()
        if key in (QtCore.Qt.Key_Escape, QtCore.Qt.Key_Q):
            self.dismiss()
            return True
        if key == QtCore.Qt.Key_Space:
            self._scroll_page(+1)
            return True
        if key == QtCore.Qt.Key_Backspace:
            self._scroll_page(-1)
            return True
        if key == QtCore.Qt.Key_Slash or (
            key == QtCore.Qt.Key_F and event.modifiers() & QtCore.Qt.ControlModifier
        ):
            self._find.show()
            self._find.setFocus()
            self._find.selectAll()
            return True
        return super().eventFilter(obj, event)

    def _scroll_page(self, direction: int) -> None:
        """Scroll one viewport-height.

        Parameters
        ----------
        direction : int
            ``+1`` down, ``-1`` up.
        """
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.value() + direction * bar.pageStep())

    def _find_next(self) -> None:
        """Move to the next match of the find box, wrapping at the end."""
        needle = self._find.text()
        if not needle:
            return
        if not self.view.find(needle):
            self.view.moveCursor(QtGui.QTextCursor.Start)
            self.view.find(needle)
