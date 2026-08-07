"""AutoForm ``store_table`` section: a columnar store shown as a full table.

The built-in ``table`` section takes a list of row mappings, which is right for a
list of a few dozen records and wrong for data: a burst table is a hundred
thousand rows of typed columns, and materialising it as dicts costs more than
reading it did. This section binds a
:class:`~chisurf.gui.widgets.chitable.ChiTableWidget` straight to a
``tttrlib.DataStore``, so the view is the store — sorted, filtered, searched,
column-hidden and exported by the shared table widget, with no copy in between.

Declare it in a view spec as a custom section::

    {"type": "custom", "key": "store_table", "title": "Data",
     "options": {"source": "current_store"}}

Column units need no option: a store column states its own unit, and the shared
table reads it into the header (``tau_green [ns]``).

Options
-------
``source``
    Model **method** (no arguments) returning the store to show, or ``None`` when
    there is nothing to show (the table then goes empty rather than keeping the
    previous contents, which would otherwise be attributed to the new selection).
``editable``
    Allow cell edits (default ``false``). A view of stored data is a view;
    editing a payload belongs to whatever wrote it.
``height``
    Minimum height in pixels (default 240).
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from .registry import register_section

logger = logging.getLogger(__name__)


@register_section("store_table")
class StoreTableSectionWidget(QtWidgets.QWidget):
    """A :class:`ChiTableWidget` bound to a model method returning a store."""

    AUTOFORM_REFRESH = True
    _autoform_expanding = True

    def __init__(self, model, target: str = "", **options):
        super().__init__()
        from chisurf.gui.widgets.chitable import ChiTableWidget

        self._model = model
        self._source = str(options.get("source", "") or target or "")
        self._editable = bool(options.get("editable", False))
        self._token: object = object()

        self.table = ChiTableWidget()
        self.table.setMinimumHeight(int(options.get("height", 240) or 240))

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.table, stretch=1)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)

        self.refresh()

    # -- data ---------------------------------------------------------------

    def _call(self, name: str):
        if not name:
            return None
        fn = getattr(self._model, name, None)
        if fn is None:
            logger.warning("store_table: model has no %r", name)
            return None
        try:
            return fn() if callable(fn) else fn
        except Exception:
            logger.debug("store_table: %s failed", name, exc_info=True)
            return None

    def refresh(self) -> None:
        """Re-read the store from the model and rebind the table when it changed."""
        store = self._call(self._source)
        # Identity, not equality: a store has no cheap __eq__, and comparing two
        # of them column-wise would read every byte the section exists to avoid.
        token = (id(store), getattr(store, "size", None) if store is not None else None)
        if token == self._token:
            return
        self._token = token
        if store is None:
            self.table.set_arrays({})
            return
        # The shared table draws its own "n rows x m columns" status line, so
        # this section adds none of its own.
        self.table.set_store(store, editable=self._editable)
