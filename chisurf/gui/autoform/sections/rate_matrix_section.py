"""Reusable AutoForm section: an editable N×N transition-rate matrix.

A transition-rate matrix appears in several ChiSurf domains — species
interconversion in the photon simulator, kinetic state models, exchange in
lifetime-FCS, etc. This section renders one editable grid so those all share a
single control instead of hand-built tables.

Declare it in a view spec as a custom section::

    {"type": "custom", "key": "rate_matrix", "target": "k_ex",
     "options": {"size_attr": "n_states", "labels_attr": "state_names",
                 "minimum": 0.0, "decimals": 4, "diagonal": false, "unit": "1/ms"}}

- ``target`` — model attribute holding the flat row-major ``N*N`` rates
  (``rate[i*N + j]`` is the i→j rate). Read on build/refresh, written on edit.
- ``size_attr`` — model attribute (or zero-arg method) giving N; the grid
  resizes to it on ``refresh`` (so it can track e.g. the species count).
- ``labels_attr`` — optional per-state row/column labels; defaults to ``1..N``.
- ``minimum`` / ``maximum`` / ``decimals`` — what a cell can show. The grid is a
  *view*: a stored rate outside that range is displayed clamped and in red, and
  is left untouched in the model until that cell is actually edited. Building or
  refreshing the grid never writes a value back.
- ``diagonal`` — when false (default) the i→i cells are fixed at 0 and disabled.
- ``popup`` — when true the grid lives behind a button instead of sitting in the
  panel. An N×N grid costs N rows of vertical space whether or not anyone is
  editing it, which is the wrong trade when the scheme is a secondary control
  (two of them, as in the acquisition simulator, push everything else off the
  screen). The button carries a live summary — size and how many transitions are
  non-zero — so the panel still says what the scheme is without being opened.
  The same grid is used either way; only where it is parented differs.
"""

from __future__ import annotations

import logging
from typing import Any

from qtpy import QtCore, QtWidgets

from .registry import register_section

logger = logging.getLogger(__name__)


def _resolve(model: Any, name: str, default=None):
    if not name or model is None:
        return default
    obj = model
    for part in name.split("."):
        if not hasattr(obj, part):
            return default
        obj = getattr(obj, part)
        if callable(obj):
            obj = obj()
    return obj


def _set_resolved(model: Any, name: str, value: Any) -> None:
    if not name or model is None:
        return
    parts = name.split(".")
    obj = model
    for part in parts[:-1]:
        if not hasattr(obj, part):
            return
        obj = getattr(obj, part)
        if callable(obj):
            obj = obj()
    setattr(obj, parts[-1], value)


@register_section("rate_matrix")
class RateMatrixWidget(QtWidgets.QWidget):
    """Editable N×N rate matrix bound to a flat row-major model list."""

    AUTOFORM_REFRESH = True
    is_form_field = False

    def __init__(self, model, target: str = "", **options):
        super().__init__()
        self._model = model
        self._attr = target or options.get("attr", "")
        self._size_attr = options.get("size_attr", "")
        self._labels_attr = options.get("labels_attr", "")
        self._min = float(options.get("minimum", 0.0))
        self._max = float(options.get("maximum", 1_000_000.0))
        self._decimals = int(options.get("decimals", 4))
        self._diagonal = bool(options.get("diagonal", False))
        self._unit_attr = options.get("unit_attr", "")
        self._unit = str(options.get("unit", ""))
        self._title = str(options.get("title", ""))
        self._popup = bool(options.get("popup", False))
        self._disable_row0 = bool(options.get("disable_row0", False))
        self._header_label = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        from chisurf.gui.widgets.general import table_font, table_row_height, table_header_height, apply_compact_table_style
        from chisurf.gui import QtGui

        self.table = QtWidgets.QTableWidget(0, 0)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        apply_compact_table_style(self.table)
        t_font = table_font()
        t_font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.table.setFont(t_font)
        self.table.horizontalHeader().setFont(t_font)
        self.table.verticalHeader().setFont(t_font)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(True)
        self.table.setStyleSheet(
            "QTableWidget { gridline-color: palette(midlight); border: 1px solid palette(mid); }"
            "QHeaderView::section { font-weight: bold; padding: 1px; }"
        )

        self.button = None
        self._dialog = None
        if self._popup:
            # One button standing in for N rows of grid. It is a real summary,
            # not just a label: a collapsed control that says nothing about its
            # contents makes the panel lie about the model's state.
            self.button = QtWidgets.QToolButton()
            self.button.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
            self.button.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                      QtWidgets.QSizePolicy.Fixed)
            self.button.clicked.connect(self._open)
            layout.addWidget(self.button)
        else:
            self._header_label = self._header()
            layout.addWidget(self._header_label)
            layout.addWidget(self.table)
        # Do not let the grid stretch to fill the panel — keep it tight.
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self._spins: dict[tuple[int, int], QtWidgets.QDoubleSpinBox] = {}
        # Per cell: (value read from the model, value the spin box can show).
        # The two differ whenever the model holds a rate outside the configured
        # range or finer than ``decimals`` -- see :meth:`_load`.
        self._loaded: dict[tuple[int, int], tuple[float, float]] = {}
        self._build()

    def _header_text(self) -> str:
        unit = _resolve(self._model, self._unit_attr, self._unit) or self._unit
        bits = []
        if self._title:
            bits.append(f"<b>{self._title}</b>")
        # Spell the direction out. The table is laid out row = source, column =
        # target (see _write_back), while the model holds K[target, source] --
        # "i → j" left it to the reader to guess which index was which, and a
        # caption that disagrees with the layout reads as a swapped matrix.
        bits.append(f"row → column rate ({unit})" if unit else "row → column rate")
        return "  ·  ".join(bits)

    def _header(self) -> QtWidgets.QLabel:
        """Return the caption naming the matrix and its rate direction."""
        label = QtWidgets.QLabel(self._header_text())
        label.setStyleSheet("color: palette(mid); font-size: 11px;")
        return label

    # -- popup ---------------------------------------------------------
    def _open(self) -> None:
        """Show the grid in its own window, building it on first use."""
        if self._dialog is None:
            self._dialog = QtWidgets.QDialog(self)
            self._dialog.setWindowTitle(self._title or "Transition rates")
            inner = QtWidgets.QVBoxLayout(self._dialog)
            inner.addWidget(self._header())
            inner.addWidget(self.table)
            buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
            buttons.rejected.connect(self._dialog.hide)
            inner.addWidget(buttons)
        # Deliberately modeless: edits apply live, so the user can watch what a
        # rate does to the model while changing it -- and a modal dialog on an
        # offscreen run has nobody to close it.
        self._dialog.show()
        self._dialog.raise_()

    def _update_button(self) -> None:
        """Put the scheme's size and how much of it is set on the button."""
        if self.button is None:
            return
        n = self.table.rowCount()
        active = sum(
            1 for (i, j), spin in self._spins.items()
            if i != j and abs(spin.value()) > 0.0
        )
        name = self._title or "Transition rates"
        unit = f" {self._unit}" if self._unit else ""
        self.button.setText(f"\u2197 {name}  ({n}\u00d7{n}, {active} set)")
        self.button.setToolTip(
            f"{name}: {n} states, {active} of {max(n * (n - 1), 0)} transitions "
            f"non-zero{unit}. Click to edit the i \u2192 j rate matrix."
        )

    # -- data helpers --------------------------------------------------
    def _size(self) -> int:
        n = _resolve(self._model, self._size_attr, None)
        try:
            return max(1, int(n))
        except (TypeError, ValueError):
            # Fall back to the stored matrix length (√len).
            flat = self._flat()
            return max(1, int(round(len(flat) ** 0.5)) if flat else 1)

    def _flat(self) -> list[float]:
        value = _resolve(self._model, self._attr, None) if self._attr else None
        if value is None:
            return []
        try:
            return [float(v) for v in value]
        except (TypeError, ValueError):
            return []

    def _labels(self, n: int) -> list[str]:
        labels = _resolve(self._model, self._labels_attr, None)
        if isinstance(labels, (list, tuple)) and len(labels) >= n:
            return [str(labels[i]).split(" ")[0].split("(")[0].strip() for i in range(n)]
        return [f"S{i}" for i in range(n)]

    def _descriptions(self, n: int) -> list[str]:
        descriptions = _resolve(self._model, "saturation.state_descriptions", None) or _resolve(self._model, "state_descriptions", None)
        if isinstance(descriptions, (list, tuple)) and len(descriptions) >= n:
            return [str(descriptions[i]) for i in range(n)]
        labels = self._labels(n)
        return [f"State {i+1} ({labels[i]})" for i in range(n)]

    def _load(self, i: int, j: int, spin: QtWidgets.QDoubleSpinBox, raw: float) -> None:
        """Show one model value in its cell and remember what was read."""
        spin.blockSignals(True)
        spin.setValue(raw)
        spin.blockSignals(False)
        shown = float(spin.value())
        self._loaded[(i, j)] = (float(raw), shown)
        clamped = not self._min <= raw <= self._max
        spin.setStyleSheet(
            "QDoubleSpinBox { color: #c62828; padding: 0px; margin: 0px; border: none; background: transparent; selection-background-color: #ff3333; selection-color: #ffffff; }"
            if clamped else
            "QDoubleSpinBox { padding: 0px; margin: 0px; border: none; background: transparent; selection-background-color: #ff3333; selection-color: #ffffff; }"
        )
        if clamped:
            logger.warning(
                "rate_matrix: %s[%d, %d] = %g is outside the range this grid "
                "shows (%g..%g); it is displayed as %g and kept unchanged in "
                "the model until the cell is edited.",
                self._attr or "rates", i, j, raw, self._min, self._max, shown,
            )
            spin.setToolTip(
                f"Stored value {raw:g} is outside the range this grid shows "
                f"({self._min:g} … {self._max:g}), so it is shown as {shown:g}. "
                f"Editing this cell replaces it with the shown value."
            )

    def _cell_value(self, i: int, j: int, spin: QtWidgets.QDoubleSpinBox) -> float:
        """Return the value to store for one cell: the edit, or what was read."""
        loaded = self._loaded.get((i, j))
        if loaded is not None and float(spin.value()) == loaded[1]:
            return loaded[0]
        return float(spin.value())

    def _write_back(self, n: int) -> None:
        flat = [0.0] * (n * n)
        for (i, j), spin in self._spins.items():
            if i < n and j < n:
                # Table cell (i, j) has row i = source, col j = target.
                # The bound list is row-major in (source, target): k_ij at i*n + j.
                flat[i * n + j] = self._cell_value(i, j, spin)
        if self._attr:
            _set_resolved(self._model, self._attr, flat)
        self._update_button()
        callback = getattr(self._model, "_on_changed", None) or getattr(self._model, "on_changed", None)
        if callable(callback):
            try:
                callback()
            except Exception:
                pass

    def _get_cell_parameter(self, i: int, j: int):
        """Look up the FittingParameter corresponding to cell (i, j)."""
        target_obj = _resolve(self._model, self._attr, None)
        if target_obj is None and "." in self._attr:
            parent_path = self._attr.rsplit(".", 1)[0]
            target_obj = _resolve(self._model, parent_path, None)
        if target_obj is not None:
            if hasattr(target_obj, "rate_items"):
                rate_map = dict(target_obj.rate_items())
                return rate_map.get((i + 1, j + 1))
            elif hasattr(target_obj, "rates_by_name"):
                prefix = getattr(target_obj, "rate_prefix", "k")
                name = f"{prefix}{i + 1}_{j + 1}"
                return target_obj.rates_by_name().get(name)
        return None

    # -- build / refresh ----------------------------------------------
    def _build(self) -> None:
        from chisurf.gui.widgets.general import table_font, table_row_height, table_header_height
        t_font = table_font()
        n = self._size()
        flat = self._flat()
        labels = self._labels(n)
        descriptions = self._descriptions(n)
        self.table.blockSignals(True)
        self.table.clear()
        self._spins.clear()
        self._checkboxes: dict[tuple[int, int], QtWidgets.QCheckBox] = {}
        self._loaded.clear()
        self.table.setRowCount(n)
        self.table.setColumnCount(n)
        self.table.setHorizontalHeaderLabels(labels)
        self.table.setVerticalHeaderLabels(labels)
        for k in range(n):
            desc = descriptions[k] if k < len(descriptions) else labels[k]
            h_item = self.table.horizontalHeaderItem(k)
            if h_item is not None:
                h_item.setToolTip(f"State {k+1}: {desc}")
            v_item = self.table.verticalHeaderItem(k)
            if v_item is not None:
                v_item.setToolTip(f"State {k+1}: {desc}")

        for i in range(n):
            for j in range(n):
                param = self._get_cell_parameter(i, j)

                cell_w = QtWidgets.QWidget()
                c_layout = QtWidgets.QHBoxLayout(cell_w)
                c_layout.setContentsMargins(1, 0, 1, 0)
                c_layout.setSpacing(1)

                chk_fix = QtWidgets.QCheckBox(cell_w)
                chk_fix.setToolTip("Fix parameter (checked = fixed, unchecked = free for fitting)")
                chk_fix.setStyleSheet(
                    "QCheckBox { spacing: 0px; background: transparent; } "
                    "QCheckBox::indicator { width: 11px; height: 11px; border: 1px solid #777777; border-radius: 2px; background-color: #2b2b2b; } "
                    "QCheckBox::indicator:disabled { border: 1px solid #444444; background-color: #1a1a1a; } "
                    "QCheckBox::indicator:hover { border: 1px solid #ff3333; } "
                    "QCheckBox::indicator:checked { background-color: #ff3333; border: 1px solid #ff3333; } "
                    "QCheckBox::indicator:checked:disabled { background-color: #552222; border: 1px solid #444444; }"
                )

                pending_load = None
                spin = QtWidgets.QDoubleSpinBox(cell_w)
                spin.setFont(t_font)
                spin.setRange(self._min, self._max)
                spin.setDecimals(self._decimals)
                spin.setKeyboardTracking(False)
                spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
                spin.setAlignment(QtCore.Qt.AlignCenter)
                idx = i * n + j
                raw = flat[idx] if idx < len(flat) else 0.0

                is_disabled_cell = (i == 0 and self._disable_row0) or (i == j and not self._diagonal)

                def _update_cell_style(p=param, chk=chk_fix, sp=spin, is_dis=is_disabled_cell):
                    if is_dis:
                        chk.setCheckState(QtCore.Qt.Checked)
                        chk.setStyleSheet(
                            "QCheckBox { spacing: 0px; background: transparent; } "
                            "QCheckBox::indicator { width: 11px; height: 11px; border: 1px solid #444444; border-radius: 2px; background-color: #552222; }"
                        )
                        sp.setStyleSheet("QDoubleSpinBox { border: 1px solid #333333; border-radius: 3px; color: #777777; background-color: #1a1a1a; }")
                        return

                    is_linked = getattr(p, "is_linked", False) if p is not None else False
                    is_fixed = bool(p.fixed) if p is not None else True

                    chk.setTristate(True)
                    if is_linked:
                        chk.setCheckState(QtCore.Qt.PartiallyChecked)
                        color = "#2a88ff"   # Blue
                    elif is_fixed:
                        chk.setCheckState(QtCore.Qt.Checked)
                        color = "#ff2a2a"   # Red
                    else:
                        chk.setCheckState(QtCore.Qt.Unchecked)
                        color = "#2acc44"   # Green

                    chk.setStyleSheet(
                        "QCheckBox { spacing: 0px; background: transparent; } "
                        "QCheckBox::indicator { width: 11px; height: 11px; border: 1px solid #666666; border-radius: 2px; } "
                        "QCheckBox::indicator:unchecked { background-color: #2acc44; border: 1px solid #2acc44; } "
                        "QCheckBox::indicator:indeterminate { background-color: #2a88ff; border: 1px solid #2a88ff; } "
                        "QCheckBox::indicator:checked { background-color: #ff2a2a; border: 1px solid #ff2a2a; }"
                    )
                    sp.setStyleSheet(
                        f"QDoubleSpinBox {{ border: 1px solid #3d3d3d; border-radius: 3px; font-weight: bold; selection-background-color: {color}; }} "
                        f"QDoubleSpinBox:focus {{ border: 1px solid {color}; }}"
                    )

                if is_disabled_cell:
                    self._load(i, j, spin, 0.0)
                    spin.setEnabled(False)
                    chk_fix.setChecked(True)
                    chk_fix.setEnabled(False)
                    if i == 0 and self._disable_row0:
                        tt = f"Ground state {descriptions[0]} dark transition is 0 (excitation is optical)."
                    else:
                        tt = f"Self-transition for state {descriptions[i]} is fixed at 0."
                    spin.setToolTip(tt)
                    chk_fix.setToolTip(tt)
                    _update_cell_style()
                else:
                    tt_desc = f"Transition rate from {descriptions[i]} to {descriptions[j]}" + (f" ({self._unit})" if self._unit else "")
                    # Loaded once the cell's tooltips are set, below: _load
                    # warns through the tooltip when a stored rate is outside
                    # the range the grid can show, and the description written
                    # after it used to replace that warning, so a clamped rate
                    # looked like any other.
                    pending_load = (i, j, spin, raw)
                    spin.valueChanged.connect(lambda _v, ni=n: self._write_back(ni))

                    if param is not None:
                        from chisurf.gui.widgets.fitting.parameter_widgets import (
                            FittingParameterProxyController,
                            FittingParameterDetailPopup,
                        )

                        def _on_proxy_change():
                            self._load_all()
                            _update_cell_style()
                            if hasattr(self._model, "update"):
                                self._model.update()

                        ctrl = FittingParameterProxyController(
                            fitting_parameter=param,
                            parent=cell_w,
                            on_change=_on_proxy_change
                        )

                        st_str = "Fixed" if param.fixed else f"Free [{param.lb:.4g}, {param.ub:.4g}]"
                        lnk_str = " (Linked)" if getattr(param, "is_linked", False) else ""
                        rich_tt = (
                            f"<b>{param.name}</b> = {param.value:.4g} ({st_str}{lnk_str})<br>"
                            f"{tt_desc}"
                        )
                        spin.setToolTip(rich_tt)
                        chk_fix.setToolTip(rich_tt)
                        cell_w.setToolTip(rich_tt)

                        _update_cell_style()

                        def _on_fix_state_changed(state, p=param):
                            if state == QtCore.Qt.Checked:
                                p.fixed = True
                            elif state == QtCore.Qt.Unchecked:
                                p.fixed = False
                            _update_cell_style()
                            if hasattr(self._model, "update"):
                                self._model.update()

                        chk_fix.stateChanged.connect(_on_fix_state_changed)

                        cell_w.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
                        spin.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

                        def _on_context_menu(pos: QtCore.QPoint, p=param, c=ctrl, cb=chk_fix, w=cell_w):
                            menu = c.build_link_menu()
                            menu.setTitle(f"🔗 {p.name}")
                            menu.addSeparator()
                            act_popup = menu.addAction("🛠 Parameter Detail Popup...")
                            def _show_popup():
                                pop = FittingParameterDetailPopup(c)
                                pop.move(QtGui.QCursor.pos())
                                pop.refresh_from_model()
                                pop.exec_()
                            act_popup.triggered.connect(_show_popup)
                            menu.exec_(w.mapToGlobal(pos))

                        cell_w.customContextMenuRequested.connect(_on_context_menu)
                        spin.customContextMenuRequested.connect(lambda pos, w=cell_w, c_fn=_on_context_menu: c_fn(pos, w=w))

                        class DblClickFilter(QtCore.QObject):
                            def __init__(self, c=ctrl, parent=None):
                                super().__init__(parent)
                                self._c = c

                            def eventFilter(self, obj, event):
                                if event.type() == QtCore.QEvent.MouseButtonDblClick and event.button() == QtCore.Qt.LeftButton:
                                    pop = FittingParameterDetailPopup(self._c)
                                    pop.move(QtGui.QCursor.pos())
                                    pop.refresh_from_model()
                                    pop.exec_()
                                    return True
                                return super().eventFilter(obj, event)

                        flt = DblClickFilter(ctrl, cell_w)
                        spin.installEventFilter(flt)
                        cell_w.installEventFilter(flt)
                    else:
                        chk_fix.setChecked(True)
                        spin.setToolTip(tt_desc)
                        chk_fix.setToolTip(tt_desc)

                if pending_load is not None:
                    self._load(*pending_load)
                    pending_load = None
                c_layout.addWidget(chk_fix)
                c_layout.addWidget(spin, 1)

                self._spins[(i, j)] = spin
                self._checkboxes[(i, j)] = chk_fix
                self.table.setCellWidget(i, j, cell_w)

        for col in range(n):
            self.table.horizontalHeader().setSectionResizeMode(col, QtWidgets.QHeaderView.Stretch)
        for row in range(n):
            self.table.verticalHeader().setSectionResizeMode(row, QtWidgets.QHeaderView.Stretch)
        # A cell holds a fix checkbox next to a spin box; if that widget wants
        # more than the nominal row height, every row grows and a height computed
        # from the nominal value clips the last state off the bottom.
        row_h = table_row_height()
        for i in range(n):
            for j in range(n):
                cell = self.table.cellWidget(i, j)
                if cell is not None:
                    row_h = max(row_h, cell.sizeHint().height())
        header_h = table_header_height()
        self.table.verticalHeader().setDefaultSectionSize(row_h)
        self.table.horizontalHeader().setDefaultSectionSize(header_h)
        # The frame and, on a narrow panel, the horizontal scroll bar both eat
        # into a fixed height: without counting them the last row of the scheme
        # is clipped, which for a 3-state scheme silently hides a whole state.
        chrome = 2 * self.table.frameWidth() + 4
        if self.table.horizontalScrollBarPolicy() != QtCore.Qt.ScrollBarAlwaysOff:
            chrome += self.table.horizontalScrollBar().sizeHint().height()
        self.table.setFixedHeight(header_h + row_h * n + chrome)
        self.table.updateGeometry()
        self.updateGeometry()
        self.table.blockSignals(False)
        if len(flat) != n * n:
            self._write_back(n)
        self._update_button()

    def refresh(self) -> None:
        """Re-read the model, rebuilding only if the state count changed."""
        if self._header_label is not None:
            self._header_label.setText(self._header_text())
        # Rebuild when the state count changed (tracks size_attr, e.g. n_species).
        if self.table.rowCount() != self._size():
            self._build()
        else:
            flat = self._flat()
            n = self.table.rowCount()
            for (i, j), spin in self._spins.items():
                idx = i * n + j
                raw = flat[idx] if idx < len(flat) else 0.0
                if i == 0 and self._disable_row0:
                    raw = 0.0
                elif i == j and not self._diagonal:
                    raw = 0.0
                self._load(i, j, spin, raw)
                param = self._get_cell_parameter(i, j)
                if param is not None and (i, j) in self._checkboxes:
                    cb = self._checkboxes[(i, j)]
                    cb.blockSignals(True)
                    cb.setChecked(bool(param.fixed))
                    cb.blockSignals(False)
            self._update_button()
