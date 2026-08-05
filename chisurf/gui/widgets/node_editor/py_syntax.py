"""Python code editor widget for the node editor.

The syntax highlighting it used to carry lived here as a near-duplicate of the
code editor's, and both have been replaced by the one implementation in
:mod:`chisurf.gui.syntax`. Only the editor widget is local now.

The module previously described itself as self-contained so ``node_editor``
could run without the chisurf GUI stack. That had stopped being true: importing
this module pulls ``chisurf.gui`` and ~465 modules regardless, because the
package lives underneath it.
"""

from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.syntax import PythonHighlighter, SyntaxHighlighter


class LineNumberArea(QtWidgets.QWidget):
    """Side widget that paints line numbers for CodeEditor.

    This is a lightweight variant of chisurf's line-number implementation and
    is intentionally self-contained.
    """

    def __init__(self, editor: "CodeEditor") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QtCore.QSize:  # type: ignore[override]
        return QtCore.QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        self._editor.line_number_area_paint_event(event)


class CodeEditor(QtWidgets.QPlainTextEdit):
    """Simple QPlainTextEdit with a line-number margin on the left."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        self.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)

        self._line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)

        self._current_line_color = QtGui.QColor(45, 45, 55, 120)

    # ----- Line number support -------------------------------------------
    def line_number_area_width(self) -> int:
        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num //= 10
            digits += 1
        space = 6 + self.fontMetrics().horizontalAdvance("9") * digits
        return space

    def update_line_number_area_width(self, _new_block_count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect: QtCore.QRect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QtCore.QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QtGui.QColor(30, 30, 35))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QtGui.QColor(150, 150, 160))
                painter.drawText(
                    0,
                    top,
                    self._line_number_area.width() - 4,
                    self.fontMetrics().height(),
                    QtCore.Qt.AlignRight,
                    number,
                )

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def highlight_current_line(self) -> None:
        extra_selections: list[QtWidgets.QTextEdit.ExtraSelection] = []

        if not self.isReadOnly():
            selection = QtWidgets.QTextEdit.ExtraSelection()
            selection.format.setBackground(self._current_line_color)
            selection.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        self.setExtraSelections(extra_selections)


__all__ = ["SyntaxHighlighter", "PythonHighlighter", "CodeEditor"]
