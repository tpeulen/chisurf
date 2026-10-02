"""Native filter-calculator state and the original numerical workflows."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from chisurf.core.fluorescence.decay import (
    afterpulse_decay_pattern,
    sample_decay_shot_noise,
    scattered_light_decay_pattern,
    synthetic_component_decay,
)

from ..api import FilterResult, compute_filters, compute_filters_mfd, unmix_decay
from ..gui_parts.instrument_options import InstrumentViewModel
from .scientific import ScientificOperations


@dataclass
class Component:
    source: dict | list
    name: str
    enabled: bool = True


class Detectors:
    def __init__(self):
        self.names = ["green"]
        self.selected = ["green"]
        self.values = {key: {} for key in ("irf", "width", "skew", "shift")}

    def _get(self, field, detector, role="", default=0):
        return self.values[field].get(f"{detector}|{role}", default)

    def irf_path(self, detector, role=""):
        return str(self._get("irf", detector, role, ""))

    def width(self, detector, role=""):
        return float(self._get("width", detector, role, 0.2))

    def skew(self, detector, role=""):
        return float(self._get("skew", detector, role, 0))

    def shift(self, detector, role=""):
        return float(self._get("shift", detector, role, 0))

    def set_width(self, detector, value, role=""):
        self.values["width"][f"{detector}|{role}"] = float(value)

    def set_skew(self, detector, value, role=""):
        self.values["skew"][f"{detector}|{role}"] = float(value)

    def set_shift(self, detector, value, role=""):
        self.values["shift"][f"{detector}|{role}"] = float(value)

    def export_state(self):
        return deepcopy(self.values)

    def import_state(self, state):
        for field in self.values:
            self.values[field] = dict(state.get(field, {}))


class FilterModel(ScientificOperations):
    def __init__(self, example=True):
        self.components = []
        self.detectors = Detectors()
        self.options_model = SimpleNamespace(fit_background=True, scatter_irf=True)
        self.instrument_model = InstrumentViewModel()
        self.polarized = False
        self.stacked = False
        self._total_paths = []
        self._total_vector = None
        self._total_vectors_by_detector = {}
        self._data_dt_ns = 0.05
        self._micro_time_binning = 1
        self._detector_settings = {"detectors": {"green": {"chs": [0, 1]}}}
        self._detector_fit_ranges = {}
        self._auto_fit_settings = {
            "kind": "lifetime",
            "n_components": 2,
            "tau_min": 0.2,
            "tau_max": 8.0,
        }
        self._auto_fit_result = None
        self._result = self._result_anisotropy = None
        self._result_multi_detector = self._result_multi_anisotropy = None
        self._unmix_result = None
        self._irf_by_detector = {}
        self._synthetic_scatter_fits = {}
        self._decay_cache = {}
        self._routing_cache = {}
        self._fit_bounds = (0, 256)
        self._suspend_compute = False
        self.message = ""
        self.total_label = ""
        if example:
            self.populate_example()

    def add_component(self, source):
        source = deepcopy(source)
        if isinstance(source, dict) and source.get("type") != "synthetic" and "paths" in source:
            source = list(source["paths"])
        name = (
            source.get("name", source.get("model", "Component"))
            if isinstance(source, dict)
            else ", ".join(Path(p).name for p in source)
        )
        self.components.append(Component(source, name))

    def _instrument(self):
        return self.instrument_model.to_dict()

    def _fit_range(self, n_bins):
        start, stop = sorted(map(int, self._fit_bounds))
        start, stop = max(0, start), min(n_bins, stop)
        return (start, stop) if stop - start >= 4 else (0, n_bins)

    def _init_fit_region(self, total):
        if self._fit_bounds[1] > len(total):
            self._fit_bounds = (0, len(total))

    def _update_status(self, message):
        self.message = str(message)

    def _on_data_changed(self):
        if not self._suspend_compute:
            self.compute()

    def populate_example(self):
        from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

        self.components.clear()
        self._total_paths = []
        self._total_vectors_by_detector = {}
        patterns = [
            dict(
                type="synthetic",
                model="lifetime",
                name="Fast example",
                lifetime=1.2,
                bin_width=0.05,
                example=True,
                patterns_by_detector={},
            ),
            dict(
                type="synthetic",
                model="lifetime",
                name="Slow example",
                lifetime=4.0,
                bin_width=0.05,
                example=True,
                patterns_by_detector={},
            ),
        ]
        time = np.arange(256) * 0.05
        for i, detector in enumerate(self.detectors.selected or ["green"]):
            irf = synthetic_irf(
                time, center_ns=0.35 + 0.06 * i, fwhm_ns=0.16 + 0.035 * i, shape=0.35 * i
            )
            self.detectors.set_width(detector, 0.16 + 0.035 * i)
            self.detectors.set_skew(detector, 0.35 * i)
            self.detectors.set_shift(detector, (0.35 + 0.06 * i) - 2 * (0.16 + 0.035 * i))
            decays = [synthetic_component_decay(256, source, irf=irf) for source in patterns]
            for source, decay in zip(patterns, decays):
                source["patterns_by_detector"][detector] = decay.tolist()
            expected = (
                0.665 * decays[0]
                + 0.285 * decays[1]
                + 0.03 * scattered_light_decay_pattern(irf, 256)
                + 0.02 * afterpulse_decay_pattern(256)
            )
            self._total_vectors_by_detector[detector] = sample_decay_shot_noise(
                expected, photon_count=100_000, seed=20260716 + i
            )
        for source in patterns:
            source["patterns_by_detector"]["__default__"] = next(
                iter(source["patterns_by_detector"].values())
            )
            self.add_component(source)
        self._total_vector = next(iter(self._total_vectors_by_detector.values())).copy()
        self.total_label = "Convolved example (70/30 + scatter + afterpulse)"
        self._fit_bounds = self.default_fit_range(self._total_vector)

    def set_total_paths(self, paths):
        self._total_paths = [Path(p) for p in paths]
        self._total_vector = None
        self._total_vectors_by_detector = {}
        self._decay_cache.clear()
        self._routing_cache.clear()
        self.total_label = "; ".join(str(p) for p in paths)
        self._fit_bounds = self.default_fit_range(self._total_decay(self.detectors.selected))

    @staticmethod
    def default_fit_range(decay):
        """The Qt tool's first fit range: just past the prompt (peak plus 1 % of the bins, at least 2) to 1 % short of the end."""
        d = np.asarray(decay, dtype=float).ravel()
        if d.size < 8:
            return (0, int(d.size))
        start = min(int(np.argmax(d)) + max(2, d.size // 100), d.size - 4)
        return (start, d.size - max(1, d.size // 100))

    def set_setup(self, setup):
        self._detector_settings = deepcopy(setup)
        names = list(setup.get("detectors", {}))
        if not names:
            raise ValueError("Detector setup must define at least one detector.")
        self.detectors.names = names
        self.detectors.selected = names
        from chisurf.core.fluorescence.fret.calibration import setup_calibration_values

        self.instrument_model.update_from(setup_calibration_values(setup))
        self._decay_cache.clear()

    def compute(self):
        if not self._has_total_decay():
            raise ValueError("Load a mixed decay first.")
        checked = [c for c in self.components if c.enabled]
        if not checked:
            raise ValueError("Select at least one component.")
        names = self.detectors.selected or ["green"]
        self._irf_by_detector = {}
        self._result = self._result_anisotropy = None
        self._result_multi_detector = self._result_multi_anisotropy = None
        if self.polarized:
            results = []
            for detector in names:
                channels = (
                    self._detector_settings.get("detectors", {}).get(detector, {}).get("chs", [])
                )
                if len(channels) < 2:
                    raise ValueError(
                        f"{detector} needs parallel and perpendicular routing channels."
                    )
                selected_roles = [
                    [f"routing_{c}" for c in routing] for routing in (channels[::2], channels[1::2])
                ]
                full_totals = [self._total_decay(selected) for selected in selected_roles]
                n_bins = max(map(len, full_totals))
                full_totals = [self._resize_pattern(total, n_bins) for total in full_totals]
                start, stop = self._detector_fit_range(detector, n_bins)
                full_patterns, full_nuisance, nuisance, labels = [], [], [], []
                for role, selected, total in zip(("par", "perp"), selected_roles, full_totals):
                    basis = [self._species_item_pattern(c, n_bins, selected)[0] for c in checked]
                    full_patterns.append(basis)
                    nd, nl = self._nuisance_patterns(total, basis, detector, role)
                    full_nuisance.append(nd)
                    nuisance.append([p[start:stop] for p in nd])
                    labels = nl
                result = compute_filters_mfd(
                    *[total[start:stop] for total in full_totals],
                    *[[p[start:stop] for p in basis] for basis in full_patterns],
                    metadata={"detector": detector, "fit_range": [start, stop]},
                    nuisance_decays_par=nuisance[0],
                    nuisance_decays_perp=nuisance[1],
                    nuisance_labels=labels,
                )
                result.metadata["n_bins"] = n_bins
                for role, total, basis, nuisance_basis in zip(
                    ("par", "perp"), full_totals, full_patterns, full_nuisance
                ):
                    solved = getattr(result, f"filters_{role}")
                    weights = np.zeros((solved.shape[0], n_bins))
                    weights[:, start:stop] = solved
                    reconstruction = total.copy()
                    reconstruction[start:stop] = getattr(result, f"reconstruction_{role}")
                    residual = np.zeros(n_bins)
                    residual[start:stop] = getattr(result, f"weighted_residuals_{role}")
                    setattr(result, f"filters_{role}", weights)
                    setattr(result, f"reconstruction_{role}", reconstruction)
                    setattr(result, f"weighted_residuals_{role}", residual)
                    setattr(result, f"total_decay_{role}", total)
                    setattr(result, f"species_decays_{role}", basis + nuisance_basis)
                results.append({"detector": detector, "result": result})
            if len(results) == 1:
                self._result_anisotropy = results[0]["result"]
            else:
                self._result_multi_anisotropy = results
        elif self.stacked and len(names) > 1:
            totals = [self._total_decay([det]) for det in names]
            n = min(map(len, totals))
            patterns = [
                [self._species_item_pattern(c, n, [det])[0] for c in checked] for det in names
            ]
            nuisance = [
                self._nuisance_patterns(t[:n], p, det) for t, p, det in zip(totals, patterns, names)
            ]
            n_nuis = min(len(item[0]) for item in nuisance)
            result = compute_filters(
                np.concatenate([t[:n] for t in totals]),
                [np.concatenate([p[k] for p in patterns]) for k in range(len(checked))],
                nuisance_decays=[
                    np.concatenate([item[0][k] for item in nuisance]) for k in range(n_nuis)
                ],
                nuisance_labels=nuisance[0][1][:n_nuis],
                species_patterns=[c.source for c in checked],
            )
            self._result_multi_detector = []
            for i, detector in enumerate(names):
                seg = slice(i * n, (i + 1) * n)
                part = FilterResult(
                    filters=result.filters[:, seg],
                    reconstruction=result.reconstruction[seg],
                    weighted_residuals=result.weighted_residuals[seg],
                    total_decay=result.total_decay[seg],
                    species_decays=[s[seg] for s in result.species_decays],
                    metadata={
                        **result.metadata,
                        "filter_mode": "stacked",
                        "stacked_detectors": names,
                    },
                    nuisance_count=result.nuisance_count,
                    nuisance_labels=result.nuisance_labels,
                    species_patterns=[c.source for c in checked],
                )
                self._apply_range_to_result(part, detector)
                self._result_multi_detector.append({"detector": detector, "result": part})
        else:
            results = []
            for detector in names:
                total = self._total_decay([detector])
                patterns = [
                    self._species_item_pattern(c, len(total), [detector])[0] for c in checked
                ]
                nuisance, labels = self._nuisance_patterns(total, patterns, detector)
                result = self._ranged_filters(
                    total,
                    patterns,
                    detector=detector,
                    total_path=[str(p) for p in self._total_paths],
                    species_patterns=[c.source for c in checked],
                    nuisance_decays=nuisance,
                    nuisance_labels=labels,
                )
                results.append({"detector": detector, "result": result})
            if len(results) == 1:
                self._result = results[0]["result"]
            else:
                self._result_multi_detector = results
        self.message = "Filters computed successfully."

    def unmix(self):
        total = self._total_decay(self.detectors.selected)
        checked = [c for c in self.components if c.enabled]
        patterns = [
            self._species_item_pattern(c, len(total), self.detectors.selected)[0] for c in checked
        ]
        nuisance, labels = self._nuisance_patterns(
            total,
            patterns,
            self.detectors.selected[0] if len(self.detectors.selected) == 1 else None,
        )
        self._unmix_result = unmix_decay(
            total, patterns, nuisance_decays=nuisance, nuisance_labels=labels
        )
        self.compute()
        for entry in self.results():
            entry["result"].metadata["unmixing"] = self._unmix_result.to_dict()
            entry["result"].metadata["component_names"] = [c.name for c in checked]
        self.message = "Unmixed: " + ", ".join(
            f"{c.name}: {f:.1%}" for c, f in zip(checked, self._unmix_result.fractions)
        )

    def results(self):
        if self._result is not None:
            return [
                {
                    "detector": self.detectors.selected[0] if self.detectors.selected else "all",
                    "result": self._result,
                }
            ]
        if self._result_anisotropy is not None:
            return [{"detector": self.detectors.selected[0], "result": self._result_anisotropy}]
        return self._result_multi_detector or self._result_multi_anisotropy or []

    def snapshot(self):
        model = FilterModel(example=False)
        for key, value in self.__dict__.items():
            if key != "_auto_fit_result":
                setattr(model, key, deepcopy(value))
        model._auto_fit_result = self._auto_fit_result
        return model

    def export_state(self):
        state = {
            "schema_version": 2,
            "total_path": [str(p) for p in self._total_paths],
            "total_decay": self._total_vector.tolist() if self._total_vector is not None else None,
            "total_decays_by_detector": {
                k: v.tolist() for k, v in self._total_vectors_by_detector.items()
            },
            "total_label": self.total_label,
            "species_patterns": [c.source for c in self.components],
            "component_enabled": [c.enabled for c in self.components],
            "ui_state": {
                "selected_detectors": self.detectors.selected,
                "anisotropy_mode": self.polarized,
                "stacked_mode": self.stacked,
                "afterpulse_filter": self.options_model.fit_background,
                "scatter_filter": self.options_model.scatter_irf,
                "detector_irf": self.detectors.export_state(),
            },
            "detector_setup": self._detector_settings,
            "instrument": self._instrument(),
            "auto_fit_settings": self._auto_fit_settings,
            "fit_range": self._fit_bounds,
            "detector_fit_ranges": self._detector_fit_ranges,
            "micro_time_binning": self._micro_time_binning,
            "bin_width_ns": self._data_dt_ns,
        }
        if self._result is not None:
            result = self._result.to_dict()
            result.update(state)
            state = result
        return state

    def restore_state(self, state):
        self._total_paths = (
            [Path(p) for p in state.get("total_path", []) or []]
            if not isinstance(state.get("total_path"), str)
            else [Path(state["total_path"])]
        )
        self._total_vector = (
            np.asarray(state["total_decay"], dtype=float)
            if state.get("total_decay") is not None
            else None
        )
        self._total_vectors_by_detector = {
            k: np.asarray(v, dtype=float)
            for k, v in state.get("total_decays_by_detector", {}).items()
        }
        self.total_label = state.get("total_label", "Project mixture")
        self.components = []
        for source in state.get("species_patterns", []):
            self.add_component(source)
        for c, value in zip(self.components, state.get("component_enabled", [])):
            c.enabled = bool(value)
        ui = state.get("ui_state", {})
        self._detector_settings = state.get("detector_setup", self._detector_settings)
        self.detectors.names = list(self._detector_settings.get("detectors", {}))
        self.detectors.selected = list(ui.get("selected_detectors") or self.detectors.names)
        self.detectors.import_state(ui.get("detector_irf", {}))
        self.polarized = bool(ui.get("anisotropy_mode", False))
        self.stacked = bool(ui.get("stacked_mode", False))
        self.options_model.fit_background = bool(ui.get("afterpulse_filter", True))
        self.options_model.scatter_irf = bool(ui.get("scatter_filter", True))
        self.instrument_model.update_from(state.get("instrument", {}))
        self._auto_fit_settings.update(state.get("auto_fit_settings", {}))
        self._fit_bounds = tuple(state.get("fit_range", (0, self._current_n_bins())))
        self._detector_fit_ranges = {
            k: tuple(v) for k, v in state.get("detector_fit_ranges", {}).items()
        }
        self._micro_time_binning = int(state.get("micro_time_binning", 1))
        self._data_dt_ns = float(state.get("bin_width_ns", 0.05))
        self._decay_cache.clear()
        self._routing_cache.clear()

    def save_project(self, path):
        Path(path).write_text(json.dumps(self.export_state(), indent=2))

    def load_project(self, path):
        self.restore_state(json.loads(Path(path).read_text()))
        self.compute()

    def export_results(self, path):
        results = self.results()
        if not results:
            raise ValueError("Compute filters before export.")
        if len(results) == 1:
            data = results[0]["result"].to_dict()
        else:
            data = {
                "mode": "multi_anisotropy" if self.polarized else "multi_detector",
                "detectors": [
                    {"detector": e["detector"], "result": e["result"].to_dict()} for e in results
                ],
            }
        Path(path).write_text(json.dumps(data, indent=2))
