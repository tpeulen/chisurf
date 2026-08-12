"""Modal table editor and the convenience functions call sites use.

:class:`ChiTableDialog` wraps a :class:`ChiTableWidget` in Apply / Reset / Cancel
semantics: edits are staged in the model and only written to the underlying data
when the user accepts. That contract matters — the fit's "Show model" table reads
the accepted store back and replays it through the fitting client, so a live-edit
dialog would change what "Cancel" means.

:func:`edit_store` is the drop-in entry point, deliberately keeping the calling
convention the retired ``edit_dataframe`` (and, before it, the third-party editor
and ndX's own dialog) exposed — only the container changed, from a
:class:`pandas.DataFrame` to a ``tttrlib.DataStore``.
"""

from __future__ import annotations

from collections.abc import Sequence

from qtpy import QtCore, QtWidgets

from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.chitable.colorize import ValueColorScheme
from chisurf.gui.widgets.chitable.source import DataStoreSource, TableSource
from chisurf.gui.widgets.chitable.widget import (
    DEFAULT_FEATURES,
    ChiTableWidget,
    TableFeature,
)


class ChiTableDialog(QtWidgets.QDialog):
    """Modal viewer/editor for a table.

    Parameters
    ----------
    source : TableSource, optional
        Data adapter to display.
    model : qtpy.QtCore.QAbstractItemModel, optional
        Existing model to display instead of ``source``.
    title : str
        Window title.
    features : TableFeature, optional
        Feature set; defaults to :data:`DEFAULT_FEATURES` plus editing when
        ``readonly`` is false.
    readonly : bool
        Hide the Apply/Reset buttons and disable editing.
    color_scheme : ValueColorScheme, optional
        Initial colouring policy.
    parent : qtpy.QtWidgets.QWidget, optional
        Parent widget.
    """

    def __init__(
        self,
        *,
        source: TableSource | None = None,
        model: QtCore.QAbstractItemModel | None = None,
        title: str = "Data",
        features: TableFeature | None = None,
        readonly: bool = False,
        color_scheme: ValueColorScheme | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 600)
        self.setMinimumSize(480, 280)

        self._readonly = bool(readonly)
        if features is None:
            features = DEFAULT_FEATURES
            if not readonly:
                features = features | TableFeature.EDIT

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._table = ChiTableWidget(
            source=source,
            model=model,
            features=features,
            color_scheme=color_scheme,
            staged=not readonly,
            parent=self,
        )
        layout.addWidget(self._table, 1)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)

        self._btn_reset = QtWidgets.QToolButton(self)
        self._btn_reset.setText(f"{Glyphs.RESET} Reset")
        self._btn_reset.setToolTip("Discard every change made in this dialog")
        self._btn_reset.clicked.connect(self._table.rollback)
        self._btn_reset.setVisible(not readonly)
        buttons.addWidget(self._btn_reset)

        self._btn_ok = QtWidgets.QToolButton(self)
        self._btn_ok.setText(f"{Glyphs.CHECK} {'Close' if readonly else 'Apply'}")
        self._btn_ok.setToolTip(
            "Close the dialog" if readonly else "Write every change back to the data"
        )
        self._btn_ok.clicked.connect(self.accept)
        buttons.addWidget(self._btn_ok)

        self._btn_cancel = QtWidgets.QToolButton(self)
        self._btn_cancel.setText(f"{Glyphs.CLOSE} Cancel")
        self._btn_cancel.setToolTip("Close without writing any change back")
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_cancel.setVisible(not readonly)
        buttons.addWidget(self._btn_cancel)

        layout.addLayout(buttons)

    def accept(self) -> None:  # noqa: D102 (Qt override)
        if not self._readonly:
            self._table.commit()
        super().accept()

    def reject(self) -> None:  # noqa: D102 (Qt override)
        if not self._readonly:
            self._table.rollback()
        super().reject()

    @property
    def table(self) -> ChiTableWidget:
        """Return the embedded table widget.

        Returns
        -------
        ChiTableWidget
        """
        return self._table

    @property
    def store(self):
        """Return the edited store.

        Returns
        -------
        tttrlib.DataStore or None
        """
        return self._table.to_store()

    def get_value(self):
        """Return the edited store.

        Kept for parity with the editor this replaces, whose callers read the
        result through ``get_value()``.

        Returns
        -------
        tttrlib.DataStore or None
        """
        return self._table.to_store()


def edit_store(
    store,
    *,
    parent: QtWidgets.QWidget | None = None,
    title: str = "Data",
    readonly: bool = False,
    readonly_columns: Sequence[str] = (),
    colorize_columns: Sequence[str] | None = None,
    color: bool = False,
    features: TableFeature | None = None,
):
    """Open a modal editor on a store and return the accepted result.

    The store is copied, so a cancelled dialog cannot leave partial edits behind.

    Parameters
    ----------
    store : tttrlib.DataStore
        The store to edit.
    parent : qtpy.QtWidgets.QWidget, optional
        Parent widget.
    title : str
        Window title.
    readonly : bool
        Open as a viewer.
    readonly_columns : sequence of str
        Column labels that must not be edited.
    colorize_columns : sequence of str, optional
        Columns eligible for value shading; ``None`` means every numeric column.
        A column renders as a checkbox automatically when its own dtype is
        ``bool`` -- unlike the retired ``DataFrameSource``, nothing here needs
        telling which columns are boolean.
    color : bool
        Start with value shading switched on.
    features : TableFeature, optional
        Override the feature set.

    Returns
    -------
    tttrlib.DataStore or None
        The edited store, or ``None`` when the dialog was cancelled.
    """
    from chisurf.core.datastore import row_count, take_rows

    working = take_rows(store, range(row_count(store)))
    source = DataStoreSource(
        working,
        editable=not readonly,
        readonly_columns=readonly_columns,
        colorize_columns=colorize_columns,
    )
    dlg = ChiTableDialog(
        source=source,
        title=title,
        readonly=readonly,
        features=features,
        color_scheme=ValueColorScheme(enabled=bool(color)),
        parent=parent,
    )
    if dlg.exec_() == QtWidgets.QDialog.Accepted:
        return working
    return None


def show_store(
    store,
    *,
    parent: QtWidgets.QWidget | None = None,
    title: str = "Data",
    color: bool = False,
) -> ChiTableDialog:
    """Open a non-modal, read-only viewer on a store.

    Parameters
    ----------
    store : tttrlib.DataStore
        The store to display.
    parent : qtpy.QtWidgets.QWidget, optional
        Parent widget.
    title : str
        Window title.
    color : bool
        Start with value shading switched on.

    Returns
    -------
    ChiTableDialog
        The shown dialog; the caller must keep a reference to it.
    """
    dlg = ChiTableDialog(
        source=DataStoreSource(store),
        title=title,
        readonly=True,
        color_scheme=ValueColorScheme(enabled=bool(color)),
        parent=parent,
    )
    dlg.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
    dlg.show()
    return dlg
