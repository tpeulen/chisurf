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

    def _make_column_specs(self, records: list[dict]) -> list:
        from chisurf.gui.widgets.chitable.columns import ColumnSpec

        if not records:
            return []
        keys = []
        seen = set()
        for row in records:
            for k in row:
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        override = {}
        if self._column_specs_raw:
            for spec in self._column_specs_raw:
                if isinstance(spec, dict) and "key" in spec:
                    override[spec["key"]] = spec
        specs = []
        for key in keys:
            ov = override.get(key, {})
            specs.append(
                ColumnSpec(
                    key=key,
                    label=str(ov.get("title", ov.get("label", key))),
                    visible=bool(ov.get("visible", True)),
                    editable=bool(ov.get("editable", self._editable)),
                    width=int(ov.get("width", 0) or 0),
                    tooltip=str(ov.get("tooltip", "") or ""),
                )
            )
        return specs

    def refresh(self) -> None:
        """Re-read data from the model and rebind the table when it changed."""
        data = self._call(self._source)
        token = (
            id(data),
            getattr(data, "size", None) if data is not None else None,
        )
        if token == self._token:
            return
        self._token = token

        if data is None:
            self._records = []
            self.table.set_arrays({})
            return

        if self._is_data_store(data):
            self.table.set_store(data, editable=self._editable)
            return

        if isinstance(data, list) and (
            not data or isinstance(data[0], dict)
        ):
            specs = self._make_column_specs(data)
            self._records = data
            # No ``editable=`` here: RecordSource does not take one, and
            # per-column editability already rides on each ColumnSpec (set in
            # _make_column_specs). Passing it raised TypeError, so a data_table
            # bound to a list of records never rendered at all.
            self.table.set_records(data, specs)
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
