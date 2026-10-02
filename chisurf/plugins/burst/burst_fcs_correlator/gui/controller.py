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
        from emtk.widgets.text_editor import TextEditor

        self.pairs_editor = TextEditor(self.pairs_text)
        self.filter = ""
        self.status = "Choose burst files and channel pairs, then Run FCS."
        self.running = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="burst-fcs")
        self._future = None
        self._cancel = Event()
        self.dialog = None
        self.action = "files"
        from chisurf.emtk.dataset_picker import DatasetPicker

        self.datasets = DatasetPicker(
            kinds=["analysis_result", "raw_data", "raw_measurement"], on_paths=self.add_files
        )

    def add_files(self, paths):
        for path in map(str, paths):
            if path not in self.files:
                self.files.append(path)

    def on_paths_dropped(self, paths):
        self.add_files(paths)

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
            self.pairs_editor.set_text(self.pairs_text)
            self.status = "Channel pairs applied."
            return True
        except (ValueError, TypeError, KeyError) as exc:
            self.status = f"Invalid channel pairs: {exc}"
            return False

    def resolve_files(self):
        results = []
        for entry in self.files:
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
        for raw, ranges in files:
            self.check_cancel()
            curves.extend(
                core.correlate_burst_file(
                    raw, ranges, pairs, settings, cancel_check=self.check_cancel
                )
            )
        self.check_cancel()
        return curves

    def _on_run(self):
        if self.running:
            return
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

    def browse(self, action="files"):
        from emtk.file_dialog import FileDialog

        self.action = action
        self.dialog = FileDialog(
            "Burst FCS file chooser",
            mode="folder"
            if action == "folder"
            else ("save" if action in ("save", "export", "save_pairs") else "open"),
            multiselect=action == "files",
            filters=[("BUR/BST", ["*.bur", "*.bst"])]
            if action == "files"
            else [("JSON", ["*.json"])],
            filename="burst_fcs.json" if action in ("save", "export", "save_pairs") else None,
        )

    def draw_controls(self):
        from emtk import im

        im.begin_disabled(self.running)
        for label, action, tip in (
            ("Open BUR/BST files", "files", "Choose burst tables or burst-ID ranges."),
            ("Add analysis folder", "folder", "Find burst files in an analysis folder."),
            ("Load settings", "load", "Load correlator and fitting parameters from JSON."),
            ("Save settings", "save", "Save current correlator and fitting parameters."),
            (
                "Load detector setup / pairs",
                "pairs",
                "Load a detector setup or explicit channel-pair JSON.",
            ),
            (
                "Save channel pairs",
                "save_pairs",
                "Export all channel pairs with their microtime gates.",
            ),
            (
                "Export curves",
                "export",
                "Save calculated data, fits and diffusion distributions as JSON.",
            ),
        ):
            if im.button(label):
                self.browse(action)
            im.set_item_tooltip(tip)
        if im.button("MMFDB datasets"):
            self.datasets.open()
        im.set_item_tooltip("Resolve a burst analysis dataset from MMFDB.")
        if im.button("Clear files and results"):
            self.files, self._curves, self._model._selected = [], [], None
        im.set_item_tooltip("Remove inputs and previous correlation curves.")
        for path in list(self.files):
            im.text_wrapped(path)
            if im.button(f"Remove##{path}"):
                self.files.remove(path)
            im.set_item_tooltip(f"Remove input {Path(path).name}.")
        im.text("Channel pair JSON:")
        changed = im.text_editor(
            "##pairs", self.pairs_editor, size=(im.get_content_region_avail()[0], 140)
        )
        im.set_item_tooltip(
            "List named chs_a/chs_b channel pairs with optional micro_a/micro_b gates."
        )
        if changed:
            self.pairs_text = self.pairs_editor.text
        if im.button("Apply channel pairs"):
            self.apply_pairs(self.pairs_text)
        im.set_item_tooltip("Validate and use the edited channel pairs.")
        for pair in self._pair_presets:
            name = pair["pair_name"]
            changed, enabled = im.checkbox(name, name in self.enabled_pairs)
            im.set_item_tooltip(f"Include {name} when correlating each burst.")
            if changed:
                if enabled:
                    self.enabled_pairs.add(name)
                else:
                    self.enabled_pairs.discard(name)
        for attr, label, tip in (
            (
                "maxent_log10_reg",
                "MaxEnt log10 regularization",
                "Log10 of the regularization strength.",
            ),
            (
                "maxent_td_min",
                "Min diffusion time (ms)",
                "Lower diffusion-time grid limit; zero chooses automatically.",
            ),
            (
                "maxent_td_max",
                "Max diffusion time (ms)",
                "Upper diffusion-time grid limit; zero chooses automatically.",
            ),
            (
                "tmin_fit",
                "Fit lag min (ms)",
                "Exclude shorter lag times from fitting; zero uses all.",
            ),
            (
                "tmax_fit",
                "Fit lag max (ms)",
                "Exclude longer lag times from fitting; zero uses all.",
            ),
        ):
            changed, value = im.input_float(label, getattr(self._model, attr))
            im.set_item_tooltip(tip)
            if changed:
                setattr(
                    self._model,
                    attr,
                    max(-12, min(12, value)) if attr == "maxent_log10_reg" else max(0, value),
                )
        im.end_disabled()
        if im.button("Stop FCS"):
            self.stop()
        im.set_item_tooltip("Cancel between burst correlations, preserving previous results.")
        im.text_wrapped(self.status)
        im.text("Filter curves:")
        changed, self.filter = im.input_text("##curve_filter", self.filter)
        im.set_item_tooltip("Filter calculated curves by measurement, burst index or channel pair.")
        for i, curve in enumerate(self._curves):
            label = f"{curve.get('file', '')} · b{curve.get('burst_index', 0)} · {curve.get('pair_name', '')}"
            if self.filter.lower() not in label.lower():
                continue
            if im.selectable(f"{label}##curve{i}", self._model._selected is curve):
                self._model._selected = curve
            im.set_item_tooltip(
                "Show this burst correlation and its fitted diffusion distribution."
            )

    def draw_dialogs(self, frame):
        from emtk import im

        if self.dialog is not None:
            if im.begin("FCS input / output chooser"):
                result = self.dialog.draw()
                if result:
                    try:
                        if self.action in ("files", "folder"):
                            self.add_files(result)
                        elif self.action == "load":
                            self.load_settings(result[0])
                        elif self.action == "save":
                            self.save_settings(result[0])
                        elif self.action == "pairs":
                            self.apply_pairs(Path(result[0]).read_text())
                        elif self.action == "save_pairs":
                            Path(result[0]).write_text(json.dumps(self._pair_presets, indent=2))
                        else:
                            self.export_curves(result[0])
                    except Exception as exc:
                        self.status = f"Error: {exc}"
                    self.dialog = None
                elif result is False:
                    self.dialog = None
            im.end()
        self.datasets.render(frame)

    def close(self):
        self.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
