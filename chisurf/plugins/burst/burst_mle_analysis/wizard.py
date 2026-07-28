import typing
import faulthandler

from chisurf.plugins.burst.burst_mle_analysis.utils import \
    LazyTTTRDict, NumpyEncoder, FileListWidget, random_search_hpo
from chisurf.plugins.burst.burst_mle_analysis.interpolate import interpolate_shift
from chisurf.gui import dialogs
from chisurf.gui.progress import ChiSurfProgress

faulthandler.enable(all_threads=True)

from typing import Union

from qtpy import QtWidgets, QtCore
from qtpy.QtWidgets import QFileDialog
import pyqtgraph as pg
import numpy as np
import pandas as pd

import json

import chisurf as cs

from chisurf.gui.autoform import AutoForm
from chisurf.gui.autoform.sections.registry import register_section
from chisurf.gui.widgets.tool_buttons import action_button, flag_attention

#: Bump in the same change that alters what this step computes, so the exported
#: burst fits of the previous version stop reading as current. This is the only
#: step whose reuse survives a restart, so it is the one that would otherwise
#: inherit an old estimator's results across an upgrade without saying so.
ALGORITHM_VERSION = 1


def _mle_progress(widget, text: str, maximum: int) -> ChiSurfProgress:
    """Return a progress handle for a long MLE loop.

    Thin alias for :class:`~chisurf.gui.progress.ChiSurfProgress`, which decides
    where the bar appears from *widget*: the Burst Analysis shell's status bar
    when embedded, a modal dialog when standalone, the log when headless.
    """
    return ChiSurfProgress(widget, text, maximum)


@register_section("host_widget")
def _host_widget_section(model, target=None, **options):
    """AutoForm custom section that hosts an existing widget owned by the model.

    Lets the AutoForm dock shell reuse the wizard's programmatically built pages
    as dock panels (``{"attr": "tab_files"}`` → ``model.tab_files``) instead of
    reimplementing them, so the QTabWidget can be replaced without rewriting the
    fit UI. Returns ``None`` when the attribute is missing so a stale reference
    just drops its panel rather than raising.
    """
    widget = getattr(model, options.get("attr", ""), None)
    if widget is not None:
        # A QTabWidget hides every non-current page; that explicit-hidden flag
        # survives reparenting, so the hosted page would stay blank inside its
        # panel. Clear it so the page shows with the panel.
        widget.setVisible(True)
    return widget
import chisurf.gui.decorators
import chisurf.core.settings
import chisurf.gui.widgets.wizard
from chisurf.gui.widgets.wizard.tttr_channeldefinition import \
    load_detector_setups, save_detector_setups

from pathlib import Path
import tttrlib
from typing import Dict
from chisurf.core.fio import write_vv_vh
from chisurf.core.fluorescence.mle import Fit2x, Fit2xModel, Fit2xSettings

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:
    persist_plugin_state = lambda n: lambda c: c


class _MleParameterRows:
    """The estimator's parameters as rows, for the general ``state_table``.

    Four parallel lists rather than a dictionary of widgets: the fit reads the
    same lists the table edits, so there is nothing to keep in step. Bounds are
    per row because the rows are not interchangeable — a lifetime and an
    anisotropy fraction share a column but not a range.
    """

    def __init__(self):
        """Start with no parameters; the schema fills them in."""
        self.names: list = []
        self.labels: list = []
        self.descriptions: list = []
        self.values: list = []
        self.fixed: list = []
        self.results: list = []
        self.minimums: list = []
        self.maximums: list = []
        #: Called after any edit, so the wizard can refit.
        self.changed = None

    def append(self, name, label, description, value, fixed, minimum, maximum):
        """Add one parameter row."""
        self.names.append(str(name))
        self.labels.append(str(label))
        self.descriptions.append(str(description))
        self.values.append(float(value))
        self.fixed.append(float(bool(fixed)))
        self.results.append(0.0)
        self.minimums.append(float(minimum))
        self.maximums.append(float(maximum))

    def __len__(self):
        """Return the number of parameters."""
        return len(self.names)

    @property
    def n(self) -> int:
        """Number of parameter rows."""
        return len(self.names)

    def index_of(self, name: str) -> int:
        """Return the row of ``name``, or ``-1``."""
        return self.names.index(name) if name in self.names else -1

    def initial_values(self) -> list:
        """Return the starting values, in schema order."""
        return [float(v) for v in self.values]

    def fixed_flags(self) -> list:
        """Return the fix flags as ints, in schema order."""
        return [int(bool(f)) for f in self.fixed]

    def set_results(self, values) -> None:
        """Write the fitted values back into the read-only column."""
        for i, value in enumerate(values):
            if i < len(self.results):
                self.results[i] = float(value)

    def columns(self) -> list:
        """Return the three columns: start it, hold it, read it back."""
        return [
            {"attr": "values", "label": "Initial value", "decimals": 4,
             "minimum_attr": "minimums", "maximum_attr": "maximums",
             "description": "Starting value handed to the estimator."},
            {"attr": "fixed", "label": "F", "kind": "bool",
             "description": "Hold this parameter at its starting value."},
            {"attr": "results", "label": "Fit", "kind": "readonly", "decimals": 4,
             "minimum": -1e9, "maximum": 1e9,
             "description": "Value the estimator returned."},
        ]

    def on_edit(self, *_args) -> None:
        """Notify the wizard that a row changed."""
        if callable(self.changed):
            self.changed()

    def view_spec(self):
        """Return the declared table."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec({
            "sections": [
                {"type": "custom", "key": "state_table",
                 "options": {"size_attr": "n", "row_labels_attr": "labels",
                             "columns_source": "columns"}},
            ]
        })


@persist_plugin_state("burst_mle_analysis")
class MLELifetimeAnalysisWizard(QtWidgets.QMainWindow):
    """
    Note on legacy burst processors:
    Older implementations (process_bursts_old, process_bursts_new, process_bursts_new2, process_bursts_new3)
    were moved to cs.plugins.burst_mle_analysis.wizard_old for documentation/archiving.
    Only process_bursts_new4 is kept here and exposed as `process_bursts`.
    """

    @staticmethod
    def _burst_result_columns(color: str, model: str, param_names) -> list:
        """Per-detector export columns for ``model`` (matches the worker rows).

        ``fit23`` keeps its historical column order so the ``.b?4`` export is
        unchanged; other fit2x models write ``Tau`` (the best lifetime) followed
        by one column per registry free parameter, then the flags.
        """
        if model == "fit23":
            return [
                'Ng-p-all', 'Ng-s-all',
                f'Number of Photons (fit window) ({color})',
                f'2I*  ({color})', f'Tau ({color})', f'gamma ({color})',
                f'r0 ({color})', f'rho ({color})', f'BIFL scatter? ({color})',
                f'2I*: P+2S? ({color})', f'r Scatter ({color})',
                f'r Experimental ({color})',
            ]
        cols = [
            'Ng-p-all', 'Ng-s-all',
            f'Number of Photons (fit window) ({color})',
            f'2I*  ({color})', f'Tau ({color})',
        ]
        cols += [f'{nm} ({color})' for nm in param_names]
        cols += [f'BIFL scatter? ({color})', f'2I*: P+2S? ({color})']
        return cols

    def _save_burst_results_fast(self, result_df: pd.DataFrame) -> None:
        """
        Save burst-fit results grouped by (file stem, detector) with a fast, vectorized path.
        - Builds zero-interleaved rows (zero, data, zero, data, ..., zero) via NumPy.
        - Writes each output once with np.savetxt.
        - Writes channel_settings.json once per output folder.
        - Shows a modal QProgressDialog and supports cancelation.

        Expects columns:
          'First File', 'Detector', and the per-detector numeric columns produced above.
        Uses:
          self.burst_files_list, self.channel_definer, self.channel_settings
        """
        # Collect selected files and map by stem
        files = self.burst_files_list.get_selected_files()
        files_by_stem = {Path(p).stem: Path(p) for p in files}
        selected_stems = set(files_by_stem.keys())

        if result_df is None or result_df.empty:
            self._set_status("No burst-fit results to save.")
            return
        if not selected_stems:
            self._set_status("No files selected to save.")
            return

        # Compute stems once; filter to selected stems; attach "First Stem" without double-mapping
        stems_series = result_df['First File'].map(lambda fn: Path(fn).stem)
        mask = stems_series.isin(selected_stems)
        if not mask.any():
            self._set_status("No burst-fit rows matched the selected files.")
            return
        res = result_df.loc[mask].copy()
        res['First Stem'] = stems_series.loc[mask].values

        # Prepare detector metadata (columns per detector). The column set is
        # model-aware: fit23 keeps its historical layout (byte-for-byte export);
        # other fit2x models write Tau + one column per registry free parameter.
        dets = list(self.channel_definer.detectors.keys())
        model = self.fit_model
        param_names = self._fit_param_names(model)
        det_meta = {}
        for det in dets:
            color = det.lower()
            letter = color[0]
            cols = self._burst_result_columns(color, model, param_names)
            det_meta[det] = (color, letter, cols)

        # Group once by (First Stem, Detector)
        groups = res.groupby(['First Stem', 'Detector'], sort=False)
        total_tasks = len(groups)

        progress = _mle_progress(self, "Saving burst-fit results...", total_tasks)
        progress.setWindowTitle("Saving burst-fit results")
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setAutoClose(True)
        progress.show()

        current_task = 0
        written_dirs = set()
        wrote_settings_for = set()
        written_files: list[Path] = []

        def maybe_pump_ui(k: int) -> None:
            # Throttle UI event processing
            if (k % 25) == 0:
                QtWidgets.QApplication.processEvents()

        for (stem, det), df_g in groups:
            meta = det_meta.get(det)
            if meta is None:
                # Unknown detector label in results; skip gracefully
                current_task += 1
                progress.setValue(current_task)
                maybe_pump_ui(current_task)
                if progress.wasCanceled():
                    progress.close()
                    self._set_status("Save operation was canceled.")
                    return
                continue

            color, letter, cols = meta
            file_path = files_by_stem.get(stem)
            if file_path is None:
                # Group doesn't map to a selected file (filtered above, but guard anyway)
                current_task += 1
                progress.setValue(current_task)
                maybe_pump_ui(current_task)
                if progress.wasCanceled():
                    progress.close()
                    self._set_status("Save operation was canceled.")
                    return
                continue

            out_dir = file_path.parent.parent / f"b{letter}4"
            out_dir.mkdir(parents=True, exist_ok=True)
            written_dirs.add(out_dir.name)

            # Build zero-interleaved matrix efficiently (reindex tolerates a
            # model that did not emit every column — missing → NaN).
            arr = df_g.reindex(columns=cols).to_numpy(dtype=float, copy=False)
            out = np.zeros((arr.shape[0] * 2 + 1, arr.shape[1]), dtype=float)
            out[1::2] = arr  # fill odd rows with data

            out_file = out_dir / f"{stem}.b{letter}4"
            written_files.append(out_file)
            with open(out_file, 'w', newline='') as f:
                f.write('\t'.join(cols) + '\t\n')  # keep trailing tab + newline
                np.savetxt(f, out, delimiter='\t', fmt='%.6f')

            # Write channel settings once per folder
            if out_dir not in wrote_settings_for:
                settings_file = out_dir / 'channel_settings.json'
                with open(settings_file, 'w') as sf:
                    json.dump(self.channel_settings, sf, indent=4, cls=NumpyEncoder)
                wrote_settings_for.add(out_dir)

            current_task += 1
            progress.setValue(current_task)
            maybe_pump_ui(current_task)
            if progress.wasCanceled():
                progress.close()
                self._set_status("Save operation was canceled.")
                return

        progress.close()
        folder_list = ", ".join(sorted(written_dirs)) if written_dirs else "(no data)"
        self._set_status(f"Burst-fit results saved in folders: {folder_list}")
        return written_files

    @property
    def scatter_count_rate(self) -> float:
        """
        Total background count‐rate (in counts per second)
        for the currently selected detector.
        """
        # self.bg is an array of counts/sec per channel bin
        return float(np.sum(self.bg))

    @property
    def irf_threshold_vv(self) -> float:
        return float(self.doubleSpinBox_irf_threshold_vv.value())

    @irf_threshold_vv.setter
    def irf_threshold_vv(
            self,
            v: float
    ):
        self.doubleSpinBox_irf_threshold_vv.setValue(v)
        try:
            if not self.doubleSpinBox_irf_threshold_vv.signalsBlocked():
                self.on_irf_parameters_changed()
        except Exception:
            pass

    @property
    def irf_threshold_vh(self) -> float:
        return float(self.doubleSpinBox_irf_threshold_vh.value())

    @irf_threshold_vh.setter
    def irf_threshold_vh(
            self,
            v: float
    ):
        self.doubleSpinBox_irf_threshold_vh.setValue(v)
        try:
            if not self.doubleSpinBox_irf_threshold_vh.signalsBlocked():
                self.on_irf_parameters_changed()
        except Exception:
            pass

    @property
    def min_photons(self) -> float:
        return float(self.spinBox_min_photons.value())

    @min_photons.setter
    def min_photons(
            self,
            v: int
    ):
        self.spinBox_min_photons.setValue(int(v))

    @property
    def one_for_all_irf(self) -> bool:
        return self.checkBox_irf_one_for_all.isChecked()

    @one_for_all_irf.setter
    def one_for_all_irf(
            self,
            v: bool
    ):
        self.checkBox_irf_one_for_all.setChecked(v)

    @property
    def one_for_all_bg(self) -> bool:
        return self.checkBox_bg_one_for_all.isChecked()

    @one_for_all_bg.setter
    def one_for_all_bg(
            self,
            v: bool
    ):
        self.checkBox_bg_one_for_all.setChecked(v)

    @property
    def p2s_twoIstar(self) -> bool:
        return self.checkBox_2IStar.isChecked()

    @p2s_twoIstar.setter
    def p2s_twoIstar(self, v: bool):
        self.checkBox_2IStar.setChecked(v)

    @property
    def shift(self) -> int:
        """Global shift of the second (ss) decay relative to the first (sp).
        Stored as double in settings JSON and restored as float.
        """
        return int(self.doubleSpinBox_shift.value())

    @shift.setter
    def shift(self, v: int):
        # accept int or float, store/display as float
        self.doubleSpinBox_shift.setValue(int(v))
        try:
            if not self.doubleSpinBox_shift.signalsBlocked():
                self.on_irf_parameters_changed()
        except Exception:
            pass

    @property
    def shift_sp(self) -> float:
        """Sub-channel (fractional) shift to apply to the sp IRF."""
        return float(self.doubleSpinBox_shift_sp.value())

    @shift_sp.setter
    def shift_sp(self, v: float):
        self.doubleSpinBox_shift_sp.setValue(float(v))
        try:
            if not self.doubleSpinBox_shift_sp.signalsBlocked():
                self.on_irf_parameters_changed()
        except Exception:
            pass

    @property
    def shift_ss(self) -> float:
        """Sub-channel (fractional) shift to apply to the ss IRF."""
        return float(self.doubleSpinBox_shift_ss.value())

    @shift_ss.setter
    def shift_ss(self, v: float):
        self.doubleSpinBox_shift_ss.setValue(float(v))
        try:
            if not self.doubleSpinBox_shift_ss.signalsBlocked():
                self.on_irf_parameters_changed()
        except Exception:
            pass

    @property
    def irf_start(self) -> int:
        """Start index for IRF windowing. If < 0, do not zero the beginning."""
        return int(self.spinBox_irf_start.value())

    @irf_start.setter
    def irf_start(self, v: int):
        self.spinBox_irf_start.setValue(int(v))
        try:
            if not self.spinBox_irf_start.signalsBlocked():
                self.on_irf_parameters_changed()
        except Exception:
            pass

    @property
    def irf_stop(self) -> int:
        """Stop index for IRF windowing. If < 0, do not zero the end."""
        return int(self.spinBox_irf_stop.value())

    @irf_stop.setter
    def irf_stop(self, v: int):
        self.spinBox_irf_stop.setValue(int(v))
        try:
            if not self.spinBox_irf_stop.signalsBlocked():
                self.on_irf_parameters_changed()
        except Exception:
            pass

    @property
    def irf(self) -> np.ndarray:
        det = self.current_detector
        arr = self.irf_np.get(det)
        if arr is None:
            # fallback default IRF
            length = max(2, (self.micro_time_range[1] // self.micro_time_binning) * 2)
            arr = np.zeros(length, dtype=np.float64)
            arr[0] = 1.0
            arr[length // 2] = 1.0

        # split into sp / ss halves
        half = len(arr) // 2
        sp = arr[:half].astype(np.float64)
        ss = arr[half:].astype(np.float64)

        # 1) Global integer shift of VH (second half)
        # shift is stored as float in settings; np.roll requires int steps
        if float(self.shift) != 0.0:
            ss = np.roll(ss, int(round(self.shift)))

        # 2) Individual sub-bin IRF shifts
        sp = interpolate_shift(sp, self.shift_sp)
        ss = interpolate_shift(ss, self.shift_ss)

        # 3) IRF range/windowing (zero outside of [start, stop])
        try:
            start = int(self.irf_start)
            stop = int(self.irf_stop)

            if start >= 0:
                sp[:max(0, start)] = 0
                ss[:max(0, start)] = 0
            if stop >= 0 and stop + 1 < sp.size:
                sp[stop + 1:] = 0
            if stop >= 0 and stop + 1 < ss.size:
                ss[stop + 1:] = 0
        except Exception:
            # be permissive if widgets not yet constructed
            pass

        # 4) IRF thresholding (background correction)
        try:
            th_vv = float(self.irf_threshold_vv)
            th_vh = float(self.irf_threshold_vh)
            if th_vv > 0 and sp.size and sp.max() > 0:
                sp[sp < th_vv * sp.max()] = 0
            if th_vh > 0 and ss.size and ss.max() > 0:
                ss[ss < th_vh * ss.max()] = 0
        except Exception:
            pass

        # reassemble after per-channel processing
        irf = np.hstack([sp, ss])
        return irf

    @property
    def bg(self) -> np.ndarray:
        """
        Return the background array for the currently selected detector.
        Apply VH integer shift (doubleSpinBox_shift) BEFORE any other operation.
        If none was loaded, return a zeros default matching the IRF length.
        """
        det = self.current_detector
        arr = self.bg_np.get(det)
        if arr is None:
            # match IRF length
            return np.zeros_like(self.irf)
        # ensure float64 copy
        arr = np.asarray(arr, dtype=np.float64)
        half = len(arr) // 2
        vv = arr[:half].copy()
        vh = arr[half:].copy()
        # IMPORTANT: apply integer shift to VH before anything else
        if self.shift != 0:
            vh = np.roll(vh, self.shift)
        return np.hstack([vv, vh])

    @property
    def BIFL_scatter(self) -> bool:
        return self.checkBox_BIFL_scatter.isChecked()

    @BIFL_scatter.setter
    def BIFL_scatter(self, v: bool):
        self.checkBox_BIFL_scatter.setChecked(v)

    @property
    def fit(self):
        if self._fit is None:
            self._fit = self.create_fit_instance()
        return self._fit

    @property
    def save_vv_vhs(self):
        return self.checkBox_save_vv_vhs.isChecked()

    @property
    def fix_tau(self) -> bool:
        """Whether the tau parameter is fixed during fitting."""
        return self.checkBox_fix_tau.isChecked()

    @fix_tau.setter
    def fix_tau(self, v: bool):
        self.checkBox_fix_tau.setChecked(v)

    @property
    def fix_gamma(self) -> bool:
        """Whether the gamma parameter is fixed during fitting."""
        return self.checkBox_fix_gamma.isChecked()

    @fix_gamma.setter
    def fix_gamma(self, v: bool):
        self.checkBox_fix_gamma.setChecked(v)

    @property
    def fix_r0(self) -> bool:
        """Whether the r0 parameter is fixed during fitting."""
        return self.checkBox_fix_r0.isChecked()

    @fix_r0.setter
    def fix_r0(self, v: bool):
        self.checkBox_fix_r0.setChecked(v)

    @property
    def fix_rho(self) -> bool:
        """Whether the rho parameter is fixed during fitting."""
        return self.checkBox_fix_rho.isChecked()

    @fix_rho.setter
    def fix_rho(self, v: bool):
        self.checkBox_fix_rho.setChecked(v)

    @property
    def current_file_idx(self) -> int:
        """Current file index in the burst files list."""
        return self.spinBox_current_file_idx.value()

    @current_file_idx.setter
    def current_file_idx(self, v: int):
        self.spinBox_current_file_idx.setValue(v)

    @property
    def tau(self) -> float:
        """Fluorescence lifetime (tau) in nanoseconds."""
        return self.doubleSpinBox_tau.value()

    @tau.setter
    def tau(self, v: float):
        self.doubleSpinBox_tau.setValue(v)
        try:
            if not self.doubleSpinBox_tau.signalsBlocked():
                self.update_variable_fit_parameters()
        except Exception:
            pass

    @property
    def gamma(self) -> float:
        """Gamma parameter for fitting."""
        return self.doubleSpinBox_gamma.value()

    @gamma.setter
    def gamma(self, v: float):
        self.doubleSpinBox_gamma.setValue(v)
        try:
            if not self.doubleSpinBox_gamma.signalsBlocked():
                self.update_variable_fit_parameters()
        except Exception:
            pass

    @property
    def r0(self) -> float:
        """Fundamental anisotropy (r0) parameter."""
        return self.doubleSpinBox_r0.value()

    @r0.setter
    def r0(self, v: float):
        self.doubleSpinBox_r0.setValue(v)
        try:
            if not self.doubleSpinBox_r0.signalsBlocked():
                self.update_variable_fit_parameters()
        except Exception:
            pass

    @property
    def rho(self) -> float:
        """Rotational correlation time (rho) in nanoseconds."""
        return self.doubleSpinBox_rho.value()

    @rho.setter
    def rho(self, v: float):
        self.doubleSpinBox_rho.setValue(v)
        try:
            if not self.doubleSpinBox_rho.signalsBlocked():
                self.update_variable_fit_parameters()
        except Exception:
            pass

    @property
    def scatter_countrate(self) -> float:
        """Scatter count rate in Hz."""
        return self.doubleSpinBox_scatter_Countrate.value()

    @scatter_countrate.setter
    def scatter_countrate(self, v: float):
        self.doubleSpinBox_scatter_Countrate.setValue(v)

    @property
    def tau_result(self) -> float:
        """Fitted fluorescence lifetime (tau) result in nanoseconds."""
        return self.doubleSpinBox_tau_result.value()

    @tau_result.setter
    def tau_result(self, v: float):
        self.doubleSpinBox_tau_result.setValue(v)

    @property
    def gamma_result(self) -> float:
        """Fitted gamma parameter result."""
        return self.doubleSpinBox_gamma_result.value()

    @gamma_result.setter
    def gamma_result(self, v: float):
        self.doubleSpinBox_gamma_result.setValue(v)

    @property
    def r0_result(self) -> float:
        """Fitted fundamental anisotropy (r0) result."""
        return self.doubleSpinBox_r0_result.value()

    @r0_result.setter
    def r0_result(self, v: float):
        self.doubleSpinBox_r0_result.setValue(v)

    @property
    def rho_result(self) -> float:
        """Fitted rotational correlation time (rho) result in nanoseconds."""
        return self.doubleSpinBox_rho_result.value()

    @rho_result.setter
    def rho_result(self, v: float):
        self.doubleSpinBox_rho_result.setValue(v)

    @property
    def twoIstar_result(self) -> float:
        """Fitted 2I* result."""
        return self.doubleSpinBox_twoIstar_result.value()

    @twoIstar_result.setter
    def twoIstar_result(self, v: float):
        self.doubleSpinBox_twoIstar_result.setValue(v)

    @property
    def r_scatter_result(self) -> float:
        """Fitted r scatter result."""
        return self.doubleSpinBox_r_scatter_result.value()

    @r_scatter_result.setter
    def r_scatter_result(self, v: float):
        self.doubleSpinBox_r_scatter_result.setValue(v)

    @property
    def r_exp_result(self) -> float:
        """Fitted r experimental result."""
        return self.doubleSpinBox_r_exp_result.value()

    @r_exp_result.setter
    def r_exp_result(self, v: float):
        self.doubleSpinBox_r_exp_result.setValue(v)

    @property
    def irf_select(self) -> str:
        """Selected detector for IRF."""
        return self.comboBox_irf_select.currentText()

    @irf_select.setter
    def irf_select(self, v: str):
        index = self.comboBox_irf_select.findText(v)
        if index >= 0:
            self.comboBox_irf_select.setCurrentIndex(index)

    @property
    def background_select(self) -> str:
        """Selected detector for background."""
        return self.comboBox_background_select.currentText()

    @background_select.setter
    def background_select(self, v: str):
        index = self.comboBox_background_select.findText(v)
        if index >= 0:
            self.comboBox_background_select.setCurrentIndex(index)

    @property
    def total_burst_time_seconds(self) -> float:
        """
        Total integrated burst duration, in seconds.
        Returns 0.0 if no burst DataFrame is loaded or if the column is missing.
        """
        if self.df_bursts is None or 'Duration (ms)' not in self.df_bursts:
            return 0.0
        # sum durations (ms) and convert to seconds
        total_ms = self.df_bursts['Duration (ms)'].sum()
        return total_ms / 1000.0

    def _header_time_ns(self):
        """(dt_ns, period_ns) from the current file's TTTR header, or ``None``.

        The MLE fit needs the micro-time channel width and the excitation period
        in the *same* unit as the lifetime it reports (nanoseconds). The
        channel-definition page cannot supply that: its micro-time field is
        picoseconds (it feeds the g-factor calculator as ``..._ps``) while its
        macro-time field is nanoseconds, and neither is populated from the file
        header — so ``Fit23`` was handed ``dt`` and ``period`` that were both
        defaulted (50) and in mismatched units, which left the reported lifetime
        in arbitrary units (a decay that visibly falls in ~1 ns was labelled
        "5 ns"). The header is the single source of truth: the channel width is
        ``micro_time_resolution`` and one excitation period is the full TAC range
        ``number_of_micro_time_channels * micro_time_resolution`` (both in
        seconds), scaled to nanoseconds and to the current binning.
        """
        tttr = self._current_tttr()
        if tttr is None:
            return None
        try:
            h = tttr.header
            micro_s = float(h.micro_time_resolution)
            n_chan = float(h.number_of_micro_time_channels)
        except Exception:
            return None
        if not (micro_s > 0.0 and n_chan > 0.0):
            return None
        binning = max(1, int(self.micro_time_binning))
        dt_ns = micro_s * 1e9 * binning
        # The period is the full TAC range and is independent of binning
        # (n_binned * dt_binned == n_chan * micro_s).
        period_ns = n_chan * micro_s * 1e9
        return dt_ns, period_ns

    @property
    def dt_effective(self):
        header = self._header_time_ns()
        if header is not None:
            return header[0]
        return self.channel_definer.effective_micro_time_resolution

    @property
    def n_bursts(self) -> int:
        """Number of bursts currently loaded."""
        return len(self.df_bursts) if self.df_bursts is not None else 0

    @property
    def detector_channels(self):
        parallel = self.channel_definer.detectors[self.current_detector]["chs"][::2]
        perp = self.channel_definer.detectors[self.current_detector]["chs"][1::2]
        return parallel, perp

    @property
    def micro_time_range(self):
        """
        Returns [start_bin, stop_bin] as set by the spin boxes.
        """
        return [
            self.spinBox_micro_time_start.value(),
            self.spinBox_micro_time_stop.value()
        ]

    @micro_time_range.setter
    def micro_time_range(self, value):
        start, stop = value
        self.spinBox_micro_time_start.setValue(start)
        self.spinBox_micro_time_stop.setValue(stop)
        # self.spinBox_micro_time_start.setMinimum(start)
        # self.spinBox_micro_time_start.setMaximum(stop)
        # self.spinBox_micro_time_stop.setMinimum(start)
        # self.spinBox_micro_time_stop.setMaximum(stop)

    @property
    def micro_time_start(self) -> int:
        """Start bin of the micro-time window."""
        return int(self.spinBox_micro_time_start.value())

    @micro_time_start.setter
    def micro_time_start(self, v: int):
        self.spinBox_micro_time_start.setValue(int(v))

    @property
    def micro_time_stop(self) -> int:
        """Stop bin (exclusive) of the micro-time window."""
        return int(self.spinBox_micro_time_stop.value())

    @micro_time_stop.setter
    def micro_time_stop(self, v: int):
        self.spinBox_micro_time_stop.setValue(int(v))

    @property
    def micro_time_binning(self):
        return self.channel_definer.tttr_reading['micro_time_binning']

    @property
    def tttr_file_type(self):
        # Use the filetype property from DetectorWizardPage
        txt = self.channel_definer.filetype
        if txt is None:  # This means "Auto" was selected in DetectorWizardPage
            # Try to use the first tttr path from the LazyTTTRDict
            if self._tttr_paths:
                # Get the first tttr path from the LazyTTTRDict
                first_path = next(iter(self._tttr_paths.values()))
                if first_path:
                    file_type_int = tttrlib.inferTTTRFileType(str(first_path))
                    return file_type_int

            # Fall back to current_filename if no tttr paths are available
            filename = self.current_filename
            if filename:
                file_type_int = tttrlib.inferTTTRFileType(filename)
                return file_type_int
            return None
        return txt

    @property
    def fit_parameters(self):
        # fit23 keeps its authored spin boxes; other models read the
        # registry-driven editor built for them.
        if self.fit_model != "fit23" and getattr(self, "_dyn_params", None):
            rows = self._dyn_params
            return np.array(rows.initial_values()), np.array(rows.fixed_flags())
        tau = self.tau
        gamma = self.gamma
        r0 = self.r0
        rho = self.rho
        fixed = [
            int(self.fix_tau),
            int(self.fix_gamma),
            int(self.fix_r0),
            int(self.fix_rho),
        ]
        return np.array([tau, gamma, r0, rho]), np.array(fixed)

    @property
    def current_filename(self) -> str:
        return self.lineEdit_current_filename.text()

    @current_filename.setter
    def current_filename(self, value: str):
        self.lineEdit_current_filename.setText(value)

    @property
    def current_detector(self):
        return self.comboBox_window.currentText()

    @property
    def excitation_period(self) -> float:
        header = self._header_time_ns()
        if header is not None:
            return header[1]
        return float(self.channel_definer.excitation_period)

    @property
    def g_factor(self) -> float:
        """
        Returns the g-factor value for the current detector.
        If the current detector doesn't have a g_factor value, returns the default value (1).
        """
        try:
            return float(self.channel_definer.detectors[self.current_detector].get("g_factor", 1.0))
        except (KeyError, AttributeError):
            return 1.0

    @g_factor.setter
    def g_factor(
            self,
            v: float
    ):
        """
        Sets the g-factor value for the current detector.
        Updates the detector data structure directly.
        """
        try:
            # Get the current detector data
            detector = self.current_detector
            if detector in self.channel_definer.detectors:
                # Update the g_factor value in the data structure
                self.channel_definer.detectors[detector]["g_factor"] = float(v)
                # Update the UI
                row = self._find_detector_row(detector)
                if row >= 0:
                    self.channel_definer.detectors_form.cellWidget(row, 3).setText(str(v))
                self._set_polarization_display("doubleSpinBox_g_factor", v)
        except (KeyError, AttributeError):
            pass

    @property
    def l1(self) -> float:
        """
        Returns the l1 value for the current detector.
        If the current detector doesn't have an l1 value, returns the default value (0).
        """
        try:
            return float(self.channel_definer.detectors[self.current_detector].get("l1", 0.0))
        except (KeyError, AttributeError):
            return 0.0

    @l1.setter
    def l1(
            self,
            v: float
    ):
        """
        Sets the l1 value for the current detector.
        Updates the detector data structure directly.
        """
        try:
            # Get the current detector data
            detector = self.current_detector
            if detector in self.channel_definer.detectors:
                # Update the l1 value in the data structure
                self.channel_definer.detectors[detector]["l1"] = float(v)
                # Update the UI
                row = self._find_detector_row(detector)
                if row >= 0:
                    self.channel_definer.detectors_form.cellWidget(row, 4).setText(str(v))
                self._set_polarization_display("doubleSpinBox_l1", v)
        except (KeyError, AttributeError):
            pass

    @property
    def l2(self) -> float:
        """
        Returns the l2 value for the current detector.
        If the current detector doesn't have an l2 value, returns the default value (0).
        """
        try:
            return float(self.channel_definer.detectors[self.current_detector].get("l2", 0.0))
        except (KeyError, AttributeError):
            return 0.0

    @l2.setter
    def l2(
            self,
            v: float
    ):
        """
        Sets the l2 value for the current detector.
        Updates the detector data structure directly.
        """
        try:
            # Get the current detector data
            detector = self.current_detector
            if detector in self.channel_definer.detectors:
                # Update the l2 value in the data structure
                self.channel_definer.detectors[detector]["l2"] = float(v)
                # Update the UI
                row = self._find_detector_row(detector)
                if row >= 0:
                    self.channel_definer.detectors_form.cellWidget(row, 5).setText(str(v))
                self._set_polarization_display("doubleSpinBox_l2", v)
        except (KeyError, AttributeError):
            pass

    def _ensure_channel_state(self, det: str):
        """
        Ensure self.channel_settings[det] exists and contains all required
        per-detector settings. If a key is missing, initialize it from the
        current UI/properties at the time of the call. This guarantees that
        later code can safely use st['key'] without fallbacks.
        """
        st = self.channel_settings.get(det, {})
        # micro-time
        if 'micro_time_start' not in st or 'micro_time_stop' not in st:
            sb, eb = self.micro_time_range
            st['micro_time_start'] = int(sb)
            st['micro_time_stop'] = int(eb)
        if 'micro_time_binning' not in st:
            st['micro_time_binning'] = int(self.micro_time_binning)
        # thresholds and shifts
        st.setdefault('irf_threshold_vv', float(getattr(self, 'irf_threshold_vv', 0.0)))
        st.setdefault('irf_threshold_vh', float(getattr(self, 'irf_threshold_vh', 0.0)))
        st.setdefault('shift', int(getattr(self, 'shift', 0)))
        st.setdefault('shift_sp', float(getattr(self, 'shift_sp', 0.0)))
        st.setdefault('shift_ss', float(getattr(self, 'shift_ss', 0.0)))
        # timing
        st.setdefault('dt', float(self.dt_effective))
        st.setdefault('excitation_period', float(self.excitation_period))
        # model parameters — the polarisation corrections belong to THIS detector
        # (``det``), so seed them from its own definition, not from ``self.g_factor``
        # (the *current* detector). Seeding from the current detector cached one
        # detector's g/l1/l2 onto another, and _apply_ui_state then wrote the wrong
        # values back into channel_definer.detectors on the next switch.
        try:
            det_def = self.channel_definer.detectors.get(det, {})
        except AttributeError:
            det_def = {}
        st.setdefault('g_factor', float(det_def.get('g_factor', 1.0)))
        st.setdefault('l1', float(det_def.get('l1', 0.0)))
        st.setdefault('l2', float(det_def.get('l2', 0.0)))
        # initial guesses and fixed flags
        x0, fixed = self.fit_parameters
        st.setdefault('initial_x0', np.array(x0))
        st.setdefault('fixed_flags', np.array(fixed))
        # options and counts
        st.setdefault('p2s_twoIstar', bool(getattr(self, 'p2s_twoIstar', False)))
        st.setdefault('BIFL_scatter', bool(getattr(self, 'BIFL_scatter', False)))
        st.setdefault('min_photons', int(getattr(self, 'min_photons', 0)))
        # IRF/BG arrays are NOT stored here. irf_np[det]/bg_np[det] are the single
        # source of truth for the raw per-detector patterns (they persist across
        # detector switches); the .irf/.bg properties apply shift/window/threshold
        # on read. Round-tripping the *processed* arrays through channel_settings
        # re-applied that processing every switch and steadily corrupted them.
        self.channel_settings[det] = st
        return st

    def _init_channels_from_wizard(self):
        """
        Called whenever the DetectorWizardPage has a new set of detectors;
        populates IRF/BG selectors, window combobox, and per-channel state.
        """
        dets = list(self.channel_definer.detectors.keys())
        cs.logging.info('_init_channels_from_wizard')
        if not dets:
            # detectorsChanged fires transiently with an empty set while the
            # detector table is being (re)loaded; nothing to build yet, and the
            # code below indexes dets[0].
            return
        # reset our per-channel state cache and pre-initialize per-detector dicts
        self.channel_settings.clear()
        for d in dets:
            self.channel_settings.setdefault(d, {})
            self.irf_np.setdefault(d, np.array([]))
            self.bg_np.setdefault(d, np.array([]))
            self._ensure_channel_state(d)

        # Repopulate the detector combobox with signals BLOCKED. Otherwise
        # clear()/setCurrentIndex fire currentTextChanged("") mid-transition,
        # which runs _on_channel_changed("") -> _apply_ui_state("") and writes a
        # spurious empty-named detector into channel_settings/irf_np/bg_np. That
        # left the real current detector without an IRF, so update_fit bailed
        # (det not in irf_np) — a stuck fit and blank plots. The real switch is
        # done once, explicitly, at the end via _on_channel_changed(dets[0]).
        self.block_widget_signals([self.comboBox_window])
        self.comboBox_window.clear()
        self.comboBox_window.addItems(dets)
        self.comboBox_window.setCurrentIndex(0)
        self.unblock_widget_signals([self.comboBox_window])
        self._switch_filewidget(self.irf_file_widgets, dets[0])
        self._switch_filewidget(self.bg_file_widgets, dets[0])

        for cb in (self.comboBox_irf_select, self.comboBox_background_select):
            cb.clear()
            cb.addItems(dets)
            cb.setCurrentIndex(0)

        # Drop any empty-named detector that slipped into the per-detector state
        # (from an earlier spurious "" channel change), so it can never shadow a
        # real detector or be fitted.
        for stale in ("", None):
            self.channel_settings.pop(stale, None)
            self.irf_np.pop(stale, None)
            self.bg_np.pop(stale, None)

        # finally, apply settings for the initially selected detector including any saved MLE settings
        if dets:
            self._on_channel_changed(dets[0])

    def _on_tab_changed(self, index: int):
        if self.tabWidget.widget(index) is self.tab_parameters:
            current_idx = self.spinBox_current_file_idx.value()
            self.spinBox_current_file_idx.blockSignals(True)
            self.spinBox_current_file_idx.setValue(current_idx)
            self.spinBox_current_file_idx.blockSignals(False)
            self.update_current_file(current_idx)
            self.update_bg_files()

    # ── AutoForm dock shell (replaces the QTabWidget) ──────────────────────
    #: Maps each source tab (by widget attribute) to the foldable panels it
    #: becomes. A tab may fan out into several panels: the Files tab's three
    #: group boxes each get their own foldable dock, kept separate from the
    #: Burst-MLE fit panel, so file selection and fitting fold independently.
    #: The conversion keeps only tabs still present, so the embedded workflow
    #: (which drops "Detector Definition") and the standalone wizard both get the
    #: right panels with no special case.
    _DOCK_LAYOUT = (
        ("tab_detector", (("tab_detector", "Detector Definition"),)),
        ("tab_files", (
            ("groupBox_burst_files", "Burst Files"),
            ("groupBox_irf_files", "IRF Files"),
            ("groupBox_bg_files", "Background Files"),
        )),
        ("tab_parameters", (("tab_parameters", "Burst-MLE"),)),
    )

    def view_spec(self):
        """AutoForm view: one draggable ChiSurf dock per wizard page.

        Each page (the three file inputs and the Burst-MLE workspace, plus the
        standalone Detector Definition) becomes its own draggable/floatable dock
        panel, so file selection and fitting can be torn apart or re-tabbed
        freely. This is safe now that the workflow embeds the wizard's *central
        widget* rather than the QMainWindow — the dock area's earlier show-time
        click-blocking was a QMainWindow-as-child artefact, not the dock itself.
        """
        from chisurf.core.dataspec import CustomSection, DockAreaSection, ModelView

        panels = tuple(
            CustomSection(key="host_widget", title=title, options={"attr": attr})
            for attr, title in getattr(self, "_dock_pages", ())
        )
        return ModelView(
            sections=(
                DockAreaSection(title="MLE", sections=panels, persist="burst_mle_dock"),
            )
        )

    def _convert_tabs_to_dock_shell(self):
        """Replace the QTabWidget with an AutoForm dock area of the same pages.

        Deferred (via singleShot) so it runs after the embedded workflow has
        removed the "Detector Definition" tab: whatever tabs remain become dock
        panels. The pages are reused as-is (see ``host_widget``), so no fit UI is
        rewritten — this only swaps the un-clickable tab bar for draggable docks.
        """
        tw = getattr(self, "tabWidget", None)
        if tw is None or getattr(self, "_dock_shell_built", False):
            return
        # Each remaining tab fans out into its configured panels (the Files tab
        # into one foldable per file group box).
        known = {}
        for tab_attr, panels in self._DOCK_LAYOUT:
            tab_widget = getattr(self, tab_attr, None)
            if tab_widget is not None:
                known[id(tab_widget)] = panels
        pages = []
        for i in range(tw.count()):
            panels = known.get(id(tw.widget(i)))
            if not panels:
                continue
            for attr, title in panels:
                if getattr(self, attr, None) is not None:
                    pages.append((attr, title))
        if getattr(self, "_embedded", False):
            # In the burst-analysis workflow the file inputs are supplied upstream
            # (Data Selection burst files; IRF & Background -> Send to MLE), so the
            # MLE panel's own file-drop docks are duplicates. Show only the fit.
            _duplicate = {"tab_files", "groupBox_burst_files",
                          "groupBox_irf_files", "groupBox_bg_files"}
            pages = [(attr, title) for attr, title in pages if attr not in _duplicate]
        if not pages:
            return
        self._dock_pages = pages
        # Let each hosted widget fill its dock (the Burst-MLE workspace holds the
        # plots). The file group boxes already carry their own title border, so
        # the foldable header would duplicate it — drop the inner title.
        file_boxes = {"groupBox_burst_files", "groupBox_irf_files", "groupBox_bg_files"}
        for attr, _title in pages:
            page = getattr(self, attr, None)
            if page is None:
                continue
            page.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
            )
            if attr in file_boxes and hasattr(page, "setTitle"):
                page.setTitle("")

        # Building the form reparents the pages into the dock panels, emptying
        # the tab widget, which is then removed from the layout and replaced by
        # the form (the dock area fills the space itself — no scroll wrapper).
        form = AutoForm(self)
        # A QTabWidget *explicitly* hides every page that is not the current one,
        # and an explicit hide survives reparenting. Inside a dock that flag is
        # never cleared -- the dock's own stack shows its content wrapper, but the
        # page inside it stays hidden -- so every page other than the tab that
        # happened to be current rendered as an empty dock: the whole Burst-MLE
        # workspace (plots, fit controls) was blank, and in the burst-analysis
        # workflow, where the file docks are dropped, the entire panel was blank.
        # Visibility is the dock area's job from here on, so hand the pages over
        # unhidden; which dock is on top is still decided by its tab bar.
        for attr, _title in pages:
            page = getattr(self, attr, None)
            if page is not None:
                page.show()
        parent = tw.parentWidget()
        layout = parent.layout() if parent is not None else None
        if layout is not None:
            index = layout.indexOf(tw)
            layout.removeWidget(tw)
            layout.insertWidget(max(0, index), form)
        tw.hide()
        tw.setParent(None)
        self._dock_form = form
        self._dock_shell_built = True

    def _update_max_bins_from_tttr(self):
        try:
            tttr = next(iter(self.tttrs.values()))
            total_channels = tttr.header.number_of_micro_time_channels
        except Exception:
            return

        max_bins: int = int(total_channels // self.micro_time_binning)
        # Only update the allowed maximums; do not overwrite current values or minimums
        try:
            self.spinBox_micro_time_start.blockSignals(True)
            self.spinBox_micro_time_stop.blockSignals(True)
            # Only set maxima based on TTTR info
            self.spinBox_micro_time_start.setMaximum(max(0, max_bins - 1))
            self.spinBox_micro_time_stop.setMaximum(max_bins)
        finally:
            self.spinBox_micro_time_start.blockSignals(False)
            self.spinBox_micro_time_stop.blockSignals(False)

        # Keep a separate "full" range for internal histogram building
        self.full_range = (0, max_bins)

    def _capture_current_ui_state(self):
        cs.logging.info("_capture_current_ui_state")
        x0, fixed = self.fit_parameters
        start_bin, stop_bin = self.micro_time_range
        d = {
            'micro_time_start': start_bin,
            'micro_time_stop': stop_bin,
            'micro_time_binning': self.micro_time_binning,
            'irf_threshold_vv': self.irf_threshold_vv,
            'irf_threshold_vh': self.irf_threshold_vh,
            'shift': self.shift,
            'shift_sp': self.shift_sp,
            'shift_ss': self.shift_ss,
            'dt': self.dt_effective,
            'excitation_period': self.excitation_period,
            'g_factor': self.g_factor,
            'l1': self.l1,
            'l2': self.l2,
            # IRF/BG are not captured — they live in irf_np/bg_np (single source
            # of truth). Capturing the processed .irf/.bg here and restoring them
            # as raw re-applied shift/threshold every switch and corrupted them.
            'initial_x0': np.array(x0),
            'fixed_flags': fixed.astype(int),
            'p2s_twoIstar': self.p2s_twoIstar,
            'BIFL_scatter': self.BIFL_scatter,
            'min_photons': self.min_photons
        }
        return d

    def _apply_ui_state(self, state):
        """Push a saved state back into the widgets."""
        # — micro-time controls —
        self.micro_time_range = (state['micro_time_start'], state['micro_time_stop'])

        # Update micro_time_binning in DetectorWizardPage instead of spinBox
        micro_time_binning = state['micro_time_binning']
        self.channel_definer.micro_binning_combo.setCurrentText(str(micro_time_binning))

        # — IRF threshold & shifts —
        self.irf_threshold_vv = state['irf_threshold_vv']
        self.irf_threshold_vh = state['irf_threshold_vh']
        self.shift = state['shift']
        self.shift_sp = state['shift_sp']
        self.shift_ss = state['shift_ss']

        self.min_photons = state['min_photons']
        self.p2s_twoIstar = state['p2s_twoIstar']
        self.BIFL_scatter = state['BIFL_scatter']

        # G factor / l1 / l2 are NOT restored here. They are per-detector
        # calibration constants owned by the detector definition (channel_definer)
        # and are read from it live via the g_factor/l1/l2 getters; writing them
        # back through the setters (which poke the definition's table cells by
        # row/column) mis-targeted the cells and swapped one detector's l1/l2 onto
        # another on repeated switches. The fit-page fields display them read-only
        # (refreshed by _sync_polarization_widgets), so nothing needs restoring.

        # — initial‐guess & fixed flags —
        x0 = state['initial_x0']
        fixed = state['fixed_flags']
        self.tau = x0[0]
        self.gamma = x0[1]
        self.r0 = x0[2]
        self.rho = x0[3]

        self.fix_tau = bool(fixed[0])
        self.fix_gamma = bool(fixed[1])
        self.fix_r0 = bool(fixed[2])
        self.fix_rho = bool(fixed[3])
        # IRF/BG are NOT restored here — irf_np[det]/bg_np[det] already hold this
        # detector's raw pattern (see _ensure_channel_state). Writing them back
        # from a captured, already-processed copy corrupted them each switch.

    def _on_channel_changed(self, new_detector):
        old = getattr(self, '_last_detector', None)
        if old is not None:
            # save old‐channel UI state
            self.channel_settings[old] = self._capture_current_ui_state()

        # pull in the channel‐definer info for the new detector
        info = self.channel_definer.detectors.get(new_detector, {})

        # set the spinboxes to any channel‐specific micro‐time defaults
        ranges = info.get('micro_time_ranges', [])
        if ranges:
            raw_start, raw_stop = ranges[0]
            bin_start = raw_start // self.micro_time_binning
            bin_stop = raw_stop // self.micro_time_binning
            # block signals so we don't trigger micro-time‐range callbacks
            widgets = (self.spinBox_micro_time_start, self.spinBox_micro_time_stop)
            self.block_widget_signals(widgets)
            self.micro_time_range = (bin_start, bin_stop)
            self.unblock_widget_signals(widgets)

        # ensure per-detector dict exists and complete to avoid KeyError later when saving arrays
        self._ensure_channel_state(new_detector)

        # restore any previously‐saved UI state for this detector, but only if it's complete
        state = self.channel_settings.get(new_detector)
        required_keys = (
            'micro_time_start', 'micro_time_stop', 'initial_x0', 'fixed_flags',
            'g_factor', 'l1', 'l2',
        )
        if isinstance(state, dict) and all(k in state for k in required_keys):
            widgets = (
                self.spinBox_micro_time_start,
                self.spinBox_micro_time_stop,
                self.doubleSpinBox_irf_threshold_vv,
                self.doubleSpinBox_irf_threshold_vh,
                self.doubleSpinBox_shift,
                self.doubleSpinBox_shift_sp,
                self.doubleSpinBox_shift_ss,
            )
            self.block_widget_signals(widgets)
            self._apply_ui_state(state)
            self.unblock_widget_signals(widgets)

        # Check if we have saved MLE settings for this detector in the current setup
        try:
            # Get the current setup name
            setup_name = self.channel_definer.setup_combo.currentText()
            if setup_name:
                # Get the detector_setups.json file path
                setups_file = self.channel_definer.current_setups_file

                # Load existing setups
                setups = load_detector_setups(setups_file)

                # Check if the setup exists and has the detector with MLE settings
                if (setup_name in setups.get("setups", {}) and
                    "detectors" in setups["setups"][setup_name] and
                    new_detector in setups["setups"][setup_name]["detectors"] and
                    "mle_settings" in setups["setups"][setup_name]["detectors"][new_detector]):

                    # Get the MLE settings for the detector
                    detector_params = setups["setups"][setup_name]["detectors"][new_detector]["mle_settings"]

                    # Block signals to prevent multiple updates
                    widgets = (
                        self.spinBox_micro_time_start,
                        self.spinBox_micro_time_stop,
                        self.doubleSpinBox_irf_threshold_vv,
                        self.doubleSpinBox_irf_threshold_vh,
                        self.doubleSpinBox_shift,
                        self.doubleSpinBox_shift_sp,
                        self.doubleSpinBox_shift_ss,
                    )
                    self.block_widget_signals(widgets)

                    # Update the UI with the loaded parameters (require new per-channel keys)
                    if "micro_time_start" in detector_params and "micro_time_stop" in detector_params:
                        self.micro_time_range = [detector_params["micro_time_start"], detector_params["micro_time_stop"]]
                    if "irf_threshold_vv" in detector_params:
                        self.irf_threshold_vv = detector_params["irf_threshold_vv"]
                    if "irf_threshold_vh" in detector_params:
                        self.irf_threshold_vh = detector_params["irf_threshold_vh"]
                    if "shift" in detector_params:
                        self.shift = detector_params["shift"]
                    if "shift_sp" in detector_params:
                        self.shift_sp = detector_params["shift_sp"]
                    if "shift_ss" in detector_params:
                        self.shift_ss = detector_params["shift_ss"]
                    if "min_photons" in detector_params:
                        self.min_photons = detector_params["min_photons"]

                    # IRF start/stop window
                    if "irf_start" in detector_params:
                        self.irf_start = detector_params["irf_start"]
                    if "irf_stop" in detector_params:
                        self.irf_stop = detector_params["irf_stop"]

                    # Update checkbox states
                    if "p2s_twoIstar" in detector_params:
                        self.p2s_twoIstar = detector_params["p2s_twoIstar"]
                    if "BIFL_scatter" in detector_params:
                        self.BIFL_scatter = detector_params["BIFL_scatter"]
                    if "fix_tau" in detector_params:
                        self.fix_tau = detector_params["fix_tau"]
                    if "fix_gamma" in detector_params:
                        self.fix_gamma = detector_params["fix_gamma"]
                    if "fix_r0" in detector_params:
                        self.fix_r0 = detector_params["fix_r0"]
                    if "fix_rho" in detector_params:
                        self.fix_rho = detector_params["fix_rho"]

                    # Unblock signals
                    self.unblock_widget_signals(widgets)
        except Exception as e:
            # Silently ignore errors when loading MLE settings
            pass

        # Show the new detector's polarisation corrections (G factor / l1 / l2).
        self._sync_polarization_widgets()

        # remember where we are now
        self._last_detector = new_detector

        # this covers everything update_selected_window used to do:
        self.update_irf_files()
        self.update_bg_files()
        self.update_decay_of_detector()
        self.update_scatter_count_rate_ui()
        self._fit = None
        self.update_fit()

    def block_widget_signals(self, widgets):
        """
        Block signals for a collection of widgets to prevent multiple updates.

        Parameters
        ----------
        widgets : tuple or list
            Collection of widgets whose signals should be blocked.
        """
        for w in widgets:
            w.blockSignals(True)

    def unblock_widget_signals(self, widgets):
        """
        Unblock signals for a collection of widgets after updates are complete.

        Parameters
        ----------
        widgets : tuple or list
            Collection of widgets whose signals should be unblocked.
        """
        for w in widgets:
            w.blockSignals(False)


    def _switch_filewidget(self, widgets_dict: dict, active: str):
        """
        Show only the FileListWidget corresponding to the active detector.
        """
        for det, fw in widgets_dict.items():
            fw.setVisible(det == active)

    def _set_irf_bg_widgets_enabled(self, enabled: bool):
        """
        Enable or disable file drops for all IRF and BG file widgets.

        Parameters
        ----------
        enabled : bool
            Whether to enable (True) or disable (False) file drops.
        """
        # Enable/disable all IRF file widgets
        for fw in self.irf_file_widgets.values():
            fw.setAcceptDrops(enabled)
            if enabled:
                fw.setToolTip("Drop IRF files here")
            else:
                fw.setToolTip("Drop burst files first before dropping IRF files")

        # Enable/disable all BG file widgets
        for fw in self.bg_file_widgets.values():
            fw.setAcceptDrops(enabled)
            if enabled:
                fw.setToolTip("Drop background files here")
            else:
                fw.setToolTip("Drop burst files first before dropping background files")

    def _prepare_irf_bg_widgets(self):
        """
        Initialize IRF and background file selection widgets, populate selectors,
        and synchronize widget visibility across detectors.

        Note: IRF and BG widgets are initially disabled and will be enabled
        only after burst files are loaded.
        """
        dets = list(self.channel_definer.detectors.keys())

        # Create IRF and background FileListWidgets for each detector
        for det in dets:
            irf_fw = FileListWidget(parent=self, file_added_callback=self.update_irf_files)
            irf_fw.hide()
            irf_fw.setAcceptDrops(False)  # Initially disable file drops
            self.verticalLayout_irf_files.addWidget(irf_fw)
            self.irf_file_widgets[det] = irf_fw

            bg_fw = FileListWidget(parent=self, file_added_callback=self.update_bg_files)
            bg_fw.hide()
            bg_fw.setAcceptDrops(False)  # Initially disable file drops
            self.verticalLayout_bg_files.addWidget(bg_fw)
            self.bg_file_widgets[det] = bg_fw

        # Populate combo boxes and connect signals to switch visible widget
        for combo, widgets_dict in (
                (self.comboBox_irf_select, self.irf_file_widgets),
                (self.comboBox_background_select, self.bg_file_widgets),
        ):
            combo.clear()
            combo.addItems(dets)
            combo.setCurrentIndex(0)
            combo.currentTextChanged.connect(
                lambda name, wd=widgets_dict: self._switch_filewidget(wd, name)
            )

        # Ensure the correct widgets are shown once the UI is laid out
        QtCore.QTimer.singleShot(0, lambda: (
            self._switch_filewidget(self.irf_file_widgets, self.comboBox_irf_select.currentText()),
            self._switch_filewidget(self.bg_file_widgets, self.comboBox_background_select.currentText())
        ))

    def _update_hist_files(
        self,
        widgets_dict: dict,
        np_dict: dict,
        one_for_all: bool,
        normalize: int,
        threshold: typing.Union[float, typing.Tuple[float, float]] = -1,
        state_key: str = None,  # should be 'irf' or 'bg' when called
        detector: Union[str, list[str]] = None
    ):
        """
        Populate np_dict[det] with the summed histogram for the current detector,
        and—if state_key is given—save the resulting array into
        self.channel_settings[det][state_key].
        """
        # figure out which detectors to update
        if one_for_all:
            dets = list(widgets_dict.keys())
        else:
            if detector is None:
                dets = [self.current_detector]
            else:
                dets = detector if isinstance(detector, (list, tuple)) else [detector]

        for det in dets:
            fw = widgets_dict.get(det)
            files: typing.List[Path] = fw.get_selected_files() if fw else []

            # register every file so that LazyTTTRDict knows where to find it,
            # then grab the TTTR object (loading on first access).
            tttr_inputs = list()
            for fp in files:
                # Extract just the filename part (without folder information) before getting the stem
                key = Path(fp.name).stem
                self._tttr_paths[key] = fp  # tell the lazy dict where the file lives
                tttr = self.tttrs.get(key)  # loads/caches on first use
                if tttr is not None:
                    tttr_inputs.append(tttr)

            # keep other file widgets in sync if one-for-all is checked. This is a
            # programmatic mirror (set_paths), which does not fire the drop
            # callback, so it cannot recurse back through update_*_files.
            if one_for_all and det == self.current_detector:
                for other_fw in widgets_dict.values():
                    if other_fw is not fw:
                        other_fw.set_paths([str(fp) for fp in files])

            if not files:
                # No dropped files for this detector: preserve any pattern set
                # programmatically (Send-to-MLE / IRF extraction) in np_dict[det].
                # Use continue (not return) so remaining detectors are still
                # processed; only blank the plot for the visible detector.
                if det == self.current_detector:
                    self.combined_plot.clear()
                continue

            det_chs = self.channel_definer.detectors[det]["chs"]

            if tttr_inputs:
                vv_vh = self.make_vv_vh(
                    tttr_list=tttr_inputs,
                    detector_chs=det_chs,
                    micro_time_range=self.full_range,
                    micro_time_binning=self.micro_time_binning,
                    save_files=self.save_vv_vhs,
                    normalize_counts=normalize,
                    threshold=threshold,
                    apply_vh_shift=False if state_key in ('irf', 'bg') else True
                )
                # np_dict is irf_np/bg_np — the single source of truth. (We no
                # longer also stash the array in channel_settings[det][state_key].)
                np_dict[det] = np.sum(vv_vh, axis=0)

        # redraw decay without fitting
        self.update_decay_of_detector()

    def inspect_bursts(self, idx: int, embed: bool = False):
        if self.df_bursts is None or not self.tttrs:
            cs.logging.info("No burst data loaded.")
            return

        row = self.df_bursts.iloc[idx]
        key = Path(row['First File']).stem
        tttr = self.tttrs.get(key)
        if tttr is None:
            cs.logging.info(f"TTTR with key {key} not found.")
            return
        burst = tttr[int(row['First Photon']):int(row['Last Photon'])]

        # clear any existing plots
        self.burst_layout.clear()

        dets = list(self.channel_definer.detectors.keys())
        for det in dets:
            # create a new subplot
            p = self.burst_layout.addPlot(title=f"Detector: {det}")
            p.setLabel('bottom', 'Micro‐time channel')
            p.setLabel('left', 'Counts')
            p.setLogMode(x=False, y=True)
            p.setYRange(-1, 2)
            p.showGrid(x=True, y=True)

            info = self.channel_definer.detectors[det]
            chs = info['chs']
            pchs = chs[::2]
            schs = chs[1::2] if len(chs) > 1 else chs

            sb, eb = self.micro_time_range
            tp = self.filter_tttr(burst, self.micro_time_range, pchs)
            ts = self.filter_tttr(burst, self.micro_time_range, schs)
            cp = tp.get_microtime_histogram(self.micro_time_binning)[0].astype(np.float64, copy=False)
            cs_hist = ts.get_microtime_histogram(self.micro_time_binning)[0].astype(np.float64, copy=False)
            # zero outside window for visualization
            if sb > 0:
                cp[:sb] = 0
                cs_hist[:sb] = 0
            if eb < cp.size:
                cp[eb:] = 0
                cs_hist[eb:] = 0
            data = np.hstack([cp, cs_hist])

            # plot it
            p.plot(data, pen=None, symbol='o', symbolSize=4)

            # move to next row in the grid
            self.burst_layout.nextRow()

    # ── Programmatic UI (replaces the former wizard.ui) ────────────────────
    @staticmethod
    def _dsb(decimals=2, minimum=0.0, maximum=99.0, value=0.0, step=None,
             adaptive=False, readonly=False, nobuttons=False):
        """Build a QDoubleSpinBox from the property set used across the UI."""
        sb = QtWidgets.QDoubleSpinBox()
        sb.setDecimals(decimals)
        sb.setMinimum(minimum)
        sb.setMaximum(maximum)
        if step is not None:
            sb.setSingleStep(step)
        if adaptive:
            sb.setStepType(QtWidgets.QAbstractSpinBox.AdaptiveDecimalStepType)
        sb.setValue(value)
        if readonly:
            sb.setReadOnly(True)
        if nobuttons:
            sb.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        return sb

    @staticmethod
    def _isb(minimum=0, maximum=99, value=0, step=1):
        """Build a QSpinBox with the given range/step/value."""
        sb = QtWidgets.QSpinBox()
        sb.setMinimum(minimum)
        sb.setMaximum(maximum)
        sb.setSingleStep(step)
        sb.setValue(value)
        return sb

    @staticmethod
    def _hspacer():
        return QtWidgets.QSpacerItem(
            40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum
        )

    def _build_ui(self):
        """Construct the wizard UI in code (this replaced ``wizard.ui``).

        Builds the same central widget / QTabWidget / ``tab_files`` /
        ``tab_parameters`` tree, with the identical widget object names the rest
        of the wizard (~200 references) and the AutoForm dock-shell conversion
        depend on. The dock shell then fans these pages out into foldable docks.
        """
        self.setWindowTitle("MLE Lifetime Analysis")
        self.centralwidget = QtWidgets.QWidget(self)
        self.verticalLayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setSpacing(0)
        self.tabWidget = QtWidgets.QTabWidget(self.centralwidget)
        self.verticalLayout.addWidget(self.tabWidget)
        self.setCentralWidget(self.centralwidget)
        self._build_files_tab()
        self._build_parameters_tab()
        self.tabWidget.setCurrentIndex(0)
        self._pin_action_toolbar()

    def _pin_action_toolbar(self) -> None:
        """Pin the action toolbar above the tab/dock area, so it is always visible.

        The Run/Save actions are built inside the Burst-MLE page; left there they
        live *inside* one tab (and, after the AutoForm dock-shell conversion,
        inside one dock), so they vanish whenever another tab/dock is on top.
        Hosting the toolbar in the top-level layout — above ``tabWidget`` / the
        dock form — keeps the primary actions pinned on top like every other
        plugin toolbar. The dock conversion re-inserts the dock area *below* it
        (``insertWidget(max(0, index), form)`` at the tab's old index, which is
        now 1).
        """
        bar = getattr(self, "toolBar_mle", None)
        if bar is not None and self.verticalLayout.indexOf(bar) == -1:
            bar.setParent(None)
            self.verticalLayout.insertWidget(0, bar)

    def _build_files_tab(self):
        """Files page: burst / IRF / background file group boxes."""
        Q = QtWidgets
        self.tab_files = Q.QWidget()
        h = Q.QHBoxLayout(self.tab_files)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.verticalLayout_3 = Q.QVBoxLayout()  # left spacer column (empty)
        h.addLayout(self.verticalLayout_3)
        self.verticalLayout_2 = Q.QVBoxLayout()
        h.addLayout(self.verticalLayout_2)

        # Burst files
        self.groupBox_burst_files = Q.QGroupBox("Burst Files")
        self.groupBox_burst_files.setSizePolicy(Q.QSizePolicy.Expanding, Q.QSizePolicy.Preferred)
        v7 = Q.QVBoxLayout(self.groupBox_burst_files)
        v7.setContentsMargins(0, 0, 0, 0)
        v7.setSpacing(0)
        hb = Q.QHBoxLayout()
        self.toolButton_clear_burst = Q.QToolButton()
        self.toolButton_clear_burst.setText("Clear")
        hb.addWidget(self.toolButton_clear_burst)
        hb.addItem(self._hspacer())
        v7.addLayout(hb)
        self.verticalLayout_burst_files = Q.QVBoxLayout()
        v7.addLayout(self.verticalLayout_burst_files)
        self.verticalLayout_2.addWidget(self.groupBox_burst_files)

        # IRF files
        self.groupBox_irf_files = Q.QGroupBox("IRF Files")
        self.groupBox_irf_files.setSizePolicy(Q.QSizePolicy.Expanding, Q.QSizePolicy.Minimum)
        v8 = Q.QVBoxLayout(self.groupBox_irf_files)
        v8.setContentsMargins(0, 0, 0, 0)
        v8.setSpacing(0)
        hb2 = Q.QHBoxLayout()
        self.toolButton_clear_irf = Q.QToolButton()
        self.toolButton_clear_irf.setText("Clear")
        self.comboBox_irf_select = Q.QComboBox()
        self.checkBox_irf_one_for_all = Q.QCheckBox("One for all")
        self.checkBox_irf_one_for_all.setChecked(True)
        hb2.addWidget(self.toolButton_clear_irf)
        hb2.addWidget(self.comboBox_irf_select)
        hb2.addWidget(self.checkBox_irf_one_for_all)
        hb2.addItem(self._hspacer())
        v8.addLayout(hb2)
        self.verticalLayout_irf_files = Q.QVBoxLayout()
        v8.addLayout(self.verticalLayout_irf_files)
        self.verticalLayout_2.addWidget(self.groupBox_irf_files)

        # Background files
        self.groupBox_bg_files = Q.QGroupBox("Background Files")
        self.groupBox_bg_files.setSizePolicy(Q.QSizePolicy.Preferred, Q.QSizePolicy.Minimum)
        v9 = Q.QVBoxLayout(self.groupBox_bg_files)
        v9.setContentsMargins(0, 0, 0, 0)
        v9.setSpacing(0)
        hb3 = Q.QHBoxLayout()
        self.toolButton_clear_bg = Q.QToolButton()
        self.toolButton_clear_bg.setText("Clear")
        self.comboBox_background_select = Q.QComboBox()
        self.checkBox_bg_one_for_all = Q.QCheckBox("One for all")
        self.checkBox_bg_one_for_all.setChecked(True)
        hb3.addWidget(self.toolButton_clear_bg)
        hb3.addWidget(self.comboBox_background_select)
        hb3.addWidget(self.checkBox_bg_one_for_all)
        hb3.addItem(self._hspacer())
        v9.addLayout(hb3)
        self.verticalLayout_bg_files = Q.QVBoxLayout()
        v9.addLayout(self.verticalLayout_bg_files)
        self.verticalLayout_2.addWidget(self.groupBox_bg_files)

        self.tabWidget.addTab(self.tab_files, "Files")

    def _build_parameters_tab(self):
        """Burst-MLE page: fit parameters, IRF controls, plots column, Run."""
        Q = QtWidgets
        self.tab_parameters = Q.QWidget()
        # The page stacks a full-width action toolbar on top of a horizontal
        # splitter (controls on the left, plots on the right). The toolbar spans
        # the WHOLE Burst-MLE panel — not just the narrow controls column — so its
        # buttons are never clipped/covered inside the embedded workflow dock.
        _page = Q.QVBoxLayout(self.tab_parameters)
        _page.setContentsMargins(0, 0, 0, 0)
        _page.setSpacing(2)

        # Action toolbar. Embedded as a plain widget (NOT addToolBar) so it shows
        # in the embedded workflow panel too; a FlowLayout wraps the buttons onto
        # another row when the panel is narrow instead of hiding overflow behind a
        # menu. Populated at the end of this method, once every hosted widget
        # exists.
        from chisurf.gui.widgets.dock_area.dock_stacked_tab_bar import FlowLayout
        self.toolBar_mle = Q.QFrame()
        self.toolBar_mle.setObjectName("mle_toolbar")
        self.toolBar_mle.setStyleSheet(
            "#mle_toolbar { border-bottom: 1px solid palette(mid); }"
        )
        self._mle_toolbar_layout = FlowLayout(
            self.toolBar_mle, margin=2, h_spacing=4, v_spacing=2
        )
        _page.addWidget(self.toolBar_mle)

        self._mle_splitter = Q.QSplitter(QtCore.Qt.Horizontal)
        _left = Q.QWidget()
        grid3 = Q.QGridLayout(_left)

        # Plots go on the right side of the splitter.
        _right = Q.QWidget()
        self.verticalLayout_plots = Q.QVBoxLayout(_right)
        self.verticalLayout_plots.setSpacing(0)
        self.verticalLayout_plots.setContentsMargins(0, 0, 0, 0)
        self._mle_splitter.addWidget(_left)
        self._mle_splitter.addWidget(_right)
        self._mle_splitter.setStretchFactor(0, 0)
        self._mle_splitter.setStretchFactor(1, 1)
        self._mle_splitter.setChildrenCollapsible(False)
        _page.addWidget(self._mle_splitter, 1)

        # Filename / detector / fit-range / min-photons block (grid at 0,0).
        g2 = Q.QGridLayout()
        g2.setSpacing(0)
        self.label_21 = Q.QLabel("Filename")
        self.lineEdit_current_filename = Q.QLineEdit()
        self.lineEdit_current_filename.setSizePolicy(Q.QSizePolicy.Minimum, Q.QSizePolicy.Fixed)
        self.spinBox_current_file_idx = Q.QSpinBox()
        self.label_window = Q.QLabel("Detector:")
        self.comboBox_window = Q.QComboBox()
        self.label_4 = Q.QLabel("Range")
        self.label_4.setToolTip("Fit window: start / stop micro-time channel.")
        self.spinBox_micro_time_start = self._isb(0, 10000, 0)
        self.spinBox_micro_time_stop = self._isb(0, 10000, 4096)
        self.label_14 = Q.QLabel("Min photons")
        self.label_14.setToolTip("Minimum photons per burst to fit.")
        self.spinBox_min_photons = self._isb(5, 1000, 20)
        self.toolButton_save_fit = action_button(
            "save", tooltip="Save the current parameters as the detector default"
        )
        g2.addWidget(self.label_21, 0, 0)
        g2.addWidget(self.lineEdit_current_filename, 0, 1, 1, 2)
        g2.addWidget(self.spinBox_current_file_idx, 0, 3)
        g2.addWidget(self.label_window, 1, 0)
        g2.addWidget(self.comboBox_window, 1, 1, 1, 3)
        g2.addWidget(self.label_4, 2, 0)
        g2.addWidget(self.spinBox_micro_time_start, 2, 1, 1, 2)
        g2.addWidget(self.spinBox_micro_time_stop, 2, 3)
        g2.addWidget(self.label_14, 3, 0)
        g2.addWidget(self.spinBox_min_photons, 3, 1)
        # toolButton_save_fit lives in the top toolbar (built below), not here.
        grid3.addLayout(g2, 0, 0)

        # IRF shift / threshold / range (groupBox_2 at 1,0).
        self.groupBox_2 = Q.QGroupBox("")
        g7 = Q.QGridLayout(self.groupBox_2)
        g7.setContentsMargins(0, 0, 0, 0)
        g7.setSpacing(0)
        self.label_7 = Q.QLabel("IRF")
        self.label = Q.QLabel("VV")
        self.label_6 = Q.QLabel("VH")
        self.label_29 = Q.QLabel("Shift")
        self.label_29.setSizePolicy(Q.QSizePolicy.Fixed, Q.QSizePolicy.Preferred)
        self.doubleSpinBox_shift_sp = self._dsb(minimum=-99.0, maximum=99.0, adaptive=True)
        self.doubleSpinBox_shift_ss = self._dsb(minimum=-99.0, maximum=99.0, adaptive=True)
        self.label_13 = Q.QLabel("Threshold")
        self.doubleSpinBox_irf_threshold_vv = self._dsb(
            decimals=3, maximum=1.0, step=0.02, adaptive=True, value=0.15)
        self.doubleSpinBox_irf_threshold_vh = self._dsb(
            decimals=2, maximum=1.0, step=0.02, value=0.15)
        self.label_8 = Q.QLabel("IRF range")
        self.spinBox_irf_start = self._isb(-1, 999999, -1)
        self.spinBox_irf_start.setToolTip("Convolution start")
        self.spinBox_irf_stop = self._isb(-1, 999999, -1)
        g7.addWidget(self.label_7, 0, 0)
        g7.addWidget(self.label, 0, 1)
        g7.addWidget(self.label_6, 0, 2)
        g7.addWidget(self.label_29, 1, 0)
        g7.addWidget(self.doubleSpinBox_shift_sp, 1, 1)
        g7.addWidget(self.doubleSpinBox_shift_ss, 1, 2)
        g7.addWidget(self.label_13, 2, 0)
        g7.addWidget(self.doubleSpinBox_irf_threshold_vv, 2, 1)
        g7.addWidget(self.doubleSpinBox_irf_threshold_vh, 2, 2)
        g7.addWidget(self.label_8, 3, 0)
        g7.addWidget(self.spinBox_irf_start, 3, 1)
        g7.addWidget(self.spinBox_irf_stop, 3, 2)
        from chisurf.gui.widgets.collapsible_box import CollapsibleBox
        _irf_box = CollapsibleBox("IRF (shift · threshold · range)", expanded=False)
        _irf_box.add_widget(self.groupBox_2)
        grid3.addWidget(_irf_box, 1, 0)

        # Shift + scatter count rate (groupBox_fit_params at 2,0).
        self.groupBox_fit_params = Q.QGroupBox("")
        self.groupBox_fit_params.setSizePolicy(Q.QSizePolicy.Minimum, Q.QSizePolicy.Minimum)
        g4 = Q.QGridLayout(self.groupBox_fit_params)
        g4.setContentsMargins(0, 0, 0, 0)
        g4.setSpacing(0)
        self.label_28 = Q.QLabel("Shift")
        self.label_28.setToolTip("VV/VH channel shift (perpendicular relative to parallel).")
        self.doubleSpinBox_shift = self._dsb(decimals=0, minimum=-9999.0, maximum=9999.0)
        self.doubleSpinBox_shift.setSizePolicy(Q.QSizePolicy.Minimum, Q.QSizePolicy.Fixed)
        self.doubleSpinBox_shift.setToolTip("VV/VH channel shift (perpendicular relative to parallel).")
        self.label_24 = Q.QLabel("Scatter [Hz]")
        self.label_24.setToolTip("Scatter count rate (Hz).")
        self.label_24.setSizePolicy(Q.QSizePolicy.Fixed, Q.QSizePolicy.Preferred)
        self.doubleSpinBox_scatter_Countrate = self._dsb(maximum=999999.0, adaptive=True)
        g4.addWidget(self.label_28, 3, 0)
        g4.addWidget(self.doubleSpinBox_shift, 3, 1)
        g4.addWidget(self.label_24, 5, 0)
        g4.addWidget(self.doubleSpinBox_scatter_Countrate, 5, 1)
        # Per-detector polarisation corrections (G factor, l1, l2). They are
        # calibration constants defined with the detector (the Channels / setup
        # step) and feed the anisotropy of the fit. The Detector Definition tab is
        # hidden inside the embedded workflow, so display them here (read-only)
        # for the current detector; edit them in the detector setup.
        _pol_tip = ("Polarisation correction for the current detector, defined in "
                    "the detector setup (Channels step). Read-only here.")
        self.label_g_factor = Q.QLabel("G")
        self.label_g_factor.setToolTip("Detector G factor (VV/VH sensitivity ratio). " + _pol_tip)
        self.label_g_factor.setSizePolicy(Q.QSizePolicy.Fixed, Q.QSizePolicy.Preferred)
        self.doubleSpinBox_g_factor = self._dsb(
            decimals=4, minimum=0.0, maximum=100.0, value=1.0, readonly=True, nobuttons=True)
        self.doubleSpinBox_g_factor.setToolTip(
            "Detector G factor (VV/VH sensitivity ratio). " + _pol_tip)
        self.label_l1 = Q.QLabel("l1")
        self.label_l1.setSizePolicy(Q.QSizePolicy.Fixed, Q.QSizePolicy.Preferred)
        self.doubleSpinBox_l1 = self._dsb(
            decimals=4, minimum=-1.0, maximum=1.0, value=0.0, readonly=True, nobuttons=True)
        self.doubleSpinBox_l1.setToolTip("Mixing factor l1 (parallel leakage). " + _pol_tip)
        self.label_l2 = Q.QLabel("l2")
        self.label_l2.setSizePolicy(Q.QSizePolicy.Fixed, Q.QSizePolicy.Preferred)
        self.doubleSpinBox_l2 = self._dsb(
            decimals=4, minimum=-1.0, maximum=1.0, value=0.0, readonly=True, nobuttons=True)
        self.doubleSpinBox_l2.setToolTip("Mixing factor l2 (perpendicular leakage). " + _pol_tip)
        g4.addWidget(self.label_g_factor, 6, 0)
        g4.addWidget(self.doubleSpinBox_g_factor, 6, 1)
        g4.addWidget(self.label_l1, 7, 0)
        g4.addWidget(self.doubleSpinBox_l1, 7, 1)
        g4.addWidget(self.label_l2, 8, 0)
        g4.addWidget(self.doubleSpinBox_l2, 8, 1)
        _shift_box = CollapsibleBox("Shift · scatter · G/l1/l2", expanded=False)
        _shift_box.add_widget(self.groupBox_fit_params)
        grid3.addWidget(_shift_box, 2, 0)

        # Model parameters + results (groupBox_model_params at 3,0).
        self.groupBox_model_params = Q.QGroupBox("")
        self.groupBox_model_params.setSizePolicy(Q.QSizePolicy.Minimum, Q.QSizePolicy.Minimum)
        g = Q.QGridLayout(self.groupBox_model_params)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(0)
        self.checkBox_BIFL_scatter = Q.QCheckBox("BIFL scatter")
        self.checkBox_BIFL_scatter.setSizePolicy(Q.QSizePolicy.Fixed, Q.QSizePolicy.Fixed)
        self.checkBox_2IStar = Q.QCheckBox("2I*: P+2S")
        self.checkBox_2IStar.setChecked(True)
        self.checkBox_save_vv_vhs = Q.QCheckBox("Save VV/VHs")
        g.addWidget(self.checkBox_BIFL_scatter, 0, 0)
        g.addWidget(self.checkBox_2IStar, 0, 1)
        g.addWidget(self.checkBox_save_vv_vhs, 0, 4)
        # Optimize target (hyperparameter optimisation) and its iteration count
        # live in the top toolbar (built below), not in this grid.
        self.toolButton_hyper_opt = Q.QToolButton()
        self.toolButton_hyper_opt.setText("🎯 Opt")
        self.toolButton_hyper_opt.setToolTip(
            "Optimise the fit hyperparameters (shift / IRF window / binning) over "
            "the chosen number of iterations, then refit."
        )
        self.spinBox_n_h_opt = self._isb(20, 999, 50, 5)
        self.spinBox_n_h_opt.setSizePolicy(Q.QSizePolicy.Fixed, Q.QSizePolicy.Fixed)
        self.spinBox_n_h_opt.setToolTip("Number of hyperparameter-optimisation iterations.")
        self.label_5 = Q.QLabel("Initial value")
        self.label_20 = Q.QLabel("F")
        self.label_20.setToolTip("Fix parameter")
        self.label_20.setSizePolicy(Q.QSizePolicy.Fixed, Q.QSizePolicy.Preferred)
        self.label_19 = Q.QLabel("Fit")
        self.label_19.setSizePolicy(Q.QSizePolicy.Minimum, Q.QSizePolicy.Preferred)
        g.addWidget(self.label_5, 5, 1)
        g.addWidget(self.label_20, 5, 3)
        g.addWidget(self.label_19, 5, 4)
        # tau / gamma / r0 / rho rows: label, initial value, fix, result
        self.label_15 = Q.QLabel("τ [ns]")
        self.label_15.setToolTip("Fluorescence lifetime tau (ns).")
        self.label_15.setSizePolicy(Q.QSizePolicy.Fixed, Q.QSizePolicy.Preferred)
        self.doubleSpinBox_tau = self._dsb(decimals=3, maximum=20.0, adaptive=True, value=4.0)
        self.doubleSpinBox_tau.setSizePolicy(Q.QSizePolicy.Minimum, Q.QSizePolicy.Fixed)
        self.checkBox_fix_tau = Q.QCheckBox()
        self.doubleSpinBox_tau_result = self._dsb(decimals=3, maximum=20.0, readonly=True, nobuttons=True)
        g.addWidget(self.label_15, 6, 0)
        g.addWidget(self.doubleSpinBox_tau, 6, 1)
        g.addWidget(self.checkBox_fix_tau, 6, 3)
        g.addWidget(self.doubleSpinBox_tau_result, 6, 4)
        self.label_16 = Q.QLabel("γ")
        self.label_16.setToolTip("Scatter fraction gamma (0..1).")
        self.doubleSpinBox_gamma = self._dsb(decimals=3, maximum=1.0, step=0.01, adaptive=True, value=0.1)
        self.checkBox_fix_gamma = Q.QCheckBox()
        self.doubleSpinBox_gamma_result = self._dsb(decimals=3, maximum=1.0, readonly=True, nobuttons=True)
        g.addWidget(self.label_16, 7, 0)
        g.addWidget(self.doubleSpinBox_gamma, 7, 1)
        g.addWidget(self.checkBox_fix_gamma, 7, 3)
        g.addWidget(self.doubleSpinBox_gamma_result, 7, 4)
        self.label_17 = Q.QLabel("r₀")
        self.label_17.setToolTip("Fundamental anisotropy r0.")
        self.doubleSpinBox_r0 = self._dsb(decimals=3, maximum=1.0, step=0.01, adaptive=True, value=0.38)
        self.checkBox_fix_r0 = Q.QCheckBox()
        self.checkBox_fix_r0.setChecked(True)
        self.doubleSpinBox_r0_result = self._dsb(decimals=3, maximum=1.0, readonly=True, nobuttons=True)
        g.addWidget(self.label_17, 8, 0)
        g.addWidget(self.doubleSpinBox_r0, 8, 1)
        g.addWidget(self.checkBox_fix_r0, 8, 3)
        g.addWidget(self.doubleSpinBox_r0_result, 8, 4)
        self.label_18 = Q.QLabel("ρ [ns]")
        self.label_18.setToolTip("Rotational correlation time rho (ns).")
        self.doubleSpinBox_rho = self._dsb(decimals=3, maximum=999.0, adaptive=True, value=1.22)
        self.checkBox_fix_rho = Q.QCheckBox()
        self.doubleSpinBox_rho_result = self._dsb(decimals=3, maximum=20.0, readonly=True, nobuttons=True)
        g.addWidget(self.label_18, 9, 0)
        g.addWidget(self.doubleSpinBox_rho, 9, 1)
        g.addWidget(self.checkBox_fix_rho, 9, 3)
        g.addWidget(self.doubleSpinBox_rho_result, 9, 4)
        self.label_3 = Q.QLabel("Score")
        self.doubleSpinBox_twoIstar_result = self._dsb(
            decimals=3, minimum=-99999.0, maximum=99999.0, readonly=True, nobuttons=True)
        g.addWidget(self.label_3, 10, 0)
        g.addWidget(self.doubleSpinBox_twoIstar_result, 10, 1)
        self.label_25 = Q.QLabel("rScatter")
        self.doubleSpinBox_r_scatter_result = self._dsb(
            decimals=3, minimum=-1.0, maximum=1.0, readonly=True, nobuttons=True)
        self.label_27 = Q.QLabel("rExp")
        self.doubleSpinBox_r_exp_result = self._dsb(
            decimals=3, minimum=-1.0, maximum=1.0, readonly=True, nobuttons=True)
        g.addWidget(self.label_25, 11, 0)
        g.addWidget(self.doubleSpinBox_r_scatter_result, 11, 1)
        g.addWidget(self.label_27, 11, 3)
        g.addWidget(self.doubleSpinBox_r_exp_result, 11, 4)
        # Fit-model selector, populated from tttrlib's registry (fit23/24/25/26).
        # Currently only fit23 (single lifetime + anisotropy) is wired end to end;
        # the selector makes the model explicit and is the seam for the others.
        self.comboBox_fit_model = Q.QComboBox()
        try:
            from chisurf.core.fluorescence.mle import registry as _fit_reg
            for _name, _spec in _fit_reg.fit_models().items():
                # This workflow builds the fit from dt/IRF/background (the
                # ``fit2x`` construction). Only offer estimators whose class
                # accepts that construction — e.g. fit26 (pattern fractioning)
                # takes two reference decays, not an IRF, so it is skipped.
                if not self._is_fit2x_constructible(_name):
                    continue
                self.comboBox_fit_model.addItem(_spec.get("label", _name), _name)
                self.comboBox_fit_model.setItemData(
                    self.comboBox_fit_model.count() - 1,
                    _spec.get("summary", ""), QtCore.Qt.ToolTipRole,
                )
        except Exception:
            pass
        if self.comboBox_fit_model.count() == 0:
            self.comboBox_fit_model.addItem("Single lifetime + anisotropy (Fit23)", "fit23")
        # A multi-exponential *tail* fit (tttrlib DecayFitNExp with tail_start):
        # fits the decay tail only, no IRF deconvolution — the standard approach
        # for FRET sensitised-emission decays whose rise is not a simple IRF.
        self.comboBox_fit_model.addItem("Tail fit (multi-exp)", "tail")
        self.comboBox_fit_model.setItemData(
            self.comboBox_fit_model.count() - 1,
            "Multi-exponential fit of the decay tail only (no IRF deconvolution); "
            "for FRET sensitised emission.", QtCore.Qt.ToolTipRole,
        )
        self.comboBox_fit_model.setToolTip(
            "Lifetime fit model (from the tttrlib registry). fit23 fits one "
            "lifetime with anisotropy; other models are selectable as they are wired."
        )
        _model_row = Q.QWidget()
        _mrl = Q.QHBoxLayout(_model_row)
        _mrl.setContentsMargins(0, 0, 0, 0)
        _mrl.setSpacing(4)
        _mlbl = Q.QLabel("Model")
        _mlbl.setToolTip("MLE lifetime fit model.")
        _mrl.addWidget(_mlbl)
        _mrl.addWidget(self.comboBox_fit_model, 1)

        # Registry-driven parameter editor for the non-fit23 models. The fit23
        # rows above stay authored (they carry the anisotropy extras); for any
        # other model this box is rebuilt from the tttrlib schema and shown in
        # their place, so fit23 is never disturbed.
        self.groupBox_dyn_params = Q.QGroupBox("")
        self.groupBox_dyn_params.setSizePolicy(Q.QSizePolicy.Minimum, Q.QSizePolicy.Minimum)
        self._dyn_grid = Q.QGridLayout(self.groupBox_dyn_params)
        self._dyn_grid.setContentsMargins(0, 0, 0, 0)
        self._dyn_grid.setSpacing(0)
        self._dyn_params = None       # _MleParameterRows, built per model
        self._dyn_form = None
        self.groupBox_dyn_params.setVisible(False)

        _params_box = CollapsibleBox("Fit parameters", expanded=True)
        _params_box.add_widget(_model_row)
        _params_box.add_widget(self.groupBox_model_params)
        _params_box.add_widget(self.groupBox_dyn_params)
        grid3.addWidget(_params_box, 3, 0)

        # Actions row: a general one-click "make it work" optimiser, a quick
        # IRF/background estimate from non-burst photons, a jump to the measured
        # IRF & Background step, and a note that a measured IRF/background gives
        # better lifetimes. Compact single row.
        self.toolButton_auto_optimize = Q.QToolButton()
        self.toolButton_auto_optimize.setText("⚡ Auto")
        self.toolButton_auto_optimize.setToolTip(
            "Auto-select the micro-time binning (count- and IRF-resolution-aware) "
            "and the fit window (the decay's filled region), then refit. Uses the "
            "current IRF/background; if none was loaded it is estimated from the "
            "non-burst photons."
        )
        _opt_font = self.toolButton_auto_optimize.font()
        _opt_font.setBold(True)
        self.toolButton_auto_optimize.setFont(_opt_font)
        self.toolButton_auto_irf = Q.QToolButton()
        self.toolButton_auto_irf.setText("✨ Auto IRF")
        self.toolButton_auto_irf.setToolTip(
            "Estimate the IRF and background from this file's non-burst photons "
            "and refit. Quick, but a measured IRF/background is more reliable."
        )
        # IRF model for Auto IRF/BG: flip between a Gaussian fitted to the
        # extracted prompt (suppresses the fluorescent-background tail) and the
        # raw experimental prompt. Changing it re-runs the auto-extraction.
        self.comboBox_irf_model = Q.QComboBox()
        self.comboBox_irf_model.addItem("Gaussian", "gaussian")
        self.comboBox_irf_model.addItem("Skewed", "skewed")
        self.comboBox_irf_model.addItem("Experimental", "experimental")
        self.comboBox_irf_model.setToolTip(
            "IRF model used by Auto IRF/BG:\n"
            "• Gaussian (fitted): a Gaussian least-squares fit to the extracted "
            "prompt — the fit cannot follow the slow fluorescent tail, so it "
            "suppresses that artifact (recommended).\n"
            "• Skewed Gaussian: a skew-normal fit (asymmetric detector response).\n"
            "• Experimental: the raw baseline-subtracted non-burst histogram."
        )
        self.toolButton_goto_irf = Q.QToolButton()
        self.toolButton_goto_irf.setText("📁 IRF step…")
        self.toolButton_goto_irf.setToolTip(
            "Open the IRF & Background step to use a measured IRF/background."
        )
        # The one-click actions (auto_optimize, auto_irf, irf-model combo,
        # goto_irf) live in the top toolbar (built below). Only the tip stays in
        # the controls column.
        self.label_irf_hint = Q.QLabel("Tip: a measured IRF/background gives better lifetimes.")
        self.label_irf_hint.setStyleSheet("color: #9ba3af; font-size: 10px;")
        self.label_irf_hint.setWordWrap(True)
        grid3.addWidget(self.label_irf_hint, 4, 0)

        # A trailing spacer pushes the controls up (the Run button now lives in
        # the toolbar, so the column no longer ends on it).
        grid3.addItem(
            Q.QSpacerItem(20, 40, Q.QSizePolicy.Minimum, Q.QSizePolicy.Expanding), 5, 0
        )
        # Canonical Run action (same 🚀 button as every other plugin); it fits
        # every burst across all loaded files, so the shell's "Next" can trigger it.
        self.pushButton_process_bursts = action_button(
            "run", tooltip="Process all loaded burst files and fit each burst"
        )
        # Exported fits that are already current are not refitted; this is how the
        # user asks for them anyway (a rebuilt fit2x, a suspect export).
        self.pushButton_restart_bursts = action_button(
            "restart", tooltip="Refit every burst from scratch, even if nothing changed"
        )

        # --- Populate the top action toolbar (every hosted widget now exists) ---
        def _tb_sep():
            line = Q.QFrame()
            line.setFrameShape(Q.QFrame.VLine)
            line.setFrameShadow(Q.QFrame.Sunken)
            return line

        flow = self._mle_toolbar_layout
        for widget in (
            self.pushButton_process_bursts,
            self.pushButton_restart_bursts,
            _tb_sep(),
            self.toolButton_auto_optimize,
            self.toolButton_auto_irf,
            self.comboBox_irf_model,
            self.toolButton_goto_irf,
            _tb_sep(),
            self.toolButton_hyper_opt,
            self.spinBox_n_h_opt,
            _tb_sep(),
            self.toolButton_save_fit,
        ):
            flow.addWidget(widget)

        self.tabWidget.addTab(self.tab_parameters, "BurstMLE")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._build_ui()
        # Core attributes
        self.df_bursts = None
        self._fit = None
        self.stop_processing = False

        self._tttr_paths: Dict[str, Path] = {}
        self.tttrs = LazyTTTRDict(self._tttr_paths, lambda: self.tttr_file_type)

        self.irf_np = {}
        self.bg_np = {}
        self.channel_settings = {}
        self.irf_file_widgets = {}
        self.bg_file_widgets = {}

        self.channel_definer = None
        self.decay_of_current_file = None
        self.current_file_idx = 0

        # File lists
        self.burst_files_list = FileListWidget(
            parent=self,
            file_added_callback=self.load_burst_data,
            process_on_drop=True
        )
        self.verticalLayout_burst_files.addWidget(self.burst_files_list)

        # Detector definition tab - moved to first page
        self.tab_detector = QtWidgets.QWidget()
        self.tabWidget.insertTab(0, self.tab_detector, "Detector Definition")
        self.tabWidget.setCurrentIndex(0)  # Start on Detector Wizard page
        self.verticalLayout_detector_tab = QtWidgets.QVBoxLayout(self.tab_detector)
        self.channel_definer = cs.gui.widgets.wizard.DetectorWizardPage(parent=self)
        self.groupBox_detector = QtWidgets.QGroupBox("Detector Configuration")
        self.verticalLayout_detector = QtWidgets.QVBoxLayout(self.groupBox_detector)
        self.verticalLayout_detector.addWidget(self.channel_definer)
        self.verticalLayout_detector_tab.addWidget(self.groupBox_detector)
        # ← as soon as the user finishes defining detectors, re-build all our channel UIs

        # Prepare irf, bg widgets
        self._prepare_irf_bg_widgets()

        # Ensure IRF and BG file widgets are disabled by default
        self._set_irf_bg_widgets_enabled(False)

        # 1) draw the plots
        self.setup_plots()

        # 2) set *all* of the spin-boxes to their default values
        self.initialize_ui_values()
        self._init_channels_from_wizard()

        self.connect_signals()

    def setup_plots(self):
        # Decay plot all bursts
        self.groupBox_combined_plot = QtWidgets.QGroupBox("All selections")
        self.verticalLayout_combined_plot = QtWidgets.QVBoxLayout(self.groupBox_combined_plot)
        self.verticalLayout_plots.addWidget(self.groupBox_combined_plot)

        # Plot for IRF, Model, and Data
        self.combined_plot = pg.PlotWidget()

        # Weighted‐residuals plot
        self.residual_plot = pg.PlotWidget()
        # insert it *above* the decay plot, give it stretch=1 (residual)
        self.verticalLayout_combined_plot.insertWidget(
            0, self.residual_plot, 1
        )
        self.residual_plot.setLabel('left', 'Weighted residuals')
        # link the x‐axes so they pan/zoom together
        self.residual_plot.setXLink(self.combined_plot)
        # optional: show grid
        self.residual_plot.showGrid(x=True, y=True)

        # Data plot, give it stretch=3 (combined)
        self.verticalLayout_combined_plot.addWidget(self.combined_plot, 3)
        self.combined_plot.setLabel('bottom', 'Time (ch.)')
        self.combined_plot.setLabel('left', 'Intensity')
        self.combined_plot.setLogMode(y=True)
        self.combined_plot.setYRange(-1, 5)
        # A legend so the four overlaid curves (data, model, IRF, background) are
        # identifiable. Created once and re-populated on each replot: the plot is
        # cleared every fit, so without an explicit legend.clear() the rows would
        # accumulate a duplicate set per fit. Each plot() call below passes name=.
        self.combined_legend = self.combined_plot.addLegend(offset=(10, 10))

    def update_variable_fit_parameters(self):
        # A fit parameter changed -> rebuild the fit and re-run so the plot stays
        # in sync (a stale cached Fit23 would keep the previous IRF/params).
        self._fit = None
        self.update_fit()

    def refit(self):
        self._fit = None
        self.update_fit()

    def _set_polarization_display(self, attr: str, value: float):
        """Mirror a G factor / l1 / l2 value into its fit-page field (no signals).

        The properties are the single source of truth (they own the detector
        definition); this keeps the display in step whenever they are written,
        without re-triggering the field's ``editingFinished`` refit.
        """
        widget = getattr(self, attr, None)
        if widget is None:
            return
        blocked = widget.blockSignals(True)
        widget.setValue(float(value))
        widget.blockSignals(blocked)

    def _sync_polarization_widgets(self):
        """Show the current detector's G factor / l1 / l2 in the fit-page fields.

        The values live on the detector definition (the ``g_factor``/``l1``/``l2``
        properties read them); this mirrors them into the display spin boxes with
        signals blocked so refreshing on a detector switch does not re-trigger a
        fit.
        """
        self._set_polarization_display("doubleSpinBox_g_factor", self.g_factor)
        self._set_polarization_display("doubleSpinBox_l1", self.l1)
        self._set_polarization_display("doubleSpinBox_l2", self.l2)

    def update_internal_fit_parameters(self):
        cs.logging.info("update internal fit parameters")
        self._sync_polarization_widgets()
        # Set fit to none to force recreation of fit
        self._fit = None
        self.update_fit()

    def on_irf_parameters_changed(self, _=None):
        """
        Called whenever any IRF parameter (threshold,
        'one‐for‐all' toggle, detector selector, or your
        shift / shift_sp / shift_ss) changes.
        """
        # 2) recompute IRFs from the files (this will use your new shift/shift_sp/shift_ss
        self.update_irf_files()

        # 3) toss out the old Fit23 so we’ll build a fresh one with the new IRF
        self._fit = None

        # 4) refresh the decay and re‐run the fit
        self.update_decay_of_detector()
        self.update_fit()

    def connect_signals(self):
        self.channel_definer.detectorsChanged.connect(self._init_channels_from_wizard)

        # hook up save/load
        self.toolButton_save_fit.clicked.connect(self.save_fit)

        # --- Clear buttons ---
        clear_buttons = {
            self.toolButton_clear_burst: self.burst_files_list,
            self.toolButton_clear_irf: self.irf_file_widgets,
            self.toolButton_clear_bg: self.bg_file_widgets,
        }
        for button, widget_group in clear_buttons.items():
            button.clicked.connect(lambda _, wg=widget_group: self.clear_files(wg))

        # --- Burst processing & navigation ---
        self.pushButton_process_bursts.clicked.connect(self.process_bursts)
        self.pushButton_restart_bursts.clicked.connect(self.restart_bursts)
        self.toolButton_auto_optimize.clicked.connect(self.auto_optimize)
        self.toolButton_auto_irf.clicked.connect(self.auto_extract_irf_bg)
        # Flipping the IRF model re-extracts so the change is immediate.
        self.comboBox_irf_model.currentIndexChanged.connect(
            lambda _=None: self.auto_extract_irf_bg()
        )
        self.toolButton_goto_irf.clicked.connect(self.go_to_irf_bg)
        # Stop button functionality is deprecated in favor of modal progress dialog cancel
        try:
            self.pushButton_stop.hide()
            self.pushButton_stop.setEnabled(False)
        except Exception:
            pass
        self.comboBox_window.currentTextChanged.connect(self._on_channel_changed)
        self.spinBox_current_file_idx.valueChanged.connect(self.update_current_file)
        self.comboBox_fit_model.currentIndexChanged.connect(self._on_fit_model_changed)

        # --- Fit‐parameter controls (internal) ---

        # Connect detector change to update_internal_fit_parameters since g_factor, l1, and l2 are now detector-specific
        self.comboBox_window.currentTextChanged.connect(self.update_internal_fit_parameters)

        # --- Micro‐time range → update decay + fit ---
        self.channel_definer.micro_binning_combo.currentTextChanged.connect(self._update_max_bins_from_tttr)
        self.channel_definer.micro_binning_combo.currentTextChanged.connect(self.on_micro_time_range_changed)
        self.spinBox_micro_time_start.valueChanged.connect(
            lambda val: self.spinBox_micro_time_stop.setMinimum(val + 1)
        )
        for sb in (self.spinBox_micro_time_start, self.spinBox_micro_time_stop):
            sb.valueChanged.connect(self.on_micro_time_range_changed)

        # --- Fit‐parameter controls (variable) ---
        variable_spins = (
            self.doubleSpinBox_tau,
            self.doubleSpinBox_gamma,
            self.doubleSpinBox_r0,
            self.doubleSpinBox_rho,
        )
        for spin in variable_spins:
            spin.valueChanged.connect(self.update_variable_fit_parameters)

        variable_checks = (
            self.checkBox_fix_tau,
            self.checkBox_fix_gamma,
            self.checkBox_fix_r0,
            self.checkBox_fix_rho,
            self.checkBox_2IStar,
            self.checkBox_BIFL_scatter
        )
        for chk in variable_checks:
            # Toggling a fix flag / option changes what is optimised -> re-fit.
            chk.stateChanged.connect(self.refit)

        # --- Other parameter updates ---
        self.spinBox_min_photons.valueChanged.connect(self.update_parameters)
        # persist min_photons per detector into channel_settings on change
        self.spinBox_min_photons.valueChanged.connect(lambda val: self._save_min_photons_for_current_detector(val))

        # --- IRF parameter controls ---
        irf_controls = [
            self.doubleSpinBox_irf_threshold_vv,
            self.doubleSpinBox_irf_threshold_vh,
            self.checkBox_irf_one_for_all,
            self.comboBox_irf_select,
            self.doubleSpinBox_shift,
            self.doubleSpinBox_shift_sp,
            self.doubleSpinBox_shift_ss,
            self.spinBox_irf_start,
            self.spinBox_irf_stop,
        ]
        for ctrl in irf_controls:
            # use currentTextChanged or stateChanged automatically based on widget type
            signal = (getattr(ctrl, 'valueChanged', None) or
                      getattr(ctrl, 'stateChanged', None) or
                      getattr(ctrl, 'currentTextChanged'))
            signal.connect(self.on_irf_parameters_changed)

        # detectorsChanged -> _init_channels_from_wizard is wired once in
        # connect_signals(); do NOT connect it again here (a duplicate connection
        # ran the full reinit twice per detector change).

        # --- UI actions ---
        self.tabWidget.currentChanged.connect(self._on_tab_changed)
        # Replace the tab bar with an AutoForm dock area. Deferred so the embedded
        # workflow's synchronous "remove Detector Definition tab" runs first and
        # the dock shell mirrors whatever tabs actually remain.
        QtCore.QTimer.singleShot(0, self._convert_tabs_to_dock_shell)
        # Start hyperparameter optimization
        try:
            self.toolButton_hyper_opt.clicked.connect(
                lambda: self.optimize_hyperparameters(n_iter=int(self.spinBox_n_h_opt.value()))
            )
        except Exception:
            pass

    def initialize_ui_values(self):
        # No need to initialize comboBox_tttr_file_type as we're using channel_definer.filetype instead
        self.micro_time_range = (0, 4096)

        # Robust "quick lifetime" defaults. tau is the only free parameter by
        # default: the scatter fraction (gamma) and anisotropy (r0, rho) are not
        # identifiable from a single-molecule burst decay against an auto-extracted
        # (scatter-shaped) background — left free they rail (gamma -> 1, rho -> 0)
        # and drag tau into a wrong likelihood basin. Fixed at physical nominals
        # they give a stable, sensible lifetime; a user with a *measured* IRF/
        # background can free them for a full anisotropy/scatter fit.
        self.tau = 4.0
        self.gamma = 0.1
        self.r0 = 0.38
        self.rho = 1.22
        self.fix_tau = False
        self.fix_gamma = True
        self.fix_r0 = True
        self.fix_rho = True
        self.min_photons = 10
        self.irf_threshold_vv = 0.02
        self.irf_threshold_vh = 0.02

    def browse_files(self, list_widget):
        dialog = QtWidgets.QFileDialog(self, "Select Files")
        dialog.setFileMode(QtWidgets.QFileDialog.ExistingFiles)
        if dialog.exec_():
            for file in dialog.selectedFiles():
                list_widget.add_file(file)

    def clear_files(self, list_widget):
        # This method resets the associated state (np dicts, df, plot) itself;
        # the list clears are programmatic and do not fire the drop callback.
        if isinstance(list_widget, dict):
            for key, value in list_widget.items():
                value.clear()
        if list_widget == self.burst_files_list:
            self.df_bursts = None
            self.tttrs.clear()  # Properly clear the LazyTTTRDict
            self._tttr_paths.clear()  # Clear the paths dictionary
            self.burst_files_list.clear()
            # No need to reset comboBox_tttr_file_type as we're using channel_definer.filetype instead
        elif list_widget == self.irf_file_widgets:
            self.irf_np.clear()
        else:
            self.bg_np.clear()
        self.combined_plot.clear()

    def update_burst_files(self):
        files = self.burst_files_list.get_selected_files()
        self.current_file_idx = 0
        max_idx = max(0, len(files) - 1)
        self.spinBox_current_file_idx.setMaximum(max_idx)
        if files:
            self.current_filename = str(files[0])
            self.lineEdit_current_filename.setText(self.current_filename)

    def update_irf_files(self, detector=None):
        self._update_hist_files(
            widgets_dict=self.irf_file_widgets,
            np_dict=self.irf_np,
            one_for_all=self.one_for_all_irf,
            normalize=2,
            threshold=-1,
            state_key='irf',
            detector=detector
        )

    def update_bg_files(self, detector=None):
        self._update_hist_files(
            widgets_dict=self.bg_file_widgets,
            np_dict=self.bg_np,
            one_for_all=self.one_for_all_bg,
            normalize=3,
            state_key='bg',
            detector=detector
        )
        # refresh the spinbox whenever bg changes
        self.update_scatter_count_rate_ui()

    def update_current_file(self, index):
        files = self.burst_files_list.get_selected_files()
        if not files or not (0 <= index < len(files)):
            return
        self.current_file_idx = index
        self.current_filename = str(files[index])
        self.update_decay_of_detector()
        self.update_fit()

    def update_scatter_count_rate_ui(self):
        """
        Push the current scatter_count_rate into the spinbox.
        """
        self.doubleSpinBox_scatter_Countrate.setValue(self.scatter_count_rate)

    def load_burst_data(self):
        files = self.burst_files_list.get_selected_files()
        if not files:
            self.df_bursts = None
            self.tttrs.clear()  # Properly clear the LazyTTTRDict
            self._tttr_paths.clear()  # Clear the paths dictionary

            # Disable IRF and BG file drops when all burst files are removed
            self._set_irf_bg_widgets_enabled(False)
        else:
            paris = files[0].parent
            if self.df_bursts is None:
                self.df_bursts = pd.DataFrame()
            df, tttrs = self.read_burst_analysis(paris.parent)
            self.tttrs = tttrs
            self.df_bursts = pd.concat([self.df_bursts, df], ignore_index=True, sort=False)

            # Enable IRF and BG file drops after burst files are loaded
            self._set_irf_bg_widgets_enabled(True)

            # Update excitation period from TTTR header if available
            if self.tttrs:
                # Get the first TTTR in our dict
                tttr = next(iter(self.tttrs.values()))
                try:
                    # Use macro_time_resolution directly (in seconds)
                    # Convert to repetition rate in MHz (1/seconds * 1e-6)
                    repetition_rate = 1.0 / tttr.header.macro_time_resolution * 1e-6

                    if repetition_rate > 0:
                        # Convert repetition rate (MHz) to excitation period (ns)
                        excitation_period = 1000.0 / repetition_rate
                        cs.logging.info(f"Updated excitation period to {excitation_period} ns based on repetition rate {repetition_rate} MHz")
                except (AttributeError, ValueError) as e:
                    cs.logging.info(f"Could not extract repetition rate from header: {e}")

            # Populate the plots on first data load — run "Auto" by default so the
            # panel isn't blank. Deferred so channel/IRF setup finishes first, and
            # guarded so it runs once (not on every re-show / detector switch).
            if not getattr(self, "_auto_populated", False):
                self._auto_populated = True
                QtCore.QTimer.singleShot(0, self._auto_populate_plots)

        self._update_max_bins_from_tttr()

    def _auto_populate_plots(self):
        """Fill the decay/fit plots automatically after the first burst load.

        With an IRF already present (loaded, or sent from IRF & Background), just
        (re)build the decay and fit; otherwise run the full one-click ``Auto``
        (auto-binning + window + IRF extraction + fit). Either way the panel shows
        data + model instead of empty axes. Best-effort — a failure just leaves
        the plots blank, exactly as before.
        """
        try:
            import numpy as _np

            if self.df_bursts is None or not len(self.df_bursts):
                return
            if self._current_tttr() is None:
                return
            det = self.current_detector
            has_irf = det and _np.asarray(self.irf_np.get(det, [])).size > 0
            if has_irf:
                self.update_decay_of_detector()
                self._fit = None
                self.update_fit()
            else:
                self.auto_optimize()  # extracts an IRF + fits (foolproof path)
        except Exception as exc:  # noqa: BLE001
            cs.logging.info(f"MLE auto-populate skipped: {exc}")

    def _save_min_photons_for_current_detector(self, val: int):
        """Persist min_photons in channel_settings for the current detector."""
        try:
            det = self.current_detector
            st = self.channel_settings.get(det, {})
            st['min_photons'] = int(val)
            self.channel_settings[det] = st
        except Exception:
            pass

    def on_micro_time_range_changed(self, _=None):
        # When micro-time window or binning changes: recompute decays AND rebuild
        # the IRF/background at the new binning. The decay length scales with
        # micro_time_binning, so without rebuilding the (file-sourced) IRF/bg here
        # they keep their old length and the fit would run on mismatched arrays.
        # (IRFs injected via Send-to-MLE have no files to rebuild from; update_fit
        # detects the length mismatch and reports it rather than fitting garbage.)
        self.update_irf_files()
        self.update_bg_files()
        self.update_decay_of_detector()
        self._fit = None
        self.update_fit()

        # Additionally refresh per-burst histogram plots
        if self.df_bursts is not None and self.tttrs:
            try:
                self.inspect_bursts(self.burst_idx, embed=True)
            except Exception:
                # keep UI responsive even if burst plot refresh fails
                pass

        # — now *save* the new micro-time state for this detector —
        det = self.current_detector
        st = self.channel_settings.get(det, {})
        st['micro_time_start'], st['micro_time_stop'] = self.micro_time_range
        st['micro_time_binning'] = self.micro_time_binning
        self.channel_settings[det] = st

    def get_current_vv_vhs(self):
        if self.df_bursts is None:
            cs.logging.info("No burst DataFrame loaded.")
            return

        # gather detector channels and microtime settings
        detector_info = getattr(self.channel_definer, 'detectors', {}).get(self.current_detector, {})
        chs = detector_info.get('chs', [])
        if not chs:
            cs.logging.info('Channels not found')
            return

        mt_bin = self.micro_time_binning

        # 1) Which .bur file is selected in the UI?
        curr_bur = Path(self.current_filename).name

        # 2) Check if 'burst_file' column exists in the DataFrame
        if 'burst_file' not in self.df_bursts.columns:
            cs.logging.info(f"'burst_file' column not found in DataFrame. Available columns: {list(self.df_bursts.columns)}")
            # Try to use the first file if burst_file column doesn't exist
            if len(self.df_bursts) > 0:
                df_this = self.df_bursts
                cs.logging.info(f"Using all rows in DataFrame as fallback")
            else:
                cs.logging.info("DataFrame is empty")
                return
        else:
            # Filter df_bursts to just its rows
            df_this = self.df_bursts[self.df_bursts["burst_file"] == curr_bur]
            if df_this.empty:
                cs.logging.info(f"No bursts found for {curr_bur!r}")
                return

        # 3) Now grab the TTTR filename from the first row of that subset
        tttr_name = df_this.loc[df_this.index[0], "First File"]

        # 4) Load or retrieve the TTTR
        key = Path(tttr_name).stem
        cs.logging.debug(f"Looking for TTTR with key: {key}")
        tttr = self.tttrs.get(key)
        if tttr is None:
            cs.logging.info(f"TTTR with key {key} not found.")
            return

        # get the list of photon‐indices for *all* bursts in this file
        indices = self.get_burst_indices_for_current_file()
        if not indices:
            cs.logging.info('No indices found')
            return
        indices = np.array(indices)

        # slice the TTTR down to just burst photons
        burst_tttr = tttr[indices]

        # build the decay histogram over every burst in the file
        vv_vhs = self.make_vv_vh(
            [burst_tttr],
            chs,
            self.micro_time_range,
            mt_bin,
            normalize_counts=-1
        )

        return vv_vhs

    def pass_photon_threshold(self, data, gui: bool = False):
        # check photon threshold
        s = np.sum(data)
        r = s >= self.min_photons
        if not r and gui:
            self._set_status(f"Not Enough Photons: {int(s)} < {self.min_photons}")
        return r

    def update_decay_of_detector(self):
        vv_vhs = self.get_current_vv_vhs()

        if vv_vhs is None:
            return
        data = np.sum(vv_vhs, axis=0)
        self.pass_photon_threshold(data)
        self.decay_of_current_file = data

    def update_fit_ui(self, res: dict):
        # Use property setters to avoid direct widget access and keep side-effects consistent
        try:
            x = res.get('x', res['x'])
        except Exception:
            x = res['x']
        two = float(res['twoIstar']) if 'twoIstar' in res else None

        # Non-fit23 models write to the registry-driven editor, by schema order.
        if self.fit_model != "fit23" and getattr(self, "_dyn_params", None):
            self._dyn_params.set_results(x)
            form = getattr(self, "_dyn_form", None)
            if form is not None:
                form.refresh_plots()
            if two is not None and hasattr(self, "doubleSpinBox_dyn_score"):
                self.doubleSpinBox_dyn_score.setValue(two)
            return

        # fit23: the authored rows (tau/gamma/r0/rho + anisotropy extras).
        self.tau_result = float(x[0])
        self.gamma_result = float(x[1])
        self.r0_result = float(x[2])
        self.rho_result = float(x[3])
        if two is not None:
            self.twoIstar_result = two
        if len(x) > 6:
            self.r_scatter_result = float(x[6])
        if len(x) > 7:
            self.r_exp_result = float(x[7])

    def update_window_combobox(self):
        dets = list(self.channel_definer.detectors.keys())

        self.comboBox_window.clear()
        self.comboBox_window.addItems(dets)
        self.comboBox_window.setCurrentIndex(0)
        self.update_selected_window()

        for cb in (self.comboBox_irf_select, self.comboBox_background_select):
            cb.clear()
            cb.addItems(dets)
            cb.setCurrentIndex(0)

        self._switch_filewidget(self.irf_file_widgets, dets[0])
        self._switch_filewidget(self.bg_file_widgets, dets[0])

    def update_selected_window(self, detectors=None):
        if detectors is None:
            detectors = [self.current_detector]
        elif detectors == "all":
            detectors = self.channel_definer.detectors.keys()

        for detector in detectors:
            info = getattr(self.channel_definer, 'detectors', {}).get(detector, {})
            chs = info.get('chs', [])
            if chs:
                ranges = info.get('micro_time_ranges', [])
                if ranges:
                    raw_start, raw_stop = ranges[0]
                    bin_start = raw_start // self.micro_time_binning
                    bin_stop = raw_stop // self.micro_time_binning
                    self.micro_time_range = (bin_start, bin_stop)
                    self.channel_settings[detector] = self._capture_current_ui_state()

    def stop_burst_processing(self):
        """
        Stop the burst processing when the stop button is clicked.
        """
        self.stop_processing = True
        cs.logging.info("Stop button clicked, stopping burst processing")
        
    def update_parameters(self):
        self._fit = None
        self.update_fit()

    def _find_detector_row(self, detector_name):
        """
        Helper method to find the row index of a detector in the detectors_form table.

        Args:
            detector_name (str): The name of the detector to find.

        Returns:
            int: The row index of the detector, or -1 if not found.
        """
        for row in range(self.channel_definer.detectors_form.rowCount()):
            if self.channel_definer.detectors_form.item(row, 0).text() == detector_name:
                return row
        return -1

    def clear_fit(self):
        self._fit = None

    def create_fit_instance(self):
        sb, eb = self.micro_time_range
        # basic params
        dt = self.dt_effective
        period = self.excitation_period
        gf = self.g_factor
        l1 = self.l1
        l2 = self.l2
        irf = self.irf
        bg = self.bg

        # Ensure arrays are float64 without modifying their shapes or window content
        irf = irf.astype(np.float64, copy=True)
        bg = bg.astype(np.float64, copy=True)

        # Area-normalise the background so gamma is a true 0..1 fraction.
        #
        # Fit23's model adds the background as ``bg[i] * gamma``: gamma is the
        # fraction of the model that is background, which only holds if the
        # background pattern has unit area. Our background is an extracted photon
        # histogram summing to tens of thousands of counts, so a raw pattern made
        # gamma an enormous multiplier — for any gamma > 0 the model amplitude
        # blew up by ~sum(bg) and the free-gamma fit diverged to gamma≈1. (The
        # normalisation is done here, not in tttrlib's modelf, because that model
        # is the cross-language Python/R/Java reference contract; gamma weighting
        # a caller-normalised background keeps the fit correct without changing
        # it.) A near-zero-sum background is left as-is.
        bg_sum = float(bg.sum())
        if bg_sum > 0.0:
            bg = bg / bg_sum

        # Build the fit for the selected model. The estimator class is taken from
        # the tttrlib registry entry's ``method`` field (no hardcoded mapping);
        # all fit2x estimators share the Fit23 constructor + __call__ interface.
        cls = self._fit_class()
        fit = cls(
            dt=dt,
            irf=irf,
            background=bg,
            period=period,
            g_factor=gf,
            l1=l1,
            l2=l2,
            p2s_twoIstar_flag=self.p2s_twoIstar,
            soft_bifl_scatter_flag=self.BIFL_scatter
        )
        return fit

    def update_fit(self):
        """Re-optimise the current file's decay and redraw both plots.

        Runs on every relevant parameter change (fix flags, IRF shift/threshold,
        fixed-parameter values, detector/file) so the plot stays live. Changing a
        *free* parameter's initial value re-converges to the same optimum by
        design — fix the parameter to pin it to a chosen value.
        """
        x0, fixed = self.fit_parameters
        sb, eb = self.micro_time_range
        det = self.current_detector
        decay = self.decay_of_current_file

        # Surface why a fit can't run instead of returning silently (which left a
        # stale/blank plot with no explanation — the classic "nothing happens").
        reason = self._fit_blocked_reason(det, decay)
        if reason is not None:
            cs.logging.info("MLE fit skipped: %s", reason)
            self._set_status(f"Cannot fit: {reason}")
            return

        self._fit = None

        # use full-length decay (already zeroed outside window)
        d = decay.astype(np.float64, copy=False)
        # Guard against a decay whose length no longer matches the IRF (e.g. after
        # a binning change): the C++ fit is now hardened against this, but skip
        # rather than fit meaningless mismatched arrays.
        irf_len = int(np.asarray(self.irf_np.get(det, [])).size)
        if irf_len and len(d) != irf_len:
            msg = (f"decay length {len(d)} != IRF length {irf_len} for {det!r} "
                   f"(rebuild IRF at the current binning)")
            cs.logging.info("MLE fit skipped: %s", msg)
            self._set_status(f"Cannot fit: {msg}")
            return
        if self.fit_model == "tail":
            res = self._run_tail_fit(d, det)
        else:
            res = self.fit(data=d, initial_values=x0, fixed=fixed)
        self.plot_fit_result(res)
        diverged = self._fit_diverged(res)
        if diverged is None:
            self._set_status("")
        else:
            self._set_status(f"Fit diverged: {diverged}")

    def _fit_blocked_reason(self, det, decay):
        """Human-readable reason the fit cannot run, or None when it can."""
        if not det:
            return "no detector selected"
        # The tail fit needs no IRF (the prompt is excluded, not deconvolved).
        if self.fit_model != "tail" and (
                det not in self.irf_np or np.asarray(self.irf_np.get(det, [])).size == 0):
            return f"no IRF for detector {det!r} (load or send an IRF)"
        if det not in self.bg_np or np.asarray(self.bg_np.get(det, [])).size == 0:
            return f"no background for detector {det!r}"
        if decay is None or np.asarray(decay).size == 0:
            return "no decay (load bursts / select a file)"
        return None

    def _fit_diverged(self, fit_result) -> typing.Optional[str]:
        """Human-readable reason the fit result is non-physical, or ``None``.

        Freeing ``gamma`` (the scattered-light fraction) is legitimate but
        poorly constrained when the IRF is the auto-extracted, decay-shaped one:
        the optimiser walks ``gamma`` to its bound (~0.999), where Fit23 returns
        an invalid quality (2I* < 0) and a model whose amplitude has run away by
        orders of magnitude. Plotting that raw blows the display up to ~1e6. This
        flags the case so the caller can warn instead of showing garbage; the
        parameters are still displayed so the user sees ``gamma`` pinned at its
        bound.
        """
        try:
            two_istar = float(fit_result.get("twoIstar", 0.0))
        except Exception:
            two_istar = 0.0
        if not np.isfinite(two_istar) or two_istar < 0.0:
            return "invalid fit quality (2I* < 0) — gamma is unconstrained; " \
                   "re-fix gamma or use a measured IRF/background"
        model = np.asarray(getattr(self.fit, "model", []), dtype=float)
        if model.size and not np.all(np.isfinite(model)):
            return "model has non-finite values"
        data = np.asarray(getattr(self.fit, "data", []), dtype=float)
        s_dat = float(np.nansum(data)) if data.size else 0.0
        s_mod = float(np.nansum(model)) if model.size else 0.0
        if s_dat > 0.0 and s_mod > 20.0 * s_dat:
            return "model amplitude diverged — gamma is unconstrained; " \
                   "re-fix gamma or use a measured IRF/background"
        return None

    def _run_tail_fit(self, d, det):
        """Fit the decay *tail* with ``DecayFitNExp`` (no IRF deconvolution).

        The tail fit is a different estimator family from the fit2x models: each
        exponential is a pure decay from ``tail_start`` and the prompt/rise is
        excluded, which is the standard treatment for FRET sensitised-emission
        decays. The recovered lifetimes/amplitudes are read from the
        registry-driven editor's ``tail_start`` + ``tauN`` rows.

        Returns a result dict shaped like the fit2x path (``x`` in schema order,
        ``twoIstar`` = negative log-likelihood) and stores a lightweight view on
        ``self._fit`` so :meth:`plot_fit_result` reads ``.data``/``.model``
        unchanged.
        """
        from types import SimpleNamespace

        rows = self._dyn_params
        values, flags = rows.initial_values(), rows.fixed_flags()
        start = rows.index_of("tail_start")
        tail_start = int(round(values[start])) if start >= 0 else 0
        keep = [i for i, nm in enumerate(rows.names) if nm != "tail_start"]
        lifetimes = [values[i] for i in keep]
        fixed = [flags[i] for i in keep]
        amps = [1.0 / len(lifetimes)] * len(lifetimes) if lifetimes else []

        d = np.asarray(d, dtype=np.float64)
        n = len(d) // 2
        bg_full = np.asarray(self.bg, dtype=np.float64)
        bg_half = bg_full[:n] if bg_full.size >= n else np.zeros(n, dtype=np.float64)
        irf_half = np.zeros(n, dtype=np.float64)          # ignored in tail mode

        opts = tttrlib.DecayFitNExpOptions()
        opts.dt = float(self.dt_effective)
        opts.period = float(self.excitation_period)
        opts.tail_start = int(tail_start)
        opts.include_model = True

        res = tttrlib.DecayFitNExp.fit(
            list(d),
            list(irf_half),
            list(bg_half),
            [float(x) for x in lifetimes],
            [float(x) for x in amps],
            [int(x) for x in fixed],
            opts,
        )
        model = np.asarray(res.model, dtype=float)
        if model.size != d.size:
            model = np.zeros_like(d)
        # Expose the fit through the same interface the fit2x path uses.
        self._fit = SimpleNamespace(data=d, model=model)
        recovered = list(res.lifetimes) if getattr(res, "lifetimes", None) else lifetimes
        # x in schema order: tail_start then the recovered lifetimes.
        x = [float(tail_start)] + [float(v) for v in recovered]
        return {"x": x, "twoIstar": float(getattr(res, "negative_log_likelihood", 0.0))}

    @property
    def fit_model(self) -> str:
        """The selected tttrlib fit model (``fit23``/``fit24``/…)."""
        combo = getattr(self, "comboBox_fit_model", None)
        return (combo.currentData() if combo is not None else None) or "fit23"

    def _is_fit2x_constructible(self, model: str) -> bool:
        """Whether ``model``'s estimator is built from dt/IRF/background.

        The burst-MLE workflow constructs every fit from the acquisition inputs
        (``dt``, ``irf``, ``background``, …). Some registry models (e.g. fit26,
        pattern fractioning) take reference decays instead, so their class does
        not accept that construction; those are not offered here. Determined from
        the class the registry names, not a hardcoded list.
        """
        try:
            import inspect
            from chisurf.core import tttrlib_registry as _reg
            method = _reg.describe(_reg.FIT_MODEL, model).get("method")
            cls = getattr(tttrlib, method, None) if method else None
            if cls is None:
                return False
            # The fit2x estimators delegate construction to their shared base
            # (``*args, **kwargs``); a class that instead declares reference-decay
            # inputs (``pattern_1``/``pattern_2``, e.g. fit26) is not built from
            # an IRF here.
            params = inspect.signature(cls.__init__).parameters
            return "pattern_1" not in params and "pattern_2" not in params
        except Exception:
            return False

    def _fit_class(self):
        """The tttrlib estimator class for the selected model, from the registry.

        The class name comes from the registry entry's ``method`` field, so no
        model→class table is hardcoded here; falls back to ``Fit23``.
        """
        try:
            from chisurf.core import tttrlib_registry as _reg
            method = _reg.describe(_reg.FIT_MODEL, self.fit_model).get("method")
            if method:
                cls = getattr(tttrlib, method, None)
                if cls is not None:
                    return cls
        except Exception:
            pass
        return tttrlib.Fit23

    @staticmethod
    def _tail_schema() -> dict:
        """Local schema for the multi-exponential tail fit (not a fit2x model).

        The tail fit is ``DecayFitNExp`` with ``tail_start`` — a different fitter
        family, so its parameters (a tail-start channel + N lifetimes) are
        described here rather than in tttrlib's fit2x registry.
        """
        return {
            "properties": {
                "tail_start": {
                    "title": "Tail start (ch.)", "default": 20.0,
                    "minimum": 0.0, "maximum": 100000.0, "fixed_default": True,
                    "description": "First channel of the tail; earlier channels "
                                   "(the rise/prompt) are excluded from the fit.",
                },
                "tau1": {
                    "title": "Lifetime τ1 (ns)", "default": 2.0,
                    "minimum": 0.01, "maximum": 100.0, "fixed_default": False,
                    "description": "First tail lifetime.",
                },
                "tau2": {
                    "title": "Lifetime τ2 (ns)", "default": 0.5,
                    "minimum": 0.01, "maximum": 100.0, "fixed_default": False,
                    "description": "Second tail lifetime (fix or set equal to τ1 "
                                   "for a mono-exponential tail).",
                },
            },
            "required": ["tail_start", "tau1", "tau2"],
        }

    def _model_schema(self, model: str) -> dict:
        """Parameter schema for ``model`` — tttrlib fit2x registry, or tail."""
        if model == "tail":
            return self._tail_schema()
        try:
            from chisurf.core import tttrlib_registry as _reg
            return _reg.describe(_reg.FIT_MODEL, model).get("params_schema") or {}
        except Exception:
            return {}

    def _fit_param_names(self, model: str) -> list:
        """Ordered parameter names for ``model`` from its schema.

        Uses the schema ``properties`` order, which (for fit2x) the registry
        guarantees to match the estimator's ``initial_values`` layout. Falls back
        to ``required`` then to the fit23 set.
        """
        schema = self._model_schema(model)
        props = schema.get("properties")
        if props:
            return list(props.keys())
        required = schema.get("required")
        if required:
            return list(required)
        return ["tau", "gamma", "r0", "rho"]

    def _rebuild_dyn_params(self, model: str) -> None:
        """(Re)build the schema-driven parameter rows for a non-fit23 model.

        Rows are the estimator's parameters and columns are the three things one
        does with each — start it somewhere, hold it there, read what came back.
        That is the shape of the general ``state_table`` section, so the rows are
        *declared* here rather than built: forty lines of grid assembly became a
        view-model holding four lists, which is also what the fit reads from, so
        there is no longer a set of widgets standing between the schema and the
        estimator.
        """
        from chisurf.gui.autoform import AutoForm

        while self._dyn_grid.count():
            item = self._dyn_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        schema = self._model_schema(model)
        props = schema.get("properties") or {}
        rows = _MleParameterRows()
        for name in self._fit_param_names(model):
            spec = props.get(name, {})
            rows.append(
                name=name,
                label=spec.get("title", name),
                description=spec.get("description", ""),
                value=float(spec.get("default", 0.0)),
                fixed=bool(spec.get("fixed_default", False)),
                minimum=float(spec.get("minimum", -1e9)),
                maximum=float(spec.get("maximum", 1e9)),
            )
        rows.changed = self.update_variable_fit_parameters
        self._dyn_params = rows
        self._dyn_form = AutoForm(rows)
        self._dyn_grid.addWidget(self._dyn_form, 0, 0)

        _score = QtWidgets.QLabel("Score")
        self.doubleSpinBox_dyn_score = self._dsb(
            decimals=3, minimum=-99999.0, maximum=99999.0, readonly=True, nobuttons=True)
        self._dyn_grid.addWidget(_score, 1, 0)
        self._dyn_grid.addWidget(self.doubleSpinBox_dyn_score, 1, 1)

    def _on_fit_model_changed(self, _index: int = 0) -> None:
        """Switch the parameter editor and refit for the selected model.

        fit23 uses its authored rows (with the anisotropy extras); every other
        model uses the registry-driven editor rebuilt from the tttrlib schema.
        The two panels swap visibility so fit23 is never disturbed.
        """
        model = self.fit_model
        is23 = model == "fit23"
        self.groupBox_model_params.setVisible(is23)
        self.groupBox_dyn_params.setVisible(not is23)
        if not is23:
            self._rebuild_dyn_params(model)
        self._fit = None
        self.update_fit()
        self._set_status("" if is23 else f"Fitting with {self.comboBox_fit_model.currentText()}.")

    def _set_status(self, text: str):
        """Show a short status message where the host offers one; never crash."""
        try:
            bar = self.statusBar() if hasattr(self, "statusBar") else None
            if bar is not None:
                bar.showMessage(text)
        except Exception:
            pass

    def _current_tttr(self):
        """The TTTR object backing the currently selected burst file, or None."""
        if self.df_bursts is None or not self.tttrs:
            return None
        df = self.df_bursts
        curr = Path(self.current_filename).name if self.current_filename else None
        if "burst_file" in df.columns and curr:
            sub = df[df["burst_file"] == curr]
            if not sub.empty:
                df = sub
        if "First File" not in df.columns or df.empty:
            return None
        return self.tttrs.get(Path(df.iloc[0]["First File"]).stem)

    def _irf_fwhm_channels(self):
        """FWHM of the scatter IRF prompt in RAW micro-time channels, or ``None``.

        Measured from the current detector's non-burst photons (the scatter
        prompt whose width *is* the instrument response). This sets how finely
        the micro-time axis can be *meaningfully* binned: binning far below the
        IRF width only spreads the same counts over more empty bins without
        adding time resolution (see :meth:`_auto_select_binning`).
        """
        tttr = self._current_tttr()
        det = self.current_detector
        info = getattr(self.channel_definer, 'detectors', {}).get(det, {})
        chs = info.get('chs', [])
        if tttr is None or not chs:
            return None
        idx = np.asarray(self.get_burst_indices_for_current_file(), dtype=int)
        if idx.size == 0:
            return None
        try:
            n_full = int(tttr.header.number_of_micro_time_channels)
        except Exception:
            return None
        if n_full <= 0:
            return None
        non_burst = np.ones(len(tttr), dtype=bool)
        non_burst[idx] = False
        sel = non_burst & np.isin(np.asarray(tttr.routing_channels),
                                  np.asarray(chs, dtype=int))
        micro = np.asarray(tttr.micro_times)[sel]
        micro = micro[(micro >= 0) & (micro < n_full)]
        if micro.size == 0:
            return None
        hist = np.bincount(micro, minlength=n_full)[:n_full].astype(float)
        pk = hist.max()
        if pk <= 0:
            return None
        above = np.where(hist >= 0.5 * pk)[0]
        if above.size == 0:
            return None
        return int(above[-1] - above[0] + 1)

    def _auto_select_binning(self, target_counts_per_bin: float = 10.0,
                             irf_oversample: float = 8.0):
        """Pick a micro-time binning that is neither too fine nor too coarse.

        Two floors set the coarsest-needed binning; the larger wins:

        * **Statistics.** A burst decay is sparse: this file's green burst
          photons (~8.6k) over the full 2×4096-channel Jordi are ~1 count/bin,
          and a maximum-likelihood ``Fit23`` on near-empty bins rails ``tau`` to
          the excitation period (an unphysical "flat" model). Coarsen until the
          bins hold ~``target_counts_per_bin`` counts.
        * **IRF resolution.** Binning finer than the IRF resolves nothing — it
          only adds empty bins. Keep the bin width at or above
          ``IRF_FWHM / irf_oversample`` channels. This is what makes "too fine"
          depend on the IRF: a broad IRF forces coarser bins, a sharp one allows
          finer.

        Returns a value from the binning combo, or ``None`` when the photon count
        can't be determined (caller keeps the current binning).
        """
        tttr = self._current_tttr()
        det = self.current_detector
        info = getattr(self.channel_definer, 'detectors', {}).get(det, {})
        chs = info.get('chs', [])
        if tttr is None or not chs:
            return None
        idx = np.asarray(self.get_burst_indices_for_current_file(), dtype=int)
        if idx.size == 0:
            return None
        rc = np.asarray(tttr.routing_channels)[idx]
        counts = int(np.isin(rc, np.asarray(chs, dtype=int)).sum())
        try:
            n_full = int(tttr.header.number_of_micro_time_channels)
        except Exception:
            return None
        if counts <= 0 or n_full <= 0:
            return None
        # Statistics floor: counts/bin = counts * binning / (2 halves * n_full).
        need_stat = target_counts_per_bin * 2.0 * n_full / counts
        # IRF-resolution floor: bin width (channels) >= FWHM / oversample.
        fwhm = self._irf_fwhm_channels()
        need_irf = (fwhm / irf_oversample) if (fwhm and irf_oversample > 0) else 0.0
        need = max(need_stat, need_irf)
        combo = self.channel_definer.micro_binning_combo
        choices = sorted(int(combo.itemText(i)) for i in range(combo.count()))
        for c in choices:
            if c >= need:
                return c
        return choices[-1]

    def _auto_select_fit_range(self, lo_frac: float = 0.02):
        """Set ``micro_time_range`` to the filled region of the current decay.

        Empty pre-prompt bins and the noise tail carry no lifetime information;
        for a maximum-likelihood fit they are just near-zero bins that add noise
        and, at a too-fine binning, destabilise it. The window is set from one
        bin before the rising edge to one bin past the last populated bin (in the
        current binning's units), spanning both Jordi halves symmetrically.
        """
        decay = self.decay_of_current_file
        if decay is None:
            return
        d = np.asarray(decay, dtype=float)
        nb = d.size // 2
        if nb < 4:
            return
        tot = d[:nb] + d[nb:2 * nb]
        pk = float(tot.max()) if tot.size else 0.0
        if pk <= 0.0:
            return
        filled = np.where(tot > lo_frac * pk)[0]
        if filled.size == 0:
            return
        onset = int(max(0, int(filled[0]) - 1))
        last = int(min(nb, int(filled[-1]) + 2))
        if last - onset < 4:
            return
        self.micro_time_range = (onset, last)

    def auto_optimize(self):
        """One-click "make it work": auto binning + fit window, then refit.

        The general auto-optimiser. Re-derives the micro-time binning (count- and
        IRF-resolution-aware, :meth:`_auto_select_binning`) and the fit window
        (the decay's filled region, :meth:`_auto_select_fit_range`) from the data
        and refits — keeping whatever IRF/background source is in use:

        * **Auto-extracted IRF** (no IRF files loaded): delegate to
          :meth:`auto_extract_irf_bg`, which re-estimates the IRF/background at
          the new binning as well. This is the foolproof path.
        * **Measured IRF** (files loaded): changing the binning rebuilds the
          file-sourced IRF/background and the decay via the binning-changed
          cascade; we then restrict the window and refit, leaving the measured
          IRF untouched.
        """
        tttr = self._current_tttr()
        if tttr is None:
            self._set_status("Load bursts first — nothing to optimise")
            return

        det = self.current_detector
        fw = self.irf_file_widgets.get(det)
        has_irf_file = bool(fw and fw.get_selected_files())
        if not has_irf_file:
            # No measured IRF for this detector: the extraction path already does
            # binning + extract-at-binning + window + fit.
            self.auto_extract_irf_bg()
            return

        # Measured IRF: coarsen the binning (rebuilds the file-sourced IRF/bg and
        # the decay through on_micro_time_range_changed), then window + refit.
        pick = self._auto_select_binning()
        combo = self.channel_definer.micro_binning_combo
        if pick is not None and str(pick) != combo.currentText():
            combo.setCurrentText(str(pick))
        else:
            self.update_decay_of_detector()
        start = self.spinBox_micro_time_start.blockSignals(True)
        stop = self.spinBox_micro_time_stop.blockSignals(True)
        try:
            self._auto_select_fit_range()
        finally:
            self.spinBox_micro_time_start.blockSignals(start)
            self.spinBox_micro_time_stop.blockSignals(stop)
        self.update_decay_of_detector()
        self._fit = None
        self.update_fit()
        self._set_status(
            f"Auto-optimised (measured IRF): binning {self.micro_time_binning}, "
            f"window {self.micro_time_range}."
        )

    def auto_extract_irf_bg(self):
        """One-click IRF/background from this file's NON-burst photons.

        A convenience for a quick lifetime: the scatter/background under the
        bursts is estimated from the photons the burst search rejected. It is an
        approximation — a measured experimental IRF and buffer background give
        more reliable lifetimes (see the warning shown next to the button).

        Also auto-selects a micro-time binning that gives well-populated bins, so
        the fit does not rail on a too-fine (sparse) default — see
        :meth:`_auto_select_binning`.
        """
        from chisurf.core.fluorescence.burst import extract_mle_irf_background

        tttr = self._current_tttr()
        if tttr is None:
            self._set_status("Load bursts first — no data to extract an IRF from")
            return
        idx = np.asarray(self.get_burst_indices_for_current_file(), dtype=int)
        if idx.size == 0:
            self._set_status("No burst photons found for the selected file")
            return

        # Coarsen the micro-time axis first so the extraction (and the fit) run at
        # a binning whose bins carry counts. Setting the combo cascades a rebuild;
        # block it (we rebuild IRF/bg/decay ourselves just below at this binning).
        pick = self._auto_select_binning()
        combo = self.channel_definer.micro_binning_combo
        if pick is not None and str(pick) != combo.currentText():
            blocked = combo.blockSignals(True)
            try:
                combo.setCurrentText(str(pick))
            finally:
                combo.blockSignals(blocked)
            self._update_max_bins_from_tttr()
        in_burst = np.zeros(len(tttr), dtype=bool)
        in_burst[idx] = True
        try:
            irf_model = "gaussian"
            combo = getattr(self, "comboBox_irf_model", None)
            if combo is not None and combo.currentData():
                irf_model = str(combo.currentData())
            patterns = extract_mle_irf_background(
                tttr,
                self.channel_definer.detectors,
                micro_time_binning=self.micro_time_binning,
                mask=~in_burst,
                min_photons=max(2, int(self.min_photons)),
                irf_model=irf_model,
            )
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"IRF extraction failed: {exc}")
            return
        n = 0
        for det, pat in patterns.items():
            if det:  # skip any stray empty-name key
                self.irf_np[det] = np.asarray(pat["irf"], dtype=float)
                self.bg_np[det] = np.asarray(pat["bg"], dtype=float)
                n += 1
        # Build the decay once at the new binning, then restrict the fit window to
        # its filled region and rebuild so the windowed decay is what we fit.
        self.update_decay_of_detector()
        start = self.spinBox_micro_time_start.blockSignals(True)
        stop = self.spinBox_micro_time_stop.blockSignals(True)
        try:
            self._auto_select_fit_range()
        finally:
            self.spinBox_micro_time_start.blockSignals(start)
            self.spinBox_micro_time_stop.blockSignals(stop)
        self.update_decay_of_detector()
        self._fit = None
        self.update_fit()
        self._set_status(
            f"Auto IRF/background estimated from non-burst photons for {n} "
            f"detector(s) (binning {self.micro_time_binning}, "
            f"window {self.micro_time_range}). For best lifetimes, use a "
            f"measured IRF/background."
        )

    def go_to_irf_bg(self):
        """Jump to the workflow's 'IRF & Background' step (when embedded)."""
        host = self.parent()
        while host is not None and not hasattr(host, "goto_workflow_role"):
            host = host.parentWidget() if hasattr(host, "parentWidget") else None
        if host is not None:
            host.goto_workflow_role("irf_bg")
        else:
            self._set_status(
                "Open the Burst Analysis workflow to use the IRF & Background step"
            )

    def _get_channel_ranges_bins(self):
        """Return per-channel (vv, vh) start/stop in histogram bins for current detector.
        Falls back to the global micro_time_range if specific ranges are not available.
        """
        # default fallback
        sb_def, eb_def = self.micro_time_range
        sb_vv = sb_def
        eb_vv = eb_def
        sb_vh = sb_def
        eb_vh = eb_def
        try:
            info = getattr(self.channel_definer, 'detectors', {}).get(self.current_detector, {})
            ranges = info.get('micro_time_ranges', None)
            if ranges and len(ranges) >= 2:
                raw_vv = ranges[0]
                raw_vh = ranges[1]
                # convert raw (in native bins) to our current binned indices
                binning = max(1, int(self.micro_time_binning))
                sb_vv = int(raw_vv[0] // binning)
                eb_vv = int(raw_vv[1] // binning)
                sb_vh = int(raw_vh[0] // binning)
                eb_vh = int(raw_vh[1] // binning)
        except Exception:
            pass
        return sb_vv, eb_vv, sb_vh, eb_vh

    def plot_fit_result(self, fit_result):
        cs.logging.info("plot fit result")
        # clear both panels
        self.combined_plot.clear()
        self.residual_plot.clear()
        # The legend survives clear(); empty it so the replotted curves below add
        # exactly one row each rather than stacking a fresh set every fit.
        legend = getattr(self, "combined_legend", None)
        if legend is not None:
            legend.clear()
        sb, eb = self.micro_time_range

        # only plot if we actually loaded IRF *and* BG for this detector
        # (the tail fit needs no IRF, so require only BG there)
        det = self.current_detector
        if det not in self.bg_np:
            return
        if self.fit_model != "tail" and det not in self.irf_np:
            return

        # plot data and model in the bottom panel, but only within channel-specific ranges
        data_full = np.asarray(self.fit.data)
        model_full = np.asarray(self.fit.model)
        n = len(data_full) // 2
        vv_sb, vv_eb, vh_sb, vh_eb = self._get_channel_ranges_bins()
        # clamp
        vv_sb = max(0, int(vv_sb)); vv_eb = min(n, int(vv_eb)) if vv_eb is not None else n
        vh_sb = max(0, int(vh_sb)); vh_eb = min(n, int(vh_eb)) if vh_eb is not None else n
        data_vv = data_full[0:n][vv_sb:vv_eb]
        data_vh = data_full[n:2*n][vh_sb:vh_eb]
        model_vv = model_full[0:n][vv_sb:vv_eb]
        model_vh = model_full[n:2*n][vh_sb:vh_eb]
        data_rng = np.hstack([data_vv, data_vh])
        model_rng = np.hstack([model_vv, model_vh])
        # A diverged fit (gamma pinned at its bound) returns a model whose
        # amplitude has run away by orders of magnitude; plotted raw it blows the
        # log view up to ~1e6 and hides the data. Clip the *displayed* model to a
        # little above the data's own range so the panel stays readable — the fit
        # parameters shown are untouched, and the status bar says it diverged.
        diverged = self._fit_diverged(fit_result)
        model_disp = np.nan_to_num(model_rng, nan=0.0, posinf=0.0, neginf=0.0)
        if diverged is not None and data_rng.size:
            cap = float(np.nanmax(data_rng)) * 10.0
            if cap > 0:
                model_disp = np.clip(model_disp, 0.0, cap)
        self.combined_plot.plot(data_rng,
                                pen=None,
                                symbol='o',
                                symbolSize=3,
                                name='Data (VV|VH)')
        self.combined_plot.plot(model_disp, pen='g', name='Model (fit)')

        # Plot IRF & BG within per-channel windows
        irf_full = self.irf.astype(np.float64, copy=True)
        bg_full = self.bg.astype(np.float64, copy=True)

        n = len(irf_full) // 2
        vv_sb, vv_eb, vh_sb, vh_eb = self._get_channel_ranges_bins()
        vv_sb = max(0, int(vv_sb)); vv_eb = min(n, int(vv_eb)) if vv_eb is not None else n
        vh_sb = max(0, int(vh_sb)); vh_eb = min(n, int(vh_eb)) if vh_eb is not None else n

        irf_rng = np.hstack([irf_full[0:n][vv_sb:vv_eb], irf_full[n:2*n][vh_sb:vh_eb]])
        bg_rng = np.hstack([bg_full[0:n][vv_sb:vv_eb], bg_full[n:2*n][vh_sb:vh_eb]])

        # Scale IRF and background to the data amplitude for display only. Both
        # keep their SHAPE (the scatter/background is not flat — it has the
        # scattered-excitation shape); we area-normalise each and match it to the
        # data's total so it overlays legibly without swamping the decay. Peak
        # (max) normalisation would be thrown off by a single hot bin. The
        # background's actual fit weight is the scatter parameter, not this curve.
        s_dat = float(np.sum(data_rng)) if data_rng.size else 0.0

        def _overlay(arr):
            s = float(np.sum(arr))
            return arr / s * s_dat if (s > 0 and s_dat > 0) else arr

        irf_rng = _overlay(irf_rng)
        bg_rng = _overlay(bg_rng)

        # The tail fit does not deconvolve the IRF, so an IRF overlay would be
        # misleading (and may be a synthetic fallback of the wrong length).
        if self.fit_model != "tail":
            self.combined_plot.plot(irf_rng, pen='r', name='IRF')
        self.combined_plot.plot(bg_rng, pen='b', name='Background')

        # compute & plot weighted residuals
        data = np.asarray(self.fit.data, dtype=float)
        model = np.asarray(self.fit.model, dtype=float)

        resid = np.zeros_like(data, dtype=float)
        mask = data > 0
        resid[mask] = (data[mask] - model[mask]) / np.sqrt(data[mask])

        # draw residuals in the top panel only within per-channel ranges
        pen = pg.mkPen(color=(200, 20, 20), width=1)
        resid = np.asarray(resid)
        n = len(resid) // 2
        vv_sb, vv_eb, vh_sb, vh_eb = self._get_channel_ranges_bins()
        vv_sb = max(0, int(vv_sb)); vv_eb = min(n, int(vv_eb)) if vv_eb is not None else n
        vh_sb = max(0, int(vh_sb)); vh_eb = min(n, int(vh_eb)) if vh_eb is not None else n
        resid_rng = np.hstack([resid[0:n][vv_sb:vv_eb], resid[n:2*n][vh_sb:vh_eb]])

        self.residual_plot.plot(resid_rng,
                                pen=pen,
                                symbol='o',
                                symbolSize=3)

        # Pin both plots to sane ranges. A background-dominated or diverged fit
        # can make the model / scaled background span ~1e±27, which explodes
        # pyqtgraph's log auto-range (the "x1e+27 / 10^-277" axis). Anchor the
        # Intensity view to the DATA's dynamic range and the residuals to a
        # symmetric band around the actual spread.
        self._pin_decay_yrange(data_rng)
        self._pin_residual_yrange(resid_rng)

        self.update_fit_ui(fit_result)

    def _pin_decay_yrange(self, data_rng):
        """Fix the Intensity (log-y) view to the data's range; disable autorange."""
        import math
        d = np.asarray(data_rng, dtype=float)
        d = d[np.isfinite(d) & (d > 0)]
        vb = self.combined_plot.getViewBox()
        try:
            vb.enableAutoRange(axis=vb.YAxis, enable=False)
            if d.size:
                lo = math.log10(max(float(d.min()) * 0.5, 1e-2))
                hi = math.log10(float(d.max()) * 3.0)
                if hi <= lo:
                    hi = lo + 1.0
                self.combined_plot.setYRange(lo, hi, padding=0.0)
            else:
                self.combined_plot.setYRange(-1, 5, padding=0.0)
        except Exception:
            pass

    def _pin_residual_yrange(self, resid_rng):
        """Clamp the residual view to a symmetric band so a bad fit can't run off."""
        r = np.asarray(resid_rng, dtype=float)
        r = r[np.isfinite(r)]
        vb = self.residual_plot.getViewBox()
        try:
            vb.enableAutoRange(axis=vb.YAxis, enable=False)
            span = float(np.nanpercentile(np.abs(r), 99)) if r.size else 5.0
            span = max(span, 5.0)
            self.residual_plot.setYRange(-span, span, padding=0.05)
        except Exception:
            pass

    def _build_irf_bg_cache(self):
        irf_cache = {}
        bg_cache = {}
        for det in self.channel_definer.detectors.keys():
            st = self._ensure_channel_state(det)
            # Raw IRF/BG come from the single source of truth (irf_np/bg_np), not
            # channel_settings; this method applies shift/window/threshold below.
            raw_irf = np.array(self.irf_np.get(det, []), dtype=np.float64, copy=True)
            raw_bg = np.array(self.bg_np.get(det, []), dtype=np.float64, copy=True)

            # Process IRF: 1) global VH shift; 2) sub-bin shifts; 3) IRF range; 4) thresholding
            if raw_irf.size > 0:
                half = raw_irf.size // 2
                sp = raw_irf[:half].astype(np.float64, copy=True)
                ss = raw_irf[half:].astype(np.float64, copy=True)
                # 1) global integer shift on VH
                if self.shift != 0:
                    ss = np.roll(ss, self.shift)
                # 2) individual sub-bin shifts
                sp = interpolate_shift(sp, self.shift_sp)
                ss = interpolate_shift(ss, self.shift_ss)
                # 3) IRF range windowing
                start = int(self.irf_start)
                stop = int(self.irf_stop)
                if start >= 0:
                    sp[:max(0, start)] = 0
                    ss[:max(0, start)] = 0
                if stop >= 0 and stop + 1 < sp.size:
                    sp[stop + 1:] = 0
                if stop >= 0 and stop + 1 < ss.size:
                    ss[stop + 1:] = 0
                # 4) thresholding per channel
                th_vv = float(self.irf_threshold_vv)
                th_vh = float(self.irf_threshold_vh)
                if th_vv > 0 and sp.size and sp.max() > 0:
                    sp[sp < th_vv * sp.max()] = 0
                if th_vh > 0 and ss.size and ss.max() > 0:
                    ss[ss < th_vh * ss.max()] = 0
                irf_cache[det] = np.hstack([sp, ss])
            else:
                irf_cache[det] = raw_irf

            # Process BG: apply only global VH shift (background is not thresholded/ranged here)
            if raw_bg.size > 0:
                half_bg = raw_bg.size // 2
                vv = raw_bg[:half_bg].astype(np.float64, copy=True)
                vh = raw_bg[half_bg:].astype(np.float64, copy=True)
                if self.shift != 0:
                    vh = np.roll(vh, self.shift)
                bg_cache[det] = np.hstack([vv, vh])
            else:
                bg_cache[det] = raw_bg
        return irf_cache, bg_cache

    @staticmethod
    def _hist2_split(mt_bins: np.ndarray,
                     rc_slice: np.ndarray,
                     is_p_lut: np.ndarray,
                     is_s_lut: np.ndarray,
                     half_len: int):
        """
        One-pass P/S histogram:
          - classify photons as 0(P) / 1(S) via LUTs
          - bincount(mt*2 + cls, minlength=2*half_len)
          - deinterleave to cp/cs_hist
        Returns uint32 arrays; cast to float only when filling the decay buffer.
        """
        cls = np.full(rc_slice.shape[0], -1, dtype=np.int8)
        pm = is_p_lut[rc_slice]
        sm = is_s_lut[rc_slice]
        cls[pm] = 0
        cls[sm] = 1
        valid = cls >= 0
        if not np.any(valid):
            return (np.zeros(half_len, dtype=np.uint32),
                    np.zeros(half_len, dtype=np.uint32))
        b = mt_bins[valid]
        c = cls[valid].astype(np.int32, copy=False)
        h2 = np.bincount(b * 2 + c, minlength=2 * half_len)
        return (h2[0::2].astype(np.uint32, copy=False),
                h2[1::2].astype(np.uint32, copy=False))

    def _set_inputs_frozen(self, frozen: bool) -> None:
        """Make the wizard read-only (or not) while a batch runs.

        A batch reads its configuration once -- IRF and background caches, the
        per-detector channel state, the start vector -- and hands it to the
        worker processes. If the user can still edit a spin box while the run is
        in flight, part of the table is computed under one configuration and
        part under another, with nothing to show for it afterwards.

        Freezing the central widget rather than each control keeps this honest
        as the wizard grows: a control added later is frozen too, including the
        action row at the top (Auto IRF, the IRF-shape choice, Opt) — which
        lives *inside* the central widget here, not in a `QToolBar`. Measured:
        79 tool buttons and 20 spin boxes go from enabled to disabled and back,
        and the handful that were already disabled stay that way, because
        disabling a parent does not touch its children's own flags. Any real
        tool bar or menu bar a future layout adds is covered too. The progress
        display is a child of none of them, so Cancel stays reachable.

        Parameters
        ----------
        frozen : bool
            ``True`` while the batch runs.
        """
        central = self.centralWidget()
        if central is not None:
            central.setEnabled(not frozen)
        for bar in self.findChildren(QtWidgets.QToolBar):
            bar.setEnabled(not frozen)
        menu_bar = self.menuBar()
        if menu_bar is not None:
            menu_bar.setEnabled(not frozen)
        self._inputs_frozen = bool(frozen)

    def batch_input_files(self) -> list:
        """Everything the batch export fits *from*.

        The selected burst tables, plus the raw measurements the folder's
        manifest names and the manifest itself. Per-burst MLE fits photons, not
        tables: a source re-exported or re-staged, or a linearisation applied
        after the burst search, changes every decay that is fitted while leaving
        each `.bur` byte-identical. This gate is the only one that survives a
        restart, so it is the one that must not inherit an old result silently.
        """
        try:
            selected = [Path(p) for p in self.burst_files_list.get_selected_files()]
        except Exception:
            return []
        if not selected:
            return []
        try:
            from chisurf.core.fio.fluorescence.burst_manifest import source_inputs

            sources = list(source_inputs(selected[0]))
        except Exception:
            sources = []
        return selected + sources

    def batch_settings(self) -> dict:
        """Everything the batch fit is given, in one mapping.

        ``channel_settings`` carries the per-detector state — micro-time range,
        shifts, thresholds, g/l1/l2, min photons and the IRF/background arrays
        themselves — so an IRF sent over from the IRF & Background step counts as
        a change, as it must.
        """
        # Normalise first: the batch itself fills in per-detector defaults
        # (``_ensure_channel_state``), so fingerprinting the raw mapping before a
        # run and the filled one after it would never agree, and nothing would
        # ever be reused.
        try:
            for det in self.channel_definer.detectors:
                self._ensure_channel_state(det)
        except Exception:
            pass
        from chisurf.core import analysis_cache

        x0, fixed = self.fit_parameters
        return {
            "model": self.fit_model,
            "x0": list(x0) if x0 is not None else [],
            "fixed": list(fixed) if fixed is not None else [],
            "min_photons": float(self.min_photons),
            "channels": self.channel_settings,
            # The LUTs and micro-time shifts applied inside the reader are not a
            # setting of this step, and they change every decay it fits.
            "_read_context": analysis_cache.photon_read_context(),
        }

    def batch_fingerprint(self) -> str:
        """Fingerprint of the inputs, the settings, the read context and the code."""
        from chisurf.core import analysis_cache

        return analysis_cache.fingerprint(
            self.batch_input_files(), self.batch_settings(),
            extra=analysis_cache.algorithm_tag(
                "burst_mle", ALGORITHM_VERSION, "fit2x", "tttrlib"
            ),
        )

    def batch_stamp_path(self):
        """Where the exported burst fits record what produced them.

        Beside the ``b{g,r,y}4`` folders, which are siblings of the burst tables.
        One stamp per analysis folder holds an entry per fingerprint, so two
        selections of the same folder remember each other rather than taking
        turns overwriting one record.
        """
        try:
            selected = [Path(p) for p in self.burst_files_list.get_selected_files()]
        except Exception:
            return None
        if not selected:
            return None
        return selected[0].parent.parent / "burst_mle.stamp.json"

    def restart_bursts(self):
        """Refit every burst even though the exported fits are current."""
        self.process_bursts(force=True)

    def _flag_restart(self, on: bool) -> None:
        """Draw attention to Recompute exactly when an export was skipped."""
        button = self.__dict__.get("pushButton_restart_bursts")
        if button is not None:
            flag_attention(button, on)

    def process_bursts(self, *, force: bool = False):
        import os
        import numpy as np
        from concurrent.futures import ProcessPoolExecutor, as_completed
        import multiprocessing as mp
        from multiprocessing import shared_memory
        from chisurf.plugins.burst.burst_mle_analysis._mp_worker import process_one_file_worker

        if self.df_bursts is None or not self.tttrs:
            self._set_status("No burst data loaded.")
            return

        # Fitting every burst of every file is the most expensive step in the
        # workflow, and the shell asks for it on every Next. Its product is the
        # b{g,r,y}4 files, so results that are already on disk for exactly these
        # burst files and settings are the answer -- do not fit them again.
        from chisurf.core import analysis_cache

        fingerprint = self.batch_fingerprint()
        stamp_path = self.batch_stamp_path()
        if (
            not force
            and stamp_path is not None
            and analysis_cache.is_current(stamp_path, fingerprint)
        ):
            self._set_status(
                "Unchanged — the exported burst fits are current (nothing refitted); "
                "🔁 Restart refits them anyway"
            )
            self._flag_restart(True)
            return
        self._flag_restart(False)

        # The batch export runs every fit2x model (fit23/24/25) through the same
        # multiprocessing worker. The tail fit is a different estimator family
        # (DecayFitNExp, no per-burst gamma/anisotropy) whose per-burst export is
        # not meaningful on low burst counts, so it stays preview-only.
        model = self.fit_model
        if model == "tail":
            self._set_status(
                "Tail fit not exported per burst (under-determined at burst photon "
                "counts) — use a fit2x model (fit23/24/25) for batch export."
            )
            return

        # Registry method + free-parameter names for the selected model. fit23
        # uses its per-detector authored start vector; the other fit2x models
        # share one start vector read from the registry-driven editor.
        try:
            from chisurf.core import tttrlib_registry as _reg
            method = _reg.describe(_reg.FIT_MODEL, model).get("method") or "Fit23"
        except Exception:
            method = "Fit23"
        param_names = self._fit_param_names(model)
        batch_x0, batch_fixed = self.fit_parameters  # model-aware (see property)

        # UI
        self.stop_processing = False
        total_bursts = len(self.df_bursts)
        progress = _mle_progress(self, "Processing bursts...", total_bursts)
        progress.setWindowTitle("Processing bursts")
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setAutoClose(False)
        progress.setValue(0)
        progress.show()

        # Everything below allocates: the progress bar is already showing and
        # the loop further down creates two *named* POSIX shared-memory blocks
        # per file. Neither was covered by a `try` -- the only one started after
        # the last allocation -- so an unreadable TTTR file, a MemoryError or an
        # out-of-space `SharedMemory(create=True)` on a later file left the bar
        # running forever and leaked every block already created. These are
        # named segments: `__del__` closes but never unlinks, and the resource
        # tracker only cleans up at interpreter shutdown, so a long-lived GUI
        # session held them until ChiSurf exited and every retry added a set.
        # Bound *before* the guard: a failure ahead of the assignment inside it
        # would otherwise raise NameError out of the handler and lose the real
        # exception.
        shm_blocks = []
        try:
            def ui_pump(k: int):
                if (k % 20) == 0:
                    QtWidgets.QApplication.processEvents()

            # Per-detector constants
            irf_cache, bg_cache = self._build_irf_bg_cache()
            settings_cache = {det: self._ensure_channel_state(det) for det in self.channel_definer.detectors.keys()}
            det_order = list(self.channel_definer.detectors.keys())

            # Diagnostics: a detector whose whole batch column comes back NaN (while the
            # live single-burst fit works) is almost always an empty IRF or a
            # too-high min-photons threshold — surface both up front, per detector.
            for det in det_order:
                irf_arr = np.asarray(irf_cache.get(det, []), dtype=float)
                irf_sz = int(irf_arr.size)
                irf_sum = float(irf_arr.sum()) if irf_sz else 0.0
                # NB: not ``mp`` — that name is ``import multiprocessing as mp`` here.
                min_ph = int(settings_cache[det].get('min_photons', 0))
                cs.logging.info(
                    f"MLE batch: detector '{det}' IRF size={irf_sz} sum={irf_sum:.3g}, "
                    f"bg size={int(np.asarray(bg_cache.get(det, [])).size)}, min_photons={min_ph}"
                )
                # An empty *or all-zero* IRF (e.g. over-aggressive IRF range/threshold
                # zeroing) makes every burst's τ NaN — the live fit may still work if it
                # processes the IRF differently, so call this out explicitly.
                if model != "tail" and (irf_sz == 0 or irf_sum <= 0.0):
                    cs.logging.warning(
                        f"MLE batch: detector '{det}' IRF is empty/all-zero (size={irf_sz}, "
                        f"sum={irf_sum:.3g}) — every burst's τ will be NaN. Check the IRF "
                        f"range/threshold, or run 'Auto IRF' / load an IRF for '{det}'."
                    )

            # Bin the per-burst data at the SAME binning the IRF/background were built
            # at (``irf_np``/``bg_np`` are always at ``self.micro_time_binning``).
            # Deriving the binning from the per-detector cache instead was a bug: Auto
            # IRF's ``_auto_select_binning`` changes ``self.micro_time_binning`` while
            # the cache keeps the pre-Auto value, so the data histogram and the IRF
            # ended up at different binnings — their peaks landed on different bins and
            # Fit23 diverged to τ = period (13.5 ns) for every burst. Force both the
            # data binning and ``dt`` to the current (IRF) values, overriding stale
            # cache, so batch and live fits agree.
            global_mb = int(self.micro_time_binning)
            cur_dt = float(self.dt_effective)
            for _st in settings_cache.values():
                _st['micro_time_binning'] = global_mb
                _st['dt'] = cur_dt

            # windows, channels, rc max
            window_cache = {}
            channels_cache = {}
            rc_max_seen = 0
            for det, info in self.channel_definer.detectors.items():
                st = settings_cache[det]
                sb = int(st['micro_time_start']);
                eb = int(st['micro_time_stop'])
                if eb <= sb:
                    sb, eb = map(int, self.micro_time_range)
                window_cache[det] = (sb, eb)

                chs = info.get('chs', [])
                pchs = chs[::2] if len(chs) >= 2 else chs
                schs = chs[1::2] if len(chs) >= 2 else chs
                pchs = np.asarray(pchs, dtype=int);
                schs = np.asarray(schs, dtype=int)
                channels_cache[det] = (pchs, schs)
                if len(chs):
                    rc_max_seen = max(rc_max_seen, int(np.max(chs)))

            # Build per-file jobs with shared memory
            jobs = []
            shm_blocks = []  # to unlink at end
            for fname, df_file in self.df_bursts.groupby('First File', sort=False):
                key = Path(fname).stem
                tttr = self.tttrs.get(key)

                if tttr is None:
                    jobs.append((fname,
                                 list(df_file[['First Photon', 'Last Photon']].itertuples(index=False, name=None)),
                                 None, None, None, None, None, None,
                                 det_order, {}, int(self.shift or 0)))
                    continue

                rc_full = np.asarray(tttr.routing_channels)
                mt_full = np.asarray(tttr.micro_times)
                mt_bins_full = (mt_full // global_mb).astype(np.int32, copy=False) if global_mb > 1 else mt_full.astype(
                    np.int32, copy=True)

                # compact dtypes to reduce bandwidth
                if rc_full.dtype != np.uint16 and int(rc_full.max(initial=0)) <= 65535:
                    rc_full = rc_full.astype(np.uint16, copy=False)
                if mt_bins_full.dtype != np.uint16 and int(mt_bins_full.max(initial=0)) <= 65535:
                    mt_bins_full = mt_bins_full.astype(np.uint16, copy=False)

                # Shared memory blocks (parent owns lifecycle)
                rc_shm = shared_memory.SharedMemory(create=True, size=rc_full.nbytes)
                np.ndarray(rc_full.shape, dtype=rc_full.dtype, buffer=rc_shm.buf)[:] = rc_full
                mt_shm = shared_memory.SharedMemory(create=True, size=mt_bins_full.nbytes)
                np.ndarray(mt_bins_full.shape, dtype=mt_bins_full.dtype, buffer=mt_shm.buf)[:] = mt_bins_full
                shm_blocks.extend([rc_shm, mt_shm])

                # Per-detector config (use class LUT: -1 ignore, 0=P, 1=S)
                rc_max = int(rc_full.max(initial=rc_max_seen)) if rc_full.size else rc_max_seen
                perdet_cfg = {}
                for det in det_order:
                    st = settings_cache[det]
                    pchs, schs = channels_cache[det]
                    class_lut = np.full(rc_max + 1, -1, dtype=np.int8)
                    if pchs.size: class_lut[pchs] = 0
                    if schs.size: class_lut[schs] = 1
                    half_len = max(1, irf_cache[det].size // 2)
                    # fit23 keeps its per-detector authored start vector; every other
                    # fit2x model shares the one start vector from the registry-driven
                    # editor (the editor is not per-detector).
                    if model == "fit23":
                        x0 = np.asarray(st['initial_x0'], dtype=np.float64)
                        fixed = np.asarray(st['fixed_flags'], dtype=np.int32)
                    else:
                        x0 = np.asarray(batch_x0, dtype=np.float64)
                        fixed = np.asarray(batch_fixed, dtype=np.int32)
                    perdet_cfg[det] = {
                        'sb': int(window_cache[det][0]),
                        'eb': int(window_cache[det][1]),
                        'half_len': half_len,
                        'dt': float(st['dt']),
                        'period': float(st['excitation_period']),
                        'g_factor': float(st['g_factor']),
                        'l1': float(st['l1']), 'l2': float(st['l2']),
                        'p2s_twoIstar': bool(st['p2s_twoIstar']),
                        'BIFL_scatter': bool(st['BIFL_scatter']),
                        'min_photons': int(st['min_photons']),
                        'x0': x0,
                        'fixed': fixed,
                        'irf': np.asarray(irf_cache[det], dtype=np.float64),
                        'bg': np.asarray(bg_cache[det], dtype=np.float64),
                        'class_lut': class_lut,
                        'model': model,
                        'method': method,
                        'param_names': list(param_names),
                    }

                bursts = list(df_file[['First Photon', 'Last Photon']].itertuples(index=False, name=None))
                jobs.append((fname, bursts,
                             rc_shm.name, rc_full.shape, str(rc_full.dtype),
                             mt_shm.name, mt_bins_full.shape, str(mt_bins_full.dtype),
                             det_order, perdet_cfg, int(self.shift or 0)))

            # Processes (leave one core for UI; cap by #files)
            ctx = mp.get_context('spawn')
            max_workers = max(1, min(os.cpu_count() or 8, len(jobs)) - 1)
        except BaseException:
            try:
                progress.close()
            except Exception:
                pass
            for block in shm_blocks:
                try:
                    block.close()
                    block.unlink()
                except Exception:
                    pass
            raise

        results = []
        processed = 0
        # Nothing may change from here on: the configuration above was read
        # *once* and is already inside the job payloads, so an edit made halfway
        # through would apply to some bursts and not others, silently, and the
        # result would be a table nobody could reproduce. The modal dialog used
        # to provide this by accident -- a window-modal dialog blocks input to
        # its parent -- but only when the progress *is* a dialog: embedded in
        # the shell it renders in the status bar with no modality at all, while
        # `ui_pump` below keeps delivering the user's clicks. Freeze explicitly
        # rather than depending on where the bar happened to render, and do it
        # inside the `try` so a failure cannot leave the wizard frozen.
        cancelled = False
        failed_files: list[str] = []
        try:
            self._set_inputs_frozen(True)
            with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx) as ex:
                # One job is one file; keep the mapping so a worker that dies can
                # be named rather than silently subtracted from the table.
                fut_file = {
                    ex.submit(process_one_file_worker, j): str(j[0]) for j in jobs
                }
                for fut in as_completed(fut_file):
                    # Cancel has to be read *here*. Checked after the `with`
                    # block it is read once every future has already been joined,
                    # so pressing it could not shorten a run at all -- and the
                    # check it fed then either did nothing (every worker
                    # succeeded, so `processed == total_bursts`) or threw away
                    # every completed result as "canceled" (any worker raised, so
                    # `processed < total_bursts`).
                    if self.stop_processing or progress.wasCanceled():
                        cancelled = True
                        for pending in fut_file:
                            pending.cancel()
                        break
                    try:
                        out, nbursts = fut.result()
                    except Exception as e:
                        # A job is a whole file: dropping it silently exported a
                        # short table that looked complete.
                        failed_files.append(fut_file[fut])
                        cs.logging.error(f"Worker failed on {fut_file[fut]}: {e}")
                        out, nbursts = [], 0
                    results.extend(out)
                    processed += nbursts
                    progress.setValue(min(processed, total_bursts))
                    ui_pump(processed)
        finally:
            try:
                progress.close()
            except Exception:
                pass
            self._set_inputs_frozen(False)
            # cleanup shared memory
            for block in shm_blocks:
                try:
                    block.close();
                    block.unlink()
                except Exception:
                    pass

        if cancelled:
            self._set_status(
                f"Burst processing was cancelled after {processed}/{total_bursts} bursts."
            )
            return

        result_df = pd.DataFrame(results)

        # Diagnostics: per-detector fit yield + photon-window stats, so an all-NaN
        # τ column (e.g. every green burst below min_photons in the fit window)
        # is explained in the log rather than appearing as silent NaNs downstream.
        summary_bits = []
        try:
            for det in det_order:
                color = det.lower()
                tau_col = f"Tau ({color})"
                nph_col = f"Number of Photons (fit window) ({color})"
                if tau_col not in result_df.columns:
                    continue
                tau_vals = pd.to_numeric(result_df[tau_col], errors="coerce")
                n_ok = int(tau_vals.notna().sum())
                n_all = int(len(tau_vals))
                summary_bits.append(f"{det} {n_ok}/{n_all}")
                msg = f"MLE batch '{det}': {n_ok}/{n_all} bursts fitted (τ non-NaN)"
                if nph_col in result_df.columns:
                    nph = pd.to_numeric(result_df[nph_col], errors="coerce")
                    if nph.notna().any():
                        msg += (
                            f"; fit-window photons min/median/max="
                            f"{int(nph.min())}/{int(nph.median())}/{int(nph.max())}"
                            f", min_photons={int(settings_cache[det].get('min_photons', 0))}"
                        )
                        summary_bits[-1] += (
                            f" (ph {int(nph.min())}/{int(nph.median())}/{int(nph.max())})"
                        )
                (cs.logging.warning if n_ok == 0 and n_all else cs.logging.info)(msg)
        except Exception:
            pass
        # Surface the per-detector yield on the status bar too — an all-NaN column
        # (e.g. "green 0/938") is then visible without digging through the log.
        if failed_files:
            # Reported here because nothing else can: the per-detector summary
            # counts non-NaN tau over the rows that are *present*, so a file that
            # contributed no rows at all cannot appear in it.
            names = ", ".join(sorted({Path(f).name for f in failed_files}))
            summary_bits.append(f"{len(failed_files)} file(s) failed: {names}")
            cs.logging.warning(f"MLE batch: no rows exported for {names}")
        if summary_bits:
            self._set_status("MLE fitted τ: " + " · ".join(summary_bits))

        written = self._save_burst_results_fast(result_df)
        if written and stamp_path is not None:
            # Stamp with the settings *as the batch used them*, not as they were
            # when it started: reading the burst data settles per-detector state
            # the panel had not derived yet (micro-time binning comes from the
            # TTTR header, and dt with it). Stamping the pre-run guess would
            # describe the results wrongly, and would never match the fingerprint
            # of the settled panel — so the next run would refit every burst
            # again for nothing.
            settled = self.batch_settings()
            analysis_cache.write_stamp(
                stamp_path, self.batch_fingerprint(), params=settled,
                inputs=self.batch_input_files(), outputs=written, tool="burst_mle",
            )

    def make_vv_vh(
            self,
            tttr_list: typing.List[tttrlib.TTTR],
            detector_chs: typing.List[int],
            micro_time_range: typing.Tuple[int, int],
            micro_time_binning: int,
            save_files: bool = False,
            normalize_counts: int = 1,
            threshold: typing.Union[float, typing.Tuple[float, float]] = -1,
            minlength: int = -1,
            apply_vh_shift: bool = True
    ) -> typing.List[np.ndarray]:
        vv_vhs = list()
        # Determine per-channel ranges: fall back to provided micro_time_range for both
        sb_def, eb_def = micro_time_range
        # Try to get detector-specific ranges from the channel_definer
        vv_sb = sb_def; vv_eb = eb_def
        vh_sb = sb_def; vh_eb = eb_def
        
        info = getattr(self.channel_definer, 'detectors', {}).get(self.current_detector, {})
        ranges = info.get('micro_time_ranges', None)
        if ranges and len(ranges) >= 2:
            raw_vv = ranges[0]
            raw_vh = ranges[1]
            binning = max(1, int(micro_time_binning))
            vv_sb = int(raw_vv[0] // binning)
            vv_eb = int(raw_vv[1] // binning)
            vh_sb = int(raw_vh[0] // binning)
            vh_eb = int(raw_vh[1] // binning)

        for idx, tttr in enumerate(tttr_list):
            # Use filter_tttr helper to select relevant events
            if len(detector_chs) >= 2:
                tp = self.filter_tttr(tttr, micro_time_range, detector_chs[::2])
                ts = self.filter_tttr(tttr, micro_time_range, detector_chs[1::2])
            else:
                tp = ts = self.filter_tttr(tttr, micro_time_range, detector_chs)

            # Build full microtime histograms (default uses full range)
            cp = tp.get_microtime_histogram(micro_time_binning)[0].astype(np.float64, copy=False)
            cs_hist = ts.get_microtime_histogram(micro_time_binning)[0].astype(np.float64, copy=False)

            # Apply integer VH shift BEFORE any other operation
            if apply_vh_shift and self.shift != 0:
                cs_hist = np.roll(cs_hist, self.shift)

            # Now zero out-of-window bins per channel (after shift), only when shifting/windowing is desired
            if apply_vh_shift:
                if vv_sb > 0:
                    cp[:vv_sb] = 0
                if vv_eb < cp.size:
                    cp[vv_eb:] = 0
                if vh_sb > 0:
                    cs_hist[:vh_sb] = 0
                if vh_eb < cs_hist.size:
                    cs_hist[vh_eb:] = 0

                # Apply thresholds
                th_vv = th_vh = -1.0
                if isinstance(threshold, (tuple, list)) and len(threshold) >= 2:
                    th_vv = float(threshold[0]) if threshold[0] is not None else -1.0
                    th_vh = float(threshold[1]) if threshold[1] is not None else -1.0
                if th_vv > 0:
                    if cp.size and cp.max() > 0:
                        cp[cp < th_vv * cp.max()] = 0
                if th_vh > 0:
                    if cs_hist.size and cs_hist.max() > 0:
                        cs_hist[cs_hist < th_vh * cs_hist.max()] = 0

            # Optional normalization
            if normalize_counts == 1:
                # Normalize by average count rate
                ct = (cp.sum() + cs_hist.sum()) / 2.0
                if ct > 0:
                    cp /= ct
                    cs_hist /= ct
            elif normalize_counts == 2:
                # Normalize individually
                cp_sum = cp.sum()
                cs_sum = cs_hist.sum()
                if cp_sum > 0:
                    cp = cp / cp_sum
                if cs_sum > 0:
                    cs_hist = cs_hist / cs_sum
            elif normalize_counts == 3:
                # Normalize by acquisition time
                acquisition_time = (tttr.macro_times[-1] - tttr.macro_times[0]) * tttr.header.macro_time_resolution
                if acquisition_time > 0:
                    cs_hist /= acquisition_time
                    cp /= acquisition_time

            # now build the VV_VH vector
            j = np.hstack([cp, cs_hist])
            vv_vhs.append(j)

            # Optional save
            if save_files:
                basename = getattr(tttr, 'filename', None)
                if basename:
                    base = Path(basename).with_suffix('').as_posix()
                else:
                    base = f"vv_vh_{idx}"
                out_name = f"{base}_{''.join(map(str, detector_chs))}.dat"
                write_vv_vh(j, out_name)

        return np.array(vv_vhs)

    def filter_tttr(self, tttr, micro_time_range, detector_chs):
        """
        Return a TTTR slice filtered only by routing channels.
        Note: We intentionally ignore micro_time_range to keep full micro-time coverage.
        Zeroing outside [start, stop] is applied later at the histogram level.
        """
        ch = tttr.routing_channels
        mask = np.isin(ch, detector_chs)
        return tttr[np.where(mask)[0]]

    def get_burst_indices_for_current_file(self) -> list[int]:
        if not self.current_filename or self.df_bursts is None:
            return []

        # lazy-compute stems if missing
        if "stem" not in self.df_bursts:
            self.df_bursts["stem"] = (
                self.df_bursts["First File"]
                .str.split(r"[\\/]").str[-1]
                .str.rsplit(".", n=1).str[0]
            )

        # select only the bursts for this file
        curr_stem = Path(self.current_filename).stem
        df_file = self.df_bursts.loc[self.df_bursts["stem"] == curr_stem]
        if df_file.empty:
            return []

        # pull start/stop as int arrays
        starts = df_file["First Photon"].to_numpy(dtype=np.int32)
        stops = df_file["Last Photon"].to_numpy(dtype=np.int32)

        # build a single “difference” event array with bincount
        # - at each start index we +1, at each (stop+1) we -1
        idxs = np.concatenate([starts, stops + 1])
        weights = np.concatenate([
            np.ones_like(starts, dtype=np.int32),
            -np.ones_like(stops + 1, dtype=np.int32),
        ])
        max_len = idxs.max() + 1
        events = np.bincount(idxs, weights, minlength=max_len)

        # cumulative sum >0 gives a boolean mask of covered photons
        coverage = np.cumsum(events)[:-1] > 0

        # return all covered indices
        return np.nonzero(coverage)[0].tolist()

    def read_burst_analysis(
            self,
            paris_path: Path,
            pattern: str = "**/*.bur",
            row_stride: int = 2
    ) -> tuple[pd.DataFrame, dict[str, tttrlib.TTTR]]:
        print("def read_burst_analysis")
        # 1) Locate and sanity-check
        bur_files = sorted(paris_path.glob(pattern))
        if not bur_files:
            raise ValueError(f"No burst files found in {paris_path!s}")

        # Check for JSON file in Info folder of the burst folder
        info_directory = paris_path / 'Info'
        json_file_path = info_directory / "photon_selection_parameters.json"

        # Use safe_open_file to read the JSON file if it exists
        from chisurf.core.settings.file_utils import safe_open_file
        import json

        setup_info = None
        json_data = safe_open_file(
            json_file_path,
            processor=json.load,
            default_value=None,
            error_message=f"Could not read setup information from {json_file_path}"
        )

        if json_data:
            cs.logging.info(f"Found setup information in {json_file_path}")
            # Extract setup information from JSON
            setup_info = json_data.get("setup_info")
            if setup_info:
                cs.logging.info("Using setup information from JSON file")
                # If we have setup information, we can use it to configure the wizard
                # For example, we could set channel settings, detector settings, etc.
                # This will depend on what's available in the JSON and what's needed by the wizard

                # If the channel_definer is available, we can update its settings
                if hasattr(self, 'channel_definer') and setup_info.get("windows"):
                    self.channel_definer.windows = setup_info.get("windows", {})
                    self.channel_definer.detectors = setup_info.get("detectors", {})
                    cs.logging.info("Updated channel definitions from JSON file")

        # 2) Sample first file to infer which cols are numeric and build robust dtype spec
        sample = pd.read_csv(
            bur_files[0],
            sep="\t",
            header=0,
            skiprows=[1],
            nrows=100,
            engine="c",
            low_memory=False
        )
        # Numeric columns from sample
        num_cols = sample.select_dtypes(include="number").columns
        dtype_spec: dict[str, str] = {col: "float64" for col in num_cols}
        # Ensure file/path-like columns are treated as strings across all files
        string_like_cols = set()
        for col in sample.columns:
            if col.strip() == "" or "File" in col or col in ("First File", "Last File", "BID File", "burst_file"):
                string_like_cols.add(col)
        # Explicitly include common string columns even if not present in the sample
        string_like_cols.update({"First File", "Last File", "BID File", "burst_file", ""})
        for col in string_like_cols:
            dtype_spec[col] = "string"
        # BID Index should be integer if present (use pandas nullable integer)
        if "BID Index" in sample.columns:
            dtype_spec["BID Index"] = "Int64"
        else:
            # add proactively; ignored for files without the column
            dtype_spec["BID Index"] = "Int64"

        # 3) Read each file and concat
        file_dfs = []
        for fn in bur_files:
            df_part = pd.read_csv(
                fn,
                sep="\t",
                header=0,
                skiprows=[1],
                dtype=dtype_spec,
                engine="c",
                low_memory=False
            )
            # Track source .bur file name
            df_part["burst_file"] = str(getattr(fn, 'name', fn))
            file_dfs.append(df_part)
        df = pd.concat(file_dfs, ignore_index=True)

        # 4) One-time down-sampling
        if row_stride > 1:
            df = df.iloc[::row_stride].reset_index(drop=True)

        raw_files = df["First File"].dropna().unique()
        base_dir = paris_path.parent
        # clear any old registrations
        print("self._tttr_paths:", self._tttr_paths)
        for fn in raw_files:
            # Extract just the filename part from the "First File" column
            filename = Path(fn).name
            stem = Path(filename).stem
            # The TTTR file should be in the parent directory of the burst file
            self._tttr_paths[stem] = base_dir / filename

        # now self.tttrs is set up, but no TTTR objects created yet
        return df, self.tttrs

    def save_fit(self):
        """
        Save micro_time_start, micro_time_stop, irf_threshold_vv, irf_threshold_vh, shift, shift_sp, shift_ss,
        p2s_twoIstar, BIFL_scatter, fix_tau, fix_gamma, fix_r0, fix_rho
        to detector_setups.json file in the currently selected setup.
        """
        # Get the current detector
        current_detector = self.current_detector

        # Get the current setup name
        setup_name = self.channel_definer.setup_combo.currentText()
        if not setup_name:
            self._set_status("No setup selected. Please select a setup first.")
            return

        # Get the detector_setups.json file path
        setups_file = self.channel_definer.current_setups_file

        # Load existing setups
        setups = load_detector_setups(setups_file)

        # Check if the setup exists
        if setup_name not in setups.get("setups", {}):
            self._set_status(f"Setup '{setup_name}' not found.")
            return

        # Get the parameters for the current detector
        detector_params = {
            "micro_time_start": self.micro_time_range[0],
            "micro_time_stop": self.micro_time_range[1],
            "irf_threshold_vv": self.irf_threshold_vv,
            "irf_threshold_vh": self.irf_threshold_vh,
            "shift": self.shift,
            "shift_sp": self.shift_sp,
            "shift_ss": self.shift_ss,
            "irf_start": self.irf_start,
            "irf_stop": self.irf_stop,
            "p2s_twoIstar": self.p2s_twoIstar,
            "BIFL_scatter": self.BIFL_scatter,
            "fix_tau": self.fix_tau,
            "fix_gamma": self.fix_gamma,
            "fix_r0": self.fix_r0,
            "fix_rho": self.fix_rho,
            "min_photons": int(self.min_photons)
        }

        # Get the setup data
        setup_data = setups["setups"][setup_name]

        # Add or update the MLE settings for the current detector
        if "detectors" not in setup_data:
            setup_data["detectors"] = {}

        # Check if the detector exists in the setup
        if current_detector not in setup_data["detectors"]:
            self._set_status(f"Detector '{current_detector}' not found in setup '{setup_name}'.")
            return

        # Add MLE settings to the detector
        if "mle_settings" not in setup_data["detectors"][current_detector]:
            setup_data["detectors"][current_detector]["mle_settings"] = {}

        # Update the MLE settings (merge with existing instead of overwrite)
        existing = setup_data["detectors"][current_detector].get("mle_settings", {})
        if not isinstance(existing, dict):
            existing = {}
        existing.update(detector_params)
        setup_data["detectors"][current_detector]["mle_settings"] = existing

        # Save the updated setups
        if save_detector_setups(setups, setups_file):
            self._set_status(f"MLE settings for detector '{current_detector}' saved to setup '{setup_name}'.")
        else:
            dialogs.error(self, "Error", f"Could not save MLE settings to setup '{setup_name}'.")

    def optimize_hyperparameters(
            self,
            n_iter: int = 40,
            bounds: dict | None = None,
            seed: int | None = None,
            weights: dict | None = None
    ):
        """Delegate to external HPO function to keep this file lean.

        The search drives this wizard -- every trial writes the tunables and
        refits -- so the inputs are frozen for its duration: a click landing
        between two trials would move the ground the search is standing on, and
        the remaining trials would explore a different configuration from the
        earlier ones. The ``finally`` matters as much as the freeze: a failed
        search must not leave the wizard disabled.
        """
        try:
            from chisurf.plugins.burst.burst_mle_analysis.utils import optimize_hyperparameters as _opt_hpo
            self._set_inputs_frozen(True)
            return _opt_hpo(self, n_iter=n_iter, bounds=bounds, seed=seed, weights=weights)
        except Exception as e:
            dialogs.error(self, "HPO error", f"{e}")
            return None
        finally:
            self._set_inputs_frozen(False)

    def save_settings(self):
        """
        Dump TTTR file‐type, per‐channel settings, AND
        DetectorWizardPage windows + detectors in the exact JSON shape
        that load_data_into_tables expects.
        """
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save All Settings",
            str(Path.home() / "mle_wizard_settings.json"),
            "JSON Files (*.json)"
        )
        if not path:
            return

        detwiz = self.channel_definer

        # Ensure current detector state is captured before saving
        try:
            cur_det = self.current_detector
            if cur_det:
                self.channel_settings[cur_det] = self._capture_current_ui_state()
        except Exception:
            pass

        payload = {
            "tttr_file_type": self.channel_definer.filetype or "Auto",
            "channel_settings": self.channel_settings,
            "detector_settings": detwiz.get_settings(),
            "micro_time_binning": self.micro_time_binning
        }

        with open(path, 'w') as f:
            json.dump(payload, f, indent=4, cls=NumpyEncoder)

        # show the file in both line edits
        self._set_status(f"All settings saved to:\n{path}")

    def load_settings(self):
        """Pick a settings JSON and restore the wizard from it.

        Starts in the last analysis folder rather than the home directory: the
        settings you almost always want are the ones beside the data you just
        analysed. A burst-analysis folder is accepted directly — see
        :meth:`load_settings_from`.
        """
        start = self._settings_start_directory()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load All Settings",
            str(start),
            "JSON Files (*.json)"
        )
        if not path:
            return
        self.load_settings_from(path)

    def _settings_start_directory(self) -> Path:
        """Where the load/save dialogs should open.

        The analysis folder in use, falling back to the home directory. Opening
        in ``~`` when the settings live next to the data is a small thing that
        turns a one-click restore into a hunt.
        """
        for attribute in ("analysis_folder", "output_folder", "working_directory"):
            candidate = getattr(self, attribute, None)
            if candidate:
                try:
                    resolved = Path(candidate)
                except TypeError:
                    continue
                if resolved.is_dir():
                    return resolved
        return Path.home()

    def load_settings_from(self, source) -> None:
        """Restore the wizard from a settings JSON *or* a burst-analysis folder.

        A burst folder records how its data was read and what it was analysed
        with (``Info/analysis.json``), which is exactly what this wizard needs to
        be put back into the state that produced it. Passing the folder — or any
        `.bur` inside it — is therefore equivalent to picking the settings file,
        and is what makes an analysis folder self-describing rather than merely
        an output directory.

        Parameters
        ----------
        source : path-like
            A settings JSON, a burst-analysis folder, or a ``.bur`` in one.
        """
        from chisurf.core.fio.fluorescence.burst_manifest import (
            read_analysis_manifest,
        )

        source = Path(source)
        payload = None

        if source.is_dir() or source.suffix.lower() != ".json":
            manifest = read_analysis_manifest(source)
            if manifest:
                # The wizard's own payload if one was stored, else the settings
                # the analysis ran with.
                payload = manifest.get("mle_settings") or manifest.get("settings")
            if not payload:
                cs.logging.warning("no stored settings found under %s", source)
                return
        else:
            try:
                with open(source, "r") as fp:
                    payload = json.load(fp)
            except (OSError, ValueError) as exc:
                cs.logging.error("could not read settings from %s: %s", source, exc)
                return
            # A settings file written by AutoForm or embedded in a manifest
            # wraps the mapping; accept both shapes.
            if isinstance(payload, dict):
                payload = payload.get("state") or payload.get("mle_settings") or payload

        if not isinstance(payload, dict):
            cs.logging.error("settings in %s are not a mapping", source)
            return
        self.apply_settings_payload(payload, source)

    def apply_settings_payload(self, payload: dict, source=None) -> None:
        """Restore the wizard from an already-loaded settings mapping.

        Split out from :meth:`load_settings` so the same restore runs whether the
        settings came from a file dialog, a burst-analysis folder, or a caller
        driving the wizard headlessly.

        Parameters
        ----------
        payload : dict
            The settings mapping to apply.
        source : path-like, optional
            Where the payload came from, shown in the settings-file field and in
            the status line. A caller that built the payload itself passes
            nothing, and those two places are left alone.
        """
        # Micro time binning
        mtb = payload.get("micro_time_binning", None)
        if mtb is not None:
            # Update micro_time_binning in DetectorWizardPage
            self.channel_definer.micro_binning_combo.setCurrentText(str(int(mtb)))

        # 2) TTTR file‐type is now handled by DetectorWizardPage
        # The tttr_file_type will be set when we load the detector settings below

        # 3) where the settings came from is reported on the status line at the
        # end of the restore; the old ``lineEdit_settings_file`` field went with
        # the .ui file and no longer exists.

        # 4) channel_settings
        self.channel_settings = payload.get("channel_settings", {})
        # Make sure each detector state is complete
        try:
            for det in list(self.channel_settings.keys()):
                self._ensure_channel_state(det)
        except Exception:
            pass

        # 5) detector_settings → load into DetectorWizardPage
        det_data = payload.get("detector_settings", {})
        if det_data:
            # 5a) disconnect the one slot so it won’t fire automatically
            self.channel_definer.detectorsChanged.disconnect(self._init_channels_from_wizard)

            # 5b) repopulate the wizard page
            self.channel_definer.load_data_into_tables(det_data)

            # 5c) re-attach and manually kick off exactly one rebuild
            self.channel_definer.detectorsChanged.connect(self._init_channels_from_wizard)
            self._init_channels_from_wizard()

        # grab the *names* we just loaded directly from JSON,
        # so we don’t invoke the broken .detectors property
        valid_dets = set(det_data.get("detectors", {}).keys())

        # 6) re‐apply per‐detector UI state only to those names
        current = self.comboBox_window.currentText()
        for det, state in self.channel_settings.items():
            if det not in valid_dets:
                continue
            self.comboBox_window.setCurrentText(det)
            widgets = (
                self.spinBox_micro_time_start,
                self.spinBox_micro_time_stop,
                self.doubleSpinBox_irf_threshold_vv,
                self.doubleSpinBox_irf_threshold_vh,
                self.doubleSpinBox_shift,
                self.doubleSpinBox_shift_sp,
                self.doubleSpinBox_shift_ss,
            )
            self.block_widget_signals(widgets)
            self._apply_ui_state(state)
            self.unblock_widget_signals(widgets)

        # restore whatever was selected originally
        self.comboBox_window.setCurrentText(current)

        # 7) refresh
        self.update_decay_of_detector()
        self.update_fit()

        self._set_status(
            f"All settings loaded from:\n{source}" if source is not None
            else "All settings loaded"
        )


if __name__ == 'plugin':
    mle = MLELifetimeAnalysisWizard()
    mle.show()

if __name__ == '__main__':
    import sys

    app = QtWidgets.QApplication(sys.argv)
    app.aboutToQuit.connect(app.deleteLater)
    mle = MLELifetimeAnalysisWizard()
    mle.setWindowTitle('MLE Lifetime Analysis')
    mle.show()
    sys.exit(app.exec_())
