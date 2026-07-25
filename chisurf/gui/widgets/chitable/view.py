"""The chitable view — a ``QTableView`` with clipboard, export and paging.

:class:`ChiTableView` adds to the stock view everything a data table is expected
to do and Qt does not provide: TSV copy (with or without headers), typed paste,
CSV export, a context menu, an optional frozen leading column, and scroll-driven
paging for :class:`~chisurf.gui.widgets.chitable.model.ChiTableModel`.

Column auto-sizing samples the first few hundred rows rather than calling
``resizeColumnsToContents``, which is O(rows) and stalls visibly on large frames.
"""

from __future__ import annotations

from collections.abc import Sequence

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.chitable.model import ChiTableModel

#: Rows inspected when sizing columns to content.
RESIZE_SAMPLE_ROWS = 200
#: Column width bounds applied after auto-sizing, in pixels.
MIN_COLUMN_WIDTH = 60
MAX_COLUMN_WIDTH = 350


class ChiTableView(QtWidgets.QTableView):
    """Table view with clipboard, export, paging and a frozen-column option.

    Parameters
    ----------
    parent : qtpy.QtWidgets.QWidget, optional
        Parent widget.
    """

    #: Emitted when the user asks to filter a column from the context menu.
    filterRequested = QtCore.Signal(int)
    #: Emitted when the user hides a column from the header context menu.
    columnHidden = QtCore.Signal(int, bool)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._frozen: QtWidgets.QTableView | None = None
        self._frozen_columns = 0

        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        header = self.horizontalHeader()
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_header_menu)

        self.verticalScrollBar().valueChanged.connect(self._maybe_fetch_more)

    # ── model plumbing ───────────────────────────────────────────────────

    def setModel(self, model) -> None:  # noqa: N802, D102 (Qt override)
        super().setModel(model)
        if isinstance(model, ChiTableModel):
            self.horizontalHeader().setSortIndicatorShown(True)
            self.horizontalHeader().setSectionsClickable(True)
            try:
                self.horizontalHeader().sectionClicked.disconnect(self._on_header_clicked)
            except (TypeError, RuntimeError):
                pass
            self.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

    def chitable_model(self) -> ChiTableModel | None:
        """Return the model when it is a :class:`ChiTableModel`.

        Returns
        -------
        ChiTableModel or None
        """
        model = self.model()
        return model if isinstance(model, ChiTableModel) else None

    def _on_header_clicked(self, section: int) -> None:
        """Toggle the sort order of a clicked header section.

        Parameters
        ----------
        section : int
            Logical column index.
        """
        model = self.chitable_model()
        if model is None:
            return
        header = self.horizontalHeader()
        if model.sort_column == section and header.sortIndicatorOrder() == QtCore.Qt.AscendingOrder:
            order = QtCore.Qt.DescendingOrder
        else:
            order = QtCore.Qt.AscendingOrder
        model.sort(section, order)
        header.setSortIndicator(section, order)

    def _maybe_fetch_more(self, value: int) -> None:
        """Expose another page when the view is scrolled to the bottom.

        ``canFetchMore`` is not used: it is consulted at unpredictable times and
        interacts badly with a model that resets on every filter change.

        Parameters
        ----------
        value : int
            Current scrollbar position.
        """
        model = self.chitable_model()
        if model is None:
            return
        if value >= self.verticalScrollBar().maximum():
            model.fetch_more()

    # ── sizing ───────────────────────────────────────────────────────────

    def auto_resize_columns(self, sample_rows: int = RESIZE_SAMPLE_ROWS) -> None:
        """Size columns from a sample of rows, clamped to sane bounds.

        Parameters
        ----------
        sample_rows : int
            Number of leading rows inspected per column.
        """
        model = self.model()
        if model is None:
            return
        metrics = self.fontMetrics()
        rows = min(model.rowCount(), max(1, sample_rows))
        for col in range(model.columnCount()):
            if self.isColumnHidden(col):
                continue
            header = model.headerData(col, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole)
            width = metrics.horizontalAdvance(str(header or "")) + 24
            for row in range(rows):
                text = model.data(model.index(row, col), QtCore.Qt.DisplayRole)
                if text:
                    width = max(width, metrics.horizontalAdvance(str(text)) + 16)
            self.setColumnWidth(col, max(MIN_COLUMN_WIDTH, min(width, MAX_COLUMN_WIDTH)))

    # ── frozen columns ───────────────────────────────────────────────────

    def set_frozen_columns(self, count: int) -> None:
        """Keep the leading ``count`` columns pinned while scrolling sideways.

        Implemented as a second view sharing this one's model *and* selection
        model, stacked under the main viewport.

        Parameters
        ----------
        count : int
            Number of leading columns to freeze; ``0`` removes the pin.
        """
        self._frozen_columns = max(0, int(count))
        if self._frozen_columns == 0:
            if self._frozen is not None:
                self._frozen.deleteLater()
                self._frozen = None
            return
        if self._frozen is None:
            frozen = QtWidgets.QTableView(self)
            frozen.setFocusPolicy(QtCore.Qt.NoFocus)
            frozen.verticalHeader().hide()
            frozen.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            frozen.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            frozen.setAlternatingRowColors(self.alternatingRowColors())
            frozen.setStyleSheet("QTableView { border: none; }")
            frozen.setSelectionModel(self.selectionModel())
            self.viewport().stackUnder(frozen)
            self._frozen = frozen
            self.horizontalHeader().sectionResized.connect(self._sync_frozen_geometry)
            self.verticalHeader().sectionResized.connect(self._sync_frozen_rows)
            frozen.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue)
            self.verticalScrollBar().valueChanged.connect(frozen.verticalScrollBar().setValue)
        self._frozen.setModel(self.model())
        self._frozen.setSelectionModel(self.selectionModel())
        for col in range(self._frozen.model().columnCount() if self._frozen.model() else 0):
            self._frozen.setColumnHidden(col, col >= self._frozen_columns)
        self._frozen.show()
        self._sync_frozen_geometry()

    def _sync_frozen_rows(self, *_args) -> None:
        """Mirror row heights into the frozen view."""
        if self._frozen is None:
            return
        for row in range(self.model().rowCount() if self.model() else 0):
            self._frozen.setRowHeight(row, self.rowHeight(row))

    def _sync_frozen_geometry(self, *_args) -> None:
        """Reposition the frozen view over the pinned columns."""
        if self._frozen is None:
            return
        width = sum(self.columnWidth(c) for c in range(self._frozen_columns))
        self._frozen.setGeometry(
            self.verticalHeader().width() + self.frameWidth(),
            self.frameWidth(),
            width,
            self.viewport().height() + self.horizontalHeader().height(),
        )
        for col in range(self._frozen_columns):
            self._frozen.setColumnWidth(col, self.columnWidth(col))
        self._sync_frozen_rows()

    def resizeEvent(self, event) -> None:  # noqa: N802, D102 (Qt override)
        super().resizeEvent(event)
        self._sync_frozen_geometry()

    # ── selection helpers ────────────────────────────────────────────────

    def selected_rectangle(self) -> tuple:
        """Return the selected ``(rows, columns)`` as sorted index lists.

        Falls back to the whole table when nothing is selected.

        Returns
        -------
        tuple of (list of int, list of int)
        """
        model = self.model()
        if model is None:
            return ([], [])
        indexes = self.selectedIndexes()
        if not indexes:
            rows = list(range(model.rowCount()))
            cols = [c for c in range(model.columnCount()) if not self.isColumnHidden(c)]
            return (rows, cols)
        rows = sorted({i.row() for i in indexes})
        cols = sorted({i.column() for i in indexes if not self.isColumnHidden(i.column())})
        return (rows, cols)

    def selection_to_text(self, *, include_header: bool = False) -> str:
        """Render the selection as tab-separated text.

        Parameters
        ----------
        include_header : bool
            Prepend the column titles.

        Returns
        -------
        str
        """
        model = self.model()
        rows, cols = self.selected_rectangle()
        if not rows or not cols:
            return ""
        if isinstance(model, ChiTableModel):
            return model.rows_as_text(rows, cols, include_header=include_header)
        lines = []
        if include_header:
            lines.append(
                "\t".join(
                    str(model.headerData(c, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole) or "")
                    for c in cols
                )
            )
        for row in rows:
            lines.append(
                "\t".join(
                    str(model.data(model.index(row, c), QtCore.Qt.DisplayRole) or "") for c in cols
                )
            )
        return "\n".join(lines)

    def copy_selection(self, *, include_header: bool = False) -> str:
        """Copy the selection to the clipboard as TSV.

        Parameters
        ----------
        include_header : bool
            Prepend the column titles.

        Returns
        -------
        str
            The text placed on the clipboard.
        """
        text = self.selection_to_text(include_header=include_header)
        if text:
            QtWidgets.QApplication.clipboard().setText(text)
        return text

    def paste_clipboard(self) -> bool:
        """Paste tab-separated clipboard text into the selection.

        A single value fills every selected editable cell; a block is written
        starting at the top-left selected cell.

        Returns
        -------
        bool
            ``True`` when at least one cell was written.
        """
        model = self.model()
        text = QtWidgets.QApplication.clipboard().text()
        indexes = self.selectedIndexes()
        if model is None or not text.strip() or not indexes:
            return False
        grid = [line.split("\t") for line in text.splitlines() if line != ""]
        if not grid:
            return False
        editable = QtCore.Qt.ItemIsEditable
        written = False

        if len(grid) == 1 and len(grid[0]) == 1:
            value = grid[0][0]
            for idx in indexes:
                if model.flags(idx) & editable:
                    written |= bool(model.setData(idx, value, QtCore.Qt.EditRole))
            return written

        anchor = min(indexes, key=lambda i: (i.row(), i.column()))
        for dr, line in enumerate(grid):
            for dc, value in enumerate(line):
                idx = model.index(anchor.row() + dr, anchor.column() + dc)
                if idx.isValid() and (model.flags(idx) & editable):
                    written |= bool(model.setData(idx, value, QtCore.Qt.EditRole))
        return written

    # ── export ───────────────────────────────────────────────────────────

    def export_csv(self, path: str | None = None) -> str | None:
        """Write the filtered, visible view to a CSV file.

        Parameters
        ----------
        path : str, optional
            Target path. When omitted a file dialog is shown.

        Returns
        -------
        str or None
            The path written, or ``None`` when cancelled or unsupported.
        """
        model = self.chitable_model()
        if model is None:
            return None
        if path is None:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export table as CSV", "", "CSV files (*.csv);;All files (*)"
            )
            if not path:
                return None
        model.fetch_all()
        model.to_dataframe().to_csv(path, index=False)
        return path

    # ── context menus ────────────────────────────────────────────────────

    def _show_context_menu(self, pos: QtCore.QPoint) -> None:
        """Show the cell context menu.

        Parameters
        ----------
        pos : qtpy.QtCore.QPoint
            Position in viewport coordinates.
        """
        menu = QtWidgets.QMenu(self)
        index = self.indexAt(pos)

        act_copy = menu.addAction(f"{Glyphs.COPY} Copy")
        act_copy.setShortcut(QtGui.QKeySequence.Copy)
        act_copy.triggered.connect(lambda: self.copy_selection())

        act_copy_hdr = menu.addAction(f"{Glyphs.COPY} Copy with headers")
        act_copy_hdr.triggered.connect(lambda: self.copy_selection(include_header=True))

        act_paste = menu.addAction(f"{Glyphs.IMPORT} Paste")
        act_paste.setShortcut(QtGui.QKeySequence.Paste)
        act_paste.setEnabled(bool(QtWidgets.QApplication.clipboard().text().strip()))
        act_paste.triggered.connect(self.paste_clipboard)

        menu.addSeparator()
        act_export = menu.addAction(f"{Glyphs.EXPORT} Export as CSV…")
        act_export.triggered.connect(lambda: self.export_csv())

        act_all = menu.addAction(f"{Glyphs.CHECKBOX_ON} Select all")
        act_all.setShortcut(QtGui.QKeySequence.SelectAll)
        act_all.triggered.connect(self.selectAll)

        if index.isValid():
            menu.addSeparator()
            act_filter = menu.addAction(f"{Glyphs.SEARCH} Filter this column…")
            act_filter.triggered.connect(lambda: self.filterRequested.emit(index.column()))
            act_hide = menu.addAction("Hide this column")
            act_hide.triggered.connect(lambda: self._hide_column(index.column()))

        menu.addSeparator()
        act_fit = menu.addAction("Resize columns to contents")
        act_fit.triggered.connect(lambda: self.auto_resize_columns())

        menu.exec_(self.viewport().mapToGlobal(pos))

    def _show_header_menu(self, pos: QtCore.QPoint) -> None:
        """Show the header context menu.

        Parameters
        ----------
        pos : qtpy.QtCore.QPoint
            Position in header coordinates.
        """
        header = self.horizontalHeader()
        section = header.logicalIndexAt(pos)
        menu = QtWidgets.QMenu(self)
        if section >= 0:
            act_filter = menu.addAction(f"{Glyphs.SEARCH} Filter this column…")
            act_filter.triggered.connect(lambda: self.filterRequested.emit(section))
            act_hide = menu.addAction("Hide this column")
            act_hide.triggered.connect(lambda: self._hide_column(section))
            menu.addSeparator()
        act_fit = menu.addAction("Resize columns to contents")
        act_fit.triggered.connect(lambda: self.auto_resize_columns())
        menu.exec_(header.mapToGlobal(pos))

    def _hide_column(self, col: int) -> None:
        """Hide one column and report it.

        Parameters
        ----------
        col : int
            Logical column index.
        """
        self.setColumnHidden(col, True)
        model = self.chitable_model()
        if model is not None:
            model.set_column_visible(col, False)
        self.columnHidden.emit(col, True)

    # ── keyboard ─────────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:  # noqa: N802, D102 (Qt override)
        if event.matches(QtGui.QKeySequence.Copy):
            self.copy_selection()
            return
        if event.matches(QtGui.QKeySequence.Paste):
            self.paste_clipboard()
            return
        super().keyPressEvent(event)


def apply_column_delegates(view: QtWidgets.QTableView, model: ChiTableModel) -> list:
    """Install the delegate each column's spec asks for.

    Parameters
    ----------
    view : qtpy.QtWidgets.QTableView
        The view to configure.
    model : ChiTableModel
        Model whose specs name the delegates.

    Returns
    -------
    list
        The delegate instances, kept alive by the caller.
    """
    from chisurf.gui.widgets.chitable.delegates import delegate_for

    kept = []
    for col, spec in enumerate(model.specs):
        kind = spec.delegate
        if not kind and spec.kind == "bool":
            kind = "bool"
        delegate = delegate_for(kind, spec.choices, view)
        if delegate is not None:
            view.setItemDelegateForColumn(col, delegate)
            kept.append(delegate)
    return kept


def apply_column_widths(view: QtWidgets.QTableView, specs: Sequence) -> None:
    """Apply explicit widths from the column specs.

    Parameters
    ----------
    view : qtpy.QtWidgets.QTableView
        The view to configure.
    specs : sequence of ColumnSpec
        Columns in table order.
    """
    for col, spec in enumerate(specs):
        if spec.width:
            view.setColumnWidth(col, int(spec.width))
