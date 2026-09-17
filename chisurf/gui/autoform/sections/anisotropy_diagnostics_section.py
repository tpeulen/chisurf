"""AutoForm section: VV/VH anisotropy diagnostics for a TCSPC model.

Declare it inside an anisotropy panel::

    {"type": "custom", "key": "anisotropy_diagnostics", "target": "anisotropy"}

Two things live here, both about *checking* an anisotropy rather than fitting one:

* the background-corrected VV/VH integrals, behind a **VV/VH diag** toggle -- they
  are outputs, so they cost panel height for something most fits never look at;
* **show r(t)**, which opens r(t) for data and model, uncorrected and corrected,
  with the correction factors as live controls so the effect of `g`, `l1`/`l2`,
  the channel backgrounds and the VH↔VV time shift can be seen rather than
  guessed at.

The window is **modeless**. Its predecessor called ``exec_()``, which blocks the
event loop and, on an offscreen run, blocks it with nobody able to close the
window; that is also why nothing headless could ever screenshot it.

The arithmetic is not here: `Anisotropy.rt_from_channels` and the extraction
helpers (`_extract_vv_vh_raw_for_diag`, `_extract_vv_vh_model_for_diag`,
`_shift_trace_to_reference`) are Qt-free and live on the model, so the numbers this
view draws can be asserted without a display.
"""

from __future__ import annotations

import numpy as np
from qtpy import QtCore, QtWidgets

from chisurf import logging
from chisurf.gui import dialogs
from chisurf.gui.widgets.fitting import make_fitting_parameter_widget

from .registry import register_section

try:
    from chisurf.gui import chiplot as cp
except Exception:  # pragma: no cover - renderer may be missing headless
    cp = None


#: Curve styling: data solid, model dashed; uncorrected grey/blue, corrected green.
_CURVES = (
    ("data raw", (100, 116, 139), None),
    ("data corr", (22, 163, 74), None),
    ("model raw", (59, 130, 246), "dash"),
    ("model corr", (16, 185, 129), "dash"),
)


def _spin(parent, value: float, step: float, decimals: int) -> QtWidgets.QDoubleSpinBox:
    """Return a wide-range double spin box seeded with `value`."""
    sb = QtWidgets.QDoubleSpinBox(parent)
    sb.setRange(-100000.0, 100000.0)
    sb.setDecimals(decimals)
    sb.setSingleStep(step)
    sb.setValue(float(value))
    return sb


@register_section("anisotropy_diagnostics")
class AnisotropyDiagnostics(QtWidgets.QWidget):
    """Diagnostics row for an anisotropy group: corrected integrals + r(t) view."""

    def __init__(self, model=None, target: str = "anisotropy", parent=None, **options):
        """Build the diagnostics row.

        Parameters
        ----------
        model : optional
            The TCSPC model whose anisotropy group is inspected.
        target : str
            Attribute naming that group.
        parent : optional
            Qt parent.
        **options
            Unused view-spec options.
        """
        super().__init__(parent)
        self._model = model
        self._group = getattr(model, target, None)
        #: The r(t) window is modeless, so it must be kept alive by a reference.
        self._rt_window: QtWidgets.QWidget | None = None

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addStretch(1)

        self.diag_toggle = QtWidgets.QToolButton()
        self.diag_toggle.setText("VV/VH diag")
        self.diag_toggle.setCheckable(True)
        self.diag_toggle.setChecked(False)
        self.diag_toggle.setToolTip(
            "Show the background-corrected VV and VH integrals (computed outputs)"
        )
        self.diag_toggle.toggled.connect(self._set_outputs_visible)
        row.addWidget(self.diag_toggle)

        self.rt_button = QtWidgets.QToolButton()
        self.rt_button.setText("show r(t)")
        self.rt_button.setToolTip(
            "Open the anisotropy decay of data and model, uncorrected and corrected,\n"
            "with g / l1 / l2 / backgrounds / VH-VV shift as live controls"
        )
        self.rt_button.clicked.connect(self.show_rt_window)
        row.addWidget(self.rt_button)
        outer.addLayout(row)

        self._outputs = QtWidgets.QWidget()
        grid = QtWidgets.QHBoxLayout(self._outputs)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for attr in ("_vv_bg_int", "_vh_bg_int"):
            parameter = getattr(self._group, attr, None)
            if parameter is None:
                continue
            grid.addWidget(make_fitting_parameter_widget(parameter, decimals=3))
        outer.addWidget(self._outputs)
        self._set_outputs_visible(False)

    # -- outputs -------------------------------------------------------------
    def _set_outputs_visible(self, visible: bool) -> None:
        """Show or hide the corrected-integral outputs."""
        self._outputs.setVisible(bool(visible))

    # -- r(t) ----------------------------------------------------------------
    def show_rt_window(self) -> None:
        """Open (or raise) the modeless r(t) diagnostics window."""
        if self._rt_window is not None:
            self._rt_window.show()
            self._rt_window.raise_()
            return
        if cp is None:
            dialogs.warning(
                self,
                "Anisotropy decays",
                "The plotting backend is not available, cannot plot anisotropy decays.",
            )
            return
        group = self._group
        extract = getattr(group, "_extract_vv_vh_raw_for_diag", None)
        if not callable(extract):
            dialogs.warning(
                self,
                "Anisotropy decays",
                "This model's anisotropy group offers no VV/VH diagnostics.",
            )
            return
        t_raw, vv_raw, vh_raw, defaults = extract()
        if t_raw is None or vv_raw is None or vh_raw is None or defaults is None:
            dialogs.information(
                self,
                "Anisotropy decays",
                "VV/VH channels are not available for anisotropy-decay diagnostics.",
            )
            return
        self._rt_window = _RtWindow(group, t_raw, vv_raw, vh_raw, defaults, parent=self)
        self._rt_window.show()


class _RtWindow(QtWidgets.QWidget):
    """Modeless r(t) view with live correction factors and CSV export."""

    def __init__(self, group, t_raw, vv_raw, vh_raw, defaults, parent=None):
        super().__init__(parent, QtCore.Qt.Window)
        self.setWindowTitle("Anisotropy decays (corrected vs uncorrected)")
        self._group = group
        self._t_raw, self._vv_raw, self._vh_raw = t_raw, vv_raw, vh_raw
        self._defaults = dict(defaults)
        #: Last computed curves, for the CSV export.
        self._state: dict = {}

        layout = QtWidgets.QVBoxLayout(self)

        controls = QtWidgets.QGridLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setHorizontalSpacing(6)
        controls.setVerticalSpacing(2)
        self.g_sb = _spin(self, defaults["g"], 0.01, 6)
        self.l1_sb = _spin(self, defaults["l1"], 0.001, 6)
        self.l2_sb = _spin(self, defaults["l2"], 0.001, 6)
        self.bg_vv_sb = _spin(self, defaults["bg_vv"], 1.0, 3)
        self.bg_vh_sb = _spin(self, defaults["bg_vh"], 1.0, 3)
        self.shift_sb = _spin(
            self, float(defaults["shift_vh"]) - float(defaults["shift_vv"]), 0.01, 4
        )
        for col, (label, widget) in enumerate(
            (
                ("g:", self.g_sb),
                ("l1:", self.l1_sb),
                ("l2:", self.l2_sb),
            )
        ):
            controls.addWidget(QtWidgets.QLabel(label), 0, 2 * col)
            controls.addWidget(widget, 0, 2 * col + 1)
        for col, (label, widget) in enumerate(
            (
                ("BgVV:", self.bg_vv_sb),
                ("BgVH:", self.bg_vh_sb),
                ("dVH-VV:", self.shift_sb),
            )
        ):
            controls.addWidget(QtWidgets.QLabel(label), 1, 2 * col)
            controls.addWidget(widget, 1, 2 * col + 1)

        self.link_l = QtWidgets.QCheckBox("link l1/l2", self)
        self.link_l.setChecked(True)
        self.link_l.setToolTip("Keep l2 equal to l1 (the usual case for one detector pair)")
        controls.addWidget(self.link_l, 2, 2)
        reset = QtWidgets.QToolButton(self)
        reset.setText("Reset")
        reset.setToolTip("Restore the factors the fit is currently using")
        controls.addWidget(reset, 2, 3)
        layout.addLayout(controls)

        self.plot = cp.Plot(self)
        self.plot.grid(x=True, y=True, alpha=0.25)
        self.plot.set_labels(bottom="Time", left="r(t)")
        self.plot.set_ylim(0.0, 0.5, padding=0.0)
        self.plot.legend()
        self._curves = {
            name: self.plot.line(
                [],
                [],
                pen=cp.to_pen(colour, width=2, **({"style": style} if style else {})),
                name=name,
            )
            for name, colour, style in _CURVES
        }
        layout.addWidget(self.plot)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        save = buttons.addButton("Save CSV", QtWidgets.QDialogButtonBox.ActionRole)
        save.clicked.connect(self._save_csv)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

        self.link_l.toggled.connect(self._on_link_toggled)
        self.l1_sb.valueChanged.connect(lambda _: self._sync_l2())
        for sb in (self.g_sb, self.l1_sb, self.l2_sb, self.bg_vv_sb, self.bg_vh_sb, self.shift_sb):
            sb.valueChanged.connect(lambda _: self.recompute())
        reset.clicked.connect(self._reset)

        self._on_link_toggled(True)
        self.resize(600, 420)

    # -- controls ------------------------------------------------------------
    def _sync_l2(self) -> None:
        """Mirror l1 into l2 while they are linked."""
        if not self.link_l.isChecked():
            return
        value = float(self.l1_sb.value())
        if abs(float(self.l2_sb.value()) - value) > 1e-15:
            self.l2_sb.blockSignals(True)
            self.l2_sb.setValue(value)
            self.l2_sb.blockSignals(False)

    def _on_link_toggled(self, checked: bool) -> None:
        """Enable/disable l2 and re-draw."""
        self.l2_sb.setEnabled(not bool(checked))
        if checked:
            self._sync_l2()
        self.recompute()

    def _reset(self) -> None:
        """Restore every factor to what the fit is using."""
        d = self._defaults
        for widget, key in (
            (self.g_sb, "g"),
            (self.l1_sb, "l1"),
            (self.l2_sb, "l2"),
            (self.bg_vv_sb, "bg_vv"),
            (self.bg_vh_sb, "bg_vh"),
        ):
            widget.setValue(float(d[key]))
        self.shift_sb.setValue(float(d["shift_vh"]) - float(d["shift_vv"]))
        self.link_l.setChecked(True)

    # -- drawing -------------------------------------------------------------
    def _rt(self, t, vv, vh):
        """Background-subtract, shift VH, and return r(t) via the core algebra."""
        group = self._group
        t = np.asarray(t, dtype=np.float64)
        vv = np.asarray(vv, dtype=np.float64) - float(self.bg_vv_sb.value())
        vh = np.asarray(vh, dtype=np.float64) - float(self.bg_vh_sb.value())
        vh = group._shift_trace_to_reference(t, vh, float(self.shift_sb.value()))
        return group.rt_from_channels(
            t,
            vv,
            vh,
            float(self.g_sb.value()),
            float(self.l1_sb.value()),
            float(self.l2_sb.value()),
        )

    def recompute(self) -> None:
        """Recompute both pairs of curves and redraw."""
        tt, r_unc, r_cor = self._rt(self._t_raw, self._vv_raw, self._vh_raw)
        self._state.update(t=tt, r_data_unc=r_unc, r_data_cor=r_cor)
        self._draw("data raw", tt, r_unc)
        self._draw("data corr", tt, r_cor)

        extract = getattr(self._group, "_extract_vv_vh_model_for_diag", None)
        t_model, vv_model, vh_model = extract() if callable(extract) else (None, None, None)
        if t_model is None or vv_model is None or vh_model is None:
            self._state.update(t_model=None, r_model_unc=None, r_model_cor=None)
            self._draw("model raw", None, None)
            self._draw("model corr", None, None)
            return
        tm, rmu, rmc = self._rt(t_model, vv_model, vh_model)
        self._state.update(t_model=tm, r_model_unc=rmu, r_model_cor=rmc)
        self._draw("model raw", tm, rmu)
        self._draw("model corr", tm, rmc)

    def _draw(self, name: str, x, y) -> None:
        """Set one curve's data, clearing it when there is nothing to show."""
        curve = self._curves.get(name)
        if curve is None:
            return
        if x is None or y is None:
            curve.set_data([], [])
        else:
            curve.set_data(x, y)

    # -- export --------------------------------------------------------------
    def _save_csv(self) -> None:
        """Write the drawn curves to CSV, data and model on their own time axes."""
        s = self._state
        t, r_du, r_dc = s.get("t"), s.get("r_data_unc"), s.get("r_data_cor")
        if t is None or r_du is None or r_dc is None:
            dialogs.information(self, "Save anisotropy decay", "No anisotropy decay data to save.")
            return
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save anisotropy decay",
            "anisotropy_decay.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not filename:
            return
        tm, rmu, rmc = s.get("t_model"), s.get("r_model_unc"), s.get("r_model_cor")
        try:
            if tm is None or rmu is None or rmc is None:
                arr = np.column_stack([t, r_du, r_dc])
                header = "time_data,r_data_uncorrected,r_data_corrected"
            else:
                # Two independent axes, so pad rather than interpolate: resampling
                # here would write numbers the fit never computed.
                n = max(len(t), len(tm))
                arr = np.full((n, 6), np.nan, dtype=float)
                for col, values in enumerate((t, r_du, r_dc)):
                    arr[: len(t), col] = values
                for col, values in enumerate((tm, rmu, rmc), start=3):
                    arr[: len(tm), col] = values
                header = (
                    "time_data,r_data_uncorrected,r_data_corrected,"
                    "time_model,r_model_uncorrected,r_model_corrected"
                )
            np.savetxt(filename, arr, delimiter=",", header=header, comments="")
        except Exception as exc:
            logging.warning(f"anisotropy diagnostics: CSV export failed: {exc}")
            dialogs.warning(self, "Save anisotropy decay", f"Failed to save file:\n{exc}")
