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

from .. import engine
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

#: Values of the settings file this app writes and reads.
SETTINGS_KIND = "burst_mle_native"


def _setting_property(name: str, kind: type, rebuild_decay: bool):
    def getter(self):
        return kind(getattr(self.session.settings, name))

    def setter(self, value):
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

    # -- observers ------------------------------------------------------------------------------------------- #
    def notify(self, event: str = "updated") -> None:
        for observer in list(self._observers):
            observer(event)

    # -- detectors ------------------------------------------------------------------------------------------- #
    def detector_names(self) -> list[str]:
        return list(self.session.detectors)

    def set_setup(self, settings: dict) -> None:
        """Take the detector definition of the shared editor (every change of it)."""
        file_type = (settings.get("tttr_reading") or {}).get("file_type")
        self.session.set_detectors(settings.get("detectors") or {}, file_type)
        self.notify("setup")

    # -- split by H2MM state ------------------------------------------------------------------------------------ #
    @property
    def split_by_state(self) -> bool:
        """Fit each burst once more per H2MM state, after a pooled fit of each state (the segment-level step)."""
        return bool(self.session.split_by_state)

    @split_by_state.setter
    def split_by_state(self, value: bool) -> None:
        self.session.split_by_state = bool(value)
        self.notify("settings")

    @property
    def state_min_photons(self) -> int:
        """Photon floor of a per-state burst fit."""
        return int(self.session.state_min_photons)

    @state_min_photons.setter
    def state_min_photons(self, value: int) -> None:
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
        if value in self.session.detectors and value != self.session.current_detector:
            self.session.current_detector = value
            self.session.build_decay()
            self.refit()

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
        value = int(value)
        if value == self.binning:
            return
        self.session.set_binning(value)
        if self.auto_patterns and self.session.current_tttr() is not None:
            self.session.extract_irf_background()
        self.session.build_decay()
        self.refit()

    def binning_options(self) -> list[int]:
        return list(engine.BINNING_CHOICES)

    # -- derived read-only ----------------------------------------------------------------------------------- #
    @property
    def fit_model(self) -> str:
        return self.session.settings.model

    @property
    def fit_curves(self):
        outcome = self.session.outcome
        return outcome.curves if outcome is not None else None

    @property
    def tau_result(self) -> float:
        return self._result("tau")

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
        """Rows of the fit-parameter table: start value, fixed flag and fitted result of tau, gamma, r0, rho."""
        out = []
        for row in fit_view.parameter_rows(self):
            out.append(
                {
                    "name": row.name,
                    "start": float(row.initial),
                    "fixed": bool(row.fixed),
                    "result": f"{row.result:.4g}" if self.session.outcome is not None else "",
                }
            )
        return out

    def edit_parameter(self, record: dict, key: str, value: Any) -> None:
        """A cell of the parameter table was edited (the start value or the fixed flag)."""
        name = str(record.get("name"))
        if key == "start":
            setattr(self, name, float(value))
        elif key == "fixed":
            setattr(self, f"fix_{name}", bool(value))

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
        ready = (
            det in self.session.irf_np
            and det in self.session.bg_np
            and np.asarray(self.session.irf_np[det]).size > 0
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
            self.status_text = (
                self.session.status
                or f"tau = {self.tau_result:.3f} ns (2I* = {self.two_istar:.3f})"
            )
        self.notify("fit")

    def auto_extract(self) -> None:
        """One click: binning, IRF and background from the non-burst photons, fit window, fit."""
        if self.session.current_tttr() is None:
            self.status_text = "Add burst files first: there is no data to extract an IRF from."
            return
        self.session.auto_extract()
        self.auto_patterns = True
        self.status_text = self.session.status
        self.notify("fit")

    def run_batch(self) -> None:
        """Fit every burst of every loaded file and detector (worker processes) and keep the rows."""
        if self.session.df_bursts is None:
            raise ValueError("Add burst files first.")
        self._cancel.clear()

        def progress(done, total):
            self.status_text = f"Fitting bursts ... {done}/{total}"
            self.notify("progress")

        rows = self.session.run_batch(progress=progress, should_stop=self._cancel.is_set)
        self.burst_results = rows
        n = len(fit_view.burst_lifetimes(rows))
        self.status_text = f"Fitted {self.n_bursts} bursts ({n} lifetime series)."
        self.notify("batch")

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
        for name in ("binning", "current_detector", "current_file", "nav_burst"):
            setattr(ns, name, getattr(self, name))
        for method in (
            "detector_names",
            "binning_options",
            "file_rows",
            "parameter_records",
            "lifetime_rows",
            "select_file",
            "remove_file_row",
        ):
            setattr(ns, method, getattr(self, method))
        ns.edit_parameter = lambda *a, **k: None
        return ns


for _name, (_kind, _rebuild) in SETTING_ATTRS.items():
    setattr(MleViewModel, _name, _setting_property(_name, _kind, _rebuild))
