"""Table widget that renders a list of FittingParameter objects as editable rows.

Provides :class:`ParameterGroupTableModel` (the ``QAbstractTableModel``) and
:class:`ParameterGroupTableWidget` (the ``QWidget`` wrapper with a
``QTableView`` and checkbox delegates).  Designed for
:class:`chisurf.core.dataspec.ParameterGroupTableSection` in the AutoForm
system, but usable standalone::

    model = ParameterGroupTableModel(my_params)
    view = ParameterGroupTableWidget(model=model)
    view.show()

Each row represents one parameter; columns are controlled by the ``columns``
attribute on the section descriptor.
"""

from __future__ import annotations

import re
from functools import partial
from typing import Callable, List, Optional

from qtpy import QtCore, QtGui, QtWidgets

from chisurf import typing
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.gui.glyphs import Glyphs

# ── column enumeration ──────────────────────────────────────────────────

COL_NAME = 0
COL_VALUE = 1
COL_FIXED = 2
COL_BOUNDS_LO = 3
COL_BOUNDS_HI = 4
COL_BOUNDS_ON = 5
COL_ERROR = 6

#: (id, label, editable, kind)
COLUMN_META = [
    ("name", "Name", False, "str"),
    ("value", "Value", True, "float"),
    ("fixed", "Fixed", True, "bool"),
    ("bounds_lo", "Lo", True, "float"),
    ("bounds_hi", "Hi", True, "float"),
    ("bounds_on", "Bounds", True, "bool"),
    ("error", "Error", False, "float"),
]

COLUMN_IDS = [m[0] for m in COLUMN_META]

#: The subset of columns (without the read-only "name") repeated per parameter
#: slot in a :class:`PairedParameterTableModel`. The first entry ("value")
#: header is replaced by the slot's derived group label (e.g. ``xₗ``); the rest
#: are shared short labels.
SLOT_COLUMN_META = [m for m in COLUMN_META if m[0] != "name"]
SLOT_COLUMN_IDS = [m[0] for m in SLOT_COLUMN_META]


def _editor(param: FittingParameter):
    """Return the parameter's controller when it can apply edits, else ``None``.

    Both tables install a
    :class:`~chisurf.gui.widgets.fitting.parameter_widgets.FittingParameterProxyController`
    on every parameter they render (see ``_install_controllers``).  That
    controller is what carries an edit to the backend and into the provenance
    trace, exactly as the per-parameter row widgets do — writing the attribute
    directly would keep the edit local and invisible to the history.  A table
    used standalone (no controllers installed) falls back to the plain write.
    """
    ctrl = getattr(param, "controller", None)
    return ctrl if hasattr(ctrl, "apply_value") else None


def _set_param_value(param: FittingParameter, col_id: str, value: typing.Any) -> bool:
    """Write one editable column back onto ``param``; return success.

    Shared by :class:`ParameterGroupTableModel` and
    :class:`PairedParameterTableModel` so both tables edit parameters through the
    exact same rules (linked followers stay read-only, bounds are stored as a
    tuple).
    """
    ctrl = _editor(param)
    try:
        if col_id == "value":
            is_follower = getattr(param, "is_linked", False) and not getattr(
                param, "is_link_master", False
            )
            if is_follower:
                return False
            if ctrl is not None:
                ctrl.apply_value(float(value), param)
            else:
                param.value = float(value)
        elif col_id == "fixed":
            if ctrl is not None:
                ctrl.apply_fixed(_parse_bool(value), param)
            else:
                param.fixed = _parse_bool(value)
        elif col_id in ("bounds_lo", "bounds_hi"):
            b = list(param.bounds)
            b[0 if col_id == "bounds_lo" else 1] = float(value)
            if ctrl is not None:
                ctrl.apply_bounds(b[0], b[1], param)
            else:
                param.bounds = tuple(b)
        elif col_id == "bounds_on":
            if ctrl is not None:
                ctrl.apply_bounds_on(_parse_bool(value), param)
            else:
                param.bounds_on = _parse_bool(value)
        else:
            return False
    except Exception:
        return False
    return True


# ── rich-text (HTML) delegate ───────────────────────────────────────────


class _RichTextDelegate(QtWidgets.QStyledItemDelegate):
    """Render a cell's display text as HTML so parameter labels keep their
    sub/superscripts (e.g. ``n<sub>0</sub>`` → n₀, ``&tau;<sub>0</sub>`` → τ₀)."""

    def paint(self, painter, option, index):
        text = index.data(QtCore.Qt.DisplayRole)
        if not text or "<" not in str(text):
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
        painter.translate(rect.left() + 2, rect.top() + max(0, (rect.height() - doc.size().height()) / 2))
        ctx.clip = QtCore.QRectF(0, 0, rect.width(), rect.height())
        doc.documentLayout().draw(painter, ctx)
        painter.restore()


# ── boolean checkbox delegate ───────────────────────────────────────────


class _BooleanToggleDelegate(QtWidgets.QStyledItemDelegate):
    """Click-to-toggle checkbox rendered centered in the cell."""

    def _is_checked(self, value) -> bool:
        try:
            if isinstance(value, (bool,)) or value is None:
                return bool(value) if value is not None else False
            if isinstance(value, str):
                return value.strip().lower() in ("true", "1", "yes", "on")
            return bool(int(value))
        except Exception:
            return False

    def _toggle(self, value) -> bool:
        return not self._is_checked(value)

    def _checkbox_rect(self, option: QtWidgets.QStyleOptionViewItem) -> QtCore.QRect:
        rect = option.rect
        size = 16
        x = rect.x() + (rect.width() - size) // 2
        y = rect.y() + (rect.height() - size) // 2
        return QtCore.QRect(x, y, size, size)

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
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

    def createEditor(self, parent, option, index):
        return None

    def editorEvent(
        self,
        event: QtCore.QEvent,
        model: QtCore.QAbstractItemModel,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> bool:
        # A read-only cell must not toggle, and only the *left* button edits:
        # every other button reached here too, so right-clicking a Fixed cell to
        # open the link / copy context menu silently flipped the flag first.
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


class _FloatEditDelegate(QtWidgets.QStyledItemDelegate):
    """Float-column editor using :class:`ScientificDoubleSpinBox`.

    Qt's default item-editor factory maps a plain ``float`` EditRole value to a
    stock ``QDoubleSpinBox``, which defaults to 2 decimal places and a 0-99.99
    range — silently truncating (displaying ``0.00``) and un-enterable outside
    that range for the small/large values these tables routinely hold (e.g. a
    bunching time constant of 0.001 ms). This delegate swaps in the same
    adaptive-significant-figures, unbounded editor the standalone parameter
    widgets already use (:mod:`chisurf.gui.widgets.fitting.parameter_widgets`).
    """

    def createEditor(self, parent, option, index):
        from chisurf.gui.widgets.fitting.scientific_spinbox import ScientificDoubleSpinBox

        return ScientificDoubleSpinBox(parent, decimals=6, finite=False)

    def setEditorData(self, editor, index) -> None:
        value = index.data(QtCore.Qt.EditRole)
        try:
            editor.setValue(float(value))
        except Exception:
            pass

    def setModelData(self, editor, model, index) -> None:
        # A spin box only turns typed text into a value when the entry is
        # committed, and the delegate's commit runs *before* the editor sees the
        # Return / focus-out that would do it -- so ``value()`` would still hold
        # the pre-edit number and the cell snapped straight back. Interpreting
        # the text here is what Qt's own item delegate does for spin-box editors.
        editor.interpretText()
        model.setData(index, editor.value(), QtCore.Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index) -> None:
        editor.setGeometry(option.rect)


# ── table model ─────────────────────────────────────────────────────────


class ParameterGroupTableModel(QtCore.QAbstractTableModel):
    """Table model exposing a list of :class:`FittingParameter` objects.

    Each row is one parameter.  Columns are defined by :data:`COLUMN_META`
    and map to the parameter's value, fixed flag, bounds, and error estimate.
    The backing list is *not* copied — edits flow through to the original
    objects immediately.
    """

    def __init__(
        self,
        params: typing.List[FittingParameter],
        parent: typing.Optional[QtCore.QObject] = None,
    ):
        super().__init__(parent)
        self._params: typing.List[FittingParameter] = list(params)

    # -- row / column count -------------------------------------------------
    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self._params) if not parent.isValid() else 0

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(COLUMN_META) if not parent.isValid() else 0

    # -- header data --------------------------------------------------------
    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.DisplayRole,
    ):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            if 0 <= section < len(COLUMN_META):
                return COLUMN_META[section][1]
        return None

    # -- cell data ----------------------------------------------------------
    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        param = self._params[index.row()]
        col_id, _, editable, kind = COLUMN_META[index.column()]

        if role == QtCore.Qt.DisplayRole:
            return self._display_value(col_id, kind, param)
        if role == QtCore.Qt.EditRole:
            return self._edit_value(col_id, param)
        if role == QtCore.Qt.TextAlignmentRole:
            if kind == "float":
                return int(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            if kind == "bool":
                return int(QtCore.Qt.AlignCenter)
        if role == QtCore.Qt.ToolTipRole:
            return self._tooltip(col_id, param)
        return None

    @staticmethod
    def _display_value(col_id: str, kind: str, param: FittingParameter) -> str:
        if col_id == "name":
            return str(param.__dict__.get("label_text", param.name))
        if col_id == "value":
            v = param.value
            return f"{v:.6g}" if v is not None else ""
        if col_id == "fixed":
            return str(bool(param.fixed))
        if col_id == "bounds_lo":
            b = param.bounds
            if b is not None and b[0] is not None and param.bounds_on:
                return f"{b[0]:.6g}"
            return ""
        if col_id == "bounds_hi":
            b = param.bounds
            if b is not None and len(b) > 1 and b[1] is not None and param.bounds_on:
                return f"{b[1]:.6g}"
            return ""
        if col_id == "bounds_on":
            return str(bool(param.bounds_on))
        if col_id == "error":
            e = getattr(param, "error_estimate", None)
            if e is not None and _isfinite(e):
                return f"{e:.4g}"
            return ""
        return ""

    @staticmethod
    def _edit_value(col_id: str, param: FittingParameter):
        if col_id == "value":
            return float(param.value)
        if col_id == "fixed":
            return bool(param.fixed)
        if col_id == "bounds_lo":
            b = param.bounds
            return float(b[0]) if b is not None and b[0] is not None else 0.0
        if col_id == "bounds_hi":
            b = param.bounds
            return float(b[1]) if b is not None and len(b) > 1 and b[1] is not None else 0.0
        if col_id == "bounds_on":
            return bool(param.bounds_on)
        return None

    @staticmethod
    def _tooltip(col_id: str, param: FittingParameter) -> typing.Optional[str]:
        if col_id == "name":
            d = getattr(param, "description", "") or ""
            return d if d else None
        if col_id == "value":
            linked = getattr(param, "is_linked", False)
            if linked and not getattr(param, "is_link_master", False):
                link = getattr(param, "link", None)
                lname = getattr(link, "name", "?") if link else "?"
                return f"Linked to {lname} (read-only)"
        return None

    # -- flags / editing ----------------------------------------------------
    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        if not index.isValid():
            return QtCore.Qt.NoItemFlags
        col_id, _, editable, _ = COLUMN_META[index.column()]
        base = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        if not editable:
            return base
        # Linked followers cannot edit value
        param = self._params[index.row()]
        if col_id == "value":
            is_follower = getattr(param, "is_linked", False) and not getattr(
                param, "is_link_master", False
            )
            if is_follower:
                return base
        # Bounds columns only editable when bounds_on is True
        if col_id in ("bounds_lo", "bounds_hi") and not getattr(param, "bounds_on", False):
            return base
        return base | QtCore.Qt.ItemIsEditable

    def setData(
        self,
        index: QtCore.QModelIndex,
        value: typing.Any,
        role: int = QtCore.Qt.EditRole,
    ) -> bool:
        if role != QtCore.Qt.EditRole or not index.isValid():
            return False
        param = self._params[index.row()]
        col_id, _, _, _ = COLUMN_META[index.column()]

        if not _set_param_value(param, col_id, value):
            return False

        # Repaint the whole row, not just the edited cell: one column's edit
        # changes what its neighbours show. Enabling bounds turns the blank Lo /
        # Hi cells into editable numbers, and a bound that excludes the current
        # value clamps it — with a single-cell signal those cells kept painting
        # the superseded text.
        self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), self.columnCount() - 1))
        return True

    # -- helpers ------------------------------------------------------------
    @property
    def parameters(self) -> typing.List[FittingParameter]:
        """Live list of parameters backing the model."""
        return self._params


def _isfinite(v: typing.Any) -> bool:
    try:
        import numpy as np

        return bool(np.isfinite(v))
    except Exception:
        return True


def _parse_bool(value: typing.Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    try:
        return bool(int(value))
    except Exception:
        return bool(value)


def _release_controllers(owned, *_) -> None:
    """Clear ``parameter.controller`` back-references owned by a dead table."""
    for param, ctrl in owned:
        try:
            if getattr(param, "controller", None) is ctrl:
                param.controller = None
        except Exception:
            continue


# ── table widget ────────────────────────────────────────────────────────


class ParameterGroupTableWidget(QtWidgets.QWidget):
    """A ``QTableView`` that edits a list of :class:`FittingParameter` objects.

    Parameters
    ----------
    params : list of FittingParameter
        The parameters to display (one per row).
    section : chisurf.core.dataspec.ParameterGroupTableSection or None
        Section descriptor controlling visible columns and collapsible
        behaviour.  When ``None`` all columns are shown.
    parent : QWidget or None
        Parent widget.
    on_change : callable or None
        Optional callback invoked (with no arguments) after every edit.  In
        the AutoForm context this is wired to trigger a fit recompute.
    """

    #: Re-read parameter values after a fit/compute. The widget is emitted
    #: full-width (NOT a form field), so it opts into the refresh cycle via
    #: AUTOFORM_REFRESH; :meth:`AutoForm.sync_fields` also reaches it (it syncs
    #: AUTOFORM_REFRESH widgets), so displayed values stay current like the
    #: per-parameter widgets.
    AUTOFORM_REFRESH = True

    def __init__(
        self,
        params: typing.List[FittingParameter],
        section: typing.Any = None,
        parent: typing.Optional[QtWidgets.QWidget] = None,
        on_change: typing.Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self._section = section
        self._on_change = on_change
        self._params = params

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._model = ParameterGroupTableModel(params)
        self._table = QtWidgets.QTableView()
        self._table.setModel(self._model)
        self._table.setAlternatingRowColors(False)
        self._table.setWordWrap(False)
        self._table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self._table.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        from chisurf.gui.widgets.general import table_header_height, table_row_height

        self._row_h = table_row_height()
        self._header_h = table_header_height()
        self._table.verticalHeader().setDefaultSectionSize(self._row_h)
        self._table.verticalHeader().setMinimumSectionSize(self._row_h)
        self._table.verticalHeader().hide()
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self._table.setShowGrid(True)
        # Size the table to its rows — no internal scrollbar, no empty space
        # below the last row (that wasted the panel's vertical space).
        self._table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        # Font: the single central table font (monospace by default), so this
        # matches the log/console table and numeric columns line up.
        try:
            from chisurf.gui.widgets.general import table_font

            font = table_font()
            font.setStyleStrategy(QtGui.QFont.PreferAntialias)
            self._table.setFont(font)
            self._table.horizontalHeader().setFont(font)
        except Exception:
            pass

        # Column sizing: the Name column absorbs the spare width; the numeric /
        # checkbox columns hug their contents so nothing is left stretched wide.
        hh = self._table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setMinimumSectionSize(36)

        def _resize(col, mode):
            try:
                hh.setSectionResizeMode(col, mode)
            except Exception:
                try:
                    hh.setResizeMode(col, mode)
                except Exception:
                    pass

        _resize(COL_NAME, QtWidgets.QHeaderView.Stretch)
        for col in (COL_VALUE, COL_FIXED, COL_BOUNDS_LO, COL_BOUNDS_HI, COL_BOUNDS_ON, COL_ERROR):
            _resize(col, QtWidgets.QHeaderView.ResizeToContents)

        # Hide columns that are not in the section's whitelist
        self._apply_column_visibility()

        # Rich-text (HTML) names keep sub/superscripts; boolean toggle delegates
        # on the fixed / bounds columns.
        self._name_delegate = _RichTextDelegate(self._table)
        self._table.setItemDelegateForColumn(COL_NAME, self._name_delegate)
        self._toggle_delegate = _BooleanToggleDelegate(self._table)
        self._table.setItemDelegateForColumn(COL_FIXED, self._toggle_delegate)
        self._table.setItemDelegateForColumn(COL_BOUNDS_ON, self._toggle_delegate)
        self._float_delegate = _FloatEditDelegate(self._table)
        for col in (COL_VALUE, COL_BOUNDS_LO, COL_BOUNDS_HI):
            self._table.setItemDelegateForColumn(col, self._float_delegate)

        # Wire model changes to optional callback
        self._model.dataChanged.connect(self._on_data_changed)

        # Right-click: link/unlink the clicked parameter plus copy / paste of
        # values (also Ctrl+C / Ctrl+V while the table has focus).  Clicking a
        # name opens the same detail popup as the per-parameter row widget's
        # label, so both parameter editors behave identically.
        self._table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        self._table.clicked.connect(self._on_cell_clicked)
        #: Per-parameter controllers backing the link menu, the detail popup and
        #: each parameter's ``controller`` attribute, keyed by row.
        self._controllers: dict[int, typing.Any] = {}
        self._detail_popup = None
        #: Set while :meth:`sync` repaints, so a programmatic refresh is not
        #: mistaken for a user edit (see :meth:`_on_data_changed`).
        self._suppress_change = False
        for seq, slot in (("Ctrl+C", self._copy_selection), ("Ctrl+V", self._paste_selection)):
            sc = QtWidgets.QShortcut(QtGui.QKeySequence(seq), self._table)
            sc.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

        self._install_controllers()
        layout.addWidget(self._table)
        self._size_to_content()

    # -- parameter controllers ---------------------------------------------
    def _install_controllers(self) -> None:
        """Claim each parameter's ``controller`` so the row repaints on change.

        ``FittingParameter.update()`` and ``FittingParameterGroup.finalize()``
        drive the display through ``parameter.controller`` — the attribute the
        per-parameter row widgets set on themselves.  A table-rendered parameter
        had none, so those calls did nothing (and logged "has no controller to
        finalize" for every parameter in the group).
        """
        owned = []
        for row in range(self._model.rowCount()):
            param = self._model.parameters[row]
            ctrl = self._controller(row)
            try:
                param.controller = ctrl
            except Exception:
                continue
            owned.append((param, ctrl))
        # The parameters outlive this widget, so drop the back-reference when the
        # table goes away rather than leaving a deleted proxy behind.
        self.destroyed.connect(partial(_release_controllers, owned))

    def _size_to_content(self) -> None:
        """Fix the table height to header + visible rows so it wastes no space."""
        header_h = self._table.horizontalHeader().height() or self._header_h
        n = self._model.rowCount()
        self._table.setFixedHeight(header_h + self._row_h * max(1, n) + 2)

    # -- per-parameter controller ------------------------------------------
    def _controller(self, row: int):
        """Return (creating on first use) the proxy controller for ``row``.

        The controller supplies the link menu and the detail popup that the
        per-parameter row widgets use, so the table offers the same actions
        without duplicating their logic.
        """
        ctrl = self._controllers.get(row)
        if ctrl is None:
            from chisurf.gui.widgets.fitting.parameter_widgets import (
                FittingParameterProxyController,
            )

            ctrl = FittingParameterProxyController(
                self._model.parameters[row],
                parent=self,
                on_change=partial(self._refresh_row, row),
            )
            self._controllers[row] = ctrl
        return ctrl

    def _refresh_row(self, row: int) -> None:
        """Repaint one row from its parameter.

        This is what a proxy's ``finalize()`` does, mirroring the row widget's
        ``finalize`` — a **display** refresh only.  It must not dispatch the
        section's ``on_change`` (a fit update): the model calls ``finalize()``
        *during* a recompute, so notifying from here would feed a recompute back
        into itself.  Edits that do warrant a recompute go through the popup's
        ``_trigger_model_update`` or through a cell edit.
        """
        if row >= self._model.rowCount():
            return
        self._suppress_change = True
        try:
            left = self._model.index(row, 0)
            right = self._model.index(row, self._model.columnCount() - 1)
            self._model.dataChanged.emit(left, right)
        finally:
            self._suppress_change = False

    def _on_cell_clicked(self, index: QtCore.QModelIndex) -> None:
        """Open the parameter detail popup when its name is clicked."""
        if not index.isValid() or index.column() != COL_NAME:
            return
        self._open_details_popup(index.row())

    def _open_details_popup(self, row: int) -> None:
        from chisurf.gui.widgets.fitting.parameter_widgets import (
            FittingParameterDetailPopup,
        )

        popup = FittingParameterDetailPopup(self._controller(row))
        # Position the popup under the clicked name cell.
        rect = self._table.visualRect(self._model.index(row, COL_NAME))
        popup.move(self._table.viewport().mapToGlobal(rect.bottomLeft()))
        popup.refresh_from_model()
        popup.show()
        popup.raise_()
        popup.activateWindow()
        popup.setFocus(QtCore.Qt.PopupFocusReason)
        # Hold a reference so the popup is not garbage-collected while shown.
        self._detail_popup = popup

    # -- link / copy / paste ------------------------------------------------
    def _context_menu(self, pos) -> None:
        menu = QtWidgets.QMenu(self._table)
        index = self._table.indexAt(pos)
        if index.isValid():
            self._add_link_actions(menu, index.row())
        act_copy = menu.addAction(f"{Glyphs.COPY} Copy")
        act_paste = menu.addAction(f"{Glyphs.IMPORT} Paste")
        act_copy.setShortcut("Ctrl+C")
        act_paste.setShortcut("Ctrl+V")
        act_copy.triggered.connect(self._copy_selection)
        act_paste.triggered.connect(self._paste_selection)
        act_paste.setEnabled(bool(QtWidgets.QApplication.clipboard().text().strip()))
        menu.exec_(self._table.viewport().mapToGlobal(pos))

    def _add_link_actions(self, menu: QtWidgets.QMenu, row: int) -> None:
        """Prepend the link/unlink entries for ``row``'s parameter to ``menu``."""
        param = self._model.parameters[row]
        ctrl = self._controller(row)
        link_menu = ctrl.build_link_menu()
        link_menu.setTitle(f"🔗 Link {param.name} to")
        menu.addMenu(link_menu)

        act_unlink = menu.addAction(f"{Glyphs.CHAIN}‍💥 Unlink")
        act_unlink.setEnabled(bool(getattr(param, "is_linked", False)))
        act_unlink.triggered.connect(lambda: self._unlink(row))
        menu.addSeparator()

    def _unlink(self, row: int) -> None:
        """Drop the link on ``row``'s parameter via the fitting client."""
        from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

        ctrl = self._controller(row)
        param = self._model.parameters[row]
        source = ctrl._parameter_context(param)
        fc = get_fitting_client()
        if fc is not None:
            fc.unlink_parameter(
                parameter_name=str(param.name),
                fit_uid=source.get("fit_uid"),
            )
        ctrl._trace_operation(
            "parameter_unlink",
            f"unlink parameter '{param.name}' in fit '{source['fit_group']}' "
            f"/ local '{source['local_fit']}'",
            {"parameter_name": str(param.name), **source},
        )
        ctrl._update_linked_parameters()
        ctrl.finalize()

    def _copy_selection(self) -> None:
        """Copy the selected cells as tab/newline-separated text."""
        idxs = self._table.selectedIndexes()
        if not idxs:
            return
        rows: dict[int, list[str]] = {}
        for i in sorted(idxs, key=lambda x: (x.row(), x.column())):
            rows.setdefault(i.row(), []).append(str(i.data(QtCore.Qt.DisplayRole) or ""))
        text = "\n".join("\t".join(cells) for cells in rows.values())
        QtWidgets.QApplication.clipboard().setText(text)

    def _paste_selection(self) -> None:
        """Paste clipboard values into the selected editable cells.

        A single value fills every selected editable cell; a tab/newline block is
        placed starting at the top-left selected cell.
        """
        text = QtWidgets.QApplication.clipboard().text()
        idxs = self._table.selectedIndexes()
        if not text.strip() or not idxs:
            return
        grid = [line.split("\t") for line in text.splitlines() if line != ""]
        editable = QtCore.Qt.ItemIsEditable

        if len(grid) == 1 and len(grid[0]) == 1:
            value = grid[0][0]
            for i in idxs:
                if self._model.flags(i) & editable:
                    self._model.setData(i, value, QtCore.Qt.EditRole)
            return
        anchor = min(idxs, key=lambda x: (x.row(), x.column()))
        for dr, line in enumerate(grid):
            for dc, value in enumerate(line):
                i = self._model.index(anchor.row() + dr, anchor.column() + dc)
                if i.isValid() and (self._model.flags(i) & editable):
                    self._model.setData(i, value, QtCore.Qt.EditRole)

    # -- column visibility --------------------------------------------------
    def _apply_column_visibility(self):
        section = self._section
        if section is None:
            return
        cols = getattr(section, "columns", None)
        if not cols:
            return
        visible = set(cols)
        for i, cid in enumerate(COLUMN_IDS):
            self._table.setColumnHidden(i, cid not in visible)

    # -- change dispatch ----------------------------------------------------
    def _on_data_changed(self, *_):
        # Only a user edit dispatches; a programmatic repaint (``sync``, or a
        # parameter's ``finalize`` during a recompute) must not, or the fit
        # update it triggers comes straight back as another repaint.
        if self._suppress_change:
            return
        cb = self._on_change
        if cb is not None:
            try:
                cb()
            except Exception:
                pass

    # -- sync ---------------------------------------------------------------
    def sync(self) -> None:
        """Re-read parameter values into the model and repaint.

        A refresh, not an edit — it does not dispatch ``on_change`` (this runs
        after a fit, and dispatching would request another one).
        """
        self._suppress_change = True
        try:
            top_left = self._model.index(0, 0)
            bottom_right = self._model.index(
                self._model.rowCount() - 1,
                self._model.columnCount() - 1,
            )
            self._model.dataChanged.emit(top_left, bottom_right)
        finally:
            self._suppress_change = False

    #: :meth:`AutoForm.refresh_plots` calls ``refresh`` on AUTOFORM_REFRESH widgets.
    refresh = sync

    # -- bounds column visibility -------------------------------------------
    def _allowed_columns(self) -> typing.Optional[set]:
        """Return the section's column whitelist as a set, or ``None`` (all allowed)."""
        cols = getattr(self._section, "columns", None) if self._section else None
        return set(cols) if cols else None

    def has_bounds_columns(self) -> bool:
        """Return True when this table can show any Lo / Hi / Bounds column."""
        allowed = self._allowed_columns()
        return allowed is None or bool(
            {"bounds_lo", "bounds_hi", "bounds_on"} & allowed
        )

    def set_bounds_visible(self, visible: bool) -> None:
        """Show or hide the Lo / Hi / Bounds columns (bounds stay editable in the
        parameter details popup). Columns excluded by the section's whitelist stay
        hidden regardless."""
        allowed = self._allowed_columns()
        for cid, col in (
            ("bounds_lo", COL_BOUNDS_LO),
            ("bounds_hi", COL_BOUNDS_HI),
            ("bounds_on", COL_BOUNDS_ON),
        ):
            permitted = allowed is None or cid in allowed
            self._table.setColumnHidden(col, not (visible and permitted))

    # -- accessors ----------------------------------------------------------
    @property
    def table_model(self) -> ParameterGroupTableModel:
        return self._model

    @property
    def table_view(self) -> QtWidgets.QTableView:
        return self._table

    @property
    def parameters(self) -> typing.List[FittingParameter]:
        return self._params


# ── paired component table ──────────────────────────────────────────────
#
# The lifetime (amplitude / lifetime) and rotation (b / rho) dynamic groups pair
# two parameters per component.  Rendered as a *paired* table, each component is
# a single row: a "#" index column, then the compact Value/Fixed/Lo/Hi/Bounds/
# Error columns repeated once per parameter slot so the amplitude block sits
# beside the lifetime block (author-approved layout).


def _group_header_label(label_text: str) -> str:
    """Strip the per-component index from a parameter label for a column header.

    ``x<sub>l, 1</sub>`` → ``x<sub>l</sub>``; ``b<sub>1</sub>`` → ``b``;
    ``&rho;<sub>1</sub>`` → ``&rho;``.  The component number lives in the paired
    table's "#" column, so the header names only the *kind* of parameter (the
    amplitude column, the lifetime column).
    """

    def _strip(match: "re.Match[str]") -> str:
        inner = re.sub(r"[,\s]*\d+\s*$", "", match.group(1)).strip()
        return f"<sub>{inner}</sub>" if inner else ""

    return re.sub(r"<sub>(.*?)</sub>", _strip, str(label_text))


class _RichTextHeaderView(QtWidgets.QHeaderView):
    """Horizontal header that renders its labels as HTML (sub/superscripts).

    ``QHeaderView`` shows the raw ``x<sub>l</sub>`` markup otherwise; this paints
    the header chrome without text and overlays a rendered ``QTextDocument`` so
    the paired-table column titles read ``xₗ`` / ``τₗ`` like the parameter row
    widgets.
    """

    def __init__(self, parent: typing.Optional[QtWidgets.QWidget] = None):
        super().__init__(QtCore.Qt.Horizontal, parent)
        self.setDefaultAlignment(QtCore.Qt.AlignCenter)

    def paintSection(self, painter, rect, logicalIndex):  # noqa: N802 (Qt override)
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
        # Header chrome (background/borders) without its text, then the HTML overlay.
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


class PairedParameterTableModel(QtCore.QAbstractTableModel):
    """Table model where each row is a component of ``width`` parameters.

    The flat parameter list ``[p00, p01, p10, p11, ...]`` (as returned by the
    group's ``rows_source``) is grouped ``width`` at a time so
    ``[[p00, p01], [p10, p11], ...]`` — one component per row.  Column 0 is the
    1-based component index; the remaining columns repeat :data:`SLOT_COLUMN_META`
    once per slot.  The backing list is *not* copied — edits flow straight to the
    parameter objects.
    """

    _N_SLOT_COLS = len(SLOT_COLUMN_META)

    def __init__(
        self,
        params: typing.List[FittingParameter],
        width: int,
        parent: typing.Optional[QtCore.QObject] = None,
    ):
        super().__init__(parent)
        self._width = max(1, int(width))
        self._params: typing.List[FittingParameter] = list(params)

    # -- structural updates -------------------------------------------------
    def set_params(self, params: typing.List[FittingParameter]) -> None:
        """Replace the backing parameter list (used on add/remove of a component)."""
        self.beginResetModel()
        self._params = list(params)
        self.endResetModel()

    @property
    def parameters(self) -> typing.List[FittingParameter]:
        """Live flat list of parameters backing the model."""
        return self._params

    @property
    def width(self) -> int:
        """Number of parameters per component row."""
        return self._width

    # -- row / column count -------------------------------------------------
    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        """Return the component count (number of parameters // ``width``)."""
        if parent.isValid():
            return 0
        return len(self._params) // self._width

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        """Return one index column plus ``width`` repeats of the slot columns."""
        if parent.isValid():
            return 0
        return 1 + self._width * self._N_SLOT_COLS

    # -- column mapping -----------------------------------------------------
    def _slot(self, column: int):
        """Map a column to ``(slot, sub, col_id, kind, editable)`` or ``None``."""
        if column <= 0:
            return None
        c = column - 1
        slot = c // self._N_SLOT_COLS
        sub = c % self._N_SLOT_COLS
        col_id, _, editable, kind = SLOT_COLUMN_META[sub]
        return slot, sub, col_id, kind, editable

    def param_at(self, row: int, column: int):
        """Return ``(param, col_id)`` for a data cell, or ``None`` (index column)."""
        s = self._slot(column)
        if s is None:
            return None
        slot, _, col_id, _, _ = s
        idx = row * self._width + slot
        if 0 <= idx < len(self._params):
            return self._params[idx], col_id
        return None

    # -- header data --------------------------------------------------------
    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        """Return the column title: ``#``, the slot's group label, or a shared column label."""
        if orientation != QtCore.Qt.Horizontal or role != QtCore.Qt.DisplayRole:
            return None
        if section == 0:
            return "#"
        s = self._slot(section)
        if s is None:
            return None
        slot, sub, _, _, _ = s
        if sub == 0:
            # The slot's group label, derived from that slot's parameter in the
            # first component row (row 0): params[slot] for a width-``w`` group.
            if slot < len(self._params):
                p = self._params[slot]
                return _group_header_label(p.__dict__.get("label_text", p.name))
        return SLOT_COLUMN_META[sub][1]

    # -- cell data ----------------------------------------------------------
    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):
        """Cell value for the 1-based index column or a slot's parameter."""
        if not index.isValid():
            return None
        if index.column() == 0:
            if role == QtCore.Qt.DisplayRole:
                return str(index.row() + 1)
            if role == QtCore.Qt.TextAlignmentRole:
                return int(QtCore.Qt.AlignCenter)
            return None
        s = self._slot(index.column())
        pa = self.param_at(index.row(), index.column())
        if s is None or pa is None:
            return None
        param, col_id = pa
        kind = s[3]
        if role == QtCore.Qt.DisplayRole:
            return ParameterGroupTableModel._display_value(col_id, kind, param)
        if role == QtCore.Qt.EditRole:
            return ParameterGroupTableModel._edit_value(col_id, param)
        if role == QtCore.Qt.TextAlignmentRole:
            if kind == "float":
                return int(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            if kind == "bool":
                return int(QtCore.Qt.AlignCenter)
        if role == QtCore.Qt.ToolTipRole:
            return ParameterGroupTableModel._tooltip(col_id, param)
        return None

    # -- flags / editing ----------------------------------------------------
    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        """Return item flags: value/fixed/bounds editable, index/followers/disabled-bounds read-only."""
        if not index.isValid():
            return QtCore.Qt.NoItemFlags
        base = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        if index.column() == 0:
            return base
        s = self._slot(index.column())
        pa = self.param_at(index.row(), index.column())
        if s is None or pa is None:
            return base
        _, _, col_id, _, editable = s
        if not editable:
            return base
        param, _ = pa
        if col_id == "value":
            is_follower = getattr(param, "is_linked", False) and not getattr(
                param, "is_link_master", False
            )
            if is_follower:
                return base
        if col_id in ("bounds_lo", "bounds_hi") and not getattr(param, "bounds_on", False):
            return base
        return base | QtCore.Qt.ItemIsEditable

    def setData(self, index, value, role=QtCore.Qt.EditRole) -> bool:
        """Write an edited cell back onto its slot's parameter."""
        if role != QtCore.Qt.EditRole or not index.isValid() or index.column() == 0:
            return False
        pa = self.param_at(index.row(), index.column())
        if pa is None:
            return False
        param, col_id = pa
        if not _set_param_value(param, col_id, value):
            return False
        # Row-wide, for the reason given in ``ParameterGroupTableModel.setData``.
        self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), self.columnCount() - 1))
        return True


class PairedParameterTableWidget(QtWidgets.QWidget):
    """A ``QTableView`` editing paired-parameter components (one row each).

    Parameters
    ----------
    params : list of FittingParameter
        Flat list of ``width``-parameter components (amplitude, lifetime, ...).
    width : int
        Parameters per component (2 for amplitude/lifetime, b/rho).
    parent : QWidget or None
    on_change : callable or None
        Invoked (no args) after every user edit; wired to a fit recompute.
    """

    #: Opt into :meth:`AutoForm.sync_fields` / ``refresh_plots`` (see the sibling
    #: :class:`ParameterGroupTableWidget`).
    AUTOFORM_REFRESH = True

    def __init__(
        self,
        params: typing.List[FittingParameter],
        width: int = 2,
        parent: typing.Optional[QtWidgets.QWidget] = None,
        on_change: typing.Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self._on_change = on_change

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._model = PairedParameterTableModel(params, width)
        self._table = QtWidgets.QTableView()
        self._table.setModel(self._model)
        self._table.setHorizontalHeader(_RichTextHeaderView(self._table))
        self._table.setAlternatingRowColors(False)
        self._table.setWordWrap(False)
        self._table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self._table.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        from chisurf.gui.widgets.general import table_header_height, table_row_height

        self._row_h = table_row_height()
        self._header_h = table_header_height()
        self._table.verticalHeader().setDefaultSectionSize(self._row_h)
        self._table.verticalHeader().setMinimumSectionSize(self._row_h)
        self._table.verticalHeader().hide()
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        self._table.setSelectionMode(QtWidgets.QAbstractItemView.ContiguousSelection)
        self._table.setShowGrid(True)
        self._table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        try:
            from chisurf.gui.widgets.general import table_font

            font = table_font()
            font.setStyleStrategy(QtGui.QFont.PreferAntialias)
            self._table.setFont(font)
            self._table.horizontalHeader().setFont(font)
        except Exception:
            pass

        self._configure_columns()

        # Boolean toggle delegates on every "fixed" / "bounds_on" column.
        self._toggle_delegate = _BooleanToggleDelegate(self._table)
        for col in self._bool_columns():
            self._table.setItemDelegateForColumn(col, self._toggle_delegate)

        # Scientific-notation float editors on every value / Lo / Hi column
        # (Qt's default double-spinbox editor truncates to 2 decimals / 0-99.99).
        self._float_delegate = _FloatEditDelegate(self._table)
        for col in self._float_columns():
            self._table.setItemDelegateForColumn(col, self._float_delegate)

        self._model.dataChanged.connect(self._on_data_changed)

        self._table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        #: Per-parameter proxy controllers backing the link menu / detail popup,
        #: keyed by ``id(param)`` so they survive a model reset.
        self._controllers: dict[int, typing.Any] = {}
        self._detail_popup = None
        self._suppress_change = False
        for seq, slot in (("Ctrl+C", self._copy_selection), ("Ctrl+V", self._paste_selection)):
            sc = QtWidgets.QShortcut(QtGui.QKeySequence(seq), self._table)
            sc.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

        #: Whether the per-slot Lo / Hi / Bounds columns are shown. Tracked so an
        #: add/remove rebuild keeps the user's choice.
        self._bounds_visible = True

        self._install_controllers()
        layout.addWidget(self._table)
        self._size_to_content()

    # -- structural ---------------------------------------------------------
    def set_params(self, params: typing.List[FittingParameter]) -> None:
        """Rebuild the table for a new component list (after add/remove)."""
        self._model.set_params(params)
        self._configure_columns()
        for col in self._bool_columns():
            self._table.setItemDelegateForColumn(col, self._toggle_delegate)
        for col in self._float_columns():
            self._table.setItemDelegateForColumn(col, self._float_delegate)
        self.set_bounds_visible(self._bounds_visible)
        self._install_controllers()
        self._size_to_content()

    # -- bounds column visibility -------------------------------------------
    def has_bounds_columns(self) -> bool:
        """Paired tables always carry per-slot Lo / Hi / Bounds columns."""
        return True

    def _bounds_columns(self) -> list:
        """Global column indices of every per-slot Lo / Hi / Bounds cell."""
        cols = []
        for slot in range(self._model.width):
            base = 1 + slot * len(SLOT_COLUMN_META)
            for sub, meta in enumerate(SLOT_COLUMN_META):
                if meta[0] in ("bounds_lo", "bounds_hi", "bounds_on"):
                    cols.append(base + sub)
        return cols

    def set_bounds_visible(self, visible: bool) -> None:
        """Show or hide the per-slot Lo / Hi / Bounds columns (still editable in the details popup)."""
        self._bounds_visible = bool(visible)
        for col in self._bounds_columns():
            self._table.setColumnHidden(col, not visible)

    def _bool_columns(self) -> list:
        """Global column indices carrying a boolean (fixed / bounds_on) cell."""
        n = self._model.width
        cols = []
        for slot in range(n):
            base = 1 + slot * len(SLOT_COLUMN_META)
            for sub, meta in enumerate(SLOT_COLUMN_META):
                if meta[3] == "bool":
                    cols.append(base + sub)
        return cols

    def _float_columns(self) -> list:
        """Global column indices of every per-slot, editable value / Lo / Hi cell."""
        cols = []
        for slot in range(self._model.width):
            base = 1 + slot * len(SLOT_COLUMN_META)
            for sub, meta in enumerate(SLOT_COLUMN_META):
                if meta[2] and meta[3] == "float":
                    cols.append(base + sub)
        return cols

    def _configure_columns(self) -> None:
        hh = self._table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setMinimumSectionSize(28)

        def _resize(col, mode):
            try:
                hh.setSectionResizeMode(col, mode)
            except Exception:
                try:
                    hh.setResizeMode(col, mode)
                except Exception:
                    pass

        _resize(0, QtWidgets.QHeaderView.ResizeToContents)
        for col in range(1, self._model.columnCount()):
            s = self._model._slot(col)
            # The value columns (sub == 0) absorb spare width; flag/bound columns
            # hug their contents so the paired blocks line up compactly.
            mode = (
                QtWidgets.QHeaderView.Stretch
                if s is not None and s[1] == 0
                else QtWidgets.QHeaderView.ResizeToContents
            )
            _resize(col, mode)

    def _size_to_content(self) -> None:
        header_h = self._table.horizontalHeader().height() or self._header_h
        n = self._model.rowCount()
        self._table.setFixedHeight(header_h + self._row_h * max(1, n) + 2)

    # -- controllers --------------------------------------------------------
    def _install_controllers(self) -> None:
        """Claim each parameter's ``controller`` so rows repaint on change."""
        owned = []
        params = self._model.parameters
        live = {id(p) for p in params}
        # Drop controllers whose parameter is gone (a removed component).
        for pid in list(self._controllers):
            if pid not in live:
                self._controllers.pop(pid, None)
        for row in range(self._model.rowCount()):
            for slot in range(self._model.width):
                idx = row * self._model.width + slot
                if idx >= len(params):
                    continue
                param = params[idx]
                ctrl = self._controller(param)
                try:
                    param.controller = ctrl
                except Exception:
                    continue
                owned.append((param, ctrl))
        self.destroyed.connect(partial(_release_controllers, owned))

    def _controller(self, param: FittingParameter):
        ctrl = self._controllers.get(id(param))
        if ctrl is None:
            from chisurf.gui.widgets.fitting.parameter_widgets import (
                FittingParameterProxyController,
            )

            ctrl = FittingParameterProxyController(
                param,
                parent=self,
                on_change=self._refresh_all,
            )
            self._controllers[id(param)] = ctrl
        return ctrl

    def _refresh_all(self) -> None:
        """Display-only repaint (mirrors a proxy ``finalize`` — no fit dispatch)."""
        self._suppress_change = True
        try:
            top_left = self._model.index(0, 0)
            bottom_right = self._model.index(
                max(0, self._model.rowCount() - 1),
                max(0, self._model.columnCount() - 1),
            )
            self._model.dataChanged.emit(top_left, bottom_right)
        finally:
            self._suppress_change = False

    # -- context menu / link / copy / paste ---------------------------------
    def _param_index_at(self, pos) -> QtCore.QModelIndex:
        return self._table.indexAt(pos)

    def _context_menu(self, pos) -> None:
        menu = QtWidgets.QMenu(self._table)
        index = self._table.indexAt(pos)
        pa = None
        if index.isValid() and index.column() != 0:
            pa = self._model.param_at(index.row(), index.column())
        if pa is not None:
            param, _ = pa
            self._add_link_actions(menu, param)
            act_details = menu.addAction(f"{Glyphs.SEARCH} Details…")
            act_details.triggered.connect(lambda: self._open_details_popup(param))
            menu.addSeparator()
        act_copy = menu.addAction(f"{Glyphs.COPY} Copy")
        act_paste = menu.addAction(f"{Glyphs.IMPORT} Paste")
        act_copy.setShortcut("Ctrl+C")
        act_paste.setShortcut("Ctrl+V")
        act_copy.triggered.connect(self._copy_selection)
        act_paste.triggered.connect(self._paste_selection)
        act_paste.setEnabled(bool(QtWidgets.QApplication.clipboard().text().strip()))
        menu.exec_(self._table.viewport().mapToGlobal(pos))

    def _add_link_actions(self, menu: QtWidgets.QMenu, param: FittingParameter) -> None:
        ctrl = self._controller(param)
        link_menu = ctrl.build_link_menu()
        link_menu.setTitle(f"🔗 Link {param.name} to")
        menu.addMenu(link_menu)
        act_unlink = menu.addAction(f"{Glyphs.CHAIN}‍💥 Unlink")
        act_unlink.setEnabled(bool(getattr(param, "is_linked", False)))
        act_unlink.triggered.connect(lambda: self._unlink(param))
        menu.addSeparator()

    def _unlink(self, param: FittingParameter) -> None:
        from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

        ctrl = self._controller(param)
        source = ctrl._parameter_context(param)
        fc = get_fitting_client()
        if fc is not None:
            fc.unlink_parameter(
                parameter_name=str(param.name),
                fit_uid=source.get("fit_uid"),
            )
        ctrl._trace_operation(
            "parameter_unlink",
            f"unlink parameter '{param.name}' in fit '{source['fit_group']}' "
            f"/ local '{source['local_fit']}'",
            {"parameter_name": str(param.name), **source},
        )
        ctrl._update_linked_parameters()
        ctrl.finalize()

    def _open_details_popup(self, param: FittingParameter) -> None:
        from chisurf.gui.widgets.fitting.parameter_widgets import (
            FittingParameterDetailPopup,
        )

        popup = FittingParameterDetailPopup(self._controller(param))
        popup.move(QtGui.QCursor.pos())
        popup.refresh_from_model()
        popup.show()
        popup.raise_()
        popup.activateWindow()
        popup.setFocus(QtCore.Qt.PopupFocusReason)
        self._detail_popup = popup

    def _copy_selection(self) -> None:
        idxs = self._table.selectedIndexes()
        if not idxs:
            return
        rows: dict[int, list[str]] = {}
        for i in sorted(idxs, key=lambda x: (x.row(), x.column())):
            rows.setdefault(i.row(), []).append(str(i.data(QtCore.Qt.DisplayRole) or ""))
        text = "\n".join("\t".join(cells) for cells in rows.values())
        QtWidgets.QApplication.clipboard().setText(text)

    def _paste_selection(self) -> None:
        text = QtWidgets.QApplication.clipboard().text()
        idxs = self._table.selectedIndexes()
        if not text.strip() or not idxs:
            return
        grid = [line.split("\t") for line in text.splitlines() if line != ""]
        editable = QtCore.Qt.ItemIsEditable
        if len(grid) == 1 and len(grid[0]) == 1:
            value = grid[0][0]
            for i in idxs:
                if self._model.flags(i) & editable:
                    self._model.setData(i, value, QtCore.Qt.EditRole)
            return
        anchor = min(idxs, key=lambda x: (x.row(), x.column()))
        for dr, line in enumerate(grid):
            for dc, value in enumerate(line):
                i = self._model.index(anchor.row() + dr, anchor.column() + dc)
                if i.isValid() and (self._model.flags(i) & editable):
                    self._model.setData(i, value, QtCore.Qt.EditRole)

    # -- change dispatch / sync --------------------------------------------
    def _on_data_changed(self, *_):
        if self._suppress_change:
            return
        cb = self._on_change
        if cb is not None:
            try:
                cb()
            except Exception:
                pass

    def sync(self) -> None:
        """Re-read parameter values and repaint (no ``on_change`` dispatch)."""
        self._refresh_all()

    refresh = sync

    # -- accessors ----------------------------------------------------------
    @property
    def table_model(self) -> PairedParameterTableModel:
        """The backing :class:`PairedParameterTableModel`."""
        return self._model

    @property
    def table_view(self) -> QtWidgets.QTableView:
        """The wrapped ``QTableView``."""
        return self._table

    @property
    def parameters(self) -> typing.List[FittingParameter]:
        """Live flat list of the parameters shown in the table."""
        return self._model.parameters
