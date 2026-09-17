"""The chitable container widget.

:class:`ChiTableWidget` is what call sites embed: a compact toolbar (search,
column picker, hide-empty, colour toggle, export), a
:class:`~chisurf.gui.widgets.chitable.view.ChiTableView`, and a status line
reporting how many rows the filter kept.

It accepts either a :class:`~chisurf.gui.widgets.chitable.source.TableSource`
(the fast, fully-featured path) or a foreign
:class:`~qtpy.QtCore.QAbstractTableModel` that keeps its own semantics and gains
the features through :class:`~chisurf.gui.widgets.chitable.proxy.ForeignTableProxy`.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from typing import Any

from qtpy import QtCore, QtWidgets

from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.chitable.colorize import ValueColorScheme
from chisurf.gui.widgets.chitable.dialogs import ColumnFilterDialog, ColumnPickerDialog
from chisurf.gui.widgets.chitable.filters import FilterSpec
from chisurf.gui.widgets.chitable.model import ChiTableModel
from chisurf.gui.widgets.chitable.proxy import ForeignTableProxy
from chisurf.gui.widgets.chitable.source import (
    ArraySource,
    DataStoreSource,
    RecordSource,
    TableSource,
)
from chisurf.gui.widgets.chitable.view import (
    ChiTableView,
    apply_column_delegates,
    apply_column_widths,
)

#: Delay before a typed search string is applied, in milliseconds.
SEARCH_DEBOUNCE_MS = 150


class TableFeature(enum.Flag):
    """Opt-in feature set for :class:`ChiTableWidget`."""

    NONE = 0
    SEARCH = enum.auto()
    COLUMN_FILTERS = enum.auto()
    SORT = enum.auto()
    COLUMN_PICKER = enum.auto()
    HIDE_EMPTY = enum.auto()
    COLOR_BY_VALUE = enum.auto()
    EXPORT = enum.auto()
    STATUSBAR = enum.auto()
    EDIT = enum.auto()


#: The features a table gets when the caller does not choose.
DEFAULT_FEATURES = (
    TableFeature.SEARCH
    | TableFeature.COLUMN_FILTERS
    | TableFeature.SORT
    | TableFeature.COLUMN_PICKER
    | TableFeature.HIDE_EMPTY
    | TableFeature.COLOR_BY_VALUE
    | TableFeature.EXPORT
    | TableFeature.STATUSBAR
)


class ChiTableWidget(QtWidgets.QWidget):
    """Toolbar + table + status line over a chitable model.

    Parameters
    ----------
    source : TableSource, optional
        Data adapter for the fast path.
    model : qtpy.QtCore.QAbstractItemModel, optional
        An existing model to wrap instead of ``source``. Mutually exclusive
        with it.
    features : TableFeature
        Which toolbar controls and behaviours to enable.
    color_scheme : ValueColorScheme, optional
        Initial colouring policy; disabled by default.
    staged : bool
        Buffer edits until :meth:`commit` (used by the modal dialog).
    frozen_columns : int
        Number of leading columns to pin while scrolling sideways.
    parent : qtpy.QtWidgets.QWidget, optional
        Parent widget.
    """

    #: :meth:`AutoForm.refresh_plots` calls ``refresh`` on widgets that set this.
    AUTOFORM_REFRESH = True
    #: Marks this widget as a display element rather than a form field.
    is_form_field = False

    #: Emitted after a cell edit reaches the model.
    valueEdited = QtCore.Signal(int, int)
    #: Emitted with the **source** row index when the selection moves, or -1
    #: when nothing is selected. Source-indexed, not view-indexed: sorting and
    #: filtering reorder the view, so a view row number does not identify a
    #: record.
    rowSelected = QtCore.Signal(int)
    #: Emitted when the visible-row count changes.
    filterChanged = QtCore.Signal(int, int)

    def __init__(
        self,
        *,
        source: TableSource | None = None,
        model: QtCore.QAbstractItemModel | None = None,
        features: TableFeature = DEFAULT_FEATURES,
        color_scheme: ValueColorScheme | None = None,
        staged: bool = False,
        frozen_columns: int = 0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._features = features
        self._staged = bool(staged)
        self._color = color_scheme or ValueColorScheme()
        self._delegates: list = []
        self._foreign_proxy: ForeignTableProxy | None = None
        self._chi_model: ChiTableModel | None = None

        self._build_ui()

        if model is not None:
            self.set_source_model(model)
        elif source is not None:
            self.set_source(source)

        if frozen_columns:
            self._view.set_frozen_columns(frozen_columns)

    # ── construction ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Assemble the toolbar, view and status line."""
        from chisurf.gui.widgets.general import apply_compact_table_style

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(4)

        self._search = QtWidgets.QLineEdit(self)
        self._search.setPlaceholderText(f"{Glyphs.SEARCH} Search…")
        self._search.setClearButtonEnabled(True)
        self._search.setToolTip("Show only rows containing this text in any visible column")
        self._search.textChanged.connect(self._on_search_typed)
        self._search.setVisible(bool(self._features & TableFeature.SEARCH))
        bar.addWidget(self._search, 1)

        self._btn_columns = QtWidgets.QToolButton(self)
        self._btn_columns.setText(Glyphs.CHECKBOX_ON)
        self._btn_columns.setToolTip("Choose which columns are shown")
        self._btn_columns.clicked.connect(self.open_column_picker)
        self._btn_columns.setVisible(bool(self._features & TableFeature.COLUMN_PICKER))
        bar.addWidget(self._btn_columns)

        self._btn_empty = QtWidgets.QToolButton(self)
        self._btn_empty.setText(Glyphs.CLEAR)
        self._btn_empty.setCheckable(True)
        self._btn_empty.setToolTip("Hide columns that contain no values")
        self._btn_empty.toggled.connect(self.hide_empty_columns)
        self._btn_empty.setVisible(bool(self._features & TableFeature.HIDE_EMPTY))
        bar.addWidget(self._btn_empty)

        self._btn_color = QtWidgets.QToolButton(self)
        self._btn_color.setText(Glyphs.PALETTE)
        self._btn_color.setCheckable(True)
        self._btn_color.setChecked(self._color.enabled)
        self._btn_color.setToolTip("Shade numeric cells by their value")
        self._btn_color.toggled.connect(self._on_color_toggled)
        self._btn_color.setVisible(bool(self._features & TableFeature.COLOR_BY_VALUE))
        bar.addWidget(self._btn_color)

        self._btn_scope = QtWidgets.QToolButton(self)
        self._btn_scope.setText("∥")
        self._btn_scope.setCheckable(True)
        self._btn_scope.setToolTip("Scale colours across all columns instead of per column")
        self._btn_scope.toggled.connect(self._on_scope_toggled)
        self._btn_scope.setEnabled(self._color.enabled)
        self._btn_scope.setVisible(bool(self._features & TableFeature.COLOR_BY_VALUE))
        bar.addWidget(self._btn_scope)

        self._btn_export = QtWidgets.QToolButton(self)
        self._btn_export.setText(Glyphs.EXPORT)
        self._btn_export.setToolTip("Export the visible rows and columns as CSV")
        self._btn_export.clicked.connect(lambda: self.export_csv())
        self._btn_export.setVisible(bool(self._features & TableFeature.EXPORT))
        bar.addWidget(self._btn_export)

        layout.addLayout(bar)

        self._view = ChiTableView(self)
        apply_compact_table_style(self._view, sortable=bool(self._features & TableFeature.SORT))
        self._view.filterRequested.connect(self.open_column_filter)
        selection = self._view.selectionModel()
        if selection is not None:
            selection.currentRowChanged.connect(self._on_current_row_changed)
        self._view.columnHidden.connect(lambda *_: self._update_status())
        layout.addWidget(self._view, 1)

        self._status = QtWidgets.QLabel("", self)
        self._status.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self._status.setVisible(bool(self._features & TableFeature.STATUSBAR))
        layout.addWidget(self._status)

        self._search_timer = QtCore.QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._apply_search)

    # ── data plumbing ────────────────────────────────────────────────────

    def set_source(self, source: TableSource) -> None:
        """Show a :class:`TableSource` through a fresh :class:`ChiTableModel`.

        Parameters
        ----------
        source : TableSource
            The data adapter.
        """
        if self._chi_model is None:
            self._chi_model = ChiTableModel(
                source, color_scheme=self._color, staged=self._staged, parent=self
            )
            self._chi_model.dataChanged.connect(self._on_data_changed)
            self._view.setModel(self._chi_model)
            self._connect_selection()
        else:
            self._chi_model.set_source(source)
        self._foreign_proxy = None
        self._after_model_set()

    def set_source_model(self, model: QtCore.QAbstractItemModel) -> None:
        """Wrap an existing model, keeping its semantics intact.

        Parameters
        ----------
        model : qtpy.QtCore.QAbstractItemModel
            The model to display.
        """
        if isinstance(model, ChiTableModel):
            self._chi_model = model
            self._foreign_proxy = None
            self._view.setModel(model)
            self._connect_selection()
        else:
            proxy = ForeignTableProxy(self)
            proxy.setSourceModel(model)
            proxy.set_color_scheme(self._color if self._color.enabled else None)
            self._foreign_proxy = proxy
            self._chi_model = None
            self._view.setModel(proxy)
            self._connect_selection()
            if self._features & TableFeature.SORT:
                self._view.setSortingEnabled(True)
                # setSortingEnabled() immediately sorts by the header's current
                # indicator section, so a freshly-built table would come up
                # silently sorted by column 0. Restore source order and hide the
                # indicator until the user actually clicks a header.
                proxy.sort(-1)
                header = self._view.horizontalHeader()
                header.setSortIndicatorShown(False)
                header.sortIndicatorChanged.connect(self._on_sort_indicator_changed)
        self._after_model_set()

    def _on_sort_indicator_changed(self, section: int, _order) -> None:
        """Reveal the sort indicator once the user sorts a column.

        Parameters
        ----------
        section : int
            Column the indicator moved to.
        _order : qtpy.QtCore.Qt.SortOrder
            New sort order (unused).
        """
        if section >= 0:
            self._view.horizontalHeader().setSortIndicatorShown(True)

    def set_store(self, store, **kwargs: Any) -> None:
        """Show a ``tttrlib.DataStore``.

        Parameters
        ----------
        store : tttrlib.DataStore
            The store to display.
        **kwargs
            Forwarded to :class:`DataStoreSource`.
        """
        kwargs.setdefault("editable", bool(self._features & TableFeature.EDIT))
        self.set_source(DataStoreSource(store, **kwargs))

    def set_arrays(self, columns, **kwargs: Any) -> None:
        """Show named ``numpy`` column arrays.

        Parameters
        ----------
        columns : mapping or sequence of (str, numpy.ndarray)
            The columns to display.
        **kwargs
            Forwarded to :class:`ArraySource`.
        """
        self.set_source(ArraySource(columns, **kwargs))

    def set_records(self, rows, specs, **kwargs: Any) -> None:
        """Show a list of record objects with an explicit column spec.

        Parameters
        ----------
        rows : sequence
            Row objects or dicts.
        specs : sequence of ColumnSpec
            Column definitions.
        **kwargs
            Forwarded to :class:`RecordSource`.
        """
        self.set_source(RecordSource(rows, specs, **kwargs))

    def _after_model_set(self) -> None:
        """Install delegates, widths and visibility for the current model."""
        # Keep the row count honest when rows come and go. Only ``dataChanged``
        # was wired, which a foreign model does not emit when rows are inserted
        # or removed — so a table filled after construction went on reporting
        # "0 rows" while showing them.
        model = self._view.model()
        if model is not None:
            for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset):
                try:
                    signal.disconnect(self._on_rows_changed)
                except (TypeError, RuntimeError):
                    pass
                signal.connect(self._on_rows_changed)

        for col in range(self._view.model().columnCount() if self._view.model() else 0):
            self._view.setColumnHidden(col, False)
        if self._chi_model is not None:
            self._delegates = apply_column_delegates(self._view, self._chi_model)
            for col, spec in enumerate(self._chi_model.specs):
                self._view.setColumnHidden(col, not spec.visible)
            # Auto-size first, then let declared widths win. The other order
            # applied the widths and then had auto_resize_columns overwrite
            # every one of them, which made ColumnSpec.width dead.
            self._view.auto_resize_columns()
            apply_column_widths(self._view, self._chi_model.specs)
            # The compact style stretches the last section to fill the viewport,
            # which is right for auto-sized tables and wrong the moment an author
            # declares widths -- the final column swallows all the spare space
            # however narrow it was asked to be. Declared widths mean the layout
            # was decided; honour it and let the row end where it ends.
            if any(getattr(spec, "width", 0) for spec in self._chi_model.specs):
                self._view.horizontalHeader().setStretchLastSection(False)
            affordable = self._chi_model.color_affordable()
            self._btn_color.setEnabled(affordable)
            if not affordable:
                self._btn_color.setToolTip(
                    "Value shading is disabled: this table is too large to scan for "
                    "per-column ranges"
                )
        self._update_status()

    # ── searching and filtering ──────────────────────────────────────────

    def _on_search_typed(self, _text: str) -> None:
        """Restart the search debounce timer.

        Parameters
        ----------
        _text : str
            Current search text (unused; read when the timer fires).
        """
        self._search_timer.start()

    def _apply_search(self) -> None:
        """Apply the typed search string to the active filter."""
        self.set_filter(self.filter_spec.with_query(self._search.text()))

    @property
    def filter_spec(self) -> FilterSpec:
        """Return the active filter.

        Returns
        -------
        FilterSpec
        """
        if self._chi_model is not None:
            return self._chi_model.filter_spec
        if self._foreign_proxy is not None:
            return self._foreign_proxy.filter_spec
        return FilterSpec()

    def set_filter(self, spec: FilterSpec | None) -> None:
        """Apply a filter to whichever model backs this table.

        Parameters
        ----------
        spec : FilterSpec or None
            The filter; ``None`` clears it.
        """
        if self._chi_model is not None:
            self._chi_model.set_filter(spec)
        elif self._foreign_proxy is not None:
            self._foreign_proxy.set_filter(spec)
        self._update_status()
        self.filterChanged.emit(self.visible_row_count(), self.total_row_count())

    def set_search_text(self, text: str) -> None:
        """Set the search box content and apply it immediately.

        Parameters
        ----------
        text : str
            Search string.
        """
        self._search.setText(text)
        self._search_timer.stop()
        self._apply_search()

    def open_column_filter(self, col: int) -> None:
        """Open the per-column filter editor.

        Parameters
        ----------
        col : int
            Column index to edit.
        """
        if not (self._features & TableFeature.COLUMN_FILTERS):
            return
        model = self._view.model()
        if model is None:
            return
        label = str(model.headerData(col, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole) or col)
        numeric = True
        if self._chi_model is not None:
            numeric = self._chi_model.spec(col).is_numeric
        dlg = ColumnFilterDialog(col, label, numeric, self.filter_spec.filter_for(col), parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        self.set_filter(self.filter_spec.with_column_filter(dlg.result_filter(), col))

    # ── column visibility ────────────────────────────────────────────────

    def open_column_picker(self) -> None:
        """Open the column chooser and apply the result."""
        model = self._view.model()
        if model is None:
            return
        entries = []
        for col in range(model.columnCount()):
            label = model.headerData(col, QtCore.Qt.Horizontal, QtCore.Qt.DisplayRole)
            entries.append((str(label or col), not self._view.isColumnHidden(col)))
        dlg = ColumnPickerDialog(entries, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        for col, visible in enumerate(dlg.visibility()):
            self.set_column_visible(col, visible)
        self._update_status()

    def set_column_visible(self, col: int, visible: bool) -> None:
        """Show or hide one column.

        Parameters
        ----------
        col : int
            Column index.
        visible : bool
            Target visibility.
        """
        self._view.setColumnHidden(col, not visible)
        if self._chi_model is not None:
            self._chi_model.set_column_visible(col, visible)

    def hide_empty_columns(self, enabled: bool = True) -> None:
        """Hide (or restore) columns that hold no values at all.

        Parameters
        ----------
        enabled : bool
            ``True`` hides the empty columns; ``False`` shows every column.
        """
        if self._chi_model is None:
            return
        empty = set(self._chi_model.empty_columns()) if enabled else set()
        for col in range(self._chi_model.columnCount()):
            self.set_column_visible(col, col not in empty)
        self._update_status()

    # ── colouring ────────────────────────────────────────────────────────

    def _on_color_toggled(self, enabled: bool) -> None:
        """React to the colour toggle.

        Parameters
        ----------
        enabled : bool
            New toggle state.
        """
        self._color.enabled = bool(enabled)
        self._btn_scope.setEnabled(bool(enabled))
        self.set_color_scheme(self._color)

    def _on_scope_toggled(self, global_scope: bool) -> None:
        """React to the per-column / global range toggle.

        Parameters
        ----------
        global_scope : bool
            ``True`` scales every column against one shared range.
        """
        self._color.scope = "global" if global_scope else "column"
        self.set_color_scheme(self._color)

    def set_color_scheme(self, scheme: ValueColorScheme) -> None:
        """Apply a colouring policy to whichever model backs this table.

        Parameters
        ----------
        scheme : ValueColorScheme
            The policy.
        """
        self._color = scheme
        self._btn_color.setChecked(scheme.enabled)
        if self._chi_model is not None:
            self._chi_model.set_color_scheme(scheme)
        elif self._foreign_proxy is not None:
            self._foreign_proxy.set_color_scheme(scheme if scheme.enabled else None)

    # ── status ───────────────────────────────────────────────────────────

    def visible_row_count(self) -> int:
        """Return how many rows pass the current filter.

        Returns
        -------
        int
        """
        if self._chi_model is not None:
            return self._chi_model.total_row_count()
        model = self._view.model()
        return int(model.rowCount()) if model is not None else 0

    def total_row_count(self) -> int:
        """Return the unfiltered row count.

        Returns
        -------
        int
        """
        if self._chi_model is not None:
            return self._chi_model.source_row_count()
        if self._foreign_proxy is not None and self._foreign_proxy.sourceModel() is not None:
            return int(self._foreign_proxy.sourceModel().rowCount())
        return self.visible_row_count()

    def _update_status(self) -> None:
        """Refresh the status line."""
        if not (self._features & TableFeature.STATUSBAR):
            return
        model = self._view.model()
        if model is None:
            self._status.setText("")
            return
        shown = self.visible_row_count()
        total = self.total_row_count()
        n_cols = sum(1 for c in range(model.columnCount()) if not self._view.isColumnHidden(c))
        if shown < total:
            self._status.setText(f"{shown:,} / {total:,} rows × {n_cols} columns")
        else:
            self._status.setText(f"{total:,} rows × {n_cols} columns")

    def _connect_selection(self) -> None:
        """(Re)connect the current selection model to :attr:`rowSelected`.

        ``QAbstractItemView.setModel`` installs a *new* selection model and
        discards the old one, so every rebind has to reconnect or selection
        silently stops being reported.
        """
        selection = self._view.selectionModel()
        if selection is None:
            return
        try:
            selection.currentRowChanged.disconnect(self._on_current_row_changed)
        except (TypeError, RuntimeError):
            pass
        selection.currentRowChanged.connect(self._on_current_row_changed)

    def _on_current_row_changed(self, current, _previous=None) -> None:
        """Map the view's current row back to a source row and announce it."""
        if current is None or not current.isValid():
            self.rowSelected.emit(-1)
            return
        model = self._view.model()
        index = current
        # Walk any chain of proxies (sort/filter) back to the source model.
        while hasattr(model, "mapToSource") and hasattr(model, "sourceModel"):
            index = model.mapToSource(index)
            model = model.sourceModel()
        # ChiTableModel sorts and filters *itself*, with no proxy in between, so
        # the walk above leaves a view row. Reporting it as a source row sent a
        # sorted table's selection to whichever record sat at that position in
        # source order.
        if isinstance(model, ChiTableModel):
            self.rowSelected.emit(int(model.source_row(index.row())))
            return
        self.rowSelected.emit(int(index.row()))

    def _on_rows_changed(self, *_args) -> None:
        """Refresh the status line after rows are added, removed or reset."""
        self._update_status()

    def _on_data_changed(self, top_left, _bottom_right, *_roles) -> None:
        """Report an edit and refresh the status line.

        Parameters
        ----------
        top_left : qtpy.QtCore.QModelIndex
            First changed index.
        _bottom_right : qtpy.QtCore.QModelIndex
            Last changed index (unused).
        *_roles
            Changed roles (unused).
        """
        if top_left.isValid():
            self.valueEdited.emit(top_left.row(), top_left.column())
        self._update_status()

    # ── accessors ────────────────────────────────────────────────────────

    @property
    def table_view(self) -> ChiTableView:
        """Return the underlying view.

        Returns
        -------
        ChiTableView
        """
        return self._view

    @property
    def table_model(self):
        """Return the source model (never the proxy).

        Returns
        -------
        qtpy.QtCore.QAbstractItemModel or None
        """
        if self._chi_model is not None:
            return self._chi_model
        if self._foreign_proxy is not None:
            return self._foreign_proxy.sourceModel()
        return self._view.model()

    @property
    def proxy(self) -> ForeignTableProxy | None:
        """Return the foreign-model proxy, when one is in use.

        Returns
        -------
        ForeignTableProxy or None
        """
        return self._foreign_proxy

    def to_store(self):
        """Return the current view as a store.

        Returns
        -------
        tttrlib.DataStore or None
            ``None`` when the table is backed by a foreign model.
        """
        if self._chi_model is None:
            return None
        return self._chi_model.to_store()

    def export_csv(self, path: str | None = None) -> str | None:
        """Write the visible rows and columns to CSV.

        Parameters
        ----------
        path : str, optional
            Target path; a file dialog is shown when omitted.

        Returns
        -------
        str or None
        """
        return self._view.export_csv(path)

    def commit(self) -> int:
        """Write buffered edits through to the source.

        Returns
        -------
        int
            Number of cells written; ``0`` when not in staged mode.
        """
        return self._chi_model.commit() if self._chi_model is not None else 0

    def rollback(self) -> None:
        """Discard buffered edits."""
        if self._chi_model is not None:
            self._chi_model.rollback()

    def refresh(self) -> None:
        """Re-read the source and repaint, keeping filter and sort."""
        if self._chi_model is not None:
            self._chi_model.refresh()
        elif self._foreign_proxy is not None:
            self._foreign_proxy.invalidate_ranges()
            source = self._foreign_proxy.sourceModel()
            if hasattr(source, "refresh"):
                source.refresh()
        self._update_status()

    def set_frozen_columns(self, count: int) -> None:
        """Pin leading columns while scrolling sideways.

        Parameters
        ----------
        count : int
            Number of columns to pin.
        """
        self._view.set_frozen_columns(count)

    def select_columns(self, keys: Sequence[str]) -> None:
        """Show only the named columns.

        Parameters
        ----------
        keys : sequence of str
            :attr:`ColumnSpec.key` values to keep visible.
        """
        if self._chi_model is None:
            return
        wanted = set(keys)
        for col, spec in enumerate(self._chi_model.specs):
            self.set_column_visible(col, spec.key in wanted)
        self._update_status()
