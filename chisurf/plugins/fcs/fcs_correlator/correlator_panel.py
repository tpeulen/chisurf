"""Correlator step: the Qt custom AutoForm sections over the Qt-free :mod:`.correlator_model`."""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

from chisurf.gui import dialogs
from chisurf.gui.autoform import register_section
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.progress import ChiSurfProgress

from .correlator_model import CorrelatorSettingsModel as _CorrelatorModel
from .correlator_model import (
    apply_channel_key,
    parse_channels,
    parse_microtime_ranges,
    preset_names,
)

__all__ = ["CorrelatorSettingsModel", "parse_channels", "parse_microtime_ranges"]


class CorrelatorSettingsModel(_CorrelatorModel):
    """The Qt panel's model: the Qt-free one, with the progress dialog and warning the Qt step shows."""

    def correlate_data(self, parent_widget: QtWidgets.QWidget | None = None, progress=None) -> str:
        if self._tttr is None or len(self._tttr) == 0:
            message = super().correlate_data()
            dialogs.warning(parent_widget, "No Photons Selected", message)
            return message
        dialog = ChiSurfProgress(parent_widget, "Computing correlations...", max(1, self.n_splits))
        dialog.setWindowTitle("Correlation Progress")
        dialog.setWindowModality(QtCore.Qt.WindowModal)
        dialog.show()

        def step(done, total):
            dialog.setValue(done)
            dialog.raise_()
            QtWidgets.QApplication.processEvents()
            return not dialog.wasCanceled()

        try:
            message = super().correlate_data(progress=step)
        finally:
            dialog.close()
        if self._form is not None:
            self._form.refresh_plots()
        return message


# ---- Custom AutoForm sections ----------------------------------------------


@register_section("fcs_presets")
class _FcsPresetCombo(QtWidgets.QWidget):
    AUTOFORM_REFRESH = True

    def __init__(self, model, target: str = "", **options):
        super().__init__()
        self._model = model
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        lbl = QtWidgets.QLabel("FCS Preset:")
        layout.addWidget(lbl)
        self.combo = QtWidgets.QComboBox()
        self.combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)
        self.combo.addItem("")
        self.combo.currentIndexChanged.connect(self._on_changed)
        layout.addWidget(self.combo, 1)

    def _on_changed(self, index: int) -> None:
        self._model.apply_preset(index)

    def refresh(self) -> None:
        self.combo.blockSignals(True)
        current = self.combo.currentText()
        self.combo.clear()
        self.combo.addItem("")
        for nm in preset_names(self._model):
            self.combo.addItem(nm)
        idx = self.combo.findText(current)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)


@register_section("channel_combos")
class _ChannelComboWidget(QtWidgets.QWidget):
    AUTOFORM_REFRESH = True

    def __init__(self, model, target: str = "", **options):
        super().__init__()
        self._model = model
        # A over B (stacked vertically) to save horizontal space.
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(4)
        layout.setVerticalSpacing(2)

        self.lbl_a = QtWidgets.QLabel("A:")
        layout.addWidget(self.lbl_a, 0, 0)
        self.combo_a = QtWidgets.QComboBox()
        self.combo_a.currentIndexChanged.connect(lambda i: self._on_combo("a"))
        layout.addWidget(self.combo_a, 0, 1)

        self.lbl_b = QtWidgets.QLabel("B:")
        layout.addWidget(self.lbl_b, 1, 0)
        self.combo_b = QtWidgets.QComboBox()
        self.combo_b.currentIndexChanged.connect(lambda i: self._on_combo("b"))
        layout.addWidget(self.combo_b, 1, 1)
        layout.setColumnStretch(1, 1)

    def _on_combo(self, side: str) -> None:
        combo = self.combo_a if side == "a" else self.combo_b
        # Species-selection mode: the combos index filter rows, not channels.
        if self._model.filter_mode:
            idx = combo.currentIndex()
            if idx < 0:
                return
            setattr(self._model, "_species_a" if side == "a" else "_species_b", idx)
            return
        key = combo.currentText()
        if key:
            apply_channel_key(self._model, side, key)

    def refresh(self) -> None:
        # Species-selection mode: list filter species; A/B index filter rows.
        if self._model.filter_mode:
            self.lbl_a.setText("Species A:")
            self.lbl_b.setText("Species B:")
            labels = list(self._model._filter_labels or [])
            for combo, attr in (
                (self.combo_a, "_species_a"),
                (self.combo_b, "_species_b"),
            ):
                combo.blockSignals(True)
                combo.clear()
                combo.addItems(labels)
                want = int(getattr(self._model, attr, 0))
                if 0 <= want < combo.count():
                    combo.setCurrentIndex(want)
                elif combo.count() > 0:
                    combo.setCurrentIndex(0)
                combo.blockSignals(False)
            return

        self.lbl_a.setText("A:")
        self.lbl_b.setText("B:")
        keys = list(self._model._channel_defs.keys())
        try:
            keys.sort()
        except Exception:
            pass
        for combo in (self.combo_a, self.combo_b):
            combo.blockSignals(True)
            current = combo.currentText()
            combo.clear()
            combo.addItems(keys)
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif combo.count() > 0:
                combo.setCurrentIndex(0)
            combo.blockSignals(False)


@register_section("lifetime_filter_controls")
class _LifetimeFilterControls(QtWidgets.QWidget):
    """Load / unload lifetime (FLCS) filters for species-correlation mode."""

    AUTOFORM_REFRESH = True

    def __init__(self, model, target: str = "", **options):
        super().__init__()
        self._model = model
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.btn_load = QtWidgets.QToolButton()
        self.btn_load.setText(f"{Glyphs.DNA} Load filters…")
        self.btn_load.setToolTip(
            "Load lifetime (FLCS) filters from a Filter-Calculator JSON, or a "
            ".npy/.npz filter matrix. Correlation then produces species "
            "auto-/cross-correlations; the A/B selectors pick species."
        )
        self.btn_load.clicked.connect(self._on_load)
        layout.addWidget(self.btn_load)

        self.btn_unload = QtWidgets.QToolButton()
        self.btn_unload.setText(f"{Glyphs.CLOSE} Unload")
        self.btn_unload.setToolTip(
            "Remove the loaded lifetime filters and return to detector-channel correlation."
        )
        self.btn_unload.clicked.connect(self._on_unload)
        layout.addWidget(self.btn_unload)

        # Direct link to the Filter Calculator (which computes these filters).
        self.btn_filter_calc = QtWidgets.QToolButton()
        self.btn_filter_calc.setText(f"{Glyphs.TEST} Filter Calc…")
        self.btn_filter_calc.setToolTip(
            "Open the fFCS Filter Calculator to compute lifetime filters from decay patterns."
        )
        self.btn_filter_calc.clicked.connect(self._open_filter_calc)
        layout.addWidget(self.btn_filter_calc)

        self._status = QtWidgets.QLabel()
        layout.addWidget(self._status, 1)
        self.refresh()

    def _open_filter_calc(self) -> None:
        """Navigate the hosting FCS navigation rail to the Filter Calculator."""
        widget = self.parent()
        while widget is not None:
            show = getattr(widget, "show_panel_by_role", None)
            if callable(show):
                show("filter_calc")
                return
            widget = widget.parent()

    def _on_load(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.window() or self,
            "Load lifetime filters",
            "",
            "Lifetime filters (*.json *.npy *.npz);;All files (*)",
        )
        if not path:
            return
        try:
            n = self._model.load_lifetime_filter_file(path)
        except Exception as exc:  # pragma: no cover - GUI error path
            dialogs.error(self.window() or self, "Filter load failed", str(exc))
            return
        self._refresh_panel()
        self._status.setText(f"{n} species loaded.")

    def _on_unload(self) -> None:
        self._model.clear_lifetime_filter()
        self._refresh_panel()

    def _refresh_panel(self) -> None:
        """Refresh sibling refreshable widgets (the A/B selectors) and plots."""
        window = self.window() or self
        for w in window.findChildren(QtWidgets.QWidget):
            if w is not self and getattr(w, "AUTOFORM_REFRESH", False):
                try:
                    w.refresh()
                except Exception:
                    pass
        form = getattr(self._model, "_form", None)
        if form is not None:
            try:
                form.refresh_plots()
            except Exception:
                pass
        self.refresh()

    def refresh(self) -> None:
        if self._model.filter_mode:
            src = self._model._filter_source or "filters"
            n = len(self._model._filter_labels or [])
            self._status.setText(f"Species mode: {src} ({n} species).")
            self.btn_unload.setEnabled(True)
        else:
            # No status text in the default detector-channel mode — the empty
            # A/B selectors already make the mode obvious.
            self._status.setText("")
            self.btn_unload.setEnabled(False)


@register_section("correlate_controls")
class _CorrelateControls(QtWidgets.QWidget):
    def __init__(self, model, target: str = "", **options):
        super().__init__()
        self._model = model
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.btn = QtWidgets.QPushButton("Correlate")
        self.btn.setStyleSheet(
            "QPushButton { background-color: #1f7a1f; color: white; "
            "border: 1px solid #166016; border-radius: 4px; "
            "padding: 4px 16px; font-weight: bold; }"
            "QPushButton:hover { background-color: #249124; }"
        )
        self.btn.clicked.connect(self._on_correlate)
        layout.addWidget(self.btn)

        self._status = QtWidgets.QLabel("No data loaded.")
        layout.addWidget(self._status, 1)

    def _on_correlate(self) -> None:
        parent = self.window() if self.window() else self
        self._model.correlate_data(parent_widget=parent)
        n = len(self._model._correlations)
        self._status.setText(f"{n} chunk(s) correlated." if n else "Correlation empty.")

    def update_status(self, text: str) -> None:
        self._status.setText(text)
