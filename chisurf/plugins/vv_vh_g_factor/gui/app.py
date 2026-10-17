"""Native VV/VH calibration, slow-protein mixing and anisotropy batch analysis (emtk)."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
from emtk import im, implot, style
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form

from chisurf.core.fio import read_vv_vh
from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import (
    LabelColumn,
    action_caption,
    action_tooltip,
    button_row,
    labelled,
    layout_spec,
    window_size,
)
from chisurf.plugins.microscopy.imaging_emtk.path_list import PathListView
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .client import VvVhGFactorClient
from .model import GFactorModel

HERE = Path(__file__).parent
DISPLAY = ("show_fast", "show_slow", "show_sample", "show_raw", "show_corrected", "log_y")


class GFactorApp(TourTarget, ImApp):
    def __init__(self, client=None, on_close=None, dataset_client=None):
        primary = json.loads((HERE / "gfactor_emtk.view.json").read_text())
        self.window_size = window_size(primary, (1100, 720))
        self.on_close = on_close
        self._closed = False
        self.window_title = tr("VV/VH G-Factor Calculator")
        self.model = GFactorModel()
        self.client = client or VvVhGFactorClient()
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        panels = primary["panels"]
        self.panels = {n: layout_spec(copy.deepcopy(p)) for n, p in panels.items()}
        self.forms = {n: FormState() for n in panels}
        self.dataset_picker = DatasetPicker(client=dataset_client, on_paths=self.add_batch)
        self.ref_picker = DatasetPicker(client=dataset_client, on_paths=self.add_reference_paths)
        self.picker = self.dataset_picker
        self.path_list = PathListView(
            self,
            actions={
                "add": lambda: self.choose(tr("Batch VV/VH decays"), self.add_batch, multiple=True),
                "folder": lambda: self.choose(
                    tr("Batch VV/VH folder"), self.add_batch_folder, mode="folder"
                ),
                "database": self.dataset_picker.open,
                "remove": lambda path: self.model.remove_batch({"path": path}),
                "clear": self.clear_batch,
            },
        )
        self.forms["batch"].custom["path_list"] = lambda section, model, state, width: (
            self.path_list.draw(section, model, state)
        )
        self.labels = {n: LabelColumn() for n in panels}
        self.help = EmTkHelpWindow(
            title="VV/VH G-factor: Help", resource=HERE / "help.md", owner=self
        )
        self.help_window = self.help
        self.guide = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda key: (
                self.item_rects.get(key)
                or next((f.rects[key] for f in self.forms.values() if key in f.rects), None)
            ),
            owner=self,
            wait_for_controls=True,
        )
        self.tour = self.guide
        for form in self.forms.values():
            form.on_used = self.guide.notify_used
        self.model._on_used = self.guide.notify_used
        self.job = BackgroundJob()
        self.dialog: FileDialog | None = None
        self.dialog_window: DialogWindow | None = None
        self.dialog_callback: Callable[[list[str]], object] | None = None
        self.last_dir = ""
        self.show_fast = self.show_slow = self.show_sample = self.show_raw = self.show_corrected = True
        self.log_y = True
        self.plot_signature = None
        self.plot_info = {}
        self.settings_signature = self.fingerprint()
        self.docks = DockManager(
            Split(
                "h",
                0.43,
                Region("controls"),
                Split("v", 0.58, Region("decays"), Region("anisotropy")),
            ),
            name="vv_vh_g_factor",
        )
        self.docks.add_window(
            "controls", "Calibration (References)", self.draw_controls, dock="controls", closable=False
        )
        self.docks.add_window(
            "batch", "Unknown Samples (Batch)", self.draw_batch, dock="controls", closable=False
        )
        self.docks.add_window(
            "decays", "VV/VH decays", self.draw_decays, dock="decays", closable=False
        )
        self.docks.add_window(
            "anisotropy", "Anisotropy r(t)", self.draw_anisotropy, dock="anisotropy", closable=False
        )
        self.docks.add_window(
            "ratio", "VV/VH ratio (G-factor)", self.draw_ratio, dock="anisotropy", closable=False
        )
        self.batch_window = DialogWindow(
            tr("Batch Anisotropy"), size=(860.0, 540.0), key="vv_vh_batch"
        )
        self.plot_decay_idx = 0
        self.plot_aniso_decay_idx = 0
        self.plot_ratio_decay_idx = 0
        self.show_ratio_raw = True
        self.show_ratio_corrected = True
        self.show_g_line = True
        super().__init__(gui=self.render, continuous=False)

    def animating(self) -> bool:
        return self.job.running or getattr(self.guide, "running", False) or super().animating()

    # -- plumbing ---------------------------------------------------------------------------- #
    def fingerprint(self):
        settings = self.model.export_settings()
        settings.pop("batch_files", None)
        settings.pop("batch_open", None)
        settings.pop("decays", None)
        return json.dumps(settings, sort_keys=True)

    def form(self, name, model=None):
        spec, column = self.panels[name], self.labels[name]
        if not column.ready:
            column.measure([f["label"] for f in labelled(spec["sections"])])
        column.pad(spec["sections"])
        draw_form(spec, model or self.model, self.forms[name])

    def choose(
        self,
        title,
        callback: Callable[[list[str]], object],
        mode="open",
        multiple=False,
        filename="",
    ):
        if self.job.running:
            return
        self.dialog = FileDialog(
            title,
            mode=mode,
            multiselect=multiple,
            filename=filename,
            directory=self.last_dir or None,
            filters="VV/VH decay (*.dat *.txt *.csv);;All files (*)"
            if mode != "save"
            else "Results (*.json *.tsv *.txt *.csv *.dat);;All files (*)",
        )
        self.dialog_window = DialogWindow(title, size=(760, 540))
        self.dialog_callback = callback

    def run(self, operation, on_complete=None):
        if self.job.running:
            return False
        model = self.model.snapshot()

        def work():
            operation(model)
            return model

        def publish(done):
            self.model = done
            self.plot_signature = None
            self.settings_signature = self.fingerprint()
            if on_complete:
                on_complete()

        return self.job.start(
            work, publish, lambda exc: setattr(self.model, "message", f"Error: {exc}")
        )

    def load(self, path, slow=False, sample=False):
        self.last_dir = str(Path(path).parent)

        def operation(model):
            model.load(path, slow=slow, sample=sample)
            if model.fast is not None:
                model.compute(self.client)
            elif model.sample is not None:
                model.compute_sample()

        ok = self.run(operation)
        if ok and not slow and not sample:
            self.guide.notify_used("load_fast")
        if ok and slow:
            self.guide.notify_used("load_slow")
        if ok and sample:
            self.guide.notify_used("load_sample")
        return ok

    def load_file(self, path):
        """Unified loader for sample VV/VH decay (and fallback fast reference)."""
        self.last_dir = str(Path(path).parent)

        def operation(model):
            model.load_file(path)
            if model.fast is not None:
                model.compute(self.client)

        return self.run(operation)

    def load_any_decay(self, path):
        """Load any VV/VH decay file into the multi-decay manager."""
        self.last_dir = str(Path(path).parent)

        def operation(model):
            model.load(path, role="sample")
            model.compute_sample()

        return self.run(operation)

    example_folder = None  # None: the plugin's demo cache

    def load_example(self):
        """Load the simulated fast/slow references and two batch decays (known G)."""
        folder = self.example_folder

        def operation(model):
            model.load_example(folder, self.client)

        ok = self.run(operation)
        if ok:
            self.guide.notify_used("load_example")
        return ok

    def calculate(self):
        return self.run(lambda model: model.compute(self.client))

    def archive(self):
        if self.job.running:
            return False
        if not self.model.fast_file:
            self.model.message = "Load a reference decay before archival."
            return False
        source, parameters = self.model.fast_file, self.model.archive_parameters()

        def work():
            result = self.client.archive_g_factor(source, parameters)
            if not result.get("ok", True) or not result.get("calibration_id"):
                raise ValueError(
                    result.get("error") or "Calibration archival did not return an identifier."
                )
            return result

        return self.job.start(
            work,
            lambda result: setattr(
                self.model, "message", f"Archived calibration {result['calibration_id']}"
            ),
            lambda exc: setattr(self.model, "message", f"Error: {exc}"),
        )

    def add_batch(self, paths):
        for path in paths:
            self.last_dir = str(Path(path).parent)
            if str(path) not in self.model.batch_files:
                self.model.batch_files.append(str(path))

    def add_batch_paths(self, paths):
        return self.model.add_batch_paths([str(p) for p in paths or []])

    def add_reference_paths(self, paths):
        """Add reference decay paths from MMFDB database picker."""
        for path in paths or []:
            self.model.load_reference(path)
        if self.model.fast is not None:
            self.calculate()

    def add_batch_folder(self, folders):
        """Queue the same supported VV/VH files as the legacy recursive folder picker."""
        self.add_batch(
            str(path)
            for folder in folders
            for path in sorted(Path(folder).rglob("*"))
            if path.is_file() and path.suffix.lower() in {".dat", ".txt", ".csv"}
        )

    def clear_batch(self):
        self.model.batch_files = []
        self.model.batch_results = []

    def files_dropped(self, paths):
        """Host drop: first is fast reference, second slow protein, any more join batch queue. If fast loaded, single file is sample."""
        paths = [str(p) for p in paths or []]
        if not paths:
            return False
        if getattr(self.model, "batch_open", False):
            return self.add_batch_paths(paths) > 0
        if len(paths) == 1 and self.model.fast is not None:
            return self.load(paths[0], sample=True)
        self.load(paths[0])
        if len(paths) > 1:
            self._follow = [lambda: self.load(paths[1], slow=True)]
            if paths[2:]:
                self._follow.append(lambda: self.add_batch(paths[2:]))
        return True

    on_files_dropped = files_dropped
    on_paths_dropped = files_dropped

    def window_resized(self, width: int | float, height: int | float) -> None:
        self.window_size = (int(width), int(height))

    # -- windows ----------------------------------------------------------------------------- #
    def path_row(self, label, path, empty):
        im.text(label)
        im.same_line()
        name = Path(path).name if path else empty
        im.text_disabled(name)
        if path:
            im.set_item_tooltip(f"{label} {path}")

    def draw_controls(self, box):
        m = self.model
        m.busy = self.job.running
        busy = self.job.running or self.dialog is not None
        pressed = button_row(
            [
                {
                    "label": "Load...",
                    "key": "load_fast",
                    "enabled": not busy,
                    "tip": "Load reference standard VV/VH decay file(s) for G-factor calibration.",
                },
                {
                    "label": "Slow...",
                    "key": "load_slow",
                    "enabled": not busy,
                    "tip": "Load a slow-rotating reference standard for polarization-mixing estimation.",
                },
                {
                    "label": action_caption("example"),
                    "key": "load_example",
                    "enabled": not busy,
                    "tip": action_tooltip(
                        "example",
                        tr(
                            "Load simulated references with a known G of 1.2: a fast dye, a slow protein and two batch decays."
                        ),
                    ),
                },
                {
                    "label": "MMFDB...",
                    "key": "load_database",
                    "enabled": not busy,
                    "tip": "Select and load reference standard datasets directly from MMFDB database.",
                },
                {
                    "label": "Batch ->",
                    "key": "open_batch",
                    "enabled": not busy,
                    "tip": "Switch to the Unknown Samples / Batch tab to process unknown files with this calibration.",
                },
                {
                    "label": "Export...",
                    "key": "export",
                    "enabled": m.g_factor is not None and not busy,
                    "tip": "Export calibration results as JSON.",
                },
                {
                    "label": "Archive",
                    "key": "archive",
                    "enabled": m.g_factor is not None and not busy,
                    "tip": "Register the raw reference decay, corrected traces, anisotropy and calibration provenance through MMFDB.",
                },
                {
                    "label": "Stop",
                    "key": "stop",
                    "enabled": self.job.running,
                    "tip": "Discard the pending result; an archival already running may finish.",
                },
                {"label": action_caption("help"), "key": "help", "tip": action_tooltip("help")},
                {"label": action_caption("guide"), "key": "guide", "tip": action_tooltip("guide")},
            ],
            remember=self.remember,
        )
        if pressed == "load_example":
            self.load_example()
        elif pressed == "load_fast":
            self.choose("Reference standard decay", lambda paths: self.load(paths[0]))
        elif pressed == "load_slow":
            self.choose("Slow protein reference", lambda paths: self.load(paths[0], slow=True))
        elif pressed == "load_database":
            self.ref_picker.open()
        elif pressed == "open_batch":
            self.model.open_batch()
            self.docks.focus("batch")
        elif pressed == "export":
            self.choose(
                "Calibration results",
                lambda paths: self.run(lambda model: model.save_results(paths[0])),
                mode="save",
                filename="calibration.json",
            )
        elif pressed == "archive":
            self.archive()
        elif pressed == "stop":
            self.job.stop()
        elif pressed == "help":
            self.help.show()
        elif pressed == "guide":
            self.guide.start()

        self.form("references", m)
        status_msg = m.message or "Load reference standard VV/VH decay(s) for calibration."
        im.text(status_msg)
        self.form("parameters", m)
        warn = m.fp_result.get("warning")
        if warn and ("outside" in warn or "error" in warn.lower() or m.fp_result.get("l1") is None):
            im.text_colored(style.TEXT_WARNING, warn)

    @property
    def is_batch_mode(self) -> bool:
        """True when the user is in batch analysis mode (batch dock focused or batch dialog open)."""
        if getattr(self.model, "batch_open", False):
            return True
        if hasattr(self, "docks") and hasattr(self.docks, "active_tab"):
            try:
                return self.docks.active_tab("controls") == "batch"
            except Exception:
                return False
        return False

    def get_active_batch_file(self) -> str | None:
        m = self.model
        if not m.batch_files:
            return m.sample_file or m.fast_file or None
        path = None
        if m.selected_batch_file and m.selected_batch_file in m.batch_files:
            path = m.selected_batch_file
        elif "batch" in self.forms and hasattr(self.forms["batch"], "path_list"):
            idx = self.forms["batch"].path_list.selected.get("batch_files", 0)
            idx = min(max(0, idx), len(m.batch_files) - 1)
            path = m.batch_files[idx]
        else:
            path = m.batch_files[0]

        if m.selected_batch_file != path:
            m.selected_batch_file = path
            if not getattr(m, "selected_batch_files", None):
                m.selected_batch_files = [path]
            m.sample_file = path
            if Path(path).is_file():
                try:
                    vv, vh = read_vv_vh(str(path), split=True)
                    vv = np.asarray(vv, dtype=float)
                    vh = np.asarray(vh, dtype=float)
                    n = min(len(vv), len(vh))
                    m.sample = (vv[:n], vh[:n])
                    m.sample_region = list(m.region)
                    m.compute_sample()
                except Exception:
                    pass
        return path

    def get_active_batch_files(self) -> list[str]:
        """Return the batch files currently selected in the table."""
        m = self.model
        if not m.batch_files:
            return []
        selected = [p for p in getattr(m, "selected_batch_files", []) if p in m.batch_files]
        if selected:
            return selected
        active = self.get_active_batch_file()
        if active and active in m.batch_files:
            return [active]
        return [m.batch_files[0]]

    def draw_sample(self, box=None):
        return self.draw_batch(box)

    def draw_batch(self, box=None):
        m = self.model
        m.busy = self.job.running
        busy = self.job.running or self.dialog is not None
        pressed = button_row(
            [
                {
                    "label": "<- Calibration",
                    "key": "to_controls",
                    "enabled": not busy,
                    "tip": "Switch back to the Reference Calibration tab.",
                },
                {
                    "label": "Process all",
                    "key": "run",
                    "enabled": not busy and bool(m.batch_files) and m.g_factor is not None,
                    "tip": "Compute r(inf), corrected decays, and anisotropy for all queued files using calibrated G, l1, l2.",
                },
                {
                    "label": "Save table...",
                    "key": "save",
                    "enabled": not busy and bool(m.batch_results),
                    "tip": "Write per-file r(inf), region, backgrounds, G, l1, l2 and errors as a table.",
                },
                {
                    "label": "Export active decay...",
                    "key": "export_active_decay",
                    "enabled": not busy and (bool(m.batch_files) or m.sample is not None or m.fast is not None),
                    "tip": "Export the currently selected file's raw and corrected VV and VH decays to a CSV file.",
                },
                {
                    "label": "Export active r(t)...",
                    "key": "export_active_rt",
                    "enabled": not busy and (bool(m.batch_files) or m.sample is not None or m.fast is not None),
                    "tip": "Export the currently selected file's time-resolved anisotropy r(t) curve to a CSV file.",
                },
                {
                    "label": "Export active ratio...",
                    "key": "export_active_ratio",
                    "enabled": not busy and (bool(m.batch_files) or m.sample is not None or m.fast is not None),
                    "tip": "Export the currently selected file's raw and corrected VV/VH intensity ratio to a CSV file.",
                },
                {
                    "label": "Export all r(t)...",
                    "key": "export_all_rt",
                    "enabled": not busy and bool(m.batch_files) and m.g_factor is not None,
                    "tip": "Export time-resolved anisotropy r(t) curves for all queued batch files into a single CSV.",
                },
                {
                    "label": action_caption("close"),
                    "key": "close",
                    "enabled": not busy,
                    "tip": "Close the batch window.",
                },
            ],
            remember=self.remember,
        )
        if pressed == "to_controls":
            self.docks.focus("controls")
        elif pressed == "run":
            self.run(lambda model: model.compute_batch(self.job.cancelled.is_set))
        elif pressed == "save":
            self.choose(
                "Batch anisotropy table",
                lambda paths: self.run(lambda model: model.export_batch(paths[0])),
                mode="save",
                filename="batch_anisotropy.tsv",
            )
        elif pressed == "export_active_decay":
            active_file = self.get_active_batch_file()
            stem = Path(active_file).stem if active_file else "decay"
            self.choose(
                "Export active decay CSV",
                lambda paths: self.model.export_active_decay(paths[0], active_file),
                mode="save",
                filename=f"{stem}_decay.csv",
            )
        elif pressed == "export_active_rt":
            active_file = self.get_active_batch_file()
            stem = Path(active_file).stem if active_file else "anisotropy"
            self.choose(
                "Export active anisotropy r(t) CSV",
                lambda paths: self.model.export_active_rt(paths[0], active_file),
                mode="save",
                filename=f"{stem}_rt.csv",
            )
        elif pressed == "export_active_ratio":
            active_file = self.get_active_batch_file()
            stem = Path(active_file).stem if active_file else "ratio"
            self.choose(
                "Export active ratio CSV",
                lambda paths: self.model.export_active_ratio(paths[0], active_file),
                mode="save",
                filename=f"{stem}_ratio.csv",
            )
        elif pressed == "export_all_rt":
            self.choose(
                "Export all anisotropy r(t) CSV",
                lambda paths: self.model.export_all_rt(paths[0]),
                mode="save",
                filename="all_anisotropy_rt.csv",
            )
        elif pressed == "close":
            self.model.close_batch()
            if hasattr(self, "batch_window"):
                self.batch_window.hide()

        if m.g_factor is not None:
            l1_s = f"{m.l1:.5f}" if m.l1 is not None and np.isfinite(m.l1) else "0.00000"
            l2_s = f"{m.l2:.5f}" if m.l2 is not None and np.isfinite(m.l2) else "0.00000"
            im.text_colored(
                style.TEXT_NOTE,
                f"Applied calibration: G = {m.g_factor:.5f} | l1 = {l1_s} | l2 = {l2_s}",
            )
        else:
            im.text_colored(
                style.TEXT_WARNING,
                "Calibration pending: determine G on Calibration tab first.",
            )

        if not m.batch_files:
            im.text_wrapped(
                tr(
                    "No files queued. Add VV/VH decays to evaluate their r(inf) over the tail region with this calibration."
                )
            )
        self.form("batch", m)

        active_file = self.get_active_batch_file()
        if active_file:
            im.separator()
            im.text("Selected sample:")
            im.same_line()
            im.text_colored(style.TEXT_NOTE, Path(active_file).name)
            im.set_item_tooltip(str(active_file))
            self.form("sample", m)

    # -- plots ------------------------------------------------------------------------------- #
    def get_decay_options(self):
        if self.is_batch_mode:
            opts = ["Selected in table"]
            if self.model.batch_files:
                for p in self.model.batch_files:
                    opts.append(f"[Sample] {Path(p).name}")
            return opts
        opts = ["All (Overlay)"]
        if self.model.batch_files:
            for p in self.model.batch_files:
                opts.append(f"[Sample] {Path(p).name}")
        if self.model.decays:
            for d in self.model.decays:
                opts.append(f"[{d['role'].capitalize()}] {d['name']}")
        else:
            if self.model.fast is not None:
                opts.append("Fast reference")
            if self.model.slow is not None:
                opts.append("Slow reference")
            if self.model.sample is not None and not self.model.batch_files:
                opts.append("Sample")
        return opts

    def series(self, selected_idx: int | None = None):
        opts = self.get_decay_options()
        idx = self.plot_decay_idx if selected_idx is None else selected_idx
        idx = min(max(0, idx), len(opts) - 1) if opts else 0

        if self.is_batch_mode:
            if idx > 0 and idx < len(opts):
                selected_label = opts[idx]
                if selected_label.startswith("[Sample] "):
                    name = selected_label[9:]
                    match_path = next((p for p in self.model.batch_files if Path(p).name == name), None)
                    if match_path:
                        return [(f"Sample {name}", self.model.get_decay_series(file_path=match_path))]
            selected_files = self.get_active_batch_files()
            return [
                (f"Sample {Path(p).name}", self.model.get_decay_series(file_path=p))
                for p in selected_files
            ]

        if idx > 0 and idx < len(opts):
            selected_label = opts[idx]
            if selected_label.startswith("[Sample] "):
                name = selected_label[9:]
                match_path = next((p for p in self.model.batch_files if Path(p).name == name), None)
                if match_path:
                    return [(f"Sample {name}", self.model.get_decay_series(file_path=match_path))]
            for d in self.model.decays:
                if selected_label == f"[{d['role'].capitalize()}] {d['name']}":
                    return [(d["role"].capitalize(), self.model.decay_series(entry=d))]
            if selected_label == "Fast reference" and self.model.fast is not None:
                return [("Fast", self.model.decay_series(slow=False))]
            if selected_label == "Slow reference" and self.model.slow is not None:
                return [("Slow", self.model.decay_series(slow=True))]
            if selected_label == "Sample" and self.model.sample is not None:
                return [("Sample", self.model.decay_series(sample=True))]

        res = []
        if self.model.decays:
            seen_roles = {}
            for d in self.model.decays:
                role = d["role"]
                if (role == "fast" and not self.show_fast) or (role == "slow" and not self.show_slow) or (role == "sample" and not self.show_sample):
                    continue
                count = seen_roles.get(role, 0)
                seen_roles[role] = count + 1
                label = role.capitalize() if count == 0 else f"{role.capitalize()} {d['name']}"
                res.append((label, self.model.decay_series(entry=d)))
        else:
            for label, slow, sample, enabled in [
                ("Fast", False, False, self.show_fast),
                ("Slow", True, False, self.show_slow),
                ("Sample", False, True, self.show_sample),
            ]:
                if enabled and ((not slow and not sample and self.model.fast is not None) or (slow and self.model.slow is not None) or (sample and self.model.sample is not None)):
                    res.append((label, self.model.decay_series(slow=slow, sample=sample)))
        return res

    def draw_decays(self, box):
        opts = self.get_decay_options()
        im.text("Decay:")
        im.same_line()
        im.set_next_item_width(170.0)
        idx = min(self.plot_decay_idx, len(opts) - 1)
        changed, self.plot_decay_idx = im.combo("##vvvh_decay_select", idx, opts)
        im.set_item_tooltip(tr("Select which decay to display in the VV/VH plot, or display all overlaid."))
        im.same_line()
        used, avail = im.get_cursor_pos()[0], im.get_content_region_avail()[0]
        spacing = im.get_style().item_spacing[0]
        toggles = (
            [
                ("show_raw", "Raw"),
                ("show_corrected", "Corrected"),
                ("log_y", "Log counts"),
            ]
            if self.is_batch_mode
            else [
                ("show_fast", "Fast reference"),
                ("show_slow", "Slow reference"),
                ("show_sample", "Sample"),
                ("show_raw", "Raw"),
                ("show_corrected", "Corrected"),
                ("log_y", "Log counts"),
            ]
        )
        for attr, label in toggles:
            width = im.calc_text_size(label)[0] + 2 * im.get_frame_height() + spacing
            if used and used + width > avail:
                im.new_line()
                used = 0.0
            elif used:
                im.same_line()
            _, value = im.checkbox(label, getattr(self, attr))
            setattr(self, attr, value)
            im.set_item_tooltip(tr("Show or hide this trace group, or change the intensity scale."))
            used += width
        im.new_line()
        if self.model.fast is None and self.model.slow is None and self.model.sample is None and not self.model.decays and not self.model.batch_files:
            im.text_wrapped(tr("Load a VV/VH decay (button, or drop a file on the window)."))
            return
        if implot.begin_plot("##vvvh", (-1, -1)):
            implot.setup_axes("TAC bin", "Counts")
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            if self.log_y:
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            series = self.series(selected_idx=self.plot_decay_idx)
            vectors = [
                v[k]
                for _, v in series
                if v
                for k in ("vv_raw", "vh_raw", "vv_corrected", "vh_corrected")
            ]
            vectors = [v for v in vectors if np.any(np.isfinite(v))]
            if vectors:
                peak = max(float(np.nanmax(v)) for v in vectors)
                length = max(map(len, vectors))
                sig = (id(self.model.fast), id(self.model.slow), id(self.model.sample), self.log_y, peak, self.plot_decay_idx)
                implot.setup_axes_limits(
                    0,
                    length,
                    1 if self.log_y else 0,
                    max(2, peak * 1.1),
                    cond=implot.COND_ALWAYS if sig != self.plot_signature else implot.COND_ONCE,
                )
                self.plot_signature = sig
            for label, data in series:
                if not data:
                    continue
                for key, axis, enabled in [
                    ("vv_raw", "time", self.show_raw),
                    ("vh_raw", "shifted_time", self.show_raw),
                    ("vv_corrected", "time", self.show_corrected),
                    ("vh_corrected", "shifted_time", self.show_corrected),
                ]:
                    if enabled:
                        vector = data[key]
                        vector = np.where(vector > 0, vector, np.nan) if self.log_y else vector
                        implot.plot_line(label + " " + key.replace("_", " "), data[axis], vector)
            if self.model.fast is not None:
                for index, value in enumerate(self.model.region):
                    result = implot.drag_line_x(10 + index, value, col=(255, 200, 40, 255))
                    if result.modified and not self.job.running:
                        self.model.region[index] = round(result.value, 1)
                if self.model.background:
                    for index, value in enumerate(self.model.background_region):
                        result = implot.drag_line_x(20 + index, value, col=(100, 180, 255, 255))
                        if result.modified and not self.job.running:
                            self.model.background_region[index] = round(result.value, 1)
            self.plot_info = {
                "pos": implot.get_plot_pos(),
                "size": implot.get_plot_size(),
                "tail": [implot.plot_to_pixels(float(v), 100.0) for v in self.model.region],
                "background": [
                    implot.plot_to_pixels(float(v), 100.0) for v in self.model.background_region
                ],
            }
            implot.end_plot()

    def draw_anisotropy(self, box):
        if self.model.fast is None and self.model.slow is None and self.model.sample is None and not self.model.decays and not self.model.batch_files:
            im.text_wrapped(tr("The anisotropy r(t) of the loaded decays appears here."))
            return
        opts = self.get_decay_options()
        im.text("Decay:")
        im.same_line()
        im.set_next_item_width(170.0)
        idx = min(self.plot_aniso_decay_idx, len(opts) - 1)
        changed, self.plot_aniso_decay_idx = im.combo("##aniso_decay_select", idx, opts)
        im.set_item_tooltip(tr("Select which decay to display in the anisotropy plot, or display all overlaid."))
        im.same_line()
        _, self.show_raw = im.checkbox("Raw r(t)", self.show_raw)
        im.set_item_tooltip(tr("Show or hide raw anisotropy trace."))
        im.same_line()
        _, self.show_corrected = im.checkbox("Corrected r(t)", self.show_corrected)
        im.set_item_tooltip(tr("Show or hide corrected anisotropy trace."))
        im.new_line()
        if implot.begin_plot("##anisotropy", (-1, -1)):
            implot.setup_axes("TAC bin", "Anisotropy r(t)")
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            aniso_series = self.series(selected_idx=self.plot_aniso_decay_idx)
            max_len = 1
            for _, data in aniso_series:
                if data and "time" in data:
                    max_len = max(max_len, len(data["time"]))
            implot.setup_axes_limits(
                0,
                max(1, max_len),
                -0.2,
                0.6,
                cond=implot.COND_ONCE,
            )
            for label, data in aniso_series:
                if not data:
                    continue
                if self.show_raw and "r_raw" in data:
                    implot.plot_line(label + " raw", data["time"], data["r_raw"])
                if self.show_corrected and "r_corrected" in data:
                    implot.plot_line(label + " corrected", data["time"], data["r_corrected"])

            bounds = self.model.sample_region if (self.model.sample is not None or self.model.batch_files) else self.model.region
            implot.set_next_fill_style((60, 205, 100, 255), 0.2)
            implot.plot_shaded(
                "##rinf_region",
                np.array([min(bounds), max(bounds)]),
                np.array([0.6, 0.6]),
                np.array([-0.2, -0.2]),
            )
            for index, value in enumerate(bounds):
                result = implot.drag_line_x(200 + index, value, col=(60, 205, 100, 255))
                if result.modified and not self.job.running:
                    bounds[index] = round(result.value, 1)
                    self.model.compute_sample()

            implot.end_plot()
        im.set_item_tooltip(tr("Drag the green lines to choose the r(inf) region."))

    def draw_ratio(self, box):
        if (
            self.model.fast is None
            and self.model.slow is None
            and self.model.sample is None
            and not self.model.decays
            and not self.model.batch_files
        ):
            im.text_wrapped(
                tr(
                    "The intensity ratio VV/VH and calibrated G-factor plateau appear here once decays are loaded."
                )
            )
            return
        opts = self.get_decay_options()
        im.text("Decay:")
        im.same_line()
        im.set_next_item_width(170.0)
        idx = min(self.plot_ratio_decay_idx, len(opts) - 1)
        changed, self.plot_ratio_decay_idx = im.combo("##ratio_decay_select", idx, opts)
        im.set_item_tooltip(tr("Select which decay's VV/VH ratio to display, or display all overlaid."))
        im.same_line()
        _, self.show_ratio_raw = im.checkbox("Raw ratio##chk", self.show_ratio_raw)
        im.set_item_tooltip(tr("Show or hide raw intensity ratio VV(t) / VH(t)."))
        im.same_line()
        _, self.show_ratio_corrected = im.checkbox("Corrected ratio##chk", self.show_ratio_corrected)
        im.set_item_tooltip(tr("Show or hide background-subtracted & shifted ratio."))
        im.same_line()
        _, self.show_g_line = im.checkbox("G baseline##chk", self.show_g_line)
        im.set_item_tooltip(tr("Show horizontal baseline for calibrated detector G-factor."))
        im.new_line()

        if implot.begin_plot("##vvvh_ratio_plot", (-1, -1)):
            implot.setup_axes("TAC bin", "VV / VH Ratio")
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            ratio_series = self.series(selected_idx=self.plot_ratio_decay_idx)

            max_len = 1
            for _, data in ratio_series:
                if data and "time" in data:
                    max_len = max(max_len, len(data["time"]))

            g = self.model.g_factor
            g_val = float(g) if (g is not None and np.isfinite(g) and g > 0) else 1.0

            implot.setup_axes_limits(
                0,
                max(1, max_len),
                0.0,
                max(3.0, g_val * 2.5),
                cond=implot.COND_ONCE,
            )

            for label, data in ratio_series:
                if not data:
                    continue
                if self.show_ratio_raw and "ratio_raw" in data:
                    implot.plot_line(label + " ratio raw", data["time"], data["ratio_raw"])
                if self.show_ratio_corrected and "ratio_corrected" in data:
                    implot.plot_line(label + " ratio corrected", data["time"], data["ratio_corrected"])

            # Horizontal baseline at calibrated G
            if self.show_g_line and g is not None and np.isfinite(g) and g > 0:
                gx = np.array([0.0, float(max_len)], dtype=float)
                gy = np.array([float(g), float(g)], dtype=float)
                implot.plot_line(f"G = {g:.5f}", gx, gy)

            # Tail region shading and draggable boundary lines
            bounds = self.model.region
            implot.set_next_fill_style((255, 200, 40, 255), 0.2)
            implot.plot_shaded(
                "##tail_ratio_region",
                np.array([min(bounds), max(bounds)]),
                np.array([max(3.0, g_val * 2.5), max(3.0, g_val * 2.5)]),
                np.array([0.0, 0.0]),
            )
            for index, value in enumerate(bounds):
                result = implot.drag_line_x(300 + index, value, col=(255, 200, 40, 255))
                if result.modified and not self.job.running:
                    bounds[index] = round(result.value, 1)
                    if self.model.fast is not None:
                        self.calculate()

            implot.end_plot()
        im.set_item_tooltip(
            tr(
                "In the tail where anisotropy decays to 0, the ratio VV/VH reaches the G-factor plateau. Drag lines to adjust tail."
            )
        )

    # -- frame ------------------------------------------------------------------------------- #
    def render(self):
        self.job.poll()
        follow = getattr(self, "_follow", None)
        if follow and not self.job.running:
            follow.pop(0)()
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        self.item_rects.clear()
        self.model.busy = self.job.running
        for form in self.forms.values():
            form.rects.clear()
        im.begin_disabled(
            self.dialog is not None
            or self.dataset_picker.is_open
            or self.ref_picker.is_open
            or self.model.batch_open
        )
        self.docks.draw(frame)
        im.end_disabled()

        # Batch modal dialog window
        if self.model.batch_open:
            self.batch_window.show()
            im.begin_disabled(self.dialog is not None)
            pressed = self.batch_window.begin(frame)
            self.draw_batch(self.batch_window.box)
            self.batch_window.end()
            im.end_disabled()
            if pressed == "close":
                self.model.close_batch()
                self.batch_window.hide()
        else:
            self.batch_window.hide()
        dialog = self.dialog
        if dialog is not None:
            window, callback = self.dialog_window, self.dialog_callback
            assert window is not None and callback is not None
            pressed = window.begin(frame)
            result = dialog.draw()
            if result:
                assert isinstance(result, list)
                self.dialog = None
                callback(result)
            elif result is False or pressed == "close":
                self.dialog = None
            window.end()
        if self.dataset_picker.is_open:
            self.dataset_picker.render(frame)
        if self.ref_picker.is_open:
            self.ref_picker.render(frame)
        self.help.draw(frame)
        self.guide.draw(*vp.size)
        signature = self.fingerprint()
        if signature != self.settings_signature and not self.job.running:
            self.settings_signature = signature
            if self.model.fast is not None:
                self.calculate()
            elif self.model.sample is not None:
                self.model.compute_sample()

    # -- settings ---------------------------------------------------------------------------- #
    def export_settings(self):
        return {
            **self.model.export_settings(),
            "last_dir": self.last_dir,
            "display": {key: getattr(self, key) for key in DISPLAY},
        }

    def restore_settings(self, state):
        self.model.restore_settings(state)
        self.last_dir = str(state.get("last_dir", ""))
        for name, value in (state.get("display") or {}).items():
            if name in DISPLAY:
                setattr(self, name, bool(value))
        paths = [
            (self.model.fast_file, False, False),
            (self.model.slow_file, True, False),
            (self.model.sample_file, False, True),
        ]
        settings = self.model.export_settings()

        def operation(model):
            for path, slow, sample in paths:
                if path and Path(path).is_file():
                    model.load(path, slow=slow, sample=sample)
            model.restore_settings(settings)
            if model.fast is not None:
                model.compute(self.client)
            elif model.sample is not None:
                model.compute_sample()

        self.run(operation)

    def close(self):
        """Cancel outstanding work and publish a valid visible result only once."""
        if self._closed:
            return
        self._closed = True
        publish = (
            not self.job.running
            and not self.model.message.startswith("Error:")
            and self.model.g_factor is not None
            and np.isfinite(self.model.g_factor)
            and self.model.g_factor > 0
        )
        snapshot = self.model.snapshot() if publish else None
        self.job.close()
        self.dataset_picker.close()
        self.ref_picker.close()
        if self.on_close is not None:
            self.on_close(snapshot)


def create_app(client=None, on_close=None, dataset_client=None):
    """Create the toolkit-free calculator and optional result-publication callback."""
    return GFactorApp(client=client, on_close=on_close, dataset_client=dataset_client)


def create_host(parent=None, client=None, on_close=None, dataset_client=None):
    """Host the existing native calculator in a legacy Qt caller."""
    from emtk.qt_host import ControlHost

    control = create_app(client=client, on_close=on_close, dataset_client=dataset_client)
    host = ControlHost(control, parent=parent)
    host.setWindowTitle(control.window_title)
    return host


make_app = create_app
