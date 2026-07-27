"""FRET-2CDE / ALEX-2CDE GUI tool.

A compact panel to compute the 2CDE burst-dynamics feature over a burstwise
analysis folder and plot it against the per-burst FRET efficiency.  The heavy
lifting is in :mod:`chisurf.plugins.burst.burst_2cde.core.computation`; this is
a thin GUI over it, embeddable in the ``burst_analysis`` workflow shell.
"""

from __future__ import annotations

import logging
import pathlib

import numpy as np
from chisurf.gui import chiplot as cp
from qtpy import QtCore, QtWidgets

from chisurf.gui.widgets.tool_buttons import TOOLBAR_STYLE, action_button
from chisurf.plugins.burst.burst_2cde.core import computation as core
from chisurf.core import analysis_cache
from chisurf.gui.progress import ChiSurfProgress

try:
    from chisurf.plugins.burst.burst_selection.api.features import proximity_ratio
except Exception:  # pragma: no cover - optional dependency
    proximity_ratio = None


class BurstTwoCdeTool(QtWidgets.QMainWindow):
    """Compute and plot FRET-2CDE / ALEX-2CDE for a burstwise analysis folder."""

    name = "Spectroscopy:Single-Molecule:2CDE"

    def __init__(self, parent=None, embedded: bool = False, **kwargs):
        super().__init__(parent)
        self.setWindowTitle("FRET-2CDE / ALEX-2CDE")
        self._embedded = embedded
        self._folder: pathlib.Path | None = None
        self._df = None
        # What the plotted result was computed from: an identical request (a
        # panel revisit, another Next) reuses it instead of recomputing.
        self._result_cache = analysis_cache.ResultCache()
        self._running_fingerprint: str | None = None
        self._task = None

        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # --- action toolbar (pinned on top, same as every plugin) -------------
        toolbar = QtWidgets.QToolBar()
        toolbar.setStyleSheet(TOOLBAR_STYLE)
        self._run = action_button("run", tooltip="Compute 2CDE over all loaded data")
        self._run.clicked.connect(self.run)
        # The computation starts on its own when this step is opened, so stopping
        # it must be one click away.
        self._stop = action_button("stop", tooltip="Stop the running 2CDE computation")
        self._stop.setEnabled(False)
        self._stop.clicked.connect(self.stop)
        browse = action_button("folder", tooltip="Choose the burst analysis folder")
        browse.clicked.connect(self._browse)
        toolbar.addWidget(self._run)
        toolbar.addWidget(self._stop)
        toolbar.addWidget(browse)
        layout.addWidget(toolbar)

        # --- folder row -------------------------------------------------------
        row = QtWidgets.QHBoxLayout()
        self._folder_edit = QtWidgets.QLineEdit()
        self._folder_edit.setPlaceholderText("Burstwise analysis folder …")
        row.addWidget(QtWidgets.QLabel("Folder"))
        row.addWidget(self._folder_edit, 1)
        layout.addLayout(row)

        # --- settings form ----------------------------------------------------
        form = QtWidgets.QFormLayout()
        self._variant = QtWidgets.QComboBox()
        self._variant.addItems(["fret", "alex"])
        self._kernel = QtWidgets.QComboBox()
        self._kernel.addItems(["laplace", "gaussian"])
        self._tau = QtWidgets.QDoubleSpinBox()
        self._tau.setDecimals(1)
        self._tau.setRange(1.0, 100000.0)
        self._tau.setValue(100.0)
        self._tau.setSuffix(" µs")
        self._donor = QtWidgets.QLineEdit("0,8")
        self._acceptor = QtWidgets.QLineEdit("1,9")
        self._file_type = QtWidgets.QLineEdit("SPC-130")
        form.addRow("Variant", self._variant)
        form.addRow("Kernel", self._kernel)
        form.addRow("τ", self._tau)
        form.addRow("Donor ch.", self._donor)
        form.addRow("Acceptor ch.", self._acceptor)
        form.addRow("File type", self._file_type)
        layout.addLayout(form)

        # --- plot -------------------------------------------------------------
        self._plot = cp.Plot()
        self._plot.set_labels(bottom="FRET efficiency (proximity ratio)", left="2CDE")
        layout.addWidget(self._plot, 1)

        self._status = QtWidgets.QLabel("")
        layout.addWidget(self._status)
        # Embedded, the shared status bar carries messages — hide the local line.
        if self._embedded:
            self._status.setVisible(False)

    # -- helpers --------------------------------------------------------------
    def _set_status(self, msg: str) -> None:
        """Update the local status label and report via normal logging.

        When embedded in the Burst Analysis shell, the logged line appears in the
        shared status bar (the shell installs a handler on the burst logger).
        """
        self._status.setText(msg)
        logging.getLogger(__name__).info(msg)

    def _browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select burstwise folder")
        if d:
            self._folder_edit.setText(d)
            # Picking a folder is a request for its 2CDE, not for a button press.
            self.run()

    def _channels(self, text: str):
        return [int(x) for x in str(text).split(",") if x.strip()]

    def set_folder(self, folder) -> None:
        """Set the analysis folder (used by the workflow context)."""
        self._folder_edit.setText(str(folder))

    def input_files(self) -> list[pathlib.Path]:
        """The burst files this analysis reads (``bi4_bur/*``)."""
        folder = self._folder_edit.text().strip()
        if not folder:
            return []
        return [
            f
            for d in sorted(pathlib.Path(folder).glob("bi4_bur"))
            for f in sorted(d.glob("*"))
            if f.is_file()
        ]

    def settings(self) -> dict:
        """Everything the computation is given, in one mapping."""
        return {
            "variant": self._variant.currentText(),
            "kernel": self._kernel.currentText(),
            "tau_us": float(self._tau.value()),
            "donor_channels": self._channels(self._donor.text()),
            "acceptor_channels": self._channels(self._acceptor.text()),
            "file_type": self._file_type.text().strip(),
        }

    def analysis_fingerprint(self) -> str:
        """Fingerprint of the burst files plus the current settings."""
        return analysis_cache.fingerprint(self.input_files(), self.settings(),
                                          extra="2cde")

    def showEvent(self, event) -> None:
        """Compute for the folder this panel was given, as soon as it is shown.

        Landing on the 2CDE step of the burst workflow should show the 2CDE
        result, not an empty plot and a button: everything the computation needs
        was decided upstream, and the shell has just handed it over. The run is
        deferred by one event-loop turn so the panel paints first *and* so it
        sees the burst folder — the shell shows a panel and then applies the
        workflow context to it, in that order. Arriving again costs nothing: the
        run is gated on the fingerprint (see :meth:`run`).
        """
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._auto_run)

    def _auto_run(self) -> None:
        """Run for the current folder, quietly doing nothing when there is none."""
        folder = self._folder_edit.text().strip()
        if folder and pathlib.Path(folder).is_dir() and not self._is_running():
            self.run()

    def run(self, *, force: bool = False) -> None:
        """Read the burst folder, compute 2CDE and update the plot.

        The work happens off the GUI thread: it is minutes of correlation over a
        real burst folder, and it now starts on its own when the step is opened,
        so blocking here would freeze the window on arrival.

        A request identical to the result already plotted is skipped — the
        workflow clicks Run on every *Next* and shows this panel on every visit.
        ``force=True`` recomputes regardless.
        """
        folder = self._folder_edit.text().strip()
        if not folder or not pathlib.Path(folder).is_dir():
            self._set_status("Select a valid burstwise analysis folder.")
            return
        fingerprint = self.analysis_fingerprint()
        stamp = pathlib.Path(folder) / "2c4" / "2cde.stamp.json"
        if (
            not force
            and self._df is not None
            and self._result_cache.matches(fingerprint)
            and analysis_cache.is_current(stamp, fingerprint)
        ):
            self._set_status("Unchanged — kept the previous 2CDE result")
            return
        self._running_fingerprint = fingerprint
        self._run.setEnabled(False)
        self._stop.setEnabled(True)
        self._task = ChiSurfProgress.run(
            self, "Reading burst data …", self._analysis_worker,
            args=(folder, self.settings(), fingerprint),
            maximum=0, title="2CDE", owner=self._run,
            on_result=self._analysis_done,
            on_error=self._analysis_failed,
            on_done=self._analysis_over,
        )

    def _analysis_over(self) -> None:
        """Whatever the outcome: Run is available again, Stop is not."""
        self._task = None
        self._run.setEnabled(True)
        self._stop.setEnabled(False)

    def stop(self) -> None:
        """Stop the running computation.

        The per-burst loop checks for this through the progress window, so a stop
        lands within a burst rather than at the end of the folder. Nothing is
        left to reuse — a stopped run computed part of an answer, not an answer.
        """
        task = self._task
        if task is None:
            return
        task.cancel()
        self._result_cache.invalidate()
        self._set_status("Stopping the 2CDE computation …")

    def _is_running(self) -> bool:
        """Whether a computation started by this panel is still going."""
        return self._task is not None and self._task.is_running()

    def _analysis_worker(self, folder, settings, fingerprint, task):
        """Worker: read, compute, write the companion. No GUI here."""
        task.set_range(0, 0)  # reading has no incremental hook
        task.set_text("Reading burst data …")
        # Read only the burst tables (bi4_bur). The default ``b*4*`` glob also
        # matches sibling result folders like ``bv4/`` (and reads BVA's
        # ``bva_settings.json`` inside it), which corrupts the merged table.
        df, tttrs = core.read_burst_analysis(
            pathlib.Path(folder), settings["file_type"], pattern="bi4_bur"
        )
        task.set_range(0, len(df))
        task.set_text("Computing 2CDE …")
        df = core.compute_2cde(
            df, tttrs,
            donor_channels=settings["donor_channels"],
            acceptor_channels=settings["acceptor_channels"],
            donor_micro_time_ranges=[], acceptor_micro_time_ranges=[],
            tau=settings["tau_us"] * 1e-6, kernel=settings["kernel"],
            variant=settings["variant"],
            progress_window=task.progress_window("Computing 2CDE …"),
        )
        # Write the ``2c4/`` companion so the browser and ndXplorer can join the
        # per-burst 2CDE column to the burst table (best-effort; plotting still
        # works if the folder is read-only).
        try:
            core.write_2cde_analysis(df, folder, variant=settings["variant"])
            out = pathlib.Path(folder) / "2c4"
            analysis_cache.write_stamp(
                pathlib.Path(folder) / "2c4" / "2cde.stamp.json", fingerprint,
                params=settings, inputs=self.input_files(),
                outputs=sorted(out.glob("*.2c4")), tool="2cde",
            )
        except Exception as exc:  # pragma: no cover - GUI error path
            logging.getLogger(__name__).warning("Could not write 2c4 companion: %s", exc)
        return df

    def _analysis_done(self, df) -> None:
        """Back on the GUI thread with the 2CDE table: draw it."""
        variant = self._variant.currentText()
        column = core.COLUMN_ALEX_2CDE if variant == "alex" else core.COLUMN_FRET_2CDE
        self._df = df
        if self._running_fingerprint is not None:
            self._result_cache.remember(self._running_fingerprint)
        self._draw(df, column)

    def _analysis_failed(self, exc) -> None:
        """A failed run leaves no result to reuse."""
        self._df = None
        self._result_cache.invalidate()
        self._set_status(f"Error: {exc}")

    def _draw(self, df, column) -> None:
        vals = df[column].to_numpy(dtype=float)
        finite = np.isfinite(vals)
        e = proximity_ratio(df) if proximity_ratio is not None else None
        self._plot.clear()
        if e is not None:
            e = np.asarray(e, dtype=float)
            m = finite & np.isfinite(e)
            self._plot.scatter(e[m], vals[m], size=3, brush=(31, 119, 180, 80),
                               pen=None, symbol="o")
            self._plot.set_labels(bottom="FRET efficiency (proximity ratio)")
        else:
            y, x = np.histogram(vals[finite], bins=40)
            self._plot.line(0.5 * (x[:-1] + x[1:]), y)
            self._plot.set_labels(bottom=column)
        self._set_status(
            f"{column}: {int(finite.sum())} / {len(df)} bursts valid")
