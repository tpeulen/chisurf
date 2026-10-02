"""Native burst FCS orchestration, settings and result browser."""

import copy
import json
from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path
from threading import Event

import numpy as np

from ..core import algorithms as core
from .view_model import _BurstFcsModel


class BurstFcsController:
    def __init__(self):
        self._model = _BurstFcsModel()
        self.files = []
        self._curves = []
        self._pair_presets = [
            {
                "pair_name": "donor_ACF",
                "chs_a": [0, 8],
                "chs_b": [0, 8],
                "micro_a": [],
                "micro_b": [],
            }
        ]
        self.enabled_pairs = {"donor_ACF"}
        self.pairs_text = json.dumps(self._pair_presets, indent=2)
        self.unchecked: set[str] = set()
        self.progress = 0.0
        self.selected_file = None
        self.status = "Choose burst files and channel pairs, then Run FCS."
        self.running = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="burst-fcs")
        self._future = None
        self._cancel = Event()
        from chisurf.emtk.dataset_picker import DatasetPicker

        self.datasets = DatasetPicker(
            kinds=["analysis_result", "raw_data", "raw_measurement"], on_paths=self.add_files
        )

    def add_files(self, paths):
        for path in map(str, paths):
            if path not in self.files:
                self.files.append(path)
                self.unchecked.discard(path)

    def checked_files(self):
        """The listed inputs that are ticked (the Qt list's ``checked_paths``)."""
        return [p for p in self.files if p not in self.unchecked]

    def check_all(self):
        self.unchecked.clear()

    def check_none(self):
        self.unchecked = set(self.files)

    def remove_files(self, paths):
        for path in list(paths):
            if path in self.files:
                self.files.remove(path)
            self.unchecked.discard(path)

    def clear(self):
        """Forget the inputs and every curve (the Qt Clear button)."""
        self.files, self._curves, self._model._selected = [], [], None
        self.unchecked = set()
        self.status = "Inputs and results cleared."

    def pairs_from_setup(self, setup_name, detectors):
        """Channel pairs of a detector setup: its saved FCS pairs, else one auto-correlation per detector (as the Qt tool does)."""
        from chisurf.core.fluorescence.fcs.channel_setups import load_fcs_channel_setups

        detectors = detectors or {}
        saved = []
        try:
            block = (load_fcs_channel_setups().get("setups", {}) or {}).get(setup_name or "", {})
            saved = block.get("pairs", []) if isinstance(block, dict) else []
        except Exception:  # a missing store is the same as no saved pairs
            saved = []
        pairs = []
        for pair in saved:
            a, b = str(pair.get("channel_a", "")), str(pair.get("channel_b", ""))
            da, db = detectors.get(a, {}), detectors.get(b, {}) or detectors.get(a, {})
            chs_a, chs_b = list(da.get("chs", []) or []), list(db.get("chs", []) or da.get("chs", []) or [])
            if not chs_a or not chs_b:
                continue
            name = str(pair.get("name", "")) or (f"{a}x{b}" if a != b else f"{a}_ACF")
            pairs.append({"pair_name": name, "chs_a": chs_a, "chs_b": chs_b, "micro_a": list(da.get("micro_time_ranges", []) or []),
                          "micro_b": list(db.get("micro_time_ranges", []) or [])})
        if not pairs:
            pairs = [{"pair_name": f"{n}_ACF", "chs_a": list(d.get("chs", [])), "chs_b": list(d.get("chs", [])),
                      "micro_a": list(d.get("micro_time_ranges", []) or []), "micro_b": list(d.get("micro_time_ranges", []) or [])}
                     for n, d in detectors.items() if d.get("chs")]
        return pairs

    def adopt_setup(self, setup_name, detectors):
        """Use the pairs of a detector setup (replaces the list)."""
        pairs = self.pairs_from_setup(setup_name, detectors)
        if not pairs:
            self.status = "The detector setup has no detector with routing channels."
            return False
        return self.apply_pairs(json.dumps(pairs))

    def set_pair_enabled(self, name, enabled):
        (self.enabled_pairs.add if enabled else self.enabled_pairs.discard)(name)

    def curve_label(self, curve):
        return f"{curve.get('file', '')} - b{curve.get('burst_index', 0)} - {curve.get('pair_name', '')}"

    def on_paths_dropped(self, paths):
        """Burst files are added; a dropped JSON file is read as settings (it has ``n_bins``) or as channel pairs."""
        added = []
        for path in map(str, paths):
            if path.lower().endswith(".json"):
                try:
                    data = json.loads(Path(path).read_text())
                    if isinstance(data, dict) and ("n_bins" in data or "fit_mode" in data):
                        self.load_settings(path)
                    else:
                        self.apply_pairs(json.dumps(data))
                except Exception as exc:  # noqa: BLE001 - shown on the status line
                    self.status = f"Error: {path}: {exc}"
            else:
                added.append(path)
        self.add_files(added)

    def save_pairs(self, path):
        Path(path).write_text(json.dumps(self._pair_presets, indent=2))
        self.status = f"Channel pairs saved: {path}"

    def apply_pairs(self, text):
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "detectors" in data:
                detectors = data["detectors"]
                configured = data.get("fcs") or data.get("fcs_pairs")
                if configured:
                    data = configured
                else:
                    data = [
                        {
                            "pair_name": f"{name}_ACF",
                            "chs_a": det["chs"],
                            "chs_b": det["chs"],
                            "micro_a": det.get("micro_time_ranges", []),
                            "micro_b": det.get("micro_time_ranges", []),
                        }
                        for name, det in detectors.items()
                    ]
            if not isinstance(data, list) or not data:
                raise ValueError("Provide a nonempty list of named channel pairs.")
            result = []
            for value in data:
                pair = core.PairConfig.from_dict(value)
                if (
                    not pair.pair_name
                    or not pair.chs_a
                    or not pair.chs_b
                    or any(not isinstance(ch, int) or ch < 0 for ch in pair.chs_a + pair.chs_b)
                ):
                    raise ValueError(
                        "Each pair needs a name and nonnegative channel lists chs_a/chs_b."
                    )
                if any(
                    len(gate) != 2 or gate[0] < 0 or gate[1] <= gate[0]
                    for gate in pair.micro_a + pair.micro_b
                ):
                    raise ValueError("Use increasing microtime ranges.")
                from dataclasses import asdict

                result.append(asdict(pair))
            self._pair_presets = result
            self.enabled_pairs = {p["pair_name"] for p in result}
            self.pairs_text = json.dumps(result, indent=2)
            self.status = "Channel pairs applied."
            return True
        except (ValueError, TypeError, KeyError) as exc:
            self.status = f"Invalid channel pairs: {exc}"
            return False

    def resolve_files(self):
        results = []
        for entry in self.checked_files():
            path = Path(entry)
            candidates = []
            if path.is_dir():
                candidates.extend(path.glob("bi4_bur/*.bur"))
                candidates.extend(path.glob("bur/*.bur"))
                candidates.extend(path.glob("BID/*.bst"))
                candidates.extend(path.glob("*.bur"))
                candidates.extend(path.glob("*.bst"))
            else:
                candidates.append(path)
            for candidate in candidates:
                if candidate.suffix.lower() == ".bst":
                    raw, ranges = core.parse_bst_file(candidate)
                elif candidate.suffix.lower() == ".bur":
                    root = (
                        candidate.parent.parent
                        if candidate.parent.name in ("bi4_bur", "bur")
                        else candidate.parent
                    )
                    raw, ranges = core.parse_bur_file(candidate, root)
                else:
                    continue
                if raw is not None and ranges:
                    results.append((raw, ranges))
        return results

    def check_cancel(self):
        if self._cancel.is_set():
            raise CancelledError()

    def _compute(self, files, pairs, settings):
        curves = []
        for done, (raw, ranges) in enumerate(files):
            self.check_cancel()
            self.progress = done / max(len(files), 1)
            curves.extend(
                core.correlate_burst_file(
                    raw, ranges, pairs, settings, cancel_check=self.check_cancel
                )
            )
        self.check_cancel()
        self.progress = 1.0
        return curves

    def _on_run(self):
        if self.running:
            return
        self.progress = 0.0
        pairs = [
            core.PairConfig.from_dict(p)
            for p in self._pair_presets
            if p["pair_name"] in self.enabled_pairs
        ]
        if not pairs:
            self.status = "Select at least one channel pair."
            return
        files = self.resolve_files()
        if not files:
            self.status = "No usable BUR/BST photon ranges were found in the selected inputs."
            return
        try:
            settings = self._model.to_settings()
            if settings.n_bins < 1 or settings.n_casc < 1 or settings.padding_ms < 0:
                raise ValueError("Use positive bins/cascades and nonnegative padding.")
            if settings.tmin_fit and settings.tmax_fit and settings.tmin_fit >= settings.tmax_fit:
                raise ValueError("Fit minimum lag must be below the maximum.")
            if (
                settings.maxent_td_min
                and settings.maxent_td_max
                and settings.maxent_td_min >= settings.maxent_td_max
            ):
                raise ValueError("Minimum diffusion time must be below the maximum.")
        except (ValueError, OverflowError) as exc:
            self.status = f"Invalid settings: {exc}"
            return
        self._cancel.clear()
        self.running = True
        self.status = "Computing burst FCS …"
        self._future = self._executor.submit(self._compute, files, copy.deepcopy(pairs), settings)

    def poll(self):
        if self._future is None or not self._future.done():
            return
        future, self._future = self._future, None
        try:
            curves = future.result()
            self.check_cancel()
            self._curves = curves
            self._model._selected = curves[0] if curves else None
            self.status = f"Computed {len(curves)} burst correlation curves."
        except CancelledError:
            self.status = "Burst FCS cancelled."
        except Exception as exc:
            self.status = f"Error: {exc}"
        finally:
            self.running = False

    def stop(self):
        if self.running:
            self._cancel.set()
            self.status = "Stopping burst FCS …"

    def save_settings(self, path):
        Path(path).write_text(json.dumps(self._model.to_settings().to_dict(), indent=2))
        self.status = "Settings saved."

    def load_settings(self, path):
        data = json.loads(Path(path).read_text())
        settings = core.BurstFcsSettings.from_dict(data)
        if (
            settings.n_bins < 1
            or settings.n_casc < 1
            or settings.padding_ms < 0
            or settings.maxent_reg <= 0
            or settings.fit_mode not in ("simple", "maxent", "none")
        ):
            raise ValueError("Invalid correlation settings.")
        for key, value in settings.to_dict().items():
            if key == "maxent_reg":
                self._model.maxent_log10_reg = float(np.log10(value))
            else:
                setattr(
                    self._model,
                    key,
                    value or 0
                    if key in ("tmin_fit", "tmax_fit", "maxent_td_min", "maxent_td_max")
                    else value,
                )
        self.status = "Settings loaded."

    def export_curves(self, path):
        Path(path).write_text(json.dumps(self._curves, indent=2))
        self.status = f"Correlation curves exported: {path}"

    def close(self):
        self.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
