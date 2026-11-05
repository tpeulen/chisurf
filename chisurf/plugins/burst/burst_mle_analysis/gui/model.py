"""View model of the emtk burst-MLE app (cards ML0 to ML5): the engine's session behind spec-bound attributes.

The AutoForm spec ``mle_native.view.json`` reads and writes the attributes of :class:`MleViewModel`; each one is a view
on :class:`~..engine.MleSession` (the same session the engine tests check). Changing a setting
refits the current decay. The slow actions (auto IRF/background, the batch over every burst) run on
a snapshot through :class:`chisurf.emtk.jobs.SnapshotJob`.

Nothing here imports a GUI toolkit.
"""

from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np

from chisurf.core.fluorescence.detector_names import ACCEPTOR, DONOR
from chisurf.core.support.i18n import tr
from chisurf.plugins.core.pto_inspector.core import RunPickerMixin

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
    "fix_shift_sp": (bool, False),
    "fix_shift_ss": (bool, False),
    "fix_shift": (bool, False),
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

#: The per-detector settings "Save fit" stores on the detector setup.
SETUP_KEYS = (
    "micro_time_start",
    "micro_time_stop",
    "irf_threshold_vv",
    "irf_threshold_vh",
    "shift",
    "shift_sp",
    "shift_ss",
    "irf_start",
    "irf_stop",
    "p2s_twoIstar",
    "BIFL_scatter",
    "fix_tau",
    "fix_gamma",
    "fix_r0",
    "fix_rho",
    "fix_shift_sp",
    "fix_shift_ss",
    "fix_shift",
    "min_photons",
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
        if name in ("shift", "shift_sp", "shift_ss"):
            # a shift set by hand is the start the fit holds it at (over the calibration)
            self.session.set_shift(self.session.current_detector, MleViewModel._EDIT_KEY[name], value)
        else:
            setattr(self.session.settings, name, value)
        self._settings_changed(rebuild_decay)

    return property(getter, setter)


class MleViewModel(RunPickerMixin):
    """State and actions of the burst-MLE lifetime tool.

    A ``.pto`` among the burst files is a measurement container: the Runs table lists its burst searches and the
    one picked is the burst table the fit reads (:meth:`select_run`).
    """

    run_picker_attr = "run_container"

    def __init__(self, session: MleSession | None = None) -> None:
        self.session = session or MleSession()
        self._observers: list[Callable[[str], None]] = []
        self._cancel = threading.Event()
        self._snapshot_running = threading.Event()
        self.status_text = "Add burst tables (.pto) to begin."
        self.burst_results: list[dict] = []
        #: The pipeline's mode (standalone: everything shown); Simple hides the H2MM split.
        self.advanced = True
        #: Fingerprint of the request :attr:`burst_results` answers (``None``: nothing held, or stopped/failed).
        self.held_fingerprint: str | None = None
        #: ``True`` after a run was skipped as unchanged: the view highlights **Restart**.
        self.restart_attention = False
        self.nav_burst = 0
        self.detector_editor_data: dict | None = None
        #: ``True`` while the IRF and background are the ones estimated from non-burst photons (so a binning change
        #: re-estimates them at the new binning).
        self.auto_patterns = False
        #: A source picked while the IRF tool's tuned IRF is in use: waits for the user to say
        #: whether the tuned one is discarded (:meth:`confirm_irf_from`).
        self.irf_confirm = ""
        if not self.session.detectors:
            self.session.set_detectors(
                {
                    DONOR: {
                        "chs": [0, 1],
                        "micro_time_ranges": [],
                        "g_factor": 1.0,
                        "l1": 0.0,
                        "l2": 0.0,
                    },
                    ACCEPTOR: {
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
            elif key in ("df_bursts", "burst_results"):
                # Shared, not copied: no job writes into the burst table or into a batch's rows (a
                # new table or list replaces them, ``attach_run`` builds new rows). Copying the
                # table cost 0.27 s and the 65 k fitted rows 1-16 s of the UI thread at every
                # job start.
                setattr(session, key, value)
            else:
                setattr(session, key, copy.deepcopy(value))
        session.tttrs.paths = session.tttr_paths
        snapshot.session = session
        snapshot._observers = []
        snapshot.burst_results = self.burst_results  # shared, as the session's (above)
        snapshot._snapshot_running = threading.Event()
        snapshot._source_snapshot_running = self._snapshot_running
        return snapshot

    def _ensure_editable(self) -> None:
        """Reject edits of acquisition or model state while its snapshot job is running."""
        if self._snapshot_running.is_set():
            raise RuntimeError(tr("Wait for the running Burst MLE job before changing its inputs."))

    def release_snapshot(self) -> None:
        """:class:`~chisurf.emtk.jobs.SnapshotJob`: the job of this model's copy ended; allow edits.

        Called for every outcome, including a job stopped while held, whose method never ran
        and so never reached :meth:`_release_snapshot`.
        """
        self._snapshot_running.clear()

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
        """Take the detector definition of the shared editor (every change of it). A new G, l1
        or l2 (Data Selection's G from the reference dye) calibrates the IRF's time shifts again:
        the reference fit is the dye fitted with the polarisation factors the bursts get."""

        def factors(detectors) -> dict:
            return {d: tuple(float((v or {}).get(k, x)) for k, x in (("g_factor", 1.0), ("l1", 0.0), ("l2", 0.0)))
                    for d, v in (detectors or {}).items()}

        self._ensure_editable()
        before = factors(self.session.detectors)
        self.session.set_definition(settings)
        polarisation = factors(self.session.detectors) != before
        if self.session.current_tttr() is not None:
            self._refresh_measured()
            if self.auto_patterns:
                self.session.extract_irf_background()  # calibrates the shifts with it
            elif polarisation:
                self.session.recalibrate_shifts()
            self.session.build_decay()
            self.refit()
        elif polarisation:
            self.session.recalibrate_shifts()
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
        shifts = [k for k in ("shift", "shift_sp", "shift_ss") if k in saved]
        if shifts:
            # the setup's saved shifts are the detector's own: its base, over any edit of them
            base = self.session.shift_base(det)
            edits = self.session.shift_edits.get(det) or {}
            for key in shifts:
                base[key] = int(saved[key]) if key == "shift" else float(saved[key])
                edits.pop(self._EDIT_KEY[key], None)
            self.session.calibrate_shift(det)

    def save_fit_to_setup(self, definition) -> str:
        """Store the current detector's window, thresholds, shifts, 2I*/BIFL flags and fix flags on the selected setup.

        ``definition`` is the detector-setup store of the editor (``setups``, ``current_name`` and ``_persist``); the
        values go to ``setups[name]["detectors"][detector]["mle_settings"]`` and are applied again whenever that
        detector is selected on this setup. Returns the status line.
        """
        det = self.session.current_detector
        name = getattr(definition, "current_name", "")
        if not name or name not in definition.setups:
            self.status_text = str(
                tr(
                    "No detector setup selected: pick or save a setup in the Detector setup tab first."
                )
            )
            return self.status_text
        setup = definition.setups[name]
        detectors = setup.get("detectors") or {}
        if det not in detectors:
            self.status_text = str(tr("Detector {detector} is not in setup {setup}.")).format(
                detector=det, setup=name
            )
            return self.status_text
        settings = self.session.settings
        params = {key: SETTING_ATTRS[key][0](getattr(settings, key)) for key in SETUP_KEYS}
        existing = detectors[det].get("mle_settings")
        merged = dict(existing) if isinstance(existing, dict) else {}
        merged.update(params)
        detectors[det]["mle_settings"] = merged
        definition._persist()
        self.session.detectors.setdefault(det, {})["mle_settings"] = dict(merged)
        self.status_text = str(
            tr("MLE settings of detector {detector} saved to setup {setup}.")
        ).format(detector=det, setup=name)
        return self.status_text

    # -- files ----------------------------------------------------------------------------------------------- #
    def file_rows(self) -> list[dict]:
        return [
            {"file": p.name, "folder": str(p.parent), "path": str(p)}
            for p in self.session.bur_files
        ]

    def current_file_text(self) -> str:
        """Name of the burst file whose decay is shown, with its position."""
        files = self.session.bur_files
        if not files:
            return ""
        index = max(0, min(int(self.session.current_index), len(files) - 1))
        return str(tr("Current file: {name} ({index} of {count})")).format(
            name=files[index].name, index=index + 1, count=len(files)
        )

    def inspected_file_name(self) -> str:
        """Name of the measurement the inspected burst belongs to (its ``First File``), or an empty string.

        Drawn every frame under the inspected burst: kept per (burst, table)."""
        table = self.session.df_bursts
        if table is None or not 0 <= int(self.nav_burst) < self.n_bursts:
            return ""
        held = self.__dict__.get("_inspected_name")
        if held is not None and held[0] is table and held[1] == int(self.nav_burst):
            return held[2]
        name = ""
        if "First File" in engine.column_names(table):
            name = Path(str(table["First File"][int(self.nav_burst)])).name
        self._inspected_name = (table, int(self.nav_burst), name)
        return name

    @property
    def n_bursts(self) -> int:
        return (
            int(engine.row_count(self.session.df_bursts))
            if self.session.df_bursts is not None
            else 0
        )

    @property
    def run_container(self) -> str:
        """The first burst input that is a ``.pto`` (or a run in one); the Runs table lists its runs."""
        for path in self.session.bur_files:
            if engine._is_container(path):
                return str(path)
        return ""

    def select_run(self, row) -> None:
        """Fit the run picked in the Runs table: it replaces the container's entry among the burst files."""
        self._ensure_editable()
        super().select_run(row)
        chosen = Path(self.run_path) if self.run_path else None
        if chosen is None or not engine._is_container(chosen):
            return
        from chisurf.core.fio.analysis_path import split_container_path

        container = split_container_path(chosen)[0]
        files = [
            chosen if engine._is_container(p) and split_container_path(p)[0] == container else p
            for p in self.session.bur_files
        ]
        if files == self.session.bur_files:
            return
        self.session.bur_files = []
        self.session.df_bursts = None
        self.session.add_burst_files(files)
        self.session.build_decay()
        self.session.outcome = None
        self.burst_results = []
        self.session.burst_results = []
        self.status_text = f"Run {chosen.name}: {self.n_bursts} bursts."
        self.notify("files")

    def add_files(self, paths) -> int:
        """Add ``.pto`` containers (a folder adds the containers under it); returns how many were new.

        Legacy ``.bur`` trees are no longer an input: the File:Data:Legacy Export plugin
        is the door between them and the container world.
        """
        self._ensure_editable()
        found: list[Path] = []
        for value in map(Path, paths):
            if engine._is_container(value):
                found.append(value)
            elif value.is_dir():
                found.extend(sorted(value.rglob("*.pto")))
        new = [p for p in found if p not in self.session.bur_files]
        if not new:
            self.status_text = "No new .pto container among the given paths."
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

    def take_bursts(
        self, paths, settings: dict | None = None, prepare_from=(), references: dict | None = None
    ) -> None:
        """The pipeline's hand-over, as one background job: the new bursts replace the old (and
        their lifetimes), the workflow's setup goes on top (after the files: a container may carry
        the setup of the search that wrote it), then the IRF and background are prepared -- from
        the *references* Data Selection declared (``{"irf", "buffer", "reference"}`` file lists),
        else from the measurements found beside *prepare_from*."""
        if self.session.bur_files:
            self.clear_files()
        self.add_files(paths)
        if settings:
            self.set_setup(settings)
        if prepare_from:
            self.prepare_patterns(prepare_from, references)

    # -- the bursts searched ahead (before Next wrote them) ------------------------------------------ #
    def take_ahead(
        self, tables: dict, key: str, settings: dict | None = None, prepare_from=(),
        references: dict | None = None, dropped: threading.Event | None = None,
    ) -> None:
        """The pipeline's hand-over ahead of Next, as one background job: the bursts Burst
        Selection found ahead (``{photon file: burst table}``, nothing written yet,
        :meth:`MleSession.take_ahead`), the workflow's setup, the IRF and background prepared as
        :meth:`take_bursts` prepares them (reference dye, strict background, shift calibration,
        reference fits), then every burst fitted on half the fit's threads -- the user is still
        at the search settings. The results are written once Next wrote the run
        (:meth:`attach_ahead`). Stopped (:meth:`stop`) the job
        ends without merging anything; so does setting *dropped* (this preparation's own flag:
        the next one may start while it runs out)."""

        def stopped() -> bool:
            return self._cancel.is_set() or (dropped is not None and dropped.is_set())

        try:
            if self.session.bur_files:
                self.clear_files()
            self.session.take_ahead(tables, key)
            if settings:
                self.set_setup(settings)
            if prepare_from:
                self.prepare_patterns(prepare_from, references)
            if stopped():
                raise InterruptedError("")
            if self.session.irf_np.get(self.session.current_detector) is not None:
                self.session.ensure_background()  # the photons outside the bursts, once
            if not self.input_status()[0]:
                return  # nothing to fit with yet: Next prepares and fits as usual
            fingerprint = self.session.batch_fingerprint()
            workers = max(1, engine.fit_workers() // 2)  # the window and the search ahead first

            def progress(done, total):
                self.status_text = f"Fitting the bursts searched ahead ... {done}/{total}"
                self.notify("progress")

            try:
                rows = self.session.run_batch(
                    progress=progress, max_workers=workers, should_stop=stopped
                )
            except InterruptedError:
                raise InterruptedError("") from None  # dropped: no message, nothing merged
            self.burst_results = rows
            self.held_fingerprint = fingerprint
            self.status_text = (
                f"Fitted {self.n_bursts} bursts searched ahead; their lifetimes are written "
                "once the bursts are stored (Next)."
            )
            self.notify("batch")
        finally:
            self._release_snapshot()

    def attach_ahead(
        self, runs, key: str, settings: dict | None = None, prepare_from=(),
        references: dict | None = None,
    ) -> None:
        """Next wrote the bursts searched ahead as *runs*: the session prepared (and fitted)
        ahead becomes theirs (:meth:`MleSession.attach_run`) and its lifetimes are written into
        them. When the bursts are not those of search *key* (it was dropped, or failed) the runs
        are taken as usual (:meth:`take_bursts`)."""
        session = self.session
        session.burst_results = self.burst_results  # the rows to rename are the ones shown
        if session.ahead_key == str(key) and session.attach_run(runs):
            self.burst_results = session.burst_results  # the renamed rows (new ones)
            if self.burst_results:
                self.held_fingerprint = session.batch_fingerprint()
                self._write_results()
            self.notify("files")
            self._release_snapshot()
            return
        self.take_bursts(runs, settings, prepare_from, references)
        self._release_snapshot()

    def clear_files(self) -> None:
        self.remove_file("")
        self.session.bur_files = []
        self.session.df_bursts = None
        self.session.tttr_paths.clear()
        self.burst_results = []
        self.held_fingerprint = None
        self.restart_attention = False
        self.session.burst_results = []
        self.status_text = "Add burst tables (.pto) to begin."
        self.notify("files")

    def load_example(self) -> None:
        """Replace working inputs with generated synthetic bursts; leave fitting to the user."""
        from ..demo import SETUP, make_demo

        self._ensure_editable()
        path = make_demo()
        self.session = engine.MleSession(template=engine.MleSettings(gamma=0.0, r0=0.0))
        self.session.set_definition(SETUP)
        self.session.add_burst_files([path])
        self.session.build_decay()
        self.burst_results = []
        self.held_fingerprint = None
        self.restart_attention = False
        self.auto_patterns = False
        self.nav_burst = 0
        self.detector_editor_data = self.session.definition_payload()
        self.status_text = str(
            tr(
                "Synthetic demo: 16 bursts, 1000 photons each; input lifetime 2 ns. Press Auto IRF/background to fit."
            )
        )
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

    # -- measured IRF and background -------------------------------------------------------------------------- #
    def _refresh_measured(self) -> None:
        """Re-read the measured IRF / background files after the binning or the channels changed."""
        try:
            self.session.refresh_pattern_files()
        except Exception as exc:
            self.status_text = str(
                tr("Could not re-read the measured IRF / background files: {error}")
            ).format(error=exc)

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

    # -- where the IRF comes from ---------------------------------------------------------------- #
    #: Plain words for the selector's options; the details are in their tooltips.
    IRF_NOTES = {
        "auto": "The best there is, in this order: the reference dye (measured in the same "
        "conditions as the sample, so it comes first), the IRF measurement (water, Ludox), the "
        "photons outside the bursts, an estimate from the data.",
        "measurement": "The IRF measurement of Data Selection (water, Ludox): scattered light, "
        "the IRF itself after its background (and the buffer) is taken off.",
        "reference": "The reference dye of Data Selection (Rh110, Alexa647): its decay is the IRF "
        "times the dye's known decay; the IRF tool takes the dye's decay out (deconvolution).",
        "outside": "The scattered light between the molecules of this measurement: a pulse "
        "fitted to its rising edge (the fluorescence of dim molecules is left behind).",
        "estimate": "Estimated from the burst decay itself (blind): the last resort, when "
        "nothing was measured.",
        "tuned": "The IRF computed in the IRF tool.",
    }

    def _det(self) -> str:
        return self.session.current_detector

    @property
    def irf_from(self) -> str:
        """Where the current detector's IRF comes from (a key of ``engine.IRF_CHOICES``, or ``tuned``)."""
        return self.session.irf_choice.get(self._det(), "auto")

    @irf_from.setter
    def irf_from(self, value: str) -> None:
        self._ensure_editable()
        value = str(value)
        if value == self.irf_from:
            return
        if self.irf_from == "tuned" and value != "tuned":
            self.irf_confirm = value  # the tuned IRF goes only once the user says so
            return
        self._use_irf_from(value)

    def confirm_irf_from(self, discard: bool) -> None:
        """The answer to "discard the tuned IRF?": use the source picked, or keep the tuned one."""
        value, self.irf_confirm = self.irf_confirm, ""
        if discard and value:
            self._use_irf_from(value)

    def _use_irf_from(self, value: str) -> None:
        det = self._det()
        if value == "tuned":
            self.session.irf_choice[det] = "tuned"
            self.session.apply_irf_choice(det)
        else:
            self.session.choose_irf(det, value)
        if self.session.current_tttr() is not None:
            self.session.build_decay()
            self.refit()
        self.notify("patterns")

    def take_tuned_irf(self, det: str, irf, text: str, inputs: dict | None = None) -> bool:
        """The IRF the IRF tool computed for *det*: fitted from now on (the selector says "IRF
        tool (tuned)"); ``False`` (said in the status) when it does not fit this decay."""
        shifts = (inputs or {}).get("shifts")
        if shifts is not None:  # shifts set in the IRF tool replace the calibrated ones
            self.session.shift_edits[det] = dict(
                self.session.shift_edits.get(det) or {},
                shift_vv=float(shifts[0]), shift_vh=float(shifts[1]), source="IRF tool",
            )
        ok = self.session.take_tuned_irf(det, irf, text, inputs)
        if not ok:
            self.status_text = str(tr("The IRF tool's IRF has another length than this decay (binning?)."))
            return False
        self.irf_confirm = ""
        if det == self._det() and self.session.current_tttr() is not None:
            self.session.build_decay()
            self.refit()
        self.notify("patterns")
        return True

    def _irf_options(self) -> list[tuple[str, str, bool, str]]:
        options = list(self.session.irf_options(self._det()))
        if "tuned" in self.session.irf_candidates.get(self._det(), {}):
            options.append(("tuned", "IRF tool (tuned)", True, ""))
        return options

    def irf_from_choices(self) -> list[tuple[str, str]]:
        """(value, label) of the selector."""
        return [(key, str(tr(label))) for key, label, _ok, _why in self._irf_options()]

    def irf_from_enabled(self) -> list[bool]:
        """Which options have their measurement (the others are greyed)."""
        return [ok for _key, _label, ok, _why in self._irf_options()]

    def irf_from_notes(self) -> list[str]:
        """Each option's tooltip: what it is, or why it cannot be picked."""
        return [
            str(tr(self.IRF_NOTES[key])) if ok else str(tr(why))
            for key, _label, ok, why in self._irf_options()
        ]

    def irf_status(self) -> str:
        """What the IRF in use is, in a few words ("Rh110 · reference dye")."""
        session, det = self.session, self._det()
        text = session.irf_source.get(det, "")
        if not text:
            return str(tr("No IRF yet"))
        inputs = session.irf_inputs.get(det) or {}
        kind = inputs.get("kind")
        if self.irf_from == "tuned":
            text = str(tr("IRF tool (tuned)"))
        elif kind == "reference":
            text = f"{inputs.get('dye') or ''} · {tr('reference dye')}".strip(" ·")
        elif kind == "scatter":
            text = str(tr("IRF measurement"))
        elif kind == "non_burst":
            text = str(tr("Outside the bursts"))
        else:
            text = str(tr("Estimated from the data"))
        shift = session.shift_calibration.get(det)
        if shift:
            what = shift.get("dye") or str(tr("IRF tool"))
            text += " · " + str(tr("shift calibrated ({what})")).format(what=what)
            if shift.get("fit_chi2r") is not None:
                text += " · " + str(tr("reference fit χ²ᵣ {value:.2f}")).format(value=shift["fit_chi2r"])
            if shift.get("warning"):
                text += " ⚠"
        return text

    def irf_status_tooltip(self) -> str:
        """Every detail of the IRF in use: files, lifetime, rotation, how it was made."""
        det = self._det()
        text = self.session.irf_source.get(det, "")
        if not text:
            return str(tr("Press Next: the IRF is made from the data."))
        lines = [f"{det}: {text}"]
        shift = self.session.shift_calibration.get(det)
        if shift:
            if shift.get("text"):
                where = str(tr("single-molecule measurement")) if shift.get("single_molecule") else str(
                    tr("bulk measurement")
                )
                lines.append(f"{tr('IRF time shift')}: {shift['text']}; {where}.")
                lines.append(str(tr(
                    "A reference dye measured at single-molecule conditions is preferred: SPAD timing "
                    "moves with the count rate, so it has the bursts' timing offset; a bulk measurement "
                    "at a high rate is shifted."
                )))
                rates = [
                    f"{label} {value:.0f} kHz"
                    for label, value in ((tr("reference"), shift.get("reference_rate_khz")),
                                         (tr("bursts"), shift.get("burst_rate_khz")))
                    if value
                ]
                if rates:
                    lines.append(f"{tr('Count rate')}: " + ", ".join(rates))
                if shift.get("fit_chi2r") is not None:
                    lines.append(str(tr(
                        "Reference fit: the dye's decay fitted with this IRF and the burst model "
                        "(lifetime {tau:.2f} ns fixed, G {g:.3f}, the shifts above): χ²ᵣ {chi2r:.3f}; "
                        "with G free ({g_free:.3f}) χ²ᵣ {chi2r_free:.3f}. About 1 when the IRF, G, "
                        "l1, l2 and the rotation describe the reference; the IRF tool's Reference "
                        "fit view shows its residuals."
                    )).format(
                        tau=float(shift.get("tau_ns") or 0.0), g=float(shift["fit_g"]),
                        chi2r=float(shift["fit_chi2r"]), g_free=float(shift["fit_g_fitted"]),
                        chi2r_free=float(shift["fit_chi2r_g_free"]),
                    ))
                if shift.get("warning"):
                    lines.append("⚠ " + shift["warning"])
                if shift.get("tau_known") and shift.get("tau_source", {}).get("sources"):
                    cite = shift["tau_source"]["sources"][0].get("citation", "")
                    lines.append(f"{tr('Lifetime from')}: {cite}")
            else:
                lines.append(
                    f"{tr('IRF time shift')}: VV {shift['shift_vv']:+.2f}, VH {shift['shift_vh']:+.2f} "
                    f"{tr('bins, set in the IRF tool')}."
                )
        return "\n".join(lines)

    def irf_model_choices(self) -> list[tuple[str, str]]:
        """(value, label) pairs of the IRF models."""
        return [(name, str(tr(label))) for name, label in engine.IRF_MODELS]

    def _pattern_rows(self, files: dict) -> list[dict]:
        det = self.session.current_detector
        return [
            {"file": Path(p).name, "folder": str(Path(p).parent), "path": str(p)}
            for p in files.get(det, [])
        ]

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
            self.status_text = str(tr("No new {kind} file among the given paths.")).format(
                kind=label
            )
            return 0
        try:
            done = self.session.set_pattern_files(kind, det, current + new)
        except Exception as exc:
            self.status_text = str(tr("Could not read the {kind} file: {error}")).format(
                kind=label, error=exc
            )
            return 0
        if not done:
            self.status_text = str(
                tr("The {kind} file(s) show no detector a response; nothing changed.")
            ).format(kind=label)
            return 0
        self.status_text = (
            self.irf_source_text()
            if kind == "irf"
            else str(tr("{count} measured {kind} file(s) for {detectors}.")).format(
                count=len(current) + len(new), kind=label, detectors=", ".join(done)
            )
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
        """Forget the buffer files (a scatter IRF is then corrected by its flat floor only)."""
        self._clear_pattern("bg")

    def _clear_pattern(self, kind: str) -> None:
        self._ensure_editable()
        self.session.clear_pattern_files(kind, self.session.current_detector)
        self.session.outcome = None
        self.status_text = str(tr("Measured {kind} files cleared.")).format(
            kind="IRF" if kind == "irf" else "background"
        )
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
            self.status_text = str(tr("Optimising ... {done}/{total} fits")).format(
                done=done, total=total
            )
            self.notify("progress")

        try:
            result = hpo.optimize_hyperparameters(
                self.session,
                self.opt_iterations,
                seed=0,
                should_stop=self._cancel.is_set,
                progress=progress,
            )
            if result["stopped"]:
                self.status_text = str(tr("Optimisation stopped; settings restored."))
            else:
                self.status_text = str(
                    tr("Opt: 2I* {before:.3g} to {after:.3g} in {count} fits.")
                ).format(
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
        # the detector on screen: each detector has its own model (donor fit23, the acceptor's
        # sensitised emission a tail fit, ...)
        self.session.set_model(name, det=self.session.current_detector)
        self.refit()
        self.notify("settings")

    def fit_model_options(self) -> list[str]:
        """Return registered models that the acquisition-input facade can construct."""
        return list(engine.fit_model_specs())

    def fit_model_choices(self) -> list[tuple[str, str]]:
        """Pair canonical model values with the provider's human-readable labels.

        Until the compiled registries are read (on a worker thread: IMP.bff's import is ~200 ms of a first frame)
        the choice offers the current model alone.
        """
        from chisurf.core.registry import catalog

        if not catalog.prefetch():
            return [(self.fit_model, str(self.fit_model))]
        return [
            (name, str(tr(spec.get("label", name))))
            for name, spec in engine.fit_model_specs().items()
        ]

    def model_availability(self) -> str:
        """Describe compatible models and the missing inputs of unavailable registry models."""
        from chisurf.core.registry import catalog

        if not catalog.prefetch():
            return str(tr("Reading the model registry…"))
        return engine.model_availability()

    def model_result_text(self) -> str:
        """Show the primary lifetime and the provider's declared classification result."""
        outcome = self.session.outcome
        if outcome is None:
            return str(tr("No fit result yet."))
        if self.fit_model == engine.TAIL_MODEL:
            return str(tr("Tail lifetimes: {lifetimes} ns; score: {score:.4g}.")).format(
                lifetimes=" / ".join(f"{float(v):.4g}" for v in outcome.x[1:]),
                score=outcome.two_istar,
            )
        text = str(tr("Primary lifetime: {tau:.4g} ns; 2I*: {score:.4g}.")).format(
            tau=self.tau_result, score=outcome.two_istar
        )
        anisotropy = self.anisotropy_text()
        if anisotropy:
            text += " " + anisotropy
        share = self.background_share()
        if share is not None:
            text += " " + str(
                tr("Background: {share:.1%} of the photons in the window ({what}).")
            ).format(share=share, what=self.background_text(detail=False))
        for name in engine.fit_result_names(self.fit_model):
            text += str(tr(" {name}: {value:.0f} (0-based).")).format(
                name=name, value=outcome.result.result(name)
            )
        return text

    def background_text(self, det: str | None = None, detail: bool = True) -> str:
        """What the fit background of *det* (the current detector) is, in words; *detail*
        ``False``: in two or three (the fit line under the model, which must stay short)."""
        det = det or self.session.current_detector
        self.session.background_of(det)  # kept: what it was made of
        info = self.session.background_info.get(det) or {}
        sel = info.get("selection") or {}
        if not detail:
            short = {"buffer": "the buffer", "strict": "strict background selection",
                     "model": "flat + scatter model"}
            return str(tr(short.get(info.get("source"), "no background yet")))
        if info.get("source") == "buffer":
            return str(tr("the buffer {files}: its shape and rate")).format(files=info.get("files", ""))
        if info.get("source") == "strict":
            return str(tr(
                "the strict background selection: {seconds:.0f} s ({fraction:.0%} of the "
                "measurement) at the background's level"
            )).format(seconds=sel.get("seconds", 0.0), fraction=sel.get("fraction", 0.0))
        if info.get("source") == "model":
            flat = info.get("flat_bursts", info["flat"])
            scatter = info.get("scatter_bursts", info["scatter"])
            return str(tr(
                "a flat + scatter model, as {reason}: flat VV {fv:.3g} | VH {fh:.3g} counts per "
                "bin, scatter {sv:.3g} | {sh:.3g} counts in the IRF's shape"
            )).format(reason=info.get("reason", ""), fv=flat[0], fh=flat[1], sv=scatter[0], sh=scatter[1])
        return str(tr("no background yet"))

    def background_share(self) -> float | None:
        """The share of the photons in the fit window that the background's rate puts there."""
        curves = self.fit_curves
        if curves is None or curves.background is None:
            return None
        data = float(np.sum(curves.data))
        return float(np.sum(curves.background)) / data if data > 0 else None

    def calibration_text(self) -> str:
        """The current detector's polarisation corrections and the rate of its background.

        The G factor and the leakages l1, l2 are the detector definition's (edit them in the Detector setup tab);
        the background rate is the buffer's, else the flat + scatter part of the photons outside the bursts over the
        time outside them, in kHz (beside it, the rate of all photons outside the bursts, mostly fluorescence).
        """
        g, l1, l2 = self.session.polarisation()
        text = str(tr("G {g:.4f}, l1 {l1:.4f}, l2 {l2:.4f}.")).format(g=g, l1=l1, l2=l2)
        det = self.session.current_detector
        self.session.background_of(det)
        info = self.session.background_info.get(det) or {}
        if info.get("rate_khz") is not None:
            text += str(tr(" Background rate: {rate:.4g} kHz")).format(rate=info["rate_khz"])
            if info.get("outside_khz") is not None:
                text += str(tr(" (all photons outside the bursts: {rate:.4g} kHz)")).format(rate=info["outside_khz"])
            text += "."
        sel = self.session.strict_background
        if sel and info.get("source") != "buffer":
            if sel.get("warning"):
                text += " ⚠ " + str(tr("No stretch at the background level: flat + scatter model."))
            else:
                text += str(tr(" Strict background selection: {fraction:.0%} of the time.")).format(
                    fraction=sel["fraction"]
                )
        return text

    def anisotropy_text(self) -> str:
        """The scatter and experimental anisotropy of the last single-lifetime (Fit23) fit, or nothing."""
        outcome = self.session.outcome
        result = getattr(outcome, "result", None)
        if self.fit_model != "fit23" or result is None:
            return ""
        r_scatter = getattr(result, "r_scatter", float("nan"))
        r_experimental = getattr(result, "r_experimental", float("nan"))
        return str(tr("r scatter {scatter:.4g}, r experimental {experimental:.4g}.")).format(
            scatter=float(r_scatter), experimental=float(r_experimental)
        )

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
        """Return the selected model's declared free parameters and their fitted values (none until the model
        registry has been read in the background)."""
        from chisurf.core.registry import catalog

        if not catalog.prefetch():
            return []
        names, values, fixed = self.session.settings.parameter_state()
        outcome = self.session.outcome
        rows = []
        for i, name in enumerate(names):
            result = self._result(name)
            if self.fit_model == "fit25" and name.startswith("tau"):
                result = float(
                    values[i]
                )  # Candidates stay inputs; the winner is shown as tau_result.
            rows.append(
                {
                    "name": name,
                    "start": float(values[i]),
                    "fixed": bool(fixed[i]),
                    "result": f"{result:.4g}" if outcome is not None else "",
                }
            )
        if self.fit_model != engine.TAIL_MODEL:
            rows += self.shift_records()
        return rows

    #: The Fit parameters table's names of the detector's time shifts -> their setting.
    SHIFT_ROWS = {label: key for key, label in engine.SHIFT_PARAMETERS}
    #: The setting of a shift -> its key in a shift calibration / edit.
    _EDIT_KEY = {"shift_sp": "shift_vv", "shift_ss": "shift_vh", "shift": "shift"}

    def shift_records(self) -> list[dict]:
        """The current detector's three time shifts as rows of the Fit parameters table: the
        IRF against the VV data, against the VH data, and the VH decay against the VV decay.
        ``start`` is the calibrated value (or the one set by hand, or 0), ``fixed`` holds it,
        ``result`` is what the fit used; ``tip`` says where the start came from."""
        session = self.session
        det = session.current_detector
        if det not in session.detectors:
            return []
        settings = session.settings
        starts = session.shift_starts(det)
        shown = session.outcome is not None
        rows = []
        for key, label in engine.SHIFT_PARAMETERS:
            used = getattr(settings, key)
            rows.append({
                "name": label,
                "start": int(starts[key]) if key == "shift" else round(float(starts[key]), 2),
                "fixed": bool(getattr(settings, f"fix_{key}")),
                "result": (f"{int(used):d}" if key == "shift" else f"{float(used):.2f}") if shown else "",
                "tip": self.shift_tooltip(key),
            })
        return rows

    def shift_tooltip(self, key: str) -> str:
        """Where the start of the shift *key* (``shift_sp``, ``shift_ss``, ``shift``) came from."""
        session, det = self.session, self.session.current_detector
        entry = session.shift_calibration.get(det) or {}
        edit_key = self._EDIT_KEY[key]
        meaning = {
            "shift_sp": tr("The IRF's time shift against the VV decay, bins (sub-bin)."),
            "shift_ss": tr("The IRF's time shift against the VH decay, bins (sub-bin)."),
            "shift": tr("The VH decay's shift against the VV decay, whole bins: the VH half of the "
                        "data, IRF and background is moved by it."),
        }[key]
        lines = [str(meaning)]
        edits = session.shift_edits.get(det) or {}
        if edit_key in edits:
            calibrated = entry.get("calibrated_shift" if key == "shift" else f"calibrated_{edit_key[6:]}")
            lines.append(str(tr("Start: set by hand ({source}); calibrated {value}.")).format(
                source=tr(str(edits.get("source") or "edited")),
                value="—" if calibrated is None else (f"{int(calibrated):d}" if key == "shift" else f"{float(calibrated):+.2f}"),
            ))
            if entry.get("used_fit_chi2r") is not None:
                lines.append(str(tr("Reference fit at these shifts: χ²ᵣ {value:.2f}.")).format(value=entry["used_fit_chi2r"]))
            lines.append(str(tr("Reset shifts goes back to the calibrated values.")))
        elif key != "shift" and entry.get("dye"):
            lines.append(str(tr("Start: calibrated on {dye} ({files}) on {detector}, χ²ᵣ {chi2r}.")).format(
                dye=entry["dye"], files=entry.get("files", ""),
                detector=entry.get("calibrated_on") or det,
                chi2r=f"{entry['fit_chi2r']:.2f}" if entry.get("fit_chi2r") is not None else "—",
            ))
            if entry.get("tau_ns") is not None:
                lines.append(str(tr("The dye as fitted: lifetime {tau:.2f} ns, rotation {rho:.2f} ns, r0 {r0:.2f}.")).format(
                    tau=float(entry["tau_ns"]), rho=float(entry.get("rho_ns") or 0.0), r0=float(entry.get("r0") or 0.38)))
            if entry.get("warning"):
                lines.append("⚠ " + str(entry["warning"]))
            if entry.get("offset_bins"):
                lines.append(str(tr(
                    "{detector} shares the detectors of {source}: their IRF and timing, placed at "
                    "the {detector} window ({offset:+d} bins, the setup's PIE windows)."
                )).format(detector=det, source=entry.get("calibrated_on"), offset=int(entry["offset_bins"])))
        else:
            lines.append(str(tr("Start: not calibrated (no reference dye of this detector in Data Selection).")))
        lines.append(str(tr("Fixed: held at the start. Unfixed: the fit refines it within ±{bound} bin.")).format(
            bound=engine.SHIFT_BOUNDS[key]))
        return "\n".join(lines)

    @property
    def shifts_edited(self) -> bool:
        """Whether a shift of the current detector was set by hand (Reset shifts is offered)."""
        edits = self.session.shift_edits.get(self.session.current_detector) or {}
        return any(k in edits for k in ("shift_vv", "shift_vh", "shift"))

    def reset_shifts(self) -> None:
        """The current detector's shifts back to their calibrated values, and fitted again."""
        self._ensure_editable()
        det = self.session.current_detector
        roll = int(self.session.settings.shift)
        self.session.reset_shifts(det)
        if int(self.session.settings.shift) != roll:
            self.session.build_decay()
        self.refit()
        self.notify("settings")

    def edit_parameter(self, record: dict, key: str, value: Any) -> None:
        """A cell of the parameter table was edited (the start value or the fixed flag)."""
        name = str(record.get("name"))
        self._ensure_editable()
        if name in self.SHIFT_ROWS:
            setting = self.SHIFT_ROWS[name]
            session = self.session
            roll = int(session.settings.shift)
            if key == "start":
                session.set_shift(session.current_detector, self._EDIT_KEY[setting], float(value))
            elif key == "fixed":
                setattr(session.settings, f"fix_{setting}", bool(value))
                session.calibrate_shift(session.current_detector)  # back to the starts first
            else:
                return
            if int(session.settings.shift) != roll:
                session.build_decay()
            self.refit()
            self.notify("settings")
            return
        if not self.parameter_cell_editable(record, key):
            raise ValueError("Fit25 lifetime candidates are always fixed.")
        if key in ("start", "fixed"):
            self.session.settings.edit_parameter(name, value, fixed=key == "fixed")
            self.refit()

    def parameter_cell_editable(self, record: dict, key: str) -> bool:
        """Keep discrete candidates fixed while retaining editable lifetime inputs."""
        if str(record.get("name", "")) in self.SHIFT_ROWS:
            return key in ("start", "fixed")
        return key == "start" or (
            key == "fixed"
            and not (self.fit_model == "fit25" and str(record.get("name", "")).startswith("tau"))
        )

    def lifetime_rows(self) -> list[dict]:
        """One row per detector series of the last batch: bursts fitted, bursts excluded (their
        fit not a lifetime: too few photons, not converged, out of the physical range -- why, in
        the cell's tooltip), median and mean lifetime of the others.

        Kept with the results it summarises: the table is drawn every frame, and reading the
        lifetimes of thousands of result rows each time made the window crawl after a fit."""
        held = self.__dict__.get("_lifetime_rows")
        if held is not None and held[0] is self.burst_results:
            return held[1]
        from .._mp_worker import REJECT_REASONS

        rows = []
        rejected = fit_view.rejected_fits(self.burst_results)
        lifetimes = fit_view.burst_lifetimes(self.burst_results)
        for label in sorted(set(lifetimes) | set(rejected)):
            values = lifetimes.get(label, np.zeros(0))
            why = rejected.get(label, {})
            excluded = sum(why.values())
            rows.append(
                {
                    "series": label,
                    "n": str(values.size),
                    "excluded": str(excluded),
                    "excluded_tip": "\n".join(
                        f"{count}: {REJECT_REASONS.get(reason, reason)}"
                        for reason, count in sorted(why.items())
                    ) or "every burst was fitted",
                    "median": f"{np.median(values):.3f}" if values.size else "-",
                    "mean": f"{values.mean():.3f}" if values.size else "-",
                }
            )
        self._lifetime_rows = (self.burst_results, rows)
        return rows

    def input_status(self) -> tuple[bool, int]:
        """Whether the current detector has an IRF and a background, and how many burst files are loaded."""
        det = self.session.current_detector
        needs_irf = self.session.settings.model != engine.TAIL_MODEL
        ready = det in self.session.bg_np and (
            not needs_irf
            or (det in self.session.irf_np and np.asarray(self.session.irf_np[det]).size > 0)
        )
        return bool(ready), len(self.session.bur_files)

    # -- actions --------------------------------------------------------------------------------------------- #
    def _settings_changed(self, rebuild_decay: bool) -> None:
        if rebuild_decay:
            self.session.build_decay()
        self.refit()

    def refit(self) -> None:
        """Fit the current decay again with the current settings."""
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

    def prepare_patterns(self, analysed=(), references: dict | None = None) -> None:
        """IRF and background without asking. The IRF of each detector comes, in the IRF tool's
        order (Auto), from a reference dye of known lifetime (Rh110, Alexa647; measured in the
        same conditions as the sample), from a scatter measurement (water, Ludox; corrected with
        the buffer), and only then from the photons outside the bursts (a skewed Gaussian fitted
        to their histogram); the IRF selector takes any of them instead. The fit's background is the photons outside
        the bursts; a buffer measurement corrects a scatter IRF and gives an independent
        background rate (:meth:`irf_source_text`). What the pipeline does when the bursts arrive.

        The measurements are those Burst Analysis' Data Selection declared, *references*
        (``{"buffer": [...], "irf": {detector: [...]}, "reference": {detector: [...]}}``: a
        colour's IRF and reference dye for each of its detectors; they replace what was set
        before, and a detector of a colour without its own IRF reads the other colours' IRF
        measurements on its channels -- never their reference dyes: a green dye does not
        calibrate the red detectors). In the pipeline that is all: Data Selection is the one
        place references come from (it proposes those beside the measurement), even when it
        declares none. Only the standalone tool (*references* ``None``) looks for them by name
        beside the *analysed* files (or a folder up).
        """
        from chisurf.core.fio.reference_files import find_reference_measurements, reference_dye

        try:
            standalone = references is None
            references = dict(references or {})
            per_det = {
                kind: {str(d): [str(p) for p in v] for d, v in (references.get(kind) or {}).items() if v}
                for kind in ("irf", "reference")
            }
            buffers = [str(p) for p in references.get("buffer") or ()]
            declared = bool(buffers or per_det["irf"] or per_det["reference"])
            session = self.session
            if declared or not standalone:
                for kind in ("bg", "irf"):  # what Data Selection declares replaces what was set
                    for det in list(session.detectors):
                        session.clear_pattern_files(kind, det)
                if buffers:  # one buffer serves every detector (each reads its own channels)
                    one, session.bg_one_for_all = session.bg_one_for_all, True
                    try:
                        session.set_pattern_files("bg", next(iter(session.detectors), ""), buffers)
                    except Exception:  # noqa: BLE001 - a buffer the detectors cannot read
                        pass
                    finally:
                        session.bg_one_for_all = one
                # a detector of a colour without its own IRF reads every declared one on its
                # channels (one water measurement under all lasers serves every colour)
                fallback = sorted({p for v in per_det["irf"].values() for p in v})
                one = session.irf_one_for_all
                session.irf_one_for_all = False  # each detector its colour's files
                try:
                    for det in list(session.detectors):
                        irf = per_det["irf"].get(det, [])
                        # a reference dye gives an IRF only when its lifetime is known (its name)
                        dyes = [p for p in per_det["reference"].get(det, []) if reference_dye(p)]
                        # both kinds: the IRF tool picks (a reference dye first, then the
                        # scatter) and the IRF selector offers each; else every declared file
                        paths = (irf + dyes) or (fallback if not per_det["reference"].get(det) else [])
                        if not paths:
                            continue
                        try:
                            session.set_pattern_files("irf", det, list(paths))
                        except Exception:  # noqa: BLE001 - a reference this detector cannot read
                            continue
                finally:
                    session.irf_one_for_all = one
                # say where the IRF came from: the measurement the user labelled in Data Selection
                for det, files in session.irf_files.items():
                    text = session.irf_source.get(det, "")
                    if not files or not text:
                        continue
                    if text.startswith("scatter "):
                        session.irf_source[det] = f"the IRF measurement {text[len('scatter '):]}"
                    else:
                        session.irf_source[det] = f"the reference-dye measurement {text}"
            elif standalone:
                found = (
                    find_reference_measurements(analysed)
                    if analysed
                    else {"irf": [], "dye": [], "bg": []}
                )
                # the buffer first: a scatter IRF is corrected with it
                for kind, paths in (("bg", found["bg"]), ("irf", found["irf"] + found["dye"])):
                    if not paths:
                        continue
                    for det in list(session.detectors):
                        if session.irf_files.get(det) if kind == "irf" else session.bg_files.get(det):
                            continue  # "one for all" set it with an earlier detector
                        try:
                            session.set_pattern_files(kind, det, list(paths))
                        except Exception:  # noqa: BLE001 - a reference this detector cannot read
                            continue
            if session.current_tttr() is not None:
                session.auto_extract()  # fills what no measured file gave
                self.auto_patterns = True
            self.status_text = self.irf_source_text() + " " + (session.status or "")
            self.notify("fit")
        finally:
            self._release_snapshot()

    def irf_source_text(self) -> str:
        """Where each detector's IRF and background came from, in one line."""
        session = self.session
        parts = [
            f"{det}: IRF from {session.irf_source.get(det, 'nowhere yet')}"
            + (
                "; background: the buffer" + self._buffer_rate_text(det)
                if self.buffer_rate(det) is not None
                else "; background: " + self.background_text(det)
            )
            for det in session.detectors
        ]
        return ". ".join(parts) + "." if parts else ""

    def buffer_rate(self, det: str) -> float | None:
        """The background rate of *det* in the buffer measurement [kHz] (``None``: no buffer)."""
        session = self.session
        if not session.bg_files.get(det) or det not in session.buffer_np:
            return None
        return float(np.sum(session.buffer_np[det])) / 1e3

    def _buffer_rate_text(self, det: str) -> str:
        rate = self.buffer_rate(det)
        if rate is None:
            return ""
        names = ", ".join(Path(p).name for p in self.session.bg_files.get(det, []))
        return f" (buffer {names}: Bg_{det} = {rate:.2f} kHz)"

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

    def run_batch(self, force: bool = False) -> None:
        """Fit every burst of every loaded file and detector (threads, `Fit2x.fit_many`) and keep the rows.

        A request identical to the one the held rows answer -- same burst files, same settings, IRF and background,
        same code (:meth:`MleSession.batch_fingerprint`) -- is not fitted again: the status line says so and
        **Restart** is highlighted. ``force`` (Restart) fits regardless. A stopped or failed run holds nothing, so
        the next press fits.
        """
        if self.session.df_bursts is None:
            self._release_snapshot()
            raise ValueError("Add burst files first.")
        self._cancel.clear()
        try:
            fingerprint = self.session.batch_fingerprint()
            if not force and self.burst_results and fingerprint == self.held_fingerprint:
                self.status_text = (
                    "Unchanged — kept the previous Burst MLE result (Restart fits again)"
                )
                self.restart_attention = True
                self.notify("batch")
                return
            self.restart_attention = False
            self.held_fingerprint = None

            def progress(done, total):
                self.status_text = f"Fitting bursts ... {done}/{total}"
                self.notify("progress")

            rows = self.session.run_batch(progress=progress, should_stop=self._cancel.is_set)
            self.burst_results = rows
            n = len(fit_view.burst_lifetimes(rows))
            self.status_text = f"Fitted {self.n_bursts} bursts ({n} lifetime series)."
            if not self._cancel.is_set():
                self.held_fingerprint = fingerprint
                # the lifetimes go into the run they were fitted from at once (Save results
                # writes them again): kept only in memory they never reached ndX or the workspace
                self._write_results()
            self.notify("batch")
        finally:
            self._release_snapshot()

    def stop(self) -> None:
        self._cancel.set()

    @property
    def cancel_event(self) -> threading.Event:
        """The Stop flag as the event :class:`~chisurf.emtk.jobs.SnapshotJob` reads.

        ``SnapshotJob``'s held-job gate asks the snapshot's ``cancel_event`` whether the
        drawn Stop control ended the job; ``stop()`` sets this model's ``_cancel`` event,
        which ``copy.copy`` shares by reference between snapshot and host -- so the
        property only has to name it what the gate looks for.
        """
        return self._cancel

    def _write_results(self) -> None:
        """After a batch: its lifetimes into the containers they were fitted from (members of the
        burst run, :func:`~..core.export.write_mle_container`); a failure is said, not raised."""
        if not self.burst_results:
            return
        try:
            self.session.burst_results = self.burst_results
            written = self.session.export_results()
        except Exception as exc:  # noqa: BLE001 - the fits are kept; Save results tries again
            self.status_text += " " + str(tr("Not written: {error}")).format(error=exc)
            return
        self.status_text += " " + str(tr("Written into {count} container(s).")).format(count=len(written))

    def export_results(self) -> int:
        """Write the lifetimes of the last batch again (they are written after every batch):
        into the runs they were fitted from; returns how many files were written."""
        self.session.burst_results = self.burst_results
        written = self.session.export_results()
        self.status_text = f"{len(written)} burst-fit file(s) written."
        self.notify("export")
        return len(written)

    # -- inspected burst ------------------------------------------------------------------------------------- #
    def inspected_burst(self) -> dict[str, np.ndarray]:
        """Per detector, the VV | VH histogram of burst :attr:`nav_burst` (the Inspected burst tab).

        The tab is drawn every frame; the histogram is made once per burst, table, photon streams
        and detector windows (a new burst search, fit window or binning makes it again): slicing
        the photon stream and converting the burst table's columns each frame made every frame
        after a fit of 80 000 bursts slow."""
        n = self.n_bursts
        if n == 0:
            return {}
        self.nav_burst = max(0, min(int(self.nav_burst), n - 1))
        session = self.session
        windows = tuple(
            (det, json.dumps(info.get("chs", [])), json.dumps(info.get("micro_time_ranges")),
             session.settings_of(det).micro_time_start, session.settings_of(det).micro_time_stop,
             session.settings_of(det).micro_time_binning)
            for det, info in session.detectors.items()
        )
        held = self.__dict__.get("_inspected")
        if (held is not None and held[0] is session.df_bursts and held[1] is session.tttrs
                and held[2] == (int(self.nav_burst), windows)):
            return held[3]
        data = session.inspect_burst(self.nav_burst)
        self._inspected = (session.df_bursts, session.tttrs, (int(self.nav_burst), windows), data)
        return data

    # -- settings file --------------------------------------------------------------------------------------- #
    def save_settings(self, path: str | Path) -> None:
        # The schema makes the file a setup row the workspace hands back to this tool.
        payload = dict(
            self.session.settings_payload(),
            schema="chisurf.tool/burst_mle_analysis/1",
            kind=SETTINGS_KIND,
            auto_patterns=self.auto_patterns,
        )
        Path(path).write_text(
            json.dumps(payload, indent=2, cls=engine.NumpyEncoder), encoding="utf-8"
        )

    def load_settings(self, path: str | Path) -> None:
        """Restore all detectors and per-model parameter edits from a settings file or a burst-analysis folder.

        A burst folder records how its data was read and what it was analysed with (``Info/analysis.json``), which is
        what the tool needs to be put back into the state that produced it: passing the folder, or any ``.bur``
        inside it, is equivalent to picking a settings file. A source that holds no settings is reported on the
        status line, not raised.
        """
        self._ensure_editable()
        source = Path(path)
        if source.is_dir() or source.suffix.lower() != ".json":
            from chisurf.core.fio.fluorescence.burst_manifest import read_analysis_manifest

            manifest = read_analysis_manifest(source)
            payload = (manifest or {}).get("mle_settings") or (manifest or {}).get("settings")
            if not payload:
                self.status_text = f"No stored settings found under {source}."
                return
        else:
            try:
                payload = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                self.status_text = f"Could not read settings from {source}: {exc}"
                return
            if not isinstance(payload, dict):
                self.status_text = f"The settings in {source} are not a mapping."
                return
            if payload.get("kind") != SETTINGS_KIND:
                raise ValueError("Not a burst-MLE settings file written by this tool.")
        self.session.apply_settings_payload(payload)
        self.auto_patterns = bool(payload.get("auto_patterns"))
        self.status_text = f"Settings restored from {source}."
        self.notify("settings")

    # -- snapshot for a running job -------------------------------------------------------------------------- #
    def values_snapshot(self) -> SimpleNamespace:
        """The spec's values as a throw-away object: edits made while a job runs go nowhere."""
        ns = SimpleNamespace(**{name: getattr(self, name) for name in SETTING_ATTRS})
        for name in (
            "binning",
            "current_detector",
            "current_file",
            "nav_burst",
            "fit_model",
            "irf_model",
            "irf_one_for_all",
            "bg_one_for_all",
            "save_vv_vhs",
            "opt_iterations",
        ):
            setattr(ns, name, getattr(self, name))
        for method in (
            "detector_names",
            "fit_model_options",
            "fit_model_choices",
            "model_availability",
            "model_result_text",
            "calibration_text",
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


def _window_property(name: str, index: int):
    """Window start / stop as fitted: a window not set shows the detector's gate it falls back to."""
    plain = _setting_property(name, int, True)

    def getter(self):
        value = int(getattr(self.session.settings, name))
        if self.session.settings.micro_time_stop > self.session.settings.micro_time_start >= 0:
            return value
        edge = int(self.session.window_ranges()[index])
        decay = self.session.decay
        return min(edge, np.asarray(decay).size // 2) if decay is not None else min(edge, 100000)

    def setter(self, value):
        settings = self.session.settings
        if not settings.micro_time_stop > settings.micro_time_start >= 0:
            # one edge set: the other keeps the edge it showed (the gate's)
            settings.micro_time_start = self.micro_time_start
            settings.micro_time_stop = self.micro_time_stop
        plain.fset(self, value)

    return property(getter, setter)


MleViewModel.micro_time_start = _window_property("micro_time_start", 0)
MleViewModel.micro_time_stop = _window_property("micro_time_stop", 1)
