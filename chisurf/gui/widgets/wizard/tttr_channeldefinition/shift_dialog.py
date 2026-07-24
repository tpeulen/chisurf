"""Visual per-routing-channel micro-time shift adjuster for the detector wizard.

Opens the calibration file **LUT-corrected** (when the setup's LUT is enabled —
shifts must be aligned on the linearized axis) and shows the per-channel
micro-time histograms with a draggable/spin per-channel shift. It reuses the
promoted micro-time-shifter core (a wrapping shift, mod n_mt): shifting a photon
stream by *k* bins is equivalent to ``np.roll`` on its histogram, so the live
preview needs no re-read.
"""

from __future__ import annotations

import numpy as np
from qtpy import QtWidgets

from chisurf.gui import chiplot as cp


class MicrotimeShiftDialog(QtWidgets.QDialog):
    """Interactive per-channel micro-time shift alignment (LUT-aware)."""

    def __init__(self, path, routine=None, channel_luts=None, channel_shifts=None,
                 apply_lut=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adjust micro-time shifts")
        self.resize(820, 520)
        self._shifts: dict[int, int] = {int(k): int(v) for k, v in (channel_shifts or {}).items()}
        self._hists: dict[int, np.ndarray] = {}
        self._n_mt = 0
        self._curves: dict[int, object] = {}
        self._spins: dict[int, QtWidgets.QSpinBox] = {}

        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(
            "Align each routing channel's micro-time histogram. Shifts wrap and are "
            "applied on the LUT-linearized axis." if apply_lut else
            "Align each routing channel's micro-time histogram (shifts wrap)."
        )
        info.setStyleSheet("color: #9ba3af; font-size: 11px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        self._load(path, routine, channel_luts, apply_lut)

        self._plot = None
        try:
            self._plot = cp.Plot()
            self._plot.set_labels(
                bottom="Micro-time bin (corrected)" if apply_lut else "Micro-time bin",
                left="Counts",
            )
            self._plot.legend()
            layout.addWidget(self._plot, 1)
        except Exception:  # pragma: no cover - environment without a plot backend
            self._plot = None

        # per-channel shift spinboxes
        controls = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(controls)
        grid.setContentsMargins(0, 0, 0, 0)
        for col, ch in enumerate(sorted(self._hists)):
            grid.addWidget(QtWidgets.QLabel(f"ch {ch}"), 0, col)
            spin = QtWidgets.QSpinBox()
            spin.setRange(-self._n_mt, self._n_mt)
            spin.setValue(int(self._shifts.get(ch, 0)))
            spin.valueChanged.connect(lambda v, c=ch: self._on_shift(c, v))
            grid.addWidget(spin, 1, col)
            self._spins[ch] = spin
        layout.addWidget(controls)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._redraw()

    def _load(self, path, routine, channel_luts, apply_lut):
        """Open the file (LUT-corrected when enabled) and cache per-channel histograms."""
        try:
            from chisurf.core.fio.staging import open_tttr

            tttr = open_tttr(str(path), routine or None,
                             channel_luts=channel_luts, apply_lut=bool(apply_lut))
            self._n_mt = int(tttr.header.get_effective_number_of_micro_time_channels())
            for ch in sorted(int(c) for c in tttr.get_used_routing_channels()):
                sel = tttr.get_tttr_by_channel([ch])
                counts = np.bincount(np.asarray(sel.micro_times), minlength=self._n_mt)
                self._hists[ch] = counts[: self._n_mt].astype(float)
        except Exception:
            self._hists = {}
            self._n_mt = max(self._n_mt, 1)

    def _on_shift(self, ch: int, value: int):
        self._shifts[int(ch)] = int(value)
        self._redraw()

    def _redraw(self):
        if self._plot is None or not self._hists:
            return
        self._plot.clear()
        x = np.arange(self._n_mt)
        for i, ch in enumerate(sorted(self._hists)):
            shift = int(self._shifts.get(ch, 0)) % max(self._n_mt, 1)
            y = np.roll(self._hists[ch], shift)  # wrapping shift == np.roll on the histogram
            self._plot.line(x, y, pen=cp.int_color(i, len(self._hists)), name=f"ch {ch}")

    def shifts(self) -> dict[int, int]:
        """Return the chosen per-channel shifts (non-zero entries)."""
        return {int(ch): int(s) for ch, s in self._shifts.items() if int(s)}
