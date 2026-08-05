"""The completion list and the signature tooltip.

Key handling lives in one place -- :meth:`CompletionPopup.handle_key`, called
first from the view's ``keyPressEvent``. Splitting it between an event filter on
the popup and another on the editor is how a completer ends up executing the
cell when you meant to accept a completion.
"""

from __future__ import annotations

import typing

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.chinsole.theme import ConsoleTheme

__all__ = ["CompletionPopup", "CallTipWidget"]

#: A glyph per completion kind, so the list says what it is offering.
_GLYPHS = {
    "name": "·",
    "attr": "▸",
    "key": "⌘",
    "path": "🗀",
    "magic": "%",
    "module": "▣",
}


class CompletionPopup(QtWidgets.QListWidget):
    """A completion list shown beneath the cursor.

    Parameters
    ----------
    parent : QtWidgets.QWidget
    """

    #: Emitted with the chosen completion.
    accepted = QtCore.Signal(str)
    #: Emitted when the popup is dismissed without a choice.
    cancelled = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.itemClicked.connect(lambda item: self._accept(item))
        self._result = None
        self.hide()

    def show_for(
            self,
            result: typing.Any,
            anchor: QtCore.QPoint,
            font: QtGui.QFont,
            theme: ConsoleTheme,
    ) -> None:
        """Display *result* at *anchor*.

        Parameters
        ----------
        result : CompletionResult
        anchor : QtCore.QPoint
            Global position of the cursor.
        font : QtGui.QFont
        theme : ConsoleTheme
        """
        self._result = result
        self.clear()
        self.setFont(font)
        glyph = _GLYPHS.get(result.kind, "·")
        for match in result.matches:
            label = match.rpartition(".")[2] if result.kind == "attr" else match
            item = QtWidgets.QListWidgetItem(f"{glyph} {label}")
            item.setData(QtCore.Qt.UserRole, match)
            self.addItem(item)
        self.setCurrentRow(0)

        self.setStyleSheet(
            f"QListWidget {{ background: {theme.background}; color: {theme.foreground};"
            f" border: 1px solid {theme.prompt_continuation}; }}"
            f"QListWidget::item:selected {{ background: {theme.selection_bg};"
            f" color: {theme.selection_fg}; }}"
        )

        metrics = QtGui.QFontMetrics(font)
        widest = max(
            (metrics.horizontalAdvance(self.item(i).text()) for i in range(self.count())),
            default=80,
        )
        rows = min(self.count(), 12)
        width = min(widest + 40, int(self.parent().width() * 0.6))
        height = rows * (metrics.height() + 6) + 8

        # Flip above the cursor when there is no room below, so the list is
        # never clipped by the bottom of a short dock.
        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        top = anchor.y()
        if top + height > screen.bottom():
            top = anchor.y() - height - metrics.height()
        left = min(anchor.x(), screen.right() - width)
        self.setGeometry(left, top, width, height)
        self.show()

    def current_completion(self) -> str | None:
        """Return the highlighted completion.

        Returns
        -------
        str or None
        """
        item = self.currentItem()
        return item.data(QtCore.Qt.UserRole) if item else None

    def _accept(self, item: QtWidgets.QListWidgetItem | None = None) -> None:
        """Emit the chosen completion and hide.

        Parameters
        ----------
        item : QtWidgets.QListWidgetItem, optional
        """
        item = item or self.currentItem()
        if item is not None:
            self.accepted.emit(item.data(QtCore.Qt.UserRole))
        self.hide()

    def handle_key(self, event: QtGui.QKeyEvent) -> bool:
        """Handle a key press while the popup is visible.

        Parameters
        ----------
        event : QtGui.QKeyEvent

        Returns
        -------
        bool
            Whether the key was consumed. Enter accepting a completion returns
            ``True`` so the cell is *not* executed -- getting that wrong means
            choosing a completion also runs the line.
        """
        if not self.isVisible():
            return False
        key = event.key()

        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Tab):
            self._accept()
            return True
        if key == QtCore.Qt.Key_Escape:
            self.hide()
            self.cancelled.emit()
            return True
        if key == QtCore.Qt.Key_Up:
            self.setCurrentRow(max(0, self.currentRow() - 1))
            return True
        if key == QtCore.Qt.Key_Down:
            self.setCurrentRow(min(self.count() - 1, self.currentRow() + 1))
            return True
        if key in (QtCore.Qt.Key_PageUp, QtCore.Qt.Key_PageDown):
            step = -10 if key == QtCore.Qt.Key_PageUp else 10
            self.setCurrentRow(max(0, min(self.count() - 1, self.currentRow() + step)))
            return True
        if key in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Right, QtCore.Qt.Key_Home,
                   QtCore.Qt.Key_End):
            self.hide()
            return False

        text = event.text()
        if text and not (text.isalnum() or text in "_."):
            self.hide()
        return False


class CallTipWidget(QtWidgets.QLabel):
    """A signature tooltip shown above the cursor.

    Parameters
    ----------
    parent : QtWidgets.QWidget
    """

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent, QtCore.Qt.ToolTip)
        self.setTextFormat(QtCore.Qt.RichText)
        self.setWordWrap(True)
        self.setMargin(6)
        self.hide()

    def show_tip(
            self,
            tip: typing.Any,
            anchor: QtCore.QPoint,
            font: QtGui.QFont,
            theme: ConsoleTheme,
    ) -> None:
        """Display *tip* at *anchor*.

        Parameters
        ----------
        tip : CallTip
        anchor : QtCore.QPoint
        font : QtGui.QFont
        theme : ConsoleTheme
        """
        signature = self._emphasise_argument(tip.signature, tip.argument)
        body = tip.doc.split("\n\n")[0].strip() if tip.doc else ""
        html = f"<b>{_escape(tip.name)}</b>{signature}"
        if body:
            html += "<br><span style='opacity:0.8'>" + _escape(body).replace("\n", "<br>") + "</span>"

        self.setFont(font)
        self.setStyleSheet(
            f"QLabel {{ background: {theme.background}; color: {theme.foreground};"
            f" border: 1px solid {theme.prompt_continuation}; }}"
        )
        self.setText(html)
        self.adjustSize()
        self.setMaximumWidth(600)
        self.move(anchor.x(), anchor.y() - self.height() - 4)
        self.show()

    @staticmethod
    def _emphasise_argument(signature: str, index: int) -> str:
        """Bold the argument the cursor is on.

        Parameters
        ----------
        signature : str
        index : int

        Returns
        -------
        str
            HTML.
        """
        if not signature.startswith("(") or not signature.endswith(")"):
            return _escape(signature)
        inner = signature[1:-1]
        if not inner:
            return "()"
        # Split on top-level commas only, so a default like ``Dict[str, int]``
        # does not read as two arguments.
        parts: list[str] = []
        depth = 0
        current = ""
        for char in inner:
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
            if char == "," and depth == 0:
                parts.append(current)
                current = ""
                continue
            current += char
        parts.append(current)

        rendered = []
        for position, part in enumerate(parts):
            escaped = _escape(part)
            rendered.append(f"<b>{escaped}</b>" if position == index else escaped)
        return "(" + ",".join(rendered) + ")"


def _escape(text: str) -> str:
    """Escape *text* for inclusion in HTML.

    Parameters
    ----------
    text : str

    Returns
    -------
    str
    """
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
