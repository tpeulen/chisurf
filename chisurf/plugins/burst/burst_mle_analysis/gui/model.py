"""View model of the emtk burst-MLE app (cards ML0 to ML5): the Qt-free engine's session behind spec-bound attributes.

The AutoForm spec ``mle_native.view.json`` reads and writes the attributes of :class:`MleViewModel`; each one is a view
on :class:`~..engine.MleSession` (the same session the parity tests compare with the Qt wizard). Changing a setting
refits the current decay, as the wizard does. The slow actions (auto IRF/background, the batch over every burst) run on
a snapshot through :class:`chisurf.emtk.jobs.SnapshotJob`.

Nothing here imports Qt or emtk.
"""

from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np

from chisurf.core.support.i18n import tr

from .. import engine, hpo
from ..engine import MleSession
from . import fit_view

#: Per-detector settings exposed as attributes: name -> (type, rebuilds the decay, rebuilds the patterns).
SETTING_ATTRS: dict[str, tuple[type, bool]] = {
    "tau": (float, False),
    "gamma": (float, False),
    "r0": (float, False),
    "rho": (float, False),
    "fix_tau": (bool, False),
    "fix_gamma": (bool, False),
    "fix_r0": (bool, False),
    "fix_rho": (bool, False),
    "micro_time_start": (int, True),
    "micro_time_stop": (int, True),
    "shift": (int, True),
    "shift_sp": (float, False),
    "shift_ss": (float, False),
    "irf_start": (int, False),
    "irf_stop": (int, False),
    "irf_threshold_vv": (float, False),
    "irf_threshold_vh": (float, False),
    "min_photons": (int, False),
    "p2s_twoIstar": (bool, False),
    "BIFL_scatter": (bool, False),
}

#: The per-detector settings "Save fit" stores on the detector setup (the keys the wizard stored).
SETUP_KEYS = (
    "micro_time_start", "micro_time_stop", "irf_threshold_vv", "irf_threshold_vh", "shift", "shift_sp", "shift_ss",
    "irf_start", "irf_stop", "p2s_twoIstar", "BIFL_scatter", "fix_tau", "fix_gamma", "fix_r0", "fix_rho", "min_photons",
)

#: Values of the settings file this app writes and reads.
SETTINGS_KIND = "burst_mle_native"


def _setting_property(name: str, kind: type, rebuild_decay: bool):
    def getter(self):
        return kind(getattr(self.session.settings, name))

    def setter(self, value):
        self._ensure_editable()
        value = kind(value)
        if getattr(self.session.settings, name) == value:
            return
        setattr(self.session.settings, name, value)
        self._settings_changed(rebuild_decay)

    return property(getter, setter)


class MleViewModel:
    """State and actions of the burst-MLE lifetime tool (no Qt, no emtk)."""

    def __init__(self, session: MleSession | None = None) -> None:
        self.session = session or MleSession()
        self._observers: list[Callable[[str], None]] = []
        self._cancel = threading.Event()
        self._snapshot_running = threading.Event()
        self.status_text = "Add burst (.bur) files to begin."
        self.burst_results: list[dict] = []
        self.nav_burst = 0
        self.detector_editor_data: dict | None = None
        #: ``True`` while the IRF and background are the ones estimated from non-burst photons (so a binning change
        #: re-estimates them at the new binning).
        self.auto_patterns = False
        if not self.session.detectors:
            self.session.set_detectors(
                {
                    "green": {
                        "chs": [0, 1],
                        "micro_time_ranges": [],
                        "g_factor": 1.0,
                        "l1": 0.0,
                        "l2": 0.0,
                    },
                    "red": {
                        "chs": [8, 9],
                        "micro_time_ranges": [],
                        "g_factor": 1.0,
                        "l1": 0.0,
                        "l2": 0.0,
                    },
                },
                "auto",
            )

    def __copy__(self):
        """Isolate a worker's mutable state while sharing read-only physical TTTR inputs."""
        self._snapshot_running.set()
        snapshot = object.__new__(type(self))
        snapshot.__dict__ = self.__dict__.copy()
        session = copy.copy(self.session)
        for key, value in vars(self.session).items():
            if key == "tttrs":
                tttrs = copy.copy(value)
                tttrs.paths = dict(value.paths)
                tttrs._cache = dict(value._cache)
                tttrs.read_kwargs = copy.deepcopy(value.read_kwargs)
                setattr(session, key, tttrs)
            elif key == "df_bursts" and value is not None:
                from chisurf.core.datastore import column_names, store_from_arrays

                setattr(
                    session,
                    key,
                    store_from_arrays(
                        {name: np.asarray(value[name]).copy() for name in column_names(value)}
                    ),
                )
            else:
                setattr(session, key, copy.deepcopy(value))
        session.tttrs.paths = session.tttr_paths
        snapshot.session = session
        snapshot._observers = []
        snapshot.burst_results = copy.deepcopy(self.burst_results)
        snapshot._snapshot_running = threading.Event()
        snapshot._source_snapshot_running = self._snapshot_running
        return snapshot

    def _ensure_editable(self) -> None:
        """Reject edits of acquisition or model state while its snapshot job is running."""
        if self._snapshot_running.is_set():
            raise RuntimeError(tr("Wait for the running Burst MLE job before changing its inputs."))

    def _release_snapshot(self) -> None:
        """Release the original model's edit guard after worker success or failure."""
        self._snapshot_running.clear()
        import sys

        source = getattr(self, "_source_snapshot_running", None)
        if source is not None and sys.exc_info()[0] is not None:
            source.clear()

    # -- observers ------------------------------------------------------------------------------------------- #
    def notify(self, event: str = "updated") -> None:
        for observer in list(self._observers):
            observer(event)

    # -- detectors ------------------------------------------------------------------------------------------- #
    def detector_names(self) -> list[str]:
        return list(self.session.detectors)

    def set_setup(self, settings: dict) -> None:
        """Take the detector definition of the shared editor (every change of it)."""
        self._ensure_editable()
        self.session.set_definition(settings)
        if self.session.current_tttr() is not None:
            self._refresh_measured()
            if self.auto_patterns:
                self.session.extract_irf_background()
            self.session.build_decay()
            self.refit()
        self.notify("setup")

    # -- split by H2MM state ------------------------------------------------------------------------------------ #
    @property
    def split_by_state(self) -> bool:
        """Fit each burst once more per H2MM state, after a pooled fit of each state (the segment-level step)."""
        return bool(self.session.split_by_state)

    @split_by_state.setter
    def split_by_state(self, value: bool) -> None:
        self._ensure_editable()
        self.session.split_by_state = bool(value)
        self.notify("settings")

    @property
    def state_min_photons(self) -> int:
        """Photon floor of a per-state burst fit."""
        return int(self.session.state_min_photons)

    @state_min_photons.setter
    def state_min_photons(self, value: int) -> None:
        self._ensure_editable()
        self.session.state_min_photons = max(1, int(value))

    def state_lifetime_text(self) -> str:
        """The pooled per-state lifetimes of the last batch, one line per detector and state."""
        rows = list(getattr(self.session, "state_lifetimes", []) or [])
        if not rows:
            if self.session.split_by_state:
                return "No state lifetimes yet: Fit bursts pools each H2MM state's photons and fits them first."
            return "Not split by state."
        lines = []
        for r in rows:
            tau = r.get("Tau")
            shown = f"{tau:.3f} ns" if isinstance(tau, float) and np.isfinite(tau) else "not fitted"
            lines.append(f"S{r['State']} {r['Colour']}: tau {shown} ({r['Photons']} photons)")
        return "\n".join(lines)

    @property
    def current_detector(self) -> str:
        return self.session.current_detector

    @current_detector.setter
    def current_detector(self, value: str) -> None:
        self._ensure_editable()
        if value in self.session.detectors and value != self.session.current_detector:
            self.session.current_detector = value
            self._apply_setup_settings(value)
            self.session.build_decay()
            self.refit()

    def _apply_setup_settings(self, det: str) -> None:
        """Take the fit settings saved on the detector setup (``mle_settings``) when its detector is selected."""
        saved = (self.session.detectors.get(det) or {}).get("mle_settings")
        if not isinstance(saved, dict):
            return
        settings = self.session.settings_of(det)
        for key in SETUP_KEYS:
            if key in saved:
                kind = SETTING_ATTRS[key][0]
                setattr(settings, key, kind(saved[key]))

    def save_fit_to_setup(self, definition) -> str:
        """Store the current detector's window, thresholds, shifts, 2I*/BIFL flags and fix flags on the selected setup.

        ``definition`` is the detector-setup store of the editor (``setups``, ``current_name`` and ``_persist``); the
        values go to ``setups[name]["detectors"][detector]["mle_settings"]`` and are applied again whenever that
        detector is selected on this setup. Returns the status line.
        """
        det = self.session.current_detector
        name = getattr(definition, "current_name", "")
        if not name or name not in definition.setups:
            self.status_text = str(tr("No detector setup selected: pick or save a setup in the Detector setup tab first."))
            return self.status_text
        setup = definition.setups[name]
        detectors = setup.get("detectors") or {}
        if det not in detectors:
            self.status_text = str(tr("Detector {detector} is not in setup {setup}.")).format(detector=det, setup=name)
            return self.status_text
        settings = self.session.settings
        params = {key: SETTING_ATTRS[key][0](getattr(settings, key)) for key in SETUP_KEYS}
        existing = detectors[det].get("mle_settings")
        merged = dict(existing) if isinstance(existing, dict) else {}
        merged.update(params)
        detectors[det]["mle_settings"] = merged
        definition._persist()
        self.session.detectors.setdefault(det, {})["mle_settings"] = dict(merged)
        self.status_text = str(tr("MLE settings of detector {detector} saved to setup {setup}.")).format(detector=det, setup=name)
        return self.status_text

    # -- files ----------------------------------------------------------------------------------------------- #
    def file_rows(self) -> list[dict]:
        return [
            {"file": p.name, "folder": str(p.parent), "path": str(p)}
            for p in self.session.bur_files
        ]

    @property
    def n_bursts(self) -> int:
        return (
            int(engine.row_count(self.session.df_bursts))
            if self.session.df_bursts is not None
            else 0
        )

    def add_files(self, paths) -> int:
        """Add ``.bur`` tables (a folder adds the tables under it); returns how many were new."""
        self._ensure_editable()
        found: list[Path] = []
        for value in map(Path, paths):
            if value.is_dir():
                found.extend(sorted(value.rglob("*.bur")))
            elif value.suffix.lower() == ".bur":
                found.append(value)
        new = [p for p in found if p not in self.session.bur_files]
        if not new:
            self.status_text = "No new .bur burst table among the given paths."
            return 0
        self.session.add_burst_files(new)
        self.session.build_decay()
        self.status_text = f"{len(self.session.bur_files)} burst file(s), {self.n_bursts} bursts."
        self.notify("files")
        return len(new)

    def remove_file(self, path: str) -> None:
        self._ensure_editable()
        keep = [p for p in self.session.bur_files if str(p) != path]
        self.session.bur_files = []
        self.session.df_bursts = None
        if keep:
            self.session.add_burst_files(keep)
        else:
            self.session.tttr_paths.clear()
        self.session.decay = None
        self.session.outcome = None
        self.notify("files")

    def clear_files(self) -> None:
        self.remove_file("")
        self.session.bur_files = []
        self.session.df_bursts = None
        self.session.tttr_paths.clear()
        self.burst_results = []
        self.session.burst_results = []
        self.status_text = "Add burst (.bur) files to begin."
        self.notify("files")

    def load_example(self) -> None:
        """Replace working inputs with generated synthetic bursts; leave fitting to the user."""
        from ..demo import SETUP, make_demo

        self._ensure_editable()
        path = make_demo()
        self.session = engine.MleSession(template=engine.MleSettings(gamma=0., r0=0.))
        self.session.set_definition(SETUP)
        self.session.add_burst_files([path])
        self.session.build_decay()
        self.burst_results = []
        self.auto_patterns = False
        self.nav_burst = 0
        self.detector_editor_data = self.session.definition_payload()
        self.status_text = str(tr("Synthetic demo: 16 bursts, 1000 photons each; input lifetime 2 ns. Press Auto IRF/background to fit."))
        self.notify("files")

    def enabled(self, name: str) -> bool:
        """Demo input replacement is unavailable during an immutable snapshot job."""
        return not self._snapshot_running.is_set() if name == "load_example" else True

    def select_file(self, record) -> None:
        """A row of the file table was selected: show that file's decay."""
        path = str(record.get("path", "")) if isinstance(record, dict) else ""
        for i, p in enumerate(self.session.bur_files):
            if str(p) == path:
                self.current_file = i
                return

    def remove_file_row(self, record) -> None:
        """Delete pressed on a row of the file table."""
        if isinstance(record, dict) and record.get("path"):
            self.remove_file(str(record["path"]))

    @property
    def current_file(self) -> int:
        return int(self.session.current_index)

    @current_file.setter
    def current_file(self, value: int) -> None:
        self._ensure_editable()
        value = max(0, min(int(value), max(0, len(self.session.bur_files) - 1)))
        if value != self.session.current_index:
            self.session.current_index = value
            self.session.build_decay()
            self.refit()

    # -- binning --------------------------------------------------------------------------------------------- #
    @property
    def binning(self) -> int:
        return int(self.session.settings.micro_time_binning)

    @binning.setter
    def binning(self, value) -> None:
        self._ensure_editable()
        value = int(value)
        if value == self.binning:
            return
        self.session.set_binning(value)
        self._refresh_measured()
        if self.auto_patterns and self.session.current_tttr() is not None:
            self.session.extract_irf_background()
        self.session.build_decay()
        self.refit()

    def binning_options(self) -> list[int]:
        return list(engine.BINNING_CHOICES)

    # -- measured IRF and background -------------------------------------------------------------------------- #
    def _refresh_measured(self) -> None:
        """Re-read the measured IRF / background files after the binning or the channels changed."""
        try:
            self.session.refresh_pattern_files()
        except Exception as exc:
            self.status_text = str(tr("Could not re-read the measured IRF / background files: {error}")).format(error=exc)

    @property
    def irf_one_for_all(self) -> bool:
        """The IRF files serve every detector (each reads its own channels)."""
        return bool(self.session.irf_one_for_all)

    @irf_one_for_all.setter
    def irf_one_for_all(self, value: bool) -> None:
        self._ensure_editable()
        self.session.irf_one_for_all = bool(value)

    @property
    def bg_one_for_all(self) -> bool:
        """The background files serve every detector (each reads its own channels)."""
        return bool(self.session.bg_one_for_all)

    @bg_one_for_all.setter
    def bg_one_for_all(self, value: bool) -> None:
        self._ensure_editable()
        self.session.bg_one_for_all = bool(value)

    @property
    def save_vv_vhs(self) -> bool:
        """Write the VV | VH histogram of each IRF / background file beside it when it is read."""
        return bool(self.session.save_vv_vhs)

    @save_vv_vhs.setter
    def save_vv_vhs(self, value: bool) -> None:
        self._ensure_editable()
        self.session.save_vv_vhs = bool(value)

    @property
    def irf_model(self) -> str:
        """IRF model of Auto IRF/background: gaussian, skewed or experimental."""
        return str(self.session.settings.irf_model)

    @irf_model.setter
    def irf_model(self, value: str) -> None:
        self._ensure_editable()
        known = [name for name, _label in engine.IRF_MODELS]
        if value not in known:
            raise ValueError(f"Unknown IRF model {value!r}: use one of {known}.")
        if value == self.irf_model:
            return
        self.session.template.irf_model = value
        for settings in self.session.det_settings.values():
            settings.irf_model = value
        if self.auto_patterns and self.session.current_tttr() is not None:
            self.session.extract_irf_background()
            self.session.build_decay()
            self.refit()
        self.notify("settings")

    def irf_model_choices(self) -> list[tuple[str, str]]:
        """(value, label) pairs of the IRF models."""
        return [(name, str(tr(label))) for name, label in engine.IRF_MODELS]

    def _pattern_rows(self, files: dict) -> list[dict]:
        det = self.session.current_detector
        return [{"file": Path(p).name, "folder": str(Path(p).parent), "path": str(p)} for p in files.get(det, [])]

    def irf_file_rows(self) -> list[dict]:
        """The measured IRF files of the current detector."""
        return self._pattern_rows(self.session.irf_files)

    def bg_file_rows(self) -> list[dict]:
        """The measured background files of the current detector."""
        return self._pattern_rows(self.session.bg_files)

    def _add_pattern_files(self, kind: str, paths) -> int:
        self._ensure_editable()
        det = self.session.current_detector
        files, _np, _n, _one = self.session._pattern_store(kind)
        current = list(files.get(det, []))
        new = [Path(p) for p in paths if Path(p).is_file() and Path(p) not in current]
        label = "IRF" if kind == "irf" else "background"
        if not new:
            self.status_text = str(tr("No new {kind} file among the given paths.")).format(kind=label)
            return 0
        try:
            done = self.session.set_pattern_files(kind, det, current + new)
        except Exception as exc:
            self.status_text = str(tr("Could not read the {kind} file: {error}")).format(kind=label, error=exc)
            return 0
        self.status_text = str(tr("{count} measured {kind} file(s) for {detectors}.")).format(
            count=len(current) + len(new), kind=label, detectors=", ".join(done)
        )
        self.session.build_decay()
        self.refit()
        return len(new)

    def add_irf_files(self, paths) -> int:
        """Use measured files as the IRF of the current detector (all detectors with "one for all")."""
        return self._add_pattern_files("irf", paths)

    def add_bg_files(self, paths) -> int:
        """Use measured files as the background of the current detector (all detectors with "one for all")."""
        return self._add_pattern_files("bg", paths)

    def _remove_pattern_row(self, kind: str, record) -> None:
        if not (isinstance(record, dict) and record.get("path")):
            return
        self._ensure_editable()
        det = self.session.current_detector
        files, _np, _n, _one = self.session._pattern_store(kind)
        keep = [p for p in files.get(det, []) if str(p) != record["path"]]
        if keep:
            self.session.set_pattern_files(kind, det, keep)
            self.session.build_decay()
            self.refit()
        else:
            self._clear_pattern(kind)

    def remove_irf_file_row(self, record) -> None:
        """Delete pressed on a row of the IRF file table."""
        self._remove_pattern_row("irf", record)

    def remove_bg_file_row(self, record) -> None:
        """Delete pressed on a row of the background file table."""
        self._remove_pattern_row("bg", record)

    def clear_irf_files(self) -> None:
        """Forget the measured IRF files; Auto IRF/background estimates the IRF again."""
        self._clear_pattern("irf")

    def clear_bg_files(self) -> None:
        """Forget the measured background files; Auto IRF/background estimates the background again."""
        self._clear_pattern("bg")

    def _clear_pattern(self, kind: str) -> None:
        self._ensure_editable()
        self.session.clear_pattern_files(kind, self.session.current_detector)
        self.session.outcome = None
        self.status_text = str(tr("Measured {kind} files cleared.")).format(kind="IRF" if kind == "irf" else "background")
        self.notify("fit")

    # -- hyperparameter optimisation ------------------------------------------------------------------------ #
    @property
    def opt_iterations(self) -> int:
        """Number of fits Opt may spend."""
        return int(getattr(self, "_opt_iterations", 50))

    @opt_iterations.setter
    def opt_iterations(self, value: int) -> None:
        self._opt_iterations = max(5, min(999, int(value)))

    def optimize(self) -> None:
        """Search shift, IRF window and thresholds for the lowest 2I* of the current decay, then apply them."""
        self._cancel.clear()

        def progress(done, total):
            self.status_text = str(tr("Optimising ... {done}/{total} fits")).format(done=done, total=total)
            self.notify("progress")

        try:
            result = hpo.optimize_hyperparameters(
                self.session, self.opt_iterations, seed=0, should_stop=self._cancel.is_set, progress=progress
            )
            if result["stopped"]:
                self.status_text = str(tr("Optimisation stopped; settings restored."))
            else:
                self.status_text = str(tr("Opt: 2I* {before:.3g} to {after:.3g} in {count} fits.")).format(
                    before=result["start_loss"], after=result["loss"], count=result["evaluations"]
                )
            self.notify("fit")
        finally:
            self._release_snapshot()

    # -- derived read-only ----------------------------------------------------------------------------------- #
    @property
    def fit_model(self) -> str:
        """Return the selected registered model for preview and batch fitting."""
        return self.session.settings.model

    @fit_model.setter
    def fit_model(self, name: str) -> None:
        """Select a compatible model without discarding another model's parameter edits."""
        self._ensure_editable()
        engine.validate_fit_model(name)
        if self.fit_model == name:
            return
        self.session.set_model(name)
        self.refit()
        self.notify("settings")

    def fit_model_options(self) -> list[str]:
        """Return registered models that the acquisition-input facade can construct."""
        return list(engine.fit_model_specs())

    def fit_model_choices(self) -> list[tuple[str, str]]:
        """Pair canonical model values with the provider's human-readable labels."""
        return [
            (name, str(tr(spec.get("label", name))))
            for name, spec in engine.fit_model_specs().items()
        ]

    def model_availability(self) -> str:
        """Describe compatible models and the missing inputs of unavailable registry models."""
        return engine.model_availability()

    def model_result_text(self) -> str:
        """Show the primary lifetime and the provider's declared classification result."""
        outcome = self.session.outcome
        if outcome is None:
            return str(tr("No fit result yet."))
        if self.fit_model == engine.TAIL_MODEL:
            return str(tr("Tail lifetimes: {lifetimes} ns; score: {score:.4g}.")).format(
                lifetimes=" / ".join(f"{float(v):.4g}" for v in outcome.x[1:]), score=outcome.two_istar
            )
        text = str(tr("Primary lifetime: {tau:.4g} ns; 2I*: {score:.4g}.")).format(
            tau=self.tau_result, score=outcome.two_istar
        )
        for name in engine.fit_result_names(self.fit_model):
            text += str(tr(" {name}: {value:.0f} (0-based).")).format(
                name=name, value=outcome.result.result(name)
            )
        return text

    @property
    def fit_curves(self):
        outcome = self.session.outcome
        return outcome.curves if outcome is not None else None

    @property
    def tau_result(self) -> float:
        """Return the provider's primary lifetime, including a classified Fit25 winner."""
        outcome = self.session.outcome
        if outcome is None:
            return float("nan")
        return float(outcome.x[1] if self.fit_model == engine.TAIL_MODEL else outcome.x[0])

    @property
    def gamma_result(self) -> float:
        return self._result("gamma")

    @property
    def r0_result(self) -> float:
        return self._result("r0")

    @property
    def rho_result(self) -> float:
        return self._result("rho")

    def _result(self, name: str) -> float:
        outcome = self.session.outcome
        if outcome is None or name not in outcome.names:
            return float("nan")
        return float(outcome.x[outcome.names.index(name)])

    @property
    def two_istar(self) -> float:
        outcome = self.session.outcome
        return float(outcome.two_istar) if outcome is not None else float("nan")

    def parameter_records(self) -> list[dict]:
        """Return the selected model's declared free parameters and their fitted values."""
        names, values, fixed = self.session.settings.parameter_state()
        outcome = self.session.outcome
        rows = []
        for i, name in enumerate(names):
            result = self._result(name)
            if self.fit_model == "fit25" and name.startswith("tau"):
                result = float(values[i])  # Candidates stay inputs; the winner is shown as tau_result.
            rows.append(
                {
                    "name": name,
                    "start": float(values[i]),
                    "fixed": bool(fixed[i]),
                    "result": f"{result:.4g}" if outcome is not None else "",
                }
            )
        return rows

    def edit_parameter(self, record: dict, key: str, value: Any) -> None:
        """A cell of the parameter table was edited (the start value or the fixed flag)."""
        name = str(record.get("name"))
        self._ensure_editable()
        if not self.parameter_cell_editable(record, key):
            raise ValueError("Fit25 lifetime candidates are always fixed.")
        if key in ("start", "fixed"):
            self.session.settings.edit_parameter(name, value, fixed=key == "fixed")
            self.refit()

    def parameter_cell_editable(self, record: dict, key: str) -> bool:
        """Keep discrete candidates fixed while retaining editable lifetime inputs."""
        return key == "start" or (
            key == "fixed"
            and not (self.fit_model == "fit25" and str(record.get("name", "")).startswith("tau"))
        )

    def lifetime_rows(self) -> list[dict]:
        """One row per detector series of the last batch: bursts fitted, median and mean lifetime."""
        rows = []
        for label, values in sorted(fit_view.burst_lifetimes(self.burst_results).items()):
            rows.append(
                {
                    "series": label,
                    "n": str(values.size),
                    "median": f"{np.median(values):.3f}",
                    "mean": f"{values.mean():.3f}",
                }
            )
        return rows

    def input_status(self) -> tuple[bool, int]:
        """Whether the current detector has an IRF and a background, and how many burst files are loaded."""
        det = self.session.current_detector
        needs_irf = self.session.settings.model != engine.TAIL_MODEL
        ready = det in self.session.bg_np and (
            not needs_irf or (det in self.session.irf_np and np.asarray(self.session.irf_np[det]).size > 0)
        )
        return bool(ready), len(self.session.bur_files)

    # -- actions --------------------------------------------------------------------------------------------- #
    def _settings_changed(self, rebuild_decay: bool) -> None:
        if rebuild_decay:
            self.session.build_decay()
        self.refit()

    def refit(self) -> None:
        """Fit the current decay again with the current settings (the wizard's ``update_fit``)."""
        if self.session.current_tttr() is None:
            return
        outcome = self.session.fit()
        if outcome is None and self.session.status:
            self.status_text = self.session.status
        elif outcome is not None:
            self.status_text = self.session.status or (
                self.model_result_text()
                if self.fit_model == engine.TAIL_MODEL
                else f"tau = {self.tau_result:.3f} ns (2I* = {self.two_istar:.3f})"
            )
        self.notify("fit")

    def auto_extract(self) -> None:
        """One click: binning, IRF and background from the non-burst photons, fit window, fit."""
        if self.session.current_tttr() is None:
            self.status_text = "Add burst files first: there is no data to extract an IRF from."
            self._release_snapshot()
            return
        try:
            self.session.auto_extract()
            self.auto_patterns = True
            self.status_text = self.session.status
            self.notify("fit")
        finally:
            self._release_snapshot()

    def run_batch(self) -> None:
        """Fit every burst of every loaded file and detector (worker processes) and keep the rows."""
        if self.session.df_bursts is None:
            self._release_snapshot()
            raise ValueError("Add burst files first.")
        self._cancel.clear()

        def progress(done, total):
            self.status_text = f"Fitting bursts ... {done}/{total}"
            self.notify("progress")

        try:
            rows = self.session.run_batch(progress=progress, should_stop=self._cancel.is_set)
            self.burst_results = rows
            n = len(fit_view.burst_lifetimes(rows))
            self.status_text = f"Fitted {self.n_bursts} bursts ({n} lifetime series)."
            self.notify("batch")
        finally:
            self._release_snapshot()

    def stop(self) -> None:
        self._cancel.set()

    def export_results(self) -> int:
        """Write the ``b?4`` burst tables beside the burst folders; returns how many files were written."""
        self.session.burst_results = self.burst_results
        written = self.session.export_results()
        self.status_text = f"{len(written)} burst-fit file(s) written."
        self.notify("export")
        return len(written)

    # -- inspected burst ------------------------------------------------------------------------------------- #
    def inspected_burst(self) -> dict[str, np.ndarray]:
        n = self.n_bursts
        if n == 0:
            return {}
        self.nav_burst = max(0, min(int(self.nav_burst), n - 1))
        return self.session.inspect_burst(self.nav_burst)

    # -- settings file --------------------------------------------------------------------------------------- #
    def save_settings(self, path: str | Path) -> None:
        payload = dict(
            self.session.settings_payload(), kind=SETTINGS_KIND, auto_patterns=self.auto_patterns
        )
        Path(path).write_text(
            json.dumps(payload, indent=2, cls=engine.NumpyEncoder), encoding="utf-8"
        )

    def load_settings(self, path: str | Path) -> None:
        """Restore all detectors and per-model parameter edits from a settings file."""
        self._ensure_editable()
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("kind") != SETTINGS_KIND:
            raise ValueError("Not a burst-MLE settings file written by this tool.")
        self.session.apply_settings_payload(payload)
        self.auto_patterns = bool(payload.get("auto_patterns"))
        self.notify("settings")

    # -- snapshot for a running job -------------------------------------------------------------------------- #
    def values_snapshot(self) -> SimpleNamespace:
        """The spec's values as a throw-away object: edits made while a job runs go nowhere."""
        ns = SimpleNamespace(**{name: getattr(self, name) for name in SETTING_ATTRS})
        for name in (
            "binning", "current_detector", "current_file", "nav_burst", "fit_model", "irf_model", "irf_one_for_all",
            "bg_one_for_all", "save_vv_vhs", "opt_iterations",
        ):
            setattr(ns, name, getattr(self, name))
        for method in (
            "detector_names",
            "binning_options",
            "fit_model_options",
            "fit_model_choices",
            "model_availability",
            "model_result_text",
            "file_rows",
            "irf_file_rows",
            "bg_file_rows",
            "irf_model_choices",
            "parameter_records",
            "parameter_cell_editable",
            "lifetime_rows",
            "select_file",
            "remove_file_row",
            "remove_irf_file_row",
            "remove_bg_file_row",
        ):
            setattr(ns, method, getattr(self, method))
        ns.edit_parameter = lambda *a, **k: None
        return ns


for _name, (_kind, _rebuild) in SETTING_ATTRS.items():
    setattr(MleViewModel, _name, _setting_property(_name, _kind, _rebuild))
