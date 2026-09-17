"""AutoForm ``data_table`` section: a general-purpose scalable table.

A generalization of :mod:`store_table` that auto-detects what the model
returns and binds it to a :class:`~chisurf.gui.widgets.chitable.ChiTableWidget`
using the right source type:

- a ``tttrlib.DataStore``  → zero-copy columnar binding (``set_store``)
- a list of dict-records   → ``set_records`` with auto-derived column specs
- a dict of named arrays   → ``set_arrays``

Declare it in a view spec as a custom section::

    {"type": "custom", "key": "data_table", "title": "Results",
     "options": {"source": "burst_table", "editable": false}}

This section is the scalable counterpart to the built-in ``table`` section:
the built-in is right for small fixed-order parameter rows, and this one is
right for data tables with hundreds of thousands of typed-column rows.

Options
-------
``source``
    Model **method** (no arguments) returning the data to show, or ``None``
    when there is nothing to show.
``editable``
    Allow cell edits (default ``false``).
``columns``
    Optional list of ``{"key": str, "title": str, "units": str, "visible": bool,
    "width": int, "tooltip": str}`` column specs overriding auto-derivation for
    record sources. ``width`` is a preferred pixel width (``0`` sizes to
    contents); ``tooltip`` shows on the header.
``height``
    Minimum height in pixels (default 240).
``selected_call``
    Model method called with the selected **record** (a dict for record
    sources, otherwise the source row index) whenever the selection moves, and
    with ``None`` when the selection is cleared. This is what lets a table
    drive a details pane.

Options shared with emtk's painted renderer (``emtk.widgets.data_table``), so
one spec reads the same in both:

``"display": "bar"`` + ``"range": [lo, hi]`` on a column
    the value drawn as a bar under its text; diverging, coloured by sign, when
    the range spans zero. ``"format"`` on a column is its printf spec.
``columns_source``
    Model method returning the column list, for columns known only at run time.
``sort``
    ``{"key": ..., "descending": bool}``: the initial order.
``tooltip_key``
    Record field holding each row's tooltip.
``row_key``
    Record field identifying a row, so the selection is kept when the source
    grows and the table is re-read.

A record list that **grows in place** (a computation appending rows while the
table is shown) is re-read on refresh without rebinding: the sort and the
selection stay, and ``selected_call`` is not fired again for a row the user
already selected.
"""

from __future__ import annotations

import logging
from typing import Any

from qtpy import QtWidgets

from .registry import register_section

logger = logging.getLogger(__name__)


@register_section("data_table")
class DataTableSectionWidget(QtWidgets.QWidget):
    """A :class:`ChiTableWidget` auto-bound to whatever the model returns."""

    AUTOFORM_REFRESH = True
    _autoform_expanding = True

    def __init__(self, model, target: str = "", **options):
        super().__init__()
        from chisurf.gui.widgets.chitable import ChiTableWidget

        self._model = model
        self._source = str(options.get("source", "") or target or "")
        self._editable = bool(options.get("editable", False))
        self._column_specs_raw = options.get("columns") or None
        self._columns_source = str(options.get("columns_source", "") or "")
        self._sort = options.get("sort") if isinstance(options.get("sort"), dict) else None
        self._tooltip_key = str(options.get("tooltip_key", "") or "")
        self._row_key = str(options.get("row_key", "") or "")
        self._restoring = False
        self._selected_call = str(options.get("selected_call", "") or "")
        #: Records as last bound, so a selection can be reported as the record
        #: itself rather than a row number the model would have to resolve.
        self._records: list[dict] = []
        self._token: object = object()

        self.table = ChiTableWidget()
        self.table.setMinimumHeight(int(options.get("height", 240) or 240))

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.table, stretch=1)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Expanding,
        )

        if self._selected_call:
            self.table.rowSelected.connect(self._on_row_selected)

        self.refresh()

    def _on_row_selected(self, row: int) -> None:
        """Hand the selected record to the model's ``selected_call``."""
        if self._restoring:
            return
        fn = getattr(self._model, self._selected_call, None)
        if not callable(fn):
            logger.warning("data_table: model has no %r", self._selected_call)
            return
        if row < 0:
            payload = None
        elif self._records and 0 <= row < len(self._records):
            payload = self._records[row]
        else:
            payload = row
        try:
            fn(payload)
        except Exception:
            logger.debug("data_table: %s failed", self._selected_call, exc_info=True)

    def _call(self, name: str) -> Any:
        if not name:
            return None
        fn = getattr(self._model, name, None)
        if fn is None:
            logger.warning("data_table: model has no %r", name)
            return None
        try:
            return fn() if callable(fn) else fn
        except Exception:
            logger.debug("data_table: %s failed", name, exc_info=True)
            return None

    @staticmethod
    def _is_data_store(obj: Any) -> bool:
        return hasattr(obj, "n_keys") and hasattr(obj, "read_column")

    @staticmethod
    def _is_named_arrays(obj: Any) -> bool:
        return (
            isinstance(obj, dict)
            and len(obj) > 0
            and all(hasattr(v, "__len__") for v in obj.values())
        )

    def _declared_columns(self) -> list:
        if self._columns_source:
            declared = self._call(self._columns_source)
            if declared:
                return [c for c in declared if isinstance(c, dict)]
        return [c for c in (self._column_specs_raw or []) if isinstance(c, dict)]

    def _make_column_specs(self, records: list[dict]) -> list:
        from chisurf.gui.widgets.chitable.columns import KIND_FLOAT, ColumnSpec

        declared = self._declared_columns()
        if not records and not declared:
            return []
        keys = []
        seen = set()
        for row in records:
            for k in row:
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        override = {}
        for spec in declared:
            if "key" in spec:
                override[spec["key"]] = spec
        if self._columns_source:
            # Columns declared at run time are the columns: a record carries
            # fields (its identity, its tooltip) that are not for display.
            keys = [spec["key"] for spec in declared if "key" in spec]
        specs = []
        for key in keys:
            ov = override.get(key, {})
            bar = str(ov.get("display", "") or "").lower() == "bar"
            span = ov.get("range") or ()
            title = str(ov.get("title", ov.get("label", key)))
            if ov.get("units"):
                title = f"{title} ({ov['units']})"
            specs.append(
                ColumnSpec(
                    key=key,
                    label=title,
                    kind=KIND_FLOAT if bar else "auto",
                    fmt=str(ov.get("format", "") or ""),
                    visible=bool(ov.get("visible", True)),
                    editable=bool(ov.get("editable", self._editable)),
                    width=int(ov.get("width", 0) or 0),
                    tooltip=str(ov.get("tooltip", ov.get("description", "")) or ""),
                    delegate="bar" if bar else "",
                    value_range=tuple(float(v) for v in span[:2]) if bar and len(span) >= 2 else (),
                )
            )
        return specs

    def _record_source(self, records: list, specs: list):
        from chisurf.gui.widgets.chitable.source import RecordSource

        tooltip_key = self._tooltip_key

        class _Source(RecordSource):
            def tooltip(self, row: int, col: int):
                if not tooltip_key or not (0 <= row < len(self.rows)):
                    return None
                record = self.rows[row]
                value = (
                    record.get(tooltip_key)
                    if isinstance(record, dict)
                    else getattr(record, tooltip_key, None)
                )
                return str(value) if value else None

        return _Source(records, specs)

    def _selected_identity(self):
        model = self.table._chi_model
        view = self.table._view
        if model is None or view.selectionModel() is None:
            return None
        current = view.selectionModel().currentIndex()
        if not current.isValid():
            return None
        row = model.source_row(current.row())
        if row < 0 or row >= len(self._records):
            return None
        if self._row_key:
            record = self._records[row]
            return (
                "key",
                record.get(self._row_key)
                if isinstance(record, dict)
                else getattr(record, self._row_key, None),
            )
        return ("row", row)

    def _restore_selection(self, identity) -> None:
        model = self.table._chi_model
        if identity is None or model is None:
            return
        kind, value = identity
        row = (
            value
            if kind == "row"
            else next(
                (
                    i
                    for i, r in enumerate(self._records)
                    if (
                        r.get(self._row_key)
                        if isinstance(r, dict)
                        else getattr(r, self._row_key, None)
                    )
                    == value
                ),
                -1,
            )
        )
        view_row = model.view_row(row) if row >= 0 else -1
        if view_row < 0:
            return
        self._restoring = True
        try:
            self.table._view.selectRow(view_row)
        finally:
            self._restoring = False

    def _apply_sort(self) -> None:
        model = self.table._chi_model
        if not self._sort or model is None:
            return
        keys = [spec.key for spec in model.specs]
        key = self._sort.get("key")
        if key not in keys:
            return
        from qtpy import QtCore

        order = (
            QtCore.Qt.DescendingOrder if self._sort.get("descending") else QtCore.Qt.AscendingOrder
        )
        model.sort(keys.index(key), order)
        header = self.table._view.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSortIndicator(keys.index(key), order)

    def refresh(self) -> None:
        """Re-read data from the model and rebind the table when it changed."""
        data = self._call(self._source)
        size = getattr(data, "size", None) if data is not None else None
        if size is None and isinstance(data, list):
            size = len(data)
        columns = tuple(repr(sorted(c.items())) for c in self._declared_columns())
        token = (id(data), size, getattr(data, "revision", None), columns)
        if token == self._token:
            return
        previous, self._token = self._token, token

        if data is None:
            self._records = []
            self.table.set_arrays({})
            return

        if self._is_data_store(data):
            self.table.set_store(data, editable=self._editable)
            return

        if isinstance(data, list) and (not data or isinstance(data[0], dict)):
            model = self.table._chi_model
            source = getattr(model, "_source", None) if model is not None else None
            grown = (
                isinstance(previous, tuple)
                and len(previous) == 4
                and previous[0] == token[0]
                and previous[3] == token[3]
                and source is not None
                and hasattr(source, "set_rows")
            )
            if grown:
                # Same list, same columns, more rows: re-read in place so the
                # sort, the scroll position and the selection stay put.
                identity = self._selected_identity()
                self._records = data
                source.set_rows(data)
                self.table.refresh()
                self._restore_selection(identity)
                return
            specs = self._make_column_specs(data)
            self._records = data
            # No ``editable=`` here: RecordSource does not take one, and
            # per-column editability already rides on each ColumnSpec (set in
            # _make_column_specs). Passing it raised TypeError, so a data_table
            # bound to a list of records never rendered at all.
            self.table.set_source(self._record_source(data, specs))
            self._apply_sort()
            return

        if self._is_named_arrays(data):
            self.table.set_arrays(data, editable=self._editable)
            return

        logger.warning(
            "data_table: model method %r returned unsupported type %s",
            self._source,
            type(data).__name__,
        )
        self.table.set_arrays({})
