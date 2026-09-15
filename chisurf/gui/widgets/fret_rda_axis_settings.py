"""The global FRET distance axis (R_DA), as an application setting.

The axis every FRET distance distribution is evaluated on is one global grid, so
this is a *settings* widget rather than part of any model's editor -- which is
where it used to live, in ``gui/widgets/models/pda2c/widgets.py``, alongside nine
model widgets that data-described models had already replaced.
"""
from __future__ import annotations

from qtpy import QtWidgets

import chisurf as cs
import chisurf.core.fluorescence
import chisurf.core.settings
from chisurf.core.settings.settings_utils import build_fret_rda_axis, set_fret_rda_axis
from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client


class FretRdaAxisSettingsWidget(QtWidgets.QGroupBox):
    """Widget for configuring the FRET distance axis (R_DA)."""

    def __init__(self, parent=None):
        """Initialize the FRET R_DA axis settings widget.

        Parameters
        ----------
        parent : QWidget, optional
            Parent widget.
        """
        super().__init__(parent)
        self.setTitle("R_DA axis (FRET distance)")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        description = QtWidgets.QLabel(
            "Distance axis used for FRET-related distance distributions.\n"
            "These values control cs.core.settings.fret['rda_min'], "
            "['rda_max'], ['rda_resolution'] and ['rda_scale'] which "
            "define the grid cs.core.fluorescence.rda_axis (log or "
            "linear spacing)."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(2)

        fret_cfg = getattr(cs.core.settings, "fret", {}) or {}
        rda_min = float(fret_cfg.get("rda_min", 1.0))
        rda_max = float(fret_cfg.get("rda_max", 130.0))
        rda_res = int(fret_cfg.get("rda_resolution", 96))
        rda_scale = str(fret_cfg.get("rda_scale", "log")).lower()

        self.sb_min = QtWidgets.QDoubleSpinBox()
        self.sb_min.setRange(0.01, 1.0e4)
        self.sb_min.setDecimals(3)
        self.sb_min.setValue(rda_min)
        self.sb_min.setSuffix(" Å")

        self.sb_max = QtWidgets.QDoubleSpinBox()
        self.sb_max.setRange(0.01, 1.0e4)
        self.sb_max.setDecimals(3)
        self.sb_max.setValue(rda_max)
        self.sb_max.setSuffix(" Å")

        self.sb_n = QtWidgets.QSpinBox()
        self.sb_n.setRange(4, 4096)
        self.sb_n.setValue(rda_res)

        self.cb_scale = QtWidgets.QComboBox()
        self.cb_scale.addItems(["log", "lin"])
        if rda_scale in ("log", "lin"):
            try:
                idx = self.cb_scale.findText(rda_scale)
                if idx >= 0:
                    self.cb_scale.setCurrentIndex(idx)
            except Exception:
                pass

        form.addRow("R_DA min:", self.sb_min)
        form.addRow("R_DA max:", self.sb_max)
        form.addRow("N points:", self.sb_n)
        form.addRow("Scale:", self.cb_scale)

        layout.addLayout(form)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(4)

        save_btn = QtWidgets.QPushButton("Save axis")
        save_btn.clicked.connect(self.on_save_clicked)
        button_layout.addWidget(save_btn)
        button_layout.addStretch(1)

        layout.addLayout(button_layout)

    def on_save_clicked(self):
        """Save the current R_DA axis settings and apply them globally."""
        rda_min = float(self.sb_min.value())
        rda_max = float(self.sb_max.value())
        n_points = int(self.sb_n.value())
        scale = self.cb_scale.currentText().strip().lower() if hasattr(self, "cb_scale") else "log"
        if scale not in ("log", "lin"):
            scale = "log"

        if rda_max <= rda_min:
            tmp = rda_min
            rda_min = rda_max
            rda_max = tmp
            self.sb_min.setValue(rda_min)
            self.sb_max.setValue(rda_max)

        ok = set_fret_rda_axis(
            rda_min=rda_min,
            rda_max=rda_max,
            rda_resolution=n_points,
            rda_scale=scale,
        )
        if not ok:
            return

        try:
            if not isinstance(getattr(cs.core.settings, "fret", None), dict):
                cs.core.settings.fret = {}
        except Exception:
            cs.core.settings.fret = {}

        cs.core.settings.fret["rda_min"] = float(rda_min)
        cs.core.settings.fret["rda_max"] = float(rda_max)
        cs.core.settings.fret["rda_resolution"] = int(n_points)
        cs.core.settings.fret["rda_scale"] = scale

        try:
            new_axis = build_fret_rda_axis(
                cs.core.settings.fret["rda_min"],
                cs.core.settings.fret["rda_max"],
                cs.core.settings.fret["rda_resolution"],
                cs.core.settings.fret.get("rda_scale", scale),
            )
        except Exception:
            return

        try:
            cs.core.fluorescence.rda_axis = new_axis
        except Exception:
            pass

        try:
            fc = get_fitting_client()
            if fc is not None:
                for i, _ in enumerate(fc.get_fit_objects()):
                    fc.update_fit(fit_index=i)
        except Exception:
            pass
