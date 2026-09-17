"""Item delegates and header views shared by every ChiSurf table.

These used to live in :mod:`chisurf.gui.autoform.sections.parameter_table`, with a
second, drifting copy of the checkbox delegate in
:mod:`chisurf.gui.plots.table_plot`. They are table furniture, not parameter
furniture, so they belong here; ``parameter_table`` re-exports them under their
historic underscore-prefixed names.

Delegates are selected per column through :attr:`ColumnSpec.delegate`:

=============  ==========================================================
``"bool"``     :class:`BooleanToggleDelegate` — click-to-toggle checkbox
``"float"``    :class:`FloatEditDelegate` — scientific spin-box editor
``"richtext"`` :class:`RichTextDelegate` — HTML labels (τ₀, x<sub>l</sub>)
``"choice"``   :class:`ChoiceDelegate` — combo box over fixed values
``"bar"``      :class:`BarDelegate` — the value as a bar under its text
=============  ==========================================================
"""

from __future__ import annotations

from collections.abc import Sequence

from qtpy import QtCore, QtGui, QtWidgets


class RichTextDelegate(QtWidgets.QStyledItemDelegate):
    """Render a cell's display text as HTML.

    Keeps parameter labels' sub/superscripts and character entities legible
    (``n<sub>0</sub>`` → n₀, ``&tau;<sub>0</sub>`` → τ₀, ``&nu;`` → ν) instead of
    printing the raw markup.
    """

    def paint(self, painter, option, index):  # noqa: D102 (Qt override)
        data = index.data(QtCore.Qt.DisplayRole)
        text = "" if data is None else str(data)
        # Render as HTML for markup (``x<sub>l</sub>``) *and* bare entities
        # (``&nu;`` → ν, ``&#8491;`` → Å), the same test
        # :class:`RichTextHeaderView` makes: a label built only from entities has
        # no ``<`` at all and was printed as its raw source text.
        if "<" not in text and "&" not in text:
            return super().paint(painter, option, index)
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        html = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        doc = QtGui.QTextDocument()
        doc.setDefaultFont(opt.font)
        doc.setDocumentMargin(0)
        doc.setHtml(html)
        selected = bool(opt.state & QtWidgets.QStyle.State_Selected)
        role = QtGui.QPalette.HighlightedText if selected else QtGui.QPalette.Text
        ctx = QtGui.QAbstractTextDocumentLayout.PaintContext()
        ctx.palette.setColor(QtGui.QPalette.Text, opt.palette.color(role))
        rect = style.subElementRect(QtWidgets.QStyle.SE_ItemViewItemText, opt, opt.widget)
        painter.save()
        painter.translate(
            rect.left() + 2,
            rect.top() + max(0, (rect.height() - doc.size().height()) / 2),
        )
        ctx.clip = QtCore.QRectF(0, 0, rect.width(), rect.height())
        doc.documentLayout().draw(painter, ctx)
        painter.restore()


class BooleanToggleDelegate(QtWidgets.QStyledItemDelegate):
    """Click-to-toggle checkbox rendered centred in the cell."""

    def _is_checked(self, value) -> bool:
        """Return the truthiness of a cell value.

        Parameters
        ----------
        value : object
            Display-role value: a bool, a number, or a string such as ``"True"``.

        Returns
        -------
        bool
        """
        try:
            if isinstance(value, bool) or value is None:
                return bool(value) if value is not None else False
            if isinstance(value, str):
                return value.strip().lower() in ("true", "1", "yes", "on", "t", "y")
            return bool(int(value))
        except Exception:
            return False

    def _toggle(self, value) -> bool:
        """Return the negation of a cell value.

        Parameters
        ----------
        value : object
            Display-role value.

        Returns
        -------
        bool
        """
        return not self._is_checked(value)

    def _checkbox_rect(self, option: QtWidgets.QStyleOptionViewItem) -> QtCore.QRect:
        """Return the centred 16×16 rectangle the checkbox is drawn in.

        Parameters
        ----------
        option : qtpy.QtWidgets.QStyleOptionViewItem
            The cell's style option.

        Returns
        -------
        qtpy.QtCore.QRect
        """
        rect = option.rect
        size = 16
        x = rect.x() + (rect.width() - size) // 2
        y = rect.y() + (rect.height() - size) // 2
        return QtCore.QRect(x, y, size, size)

    def paint(self, painter, option, index) -> None:  # noqa: D102 (Qt override)
        checked = self._is_checked(index.data(QtCore.Qt.DisplayRole))
        style = (
            QtWidgets.QApplication.style()
            if QtWidgets.QApplication.instance()
            else option.widget.style()
        )
        cb_opt = QtWidgets.QStyleOptionButton()
        cb_opt.state = QtWidgets.QStyle.State_Enabled | (
            QtWidgets.QStyle.State_On if checked else QtWidgets.QStyle.State_Off
        )
        cb_opt.rect = self._checkbox_rect(option)
        style.drawControl(QtWidgets.QStyle.CE_CheckBox, cb_opt, painter)

    def createEditor(self, parent, option, index):  # noqa: D102 (Qt override)
        return None

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: D102 (Qt override)
        # A read-only cell must not toggle, and only the *left* button edits:
        # every other button reached here too, so right-clicking a Fixed cell to
        # open the context menu silently flipped the flag first.
        if not (index.flags() & QtCore.Qt.ItemIsEditable):
            return False
        et = event.type()
        if et in (QtCore.QEvent.MouseButtonRelease, QtCore.QEvent.MouseButtonDblClick):
            if getattr(event, "button", None) and event.button() != QtCore.Qt.LeftButton:
                return False
            new_val = self._toggle(index.data(QtCore.Qt.DisplayRole))
            return model.setData(index, str(new_val), QtCore.Qt.EditRole)
        if et == QtCore.QEvent.KeyPress:
            if isinstance(event, QtGui.QKeyEvent) and event.key() in (
                QtCore.Qt.Key_Space,
                QtCore.Qt.Key_Return,
                QtCore.Qt.Key_Enter,
            ):
                new_val = self._toggle(index.data(QtCore.Qt.DisplayRole))
                return model.setData(index, str(new_val), QtCore.Qt.EditRole)
        return False


class FloatEditDelegate(QtWidgets.QStyledItemDelegate):
    """Float-column editor using :class:`ScientificDoubleSpinBox`.

    Qt's default item-editor factory maps a plain ``float`` EditRole value to a
    stock ``QDoubleSpinBox``, which defaults to 2 decimal places and a 0-99.99
    range — silently truncating (displaying ``0.00``) and un-enterable outside
    that range for the small/large values these tables routinely hold (e.g. a
    bunching time constant of 0.001 ms). This delegate swaps in the same
    adaptive-significant-figures, unbounded editor the standalone parameter
    widgets already use.
    """

    def createEditor(self, parent, option, index):  # noqa: D102 (Qt override)
        from chisurf.gui.widgets.fitting.scientific_spinbox import ScientificDoubleSpinBox

        return ScientificDoubleSpinBox(parent, decimals=6, finite=False)

    def setEditorData(self, editor, index) -> None:  # noqa: D102 (Qt override)
        value = index.data(QtCore.Qt.EditRole)
        try:
            editor.setValue(float(value))
        except Exception:
            pass

    def setModelData(self, editor, model, index) -> None:  # noqa: D102 (Qt override)
        # A spin box only turns typed text into a value when the entry is
        # committed, and the delegate's commit runs *before* the editor sees the
        # Return / focus-out that would do it -- so ``value()`` would still hold
        # the pre-edit number and the cell snapped straight back.
        editor.interpretText()
        model.setData(index, editor.value(), QtCore.Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index) -> None:  # noqa: D102 (Qt override)
        editor.setGeometry(option.rect)


class ChoiceDelegate(QtWidgets.QStyledItemDelegate):
    """Combo-box editor over a fixed set of allowed values.

    Parameters
    ----------
    choices : sequence of str
        The selectable values.
    parent : qtpy.QtCore.QObject, optional
        Owner object.
    """

    def __init__(self, choices: Sequence[str], parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._choices = [str(c) for c in choices]

    def createEditor(self, parent, option, index):  # noqa: D102 (Qt override)
        box = QtWidgets.QComboBox(parent)
        box.addItems(self._choices)
        return box

    def setEditorData(self, editor, index) -> None:  # noqa: D102 (Qt override)
        text = str(index.data(QtCore.Qt.EditRole) or "")
        pos = editor.findText(text)
        editor.setCurrentIndex(max(0, pos))

    def setModelData(self, editor, model, index) -> None:  # noqa: D102 (Qt override)
        model.setData(index, editor.currentText(), QtCore.Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index) -> None:  # noqa: D102 (Qt override)
        editor.setGeometry(option.rect)


class RichTextHeaderView(QtWidgets.QHeaderView):
    """Horizontal header that renders its labels as HTML (sub/superscripts).

    ``QHeaderView`` shows the raw ``x<sub>l</sub>`` markup otherwise; this paints
    the header chrome without text and overlays a rendered ``QTextDocument`` so
    column titles read ``xₗ`` / ``τₗ`` like the parameter row widgets.

    Parameters
    ----------
    parent : qtpy.QtWidgets.QWidget, optional
        Owning view.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(QtCore.Qt.Horizontal, parent)
        self.setDefaultAlignment(QtCore.Qt.AlignCenter)

    def paintSection(self, painter, rect, logicalIndex):  # noqa: N802, D102 (Qt override)
        model = self.model()
        text = ""
        if model is not None:
            data = model.headerData(logicalIndex, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole)
            text = "" if data is None else str(data)
        # Render as HTML for markup (``x<sub>l</sub>``) *and* bare entities
        # (``&rho;`` → ρ); the default header would print the raw entity text.
        if "<" not in text and "&" not in text:
            super().paintSection(painter, rect, logicalIndex)
            return
        painter.save()
        try:
            opt = QtWidgets.QStyleOptionHeader()
            opt.rect = rect
            opt.section = logicalIndex
            opt.text = ""
            opt.orientation = QtCore.Qt.Horizontal
            opt.palette = self.palette()
            opt.state = QtWidgets.QStyle.State_Enabled | QtWidgets.QStyle.State_Horizontal
            opt.position = QtWidgets.QStyleOptionHeader.Middle
            self.style().drawControl(QtWidgets.QStyle.CE_Header, opt, painter, self)
        except Exception:
            painter.restore()
            super().paintSection(painter, rect, logicalIndex)
            return
        painter.restore()

        doc = QtGui.QTextDocument()
        doc.setDefaultFont(self.font())
        doc.setDocumentMargin(0)
        doc.setHtml(text)
        color = self.palette().color(QtGui.QPalette.ButtonText)
        painter.save()
        painter.translate(
            rect.left() + max(0.0, (rect.width() - doc.idealWidth()) / 2.0),
            rect.top() + max(0.0, (rect.height() - doc.size().height()) / 2.0),
        )
        ctx = QtGui.QAbstractTextDocumentLayout.PaintContext()
        ctx.palette.setColor(QtGui.QPalette.Text, color)
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def sectionSizeFromContents(self, logicalIndex):  # noqa: N802 (Qt override)
        """Measure the *rendered* title, not the markup it is written in.

        The base header sizes a section from the raw string, so a column headed
        ``&sigma;<sub>x</sub>`` reserves the width of nineteen characters to
        paint two glyphs — enough, in a table of six such columns, to push the
        values off the panel. ``ResizeToContents`` asks this question, so this
        is where it is answered.
        """
        size = super().sectionSizeFromContents(logicalIndex)
        model = self.model()
        if model is None:
            return size
        data = model.headerData(logicalIndex, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole)
        text = "" if data is None else str(data)
        if "<" not in text and "&" not in text:
            return size
        doc = QtGui.QTextDocument()
        doc.setDefaultFont(self.font())
        doc.setDocumentMargin(0)
        doc.setHtml(text)
        # The margin the base measurement adds around the plain string, kept so
        # a rendered title is not flush against the section border.
        margin = 2 * self.style().pixelMetric(QtWidgets.QStyle.PM_HeaderMargin, None, self)
        return QtCore.QSize(
            int(doc.idealWidth()) + margin,
            max(size.height(), int(doc.size().height()) + margin),
        )


class BarDelegate(QtWidgets.QStyledItemDelegate):
    """Draw the cell as usual plus its value as a bar along the bottom edge.

    The ``"display": "bar"`` column option of a view spec's table, drawn the
    same way emtk's painted table draws it (``emtk.widgets.data_table``), so a
    spec reads alike in both renderers: ``(v - lo) / (hi - lo)`` of the cell
    width, and a *diverging* bar from the zero point, coloured by sign, when the
    range spans zero (Orange3's correlation colours). Under the text rather than
    behind it, so the number stays legible at every length.

    Parameters
    ----------
    value_range : tuple of float
        ``(lo, hi)``.
    parent : qtpy.QtCore.QObject, optional
        Owner.
    """

    BAR_HEIGHT = 4
    COLOUR = QtGui.QColor(90, 150, 220)
    POSITIVE = QtGui.QColor(170, 242, 43)
    NEGATIVE = QtGui.QColor(70, 190, 250)

    def __init__(self, value_range: Sequence[float] = (0.0, 1.0), parent=None) -> None:
        super().__init__(parent)
        lo, hi = (tuple(value_range) + (0.0, 1.0))[:2] if len(value_range) >= 2 else (0.0, 1.0)
        self.lo, self.hi = float(lo), float(hi)

    def bar(self, value) -> tuple | None:
        """``(start, end, colour)`` as fractions of the width, or ``None``."""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number != number or not self.hi > self.lo:
            return None

        def at(v: float) -> float:
            return min(max((v - self.lo) / (self.hi - self.lo), 0.0), 1.0)

        if self.lo < 0.0 < self.hi:
            zero, point = at(0.0), at(number)
            return (
                min(zero, point),
                max(zero, point),
                self.POSITIVE if number >= 0 else self.NEGATIVE,
            )
        return (0.0, at(number), self.COLOUR)

    def paint(self, painter, option, index):  # noqa: D102 (Qt override)
        super().paint(painter, option, index)
        from chisurf.gui.widgets.chitable.model import ChiTableModel

        bar = self.bar(index.data(ChiTableModel.RawRole))
        if bar is None:
            return
        start, end, colour = bar
        rect = option.rect.adjusted(3, 0, -3, -2)
        width = rect.width()
        painter.save()
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(colour)
        painter.drawRect(
            QtCore.QRectF(
                rect.left() + start * width,
                rect.bottom() - self.BAR_HEIGHT + 1,
                max((end - start) * width, 1.0),
                self.BAR_HEIGHT,
            )
        )
        painter.restore()

    def sizeHint(self, option, index):  # noqa: N802, D102 (Qt override)
        size = super().sizeHint(option, index)
        return QtCore.QSize(size.width(), size.height() + self.BAR_HEIGHT + 2)


def delegate_for(
    kind: str, choices: Sequence[str] = (), parent=None, value_range: Sequence[float] = ()
):
    """Return a delegate instance for a :attr:`ColumnSpec.delegate` hint.

    Parameters
    ----------
    kind : str
        ``"bool"``, ``"float"``, ``"richtext"``, ``"choice"`` or ``""``.
    choices : sequence of str
        Allowed values, used only by ``"choice"``.
    parent : qtpy.QtCore.QObject, optional
        Owner passed to the delegate.
    value_range : sequence of float
        ``(lo, hi)``, used only by ``"bar"``.

    Returns
    -------
    qtpy.QtWidgets.QStyledItemDelegate or None
        ``None`` when ``kind`` names no delegate.
    """
    if kind == "bool":
        return BooleanToggleDelegate(parent)
    if kind == "float":
        return FloatEditDelegate(parent)
    if kind == "richtext":
        return RichTextDelegate(parent)
    if kind == "choice":
        return ChoiceDelegate(choices, parent)
    if kind == "bar":
        return BarDelegate(value_range or (0.0, 1.0), parent)
    return None
