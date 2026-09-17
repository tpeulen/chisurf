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
from qtpy import QtCore, QtWidgets

from chisurf.core.datastore import numeric_column, row_count
from chisurf.core.fio.fluorescence.burst_manifest import source_inputs
from chisurf.core.runtime import analysis_cache
from chisurf.gui import chiplot as cp
from chisurf.gui.progress import ChiSurfProgress
from chisurf.gui.widgets.messages import Msg
from chisurf.gui.widgets.tool_buttons import TOOLBAR_STYLE, action_button, flag_attention
from chisurf.gui.widgets.tools import ChisurfDockTool
from chisurf.plugins.burst.burst_2cde.core import computation as core

try:
    from chisurf.plugins.burst.burst_selection.api.features import proximity_ratio
except Exception:  # pragma: no cover - optional dependency
    proximity_ratio = None

#: Bump in the same change that alters what this tool computes, so results
#: written by the previous version stop reading as current.
ALGORITHM_VERSION = 1


class BurstTwoCdeTool(ChisurfDockTool):
    """Compute and plot FRET-2CDE / ALEX-2CDE for a burstwise analysis folder."""

    name = "Spectroscopy:Single-Molecule:2CDE"

    #: Window geometry stays owned by the manifest-declared window statefulness,
    #: so the base's ``save/restore_window_geometry`` are deliberately not called.
    tool_settings_name = "BurstTwoCdeTool"

    class Information(ChisurfDockTool.Information):
        """Context worth stating about a drop that changed nothing."""

        not_a_folder = Msg("2CDE reads a burst-analysis folder; {} is not one.")

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
        self._run.clicked.connect(self._on_run_clicked)
        # A run whose inputs and settings are unchanged is skipped; this is how
        # the user asks for it anyway (a corrected estimator, a suspect result).
        self._restart = action_button(
            "restart", tooltip="Recompute 2CDE from scratch, even if nothing changed"
        )
        self._restart.clicked.connect(self._on_restart_clicked)
        # The computation starts on its own when this step is opened, so stopping
        # it must be one click away.
        self._stop = action_button("stop", tooltip="Stop the running 2CDE computation")
        self._stop.setEnabled(False)
        self._stop.clicked.connect(self.stop)
        browse = action_button("folder", tooltip="Choose the burst analysis folder")
        browse.clicked.connect(self._browse)
        toolbar.addWidget(self._run)
        toolbar.addWidget(self._restart)
        toolbar.addWidget(self._stop)
        toolbar.addWidget(browse)
        # The ``?`` and **Guide** pair, from the files beside this module. The
        # call also adds Guide on its own once ``guide.json`` is there.
        self.add_toolbar_help(toolbar, resource="help.md", title="2CDE — help")
        layout.addWidget(toolbar)

        # --- folder row -------------------------------------------------------
        row = QtWidgets.QHBoxLayout()
        self._folder_edit = QtWidgets.QLineEdit()
        self._folder_edit.setPlaceholderText("Burstwise analysis folder …")
        row.addWidget(QtWidgets.QLabel("Folder"))
        row.addWidget(self._folder_edit, 1)
        layout.addLayout(row)

        # --- settings form ----------------------------------------------------
        # In one widget so the whole form can be disabled while a run is in
        # flight: the computation is parameterised by a snapshot taken when it
        # started, and a control the user moves meanwhile describes a result
        # nobody asked for.
        self._settings_box = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(self._settings_box)
        form.setContentsMargins(0, 0, 0, 0)
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
        layout.addWidget(self._settings_box)
        # Object names so the guided tour can point at individual controls: this
        # panel is hand-built rather than an AutoForm view, so there is no view
        # spec for a step to name. They are prefixed because ``{"name": …}``
        # matches by *suffix* — a bare "tau" would also find any other widget
        # whose name ends that way.
        for widget, object_name in (
            (self._variant, "twocde_variant"),
            (self._kernel, "twocde_kernel"),
            (self._tau, "twocde_tau"),
            (self._donor, "twocde_donor"),
            (self._acceptor, "twocde_acceptor"),
            (self._file_type, "twocde_file_type"),
        ):
            widget.setObjectName(object_name)

        # --- plot -------------------------------------------------------------
        self._plot = cp.Plot()
        self._plot.setObjectName("twocde_plot")
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
            self._adopt_folder(pathlib.Path(d))

    def _adopt_folder(self, folder: pathlib.Path) -> None:
        """Take *folder* as the analysis folder and compute its 2CDE.

        The one path both ways of naming a folder go through — the Browse dialog
        and a folder dropped on the window — so the two cannot drift over what
        naming a folder means. Naming one is a request for its 2CDE, not for a
        button press.
        """
        self._folder_edit.setText(str(folder))
        self.Information.not_a_folder.clear()
        self._on_run_clicked()

    def on_paths_dropped(self, paths: list[pathlib.Path]) -> None:
        """Adopt the first dropped directory; report anything else.

        2CDE reads a burstwise *analysis folder*, so a dropped file names nothing
        this tool can run on. Reporting it beats writing it into the folder box
        and finding nothing there — the silent-drop failure the same migration
        fixed in BVA.
        """
        for path in paths:
            if path.is_dir():
                self._adopt_folder(path)
                return
        if paths:
            self.Information.not_a_folder(paths[0].name)

    def _channels(self, text: str):
        return [int(x) for x in str(text).split(",") if x.strip()]

    def set_folder(self, folder) -> None:
        """Set the analysis folder (used by the workflow context)."""
        self._folder_edit.setText(str(folder))

    def input_files(self) -> list[pathlib.Path]:
        """Everything this analysis reads: the burst tables and the photons.

        2CDE correlates photon arrival times, so the raw measurements named in
        the folder's manifest are inputs as much as the ``bi4_bur`` tables are —
        a re-exported source with unchanged burst tables changes the answer.
        """
        folder = self._folder_edit.text().strip()
        if not folder:
            return []
        tables = [
            f
            for d in sorted(pathlib.Path(folder).glob("bi4_bur"))
            for f in sorted(d.glob("*"))
            if f.is_file()
        ]
        return tables + list(source_inputs(folder))

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

    def fingerprint_params(self) -> dict:
        """The settings plus the ambient state a photon read depends on."""
        params = dict(self.settings())
        params["_read_context"] = analysis_cache.photon_read_context()
        return params

    def analysis_fingerprint(self) -> str:
        """Fingerprint of the inputs, the settings, the read context and the code."""
        return analysis_cache.fingerprint(
            self.input_files(),
            self.fingerprint_params(),
            extra=analysis_cache.algorithm_tag("2cde", ALGORITHM_VERSION, "tttrlib"),
        )

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
        """Run for the current folder, quietly doing nothing when there is none.

        A computation the user stopped does not start itself again when the step
        is revisited — otherwise Stop would only postpone it until the next
        *Next*. Changing a file or a setting gives a different fingerprint, which
        was never abandoned, so the suppression is exactly as narrow as the stop.
        """
        folder = self._folder_edit.text().strip()
        if not folder or not pathlib.Path(folder).is_dir() or self._is_running():
            return
        if self._result_cache.was_abandoned(self.analysis_fingerprint()):
            self._set_status("Stopped earlier — press Run to compute 2CDE")
            return
        self.run()

    def _on_run_clicked(self) -> None:
        """Run because the user asked, clearing any earlier stop."""
        self._result_cache.allow()
        self.run()

    def _on_restart_clicked(self) -> None:
        """Recompute even though nothing changed."""
        self._result_cache.allow()
        self.run(force=True)

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
            self._set_status("Unchanged — kept the previous 2CDE result (🔁 Restart recomputes it)")
            flag_attention(self._restart, True)
            return
        flag_attention(self._restart, False)
        self._running_fingerprint = fingerprint
        self._run.setEnabled(False)
        self._stop.setEnabled(True)
        self._settings_box.setEnabled(False)
        self._task = ChiSurfProgress.run(
            self,
            "Reading burst data …",
            self._analysis_worker,
            # Inputs and params are resolved here, on the GUI thread: the worker
            # must not read widgets.
            args=(
                folder,
                self.settings(),
                fingerprint,
                self.input_files(),
                self.fingerprint_params(),
            ),
            maximum=0,
            title="2CDE",
            owner=self._run,
            on_result=self._analysis_done,
            on_error=self._analysis_failed,
            on_done=self._analysis_over,
        )

    def _analysis_over(self) -> None:
        """Whatever the outcome: Run is available again, Stop is not."""
        self._task = None
        self._run.setEnabled(True)
        self._stop.setEnabled(False)
        self._settings_box.setEnabled(True)

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
        self._result_cache.abandon(self._running_fingerprint)
        self._set_status("Stopping the 2CDE computation …")

    def _is_running(self) -> bool:
        """Whether a computation started by this panel is still going."""
        # ``is_running`` is a property of the task handle, not a method:
        # calling it raised TypeError on every auto-run, which fast-forward
        # is the first thing to do repeatedly.
        return self._task is not None and self._task.is_running

    def _analysis_worker(self, folder, settings, fingerprint, inputs, params, task):
        """Worker: read, compute, write the companion. No GUI here."""
        task.set_range(0, 0)  # reading has no incremental hook
        task.set_text("Reading burst data …")
        # Read only the burst tables (bi4_bur). The default ``b*4*`` glob also
        # matches sibling result folders like ``bv4/`` (and reads BVA's
        # ``bva_settings.json`` inside it), which corrupts the merged table.
        df, tttrs = core.read_burst_analysis(
            pathlib.Path(folder), settings["file_type"], pattern="bi4_bur"
        )
        task.set_range(0, row_count(df))
        task.set_text("Computing 2CDE …")
        df = core.compute_2cde(
            df,
            tttrs,
            donor_channels=settings["donor_channels"],
            acceptor_channels=settings["acceptor_channels"],
            donor_micro_time_ranges=[],
            acceptor_micro_time_ranges=[],
            tau=settings["tau_us"] * 1e-6,
            kernel=settings["kernel"],
            variant=settings["variant"],
            progress_window=task.progress_window("Computing 2CDE …"),
        )
        # Write the ``2c4/`` companion so the browser and ndX can join the
        # per-burst 2CDE column to the burst table (best-effort; plotting still
        # works if the folder is read-only).
        try:
            core.write_2cde_analysis(df, folder, variant=settings["variant"])
            out = pathlib.Path(folder) / "2c4"
            analysis_cache.write_stamp(
                pathlib.Path(folder) / "2c4" / "2cde.stamp.json",
                fingerprint,
                params=params,
                inputs=inputs,
                outputs=sorted(out.glob("*.2c4")),
                tool="2cde",
            )
        except Exception as exc:  # pragma: no cover - GUI error path
            logging.getLogger(__name__).warning("Could not write 2c4 companion: %s", exc)
        # The variant travels with the frame: it is the only thing that says
        # which of the two columns was computed, and the control it came from
        # may have moved while the folder was being correlated.
        return df, settings["variant"]

    def _analysis_done(self, result) -> None:
        """Back on the GUI thread with the 2CDE table: draw it.

        The column is taken from the variant the *worker* ran with, never from
        the live combo box: a computed frame carries only that one column, so
        re-reading a control the user changed mid-run asks for a column that is
        not there (``KeyError``) or labels the plot with the wrong variant.
        """
        df, variant = result
        column = core.column_for_variant(variant)
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
        vals = numeric_column(df, column)
        finite = np.isfinite(vals)
        e = proximity_ratio(df) if proximity_ratio is not None else None
        self._plot.clear()
        if e is not None:
            e = np.asarray(e, dtype=float)
            m = finite & np.isfinite(e)
            self._plot.scatter(
                e[m], vals[m], size=3, brush=(31, 119, 180, 80), pen=None, symbol="o"
            )
            self._plot.set_labels(bottom="FRET efficiency (proximity ratio)")
        else:
            y, x = np.histogram(vals[finite], bins=40)
            self._plot.line(0.5 * (x[:-1] + x[1:]), y)
            self._plot.set_labels(bottom=column)
        self._set_status(f"{column}: {int(finite.sum())} / {row_count(df)} bursts valid")
