"""Förster radius calculator widget backed by MMFDB spectra.

The queries and the computation are Qt-free
(:mod:`chisurf.core.fluorescence.fret.forster_calculator`); this widget is the
legacy Qt face of that model. The emtk shell draws the same model as
:class:`chisurf.emtk.forster_calculator.ForsterCalculatorDialog`.
"""

from __future__ import annotations

import pathlib
from typing import Any, Callable

from qtpy import QtCore, QtWidgets

from chisurf.core.fluorescence.fret.forster_calculator import (
    ForsterCalculatorModel as _CalculatorModel,
)
from chisurf.core.fluorescence.fret.forster_calculator import spectrum_summary

_VIEW_JSON = pathlib.Path(__file__).parent / "forster_calculator.view.json"


class _SearchableCombo(QtWidgets.QComboBox):
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.completer().setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        self.completer().setCompletionMode(QtWidgets.QCompleter.PopupCompletion)


class ForsterCalculatorModel(_CalculatorModel):
    """The calculator model with the Qt parameter panel's view spec.

    Attributes mirror the ``attr`` keys in ``forster_calculator.view.json``.
    """

    def view_spec(self):
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)


class ForsterCalculatorWidget(QtWidgets.QWidget):
    """A widget to calculate Förster radius from MMFDB spectra.

    Queries the MMFDB for probes with emission / absorption spectra, lets
    the user pick donor and acceptor probes via searchable combo boxes,
    and computes R₀ via the canonical overlap integral.  Emits
    ``forster_radius_calculated`` with the result in Ångström.

    The orientation factor κ² is fixed at 2/3 (dynamic isotropic averaging)
    — orientation corrections are handled elsewhere in the FRET model.

    Parameters
    ----------
    parent : QWidget, optional
        Parent widget.
    open_database : callable, optional
        ``open_database() -> MFDatabase``; MMFDB opened read-only by default.
    """

    forster_radius_calculated = QtCore.Signal(float)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        open_database: Callable[[], Any] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Förster Radius Calculator")
        self._model = ForsterCalculatorModel(open_database=open_database, load=False)
        self._last_r0: float | None = None
        self._debounce = QtCore.QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._compute)
        self._setup_ui()
        self._load_probes()

    # ---- UI construction ------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        # Donor & Acceptor probes (collapsible)
        probe_group = QtWidgets.QGroupBox("Donor / Acceptor")
        probe_group.setCheckable(False)
        probe_layout = QtWidgets.QFormLayout(probe_group)
        self.donor_combo = _SearchableCombo()
        probe_layout.addRow("Donor emission:", self.donor_combo)
        self.acceptor_combo = _SearchableCombo()
        probe_layout.addRow("Acceptor absorption:", self.acceptor_combo)
        layout.addWidget(probe_group)

        # Parameter section (declarative — rendered from view.json by AutoForm)
        from chisurf.gui.autoform import AutoForm
        from chisurf.gui.autoform.sections.builtin import ValueWidget

        self._form = AutoForm(self._model, parent=self)
        layout.addWidget(self._form)

        # Extract editor widgets from the autoform
        self.qy_spin: QtWidgets.QDoubleSpinBox | None = None
        self.ext_spin: QtWidgets.QDoubleSpinBox | None = None
        self.n_spin: QtWidgets.QDoubleSpinBox | None = None
        for vw in self._form.findChildren(ValueWidget):
            attr = getattr(getattr(vw, "_section", None), "attr", None)
            if attr == "donor_qy":
                self.qy_spin = vw.editor
            elif attr == "acceptor_emax":
                self.ext_spin = vw.editor
            elif attr == "refractive_index":
                self.n_spin = vw.editor

        # Result section
        result_layout = QtWidgets.QHBoxLayout()
        self.result_label = QtWidgets.QLabel("")
        self.result_label.setAlignment(QtCore.Qt.AlignCenter)
        self.result_label.setStyleSheet("font-size: 14pt; font-weight: bold; padding: 8px;")
        result_layout.addWidget(self.result_label, 1)

        self.apply_btn = QtWidgets.QPushButton("Apply R₀ to model")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._apply)
        result_layout.addWidget(self.apply_btn)
        layout.addLayout(result_layout)

        # Wire up auto-calculation triggers
        self.donor_combo.currentIndexChanged.connect(self._on_donor_changed)
        self.acceptor_combo.currentIndexChanged.connect(self._on_acceptor_changed)
        if self.qy_spin is not None:
            self.qy_spin.valueChanged.connect(self._schedule)
        if self.ext_spin is not None:
            self.ext_spin.valueChanged.connect(self._schedule)
        if self.n_spin is not None:
            self.n_spin.valueChanged.connect(self._schedule)

    # ---- data loading ---------------------------------------------------

    def _load_probes(self) -> None:
        model = self._model
        if not model.load():
            self.result_label.setText(model.status)
            self.donor_combo.setEnabled(False)
            self.acceptor_combo.setEnabled(False)
            self.apply_btn.setEnabled(False)
            return
        for combo, ids, kind in (
            (self.donor_combo, model.donors, "emission"),
            (self.acceptor_combo, model.acceptors, "absorption"),
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("", None)
            for pid in ids:
                combo.addItem(model.probe_names[pid], pid)
                combo.setItemData(
                    combo.count() - 1,
                    spectrum_summary(kind, model.probe_spectra[pid][kind]),
                    QtCore.Qt.ToolTipRole,
                )
            combo.blockSignals(False)

    # ---- helpers --------------------------------------------------------

    def _current_probe_id(self, combo: _SearchableCombo) -> int | None:
        idx = combo.currentIndex()
        pid = combo.itemData(idx)
        if pid is not None:
            return pid
        text = combo.currentText().strip()
        if not text:
            return None
        for i in range(combo.count()):
            if combo.itemText(i) == text:
                return combo.itemData(i)
        return None

    def _schedule(self) -> None:
        self._debounce.start()

    # ---- computation ----------------------------------------------------

    def _compute(self) -> None:
        model = self._model
        model.donor = self._current_probe_id(self.donor_combo)
        model.acceptor = self._current_probe_id(self.acceptor_combo)
        self._last_r0 = model.compute()
        self.result_label.setText(model.status)
        self.apply_btn.setEnabled(self._last_r0 is not None)

    # ---- signal handlers -----------------------------------------------

    def _on_donor_changed(self) -> None:
        pid = self._current_probe_id(self.donor_combo)
        qy = self._model.probe_properties.get(pid, {}).get("qy")
        if qy is not None and self.qy_spin is not None:
            self.qy_spin.setValue(qy)
        self._schedule()

    def _on_acceptor_changed(self) -> None:
        pid = self._current_probe_id(self.acceptor_combo)
        emax = self._model.probe_properties.get(pid, {}).get("emax")
        if emax is not None and self.ext_spin is not None:
            self.ext_spin.setValue(emax)
        self._schedule()

    def _apply(self) -> None:
        if self._last_r0 is not None:
            self.forster_radius_calculated.emit(self._last_r0)
