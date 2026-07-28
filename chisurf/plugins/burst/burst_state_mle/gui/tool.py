"""Panel for the burst- and state-wise MLE (step 7 of the burst workflow).

A thin GUI over :mod:`..core.state_mle`: it points at a burst-analysis folder
that already holds an H2MM run and a burst-wise MLE export, refits every
``(burst, state, colour)``, and writes the per-state ``.b?4`` folders.

The panel deliberately has almost no settings of its own. Everything the fit
needs was decided by the two steps before it — the instrument description in
``b?4/channel_settings.json``, the sample's IRF and background in
``Info/experiment_settings.json``, the state assignment in ``h2mm_photons`` —
and re-asking for any of it here would be a second place for them to disagree.
"""

from __future__ import annotations

import logging
import pathlib

import numpy as np
from qtpy import QtCore, QtWidgets

from chisurf.core import analysis_cache
from chisurf.gui import chiplot as cp
from chisurf.gui.progress import ChiSurfProgress
from chisurf.gui.widgets.tool_buttons import TOOLBAR_STYLE, action_button, flag_attention

from ..core import state_mle as core

#: Bump in the same change that alters what this tool computes.
ALGORITHM_VERSION = 1

#: Pen colour per detection colour — the same language the H2MM decay plot uses.
_COLOUR_PENS = {
    "green": "#2ca02c", "donor": "#2ca02c",
    "red": "#d62728", "acceptor": "#d62728",
    "yellow": "#e8b400", "aex": "#e8b400",
}
#: Line style per state — the dash carries the state, the colour the detector.
#: chiplot dash names, not Qt pen constants: nothing here touches pyqtgraph.
_STATE_DASHES = ["solid", "dash", "dot", "dash_dot"]
_DASH_NAMES = ["solid", "dashed", "dotted", "dash-dot"]


class BurstStateMleTool(QtWidgets.QMainWindow):
    """Refit an H2MM analysis one decay per (burst, state, colour)."""

    name = "Spectroscopy:Single-Molecule:MLE per State"

    def __init__(self, parent=None, *, embedded: bool = False, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("MLE Statewise")
        self._embedded = embedded
        self._results = None
        self._detectors: list = []
        self._task = None
        self._running_fingerprint: str | None = None
        self._result_cache = analysis_cache.ResultCache()

        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        toolbar = QtWidgets.QToolBar()
        toolbar.setStyleSheet(TOOLBAR_STYLE)
        self._run = action_button("run", tooltip="Fit every burst state in the folder")
        self._run.clicked.connect(self._on_run_clicked)
        self._restart = action_button(
            "restart", tooltip="Refit from scratch, even if nothing changed"
        )
        self._restart.clicked.connect(self._on_restart_clicked)
        self._stop = action_button("stop", tooltip="Stop the running fit")
        self._stop.setEnabled(False)
        self._stop.clicked.connect(self.stop)
        browse = action_button("folder", tooltip="Choose the burst analysis folder")
        browse.clicked.connect(self._browse)
        for b in (self._run, self._restart, self._stop, browse):
            toolbar.addWidget(b)
        layout.addWidget(toolbar)

        row = QtWidgets.QHBoxLayout()
        self._folder_edit = QtWidgets.QLineEdit()
        self._folder_edit.setPlaceholderText("Burst analysis folder with an H2MM run …")
        row.addWidget(QtWidgets.QLabel("Folder"))
        row.addWidget(self._folder_edit, 1)
        layout.addLayout(row)

        # What this step is fitting, read from the folder rather than asked for.
        box = QtWidgets.QGroupBox("Inputs (from the H2MM and MLE-Burstwise steps)")
        form = QtWidgets.QFormLayout(box)
        self._lbl_photons = QtWidgets.QLabel("—")
        self._lbl_detectors = QtWidgets.QLabel("—")
        self._lbl_states = QtWidgets.QLabel("—")
        self._lbl_irf = QtWidgets.QLabel("—")
        self._lbl_photons.setToolTip("Per-photon state assignment written by H2MM.")
        self._lbl_detectors.setToolTip(
            "Colours and their routing channels, from the H2MM stream definitions."
        )
        self._lbl_irf.setToolTip(
            "The sample's instrument response and background — an experiment "
            "property, recorded in Info/experiment_settings.json."
        )
        form.addRow("Photon table", self._lbl_photons)
        form.addRow("Detectors", self._lbl_detectors)
        form.addRow("States", self._lbl_states)
        form.addRow("IRF / background", self._lbl_irf)
        layout.addWidget(box)

        self._table = QtWidgets.QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["State", "Colour", "Fitted", "median τ (ns)", "median 2I*"]
        )
        # Stretch every column: five short numeric columns read better evenly
        # spread than squeezed left with one enormous trailing column.
        self._table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._table.setMaximumHeight(170)
        layout.addWidget(self._table)

        self._plot = cp.Plot()
        self._plot.set_labels(bottom="τ (ns)", left="Bursts")
        layout.addWidget(self._plot, 1)

        self._status = QtWidgets.QLabel("")
        layout.addWidget(self._status)
        if self._embedded:
            self._status.setVisible(False)

    # ── helpers ──────────────────────────────────────────────────────

    def _set_status(self, msg: str) -> None:
        """Update the local line and report through the burst logger."""
        self._status.setText(msg)
        logging.getLogger(__name__).info(msg)

    def set_folder(self, folder) -> None:
        """Point the panel at an analysis folder (used by the workflow context)."""
        self._folder_edit.setText(str(folder))
        self._describe_inputs()

    def _folder(self) -> pathlib.Path | None:
        text = self._folder_edit.text().strip()
        if not text:
            return None
        p = pathlib.Path(text)
        return p if p.is_dir() else None

    def _browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select analysis folder")
        if d:
            self.set_folder(d)
            self._on_run_clicked()

    def input_files(self) -> list:
        """Everything the fit reads, for the reuse gate."""
        root = self._folder()
        if root is None:
            return []
        h2mm = core.h2mm_output_dir(root)
        files = [
            h2mm / "h2mm_photons.h5", h2mm / "h2mm_photons.csv",
            h2mm / "h2mm_result.json", root / "Info" / "experiment_settings.json",
        ]
        files += sorted(root.glob("b?4/channel_settings.json"))
        return [f for f in files if f.exists()] or files

    def analysis_fingerprint(self) -> str:
        """Fingerprint of the inputs, the read context and the code."""
        return analysis_cache.fingerprint(
            self.input_files(),
            {"_read_context": analysis_cache.photon_read_context()},
            extra=analysis_cache.algorithm_tag(
                "burst_state_mle", ALGORITHM_VERSION, "fit2x", "tttrlib"
            ),
        )

    def _describe_inputs(self) -> None:
        """Say what the folder offers, before anything is fitted."""
        root = self._folder()
        if root is None:
            for lbl in (self._lbl_photons, self._lbl_detectors,
                        self._lbl_states, self._lbl_irf):
                lbl.setText("—")
            return
        try:
            photons = core.read_photon_table(root)
            n = len(photons)
            states = sorted(int(s) for s in np.unique(photons["State"]))
            self._lbl_photons.setText(f"{n:,} photons")
            self._lbl_states.setText(", ".join(f"S{s}" for s in states) or "—")
        except FileNotFoundError as exc:
            self._lbl_photons.setText("missing — run H2MM first")
            self._lbl_states.setText("—")
            logging.getLogger(__name__).info(str(exc))
        try:
            dets = core.detectors_from_analysis(root)
        except FileNotFoundError:
            dets = []
        self._detectors = dets
        if dets:
            self._lbl_detectors.setText(
                ", ".join(f"{d.name} {d.channels}" for d in dets)
            )
            self._lbl_irf.setText(
                f"{len(dets)} detector(s), {dets[0].n_bins} bins per polarisation"
            )
        else:
            self._lbl_detectors.setText("none — run MLE-Burstwise first")
            self._lbl_irf.setText("missing — the IRF is recorded when MLE-Burstwise runs")

    # ── run ──────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        """Describe the folder on arrival; fitting stays an explicit click.

        Unlike 2CDE and H2MM this step does *not* start on its own: it refits
        every burst of every state, which is the most expensive thing in the
        workflow, and unlike those two it has nothing to show until it does.
        """
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._describe_inputs)

    def _on_run_clicked(self) -> None:
        self._result_cache.allow()
        self.run()

    def _on_restart_clicked(self) -> None:
        self._result_cache.allow()
        self.run(force=True)

    def _is_running(self) -> bool:
        return self._task is not None and self._task.is_running()

    def run(self, *, force: bool = False) -> None:
        """Fit every (burst, state, colour) off the GUI thread."""
        root = self._folder()
        if root is None:
            self._set_status("Select a burst analysis folder.")
            return
        if self._is_running():
            return
        self._describe_inputs()
        if not self._detectors:
            self._set_status(
                "No detector has an IRF yet — run MLE-Burstwise first; it records "
                "the sample's IRF and background."
            )
            return

        fingerprint = self.analysis_fingerprint()
        stamp = root / "Info" / "state_mle.stamp.json"
        if (
            not force
            and self._results is not None
            and self._result_cache.matches(fingerprint)
            and analysis_cache.is_current(stamp, fingerprint)
        ):
            self._set_status(
                "Unchanged — kept the previous state-wise fits (🔁 Restart refits)"
            )
            flag_attention(self._restart, True)
            return
        flag_attention(self._restart, False)

        self._running_fingerprint = fingerprint
        self._run.setEnabled(False)
        self._stop.setEnabled(True)
        self._set_status("Fitting every burst state …")
        self._task = ChiSurfProgress.run(
            self, "Reading the H2MM photon table …", self._worker,
            args=(root, list(self._detectors), fingerprint),
            maximum=100, title="MLE per State", owner=self._run,
            on_result=self._done, on_error=self._failed, on_done=self._over,
        )

    def _worker(self, root, detectors, fingerprint, task):
        """Worker: read, fit, write. No GUI here."""
        task.set_range(0, 0)
        task.set_text("Reading the H2MM photon table …")
        photons = core.read_photon_table(root)
        task.set_range(0, 100)

        def progress(done, total):
            task.raise_if_cancelled()
            task.set_progress(int(90 * done / max(total, 1)),
                              f"Fitting … {done}/{total} burst states")

        results = core.fit_state_wise(photons, detectors, progress=progress)
        task.set_progress(92, "Writing per-state results …")
        written = core.write_state_results(results, root, detectors)
        if written:
            analysis_cache.write_stamp(
                pathlib.Path(root) / "Info" / "state_mle.stamp.json", fingerprint,
                inputs=self.input_files(), outputs=written, tool="burst_state_mle",
            )
        return results, written

    def _done(self, payload) -> None:
        """Back on the GUI thread: fill the summary table and the τ histograms."""
        results, written = payload
        self._results = results
        if self._running_fingerprint is not None:
            self._result_cache.remember(self._running_fingerprint)
        self._fill_table(results)
        self._plot_taus(results)
        fitted = int((results["Fitted"] == 1).sum())
        folders = sorted({p.parent.name for p in written if p.suffix != ".csv"})
        self._set_status(
            f"Fitted {fitted} of {len(results)} burst states → {', '.join(folders)}"
        )

    def _failed(self, exc) -> None:
        self._result_cache.invalidate()
        self._set_status(f"The state-wise fit failed: {exc}")

    def _over(self) -> None:
        self._task = None
        self._run.setEnabled(True)
        self._stop.setEnabled(False)

    def stop(self) -> None:
        """Stop the running fit; a stopped fit leaves nothing to reuse."""
        task = self._task
        if task is None:
            return
        task.cancel()
        self._result_cache.abandon(self._running_fingerprint)
        self._set_status("Stopping the state-wise fit …")

    # ── presentation ─────────────────────────────────────────────────

    def _fill_table(self, results) -> None:
        """One row per (state, colour): how many fitted, and the median fit."""
        fitted = results[results["Fitted"] == 1]
        grouped = list(results.groupby(["State", "Detector"], sort=True))
        self._table.setRowCount(len(grouped))
        for r, ((state, det), grp) in enumerate(grouped):
            ok = fitted[(fitted["State"] == state) & (fitted["Detector"] == det)]
            values = [
                f"S{int(state)}", str(det), f"{len(ok)} / {len(grp)}",
                f"{ok['Tau'].median():.2f}" if len(ok) else "—",
                f"{ok['2I*'].median():.2f}" if len(ok) else "—",
            ]
            for c, text in enumerate(values):
                self._table.setItem(r, c, QtWidgets.QTableWidgetItem(text))


    def _plot_taus(self, results) -> None:
        """τ histogram per (colour, state) — colour is the detector, dash the state."""
        p = self._plot
        p.clear()
        fitted = results[results["Fitted"] == 1]
        if not len(fitted):
            return
        lo = float(np.nanpercentile(fitted["Tau"], 1))
        hi = float(np.nanpercentile(fitted["Tau"], 99))
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            lo, hi = 0.0, max(1.0, float(np.nanmax(fitted["Tau"])))
        edges = np.linspace(lo, hi, 41)
        centers = 0.5 * (edges[:-1] + edges[1:])
        states = sorted(int(s) for s in fitted["State"].unique())
        for det in sorted(fitted["Detector"].unique()):
            rgb = _COLOUR_PENS.get(str(det).lower(), "#999999")
            for s in states:
                tau = fitted[(fitted["Detector"] == det) & (fitted["State"] == s)]["Tau"]
                if not len(tau):
                    continue
                counts, _ = np.histogram(tau.to_numpy(dtype=float), bins=edges)
                style = _STATE_DASHES[s % len(_STATE_DASHES)]
                p.line(centers, counts, pen=rgb, width=2, style=style,
                       name=f"{det} S{s}")
        key = " · ".join(f"{_DASH_NAMES[s % len(_DASH_NAMES)]} S{s}" for s in states)
        p.set_labels(bottom=f"τ (ns) — {key}", left="Bursts")
