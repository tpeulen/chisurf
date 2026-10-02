"""Standalone native pixel-wise MLE: the same model and scientific core as Qt."""

from __future__ import annotations

import copy
import dataclasses
import json
import threading
import time
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.i18n import tr

from chisurf.core.datastore import (
    column_names,
    numeric_column,
    row_count,
    write_csv_table,
    write_table,
)
from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.image_canvas import ImageCanvas
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.calculator.inputs import bounded_float, bounded_int

from .view_model import PixelMleViewModel


class PixelMleApp(ImApp):
    def __init__(self, model=None, coordinator=None, ndx_callback=None):
        self.model = model or PixelMleViewModel()
        self.job = SnapshotJob(self.model)
        self.coordinator = coordinator
        self.ndx_callback = ndx_callback
        self.dialog = None
        self.dialog_window = None
        self.action = ""
        self.error = ""
        self._pending = {}
        self.map_kind = "tau"
        self.playing = False
        self.fps = 10.0
        self._last_frame = 0.0
        self.canvas = ImageCanvas("pixel_mle", image_label="Lifetime", image_unit="ns")
        self.canvas.colormap = "inferno"
        self.picker_irf = False
        self.picker = DatasetPicker(
            formats=["ptu", "pto", "ht3", "pt3", "spc"],
            on_paths=lambda paths: self.add_files(paths, irf=self.picker_irf),
        )
        self.help = EmTkHelpWindow(
            title="Pixel-wise MLE — Help", resource=Path(__file__).with_name("help.md"), owner=self
        )
        self.tour = EmTkGuidedTour(Path(__file__).with_name("guide.json"), owner=self)
        self.docks = DockManager(
            Split("h", 0.36, Region("analysis"), Split("v", 0.72, Region("map"), Region("table")))
        )
        self.docks.add_window(
            "analysis", tr("Analysis"), self.controls, dock="analysis", closable=False
        )
        self.docks.add_window("map", tr("Lifetime map"), self.map_view, dock="map", closable=False)
        self.docks.add_window(
            "table", tr("Per-pixel results"), self.table_view, dock="table", closable=False
        )
        super().__init__(self.render, continuous=False)

    def add_files(self, paths, *, irf=False):
        if self.job.busy:
            return False
        target = self.model.irf_files if irf else self.model.files
        target.extend(str(path) for path in paths if str(path) not in target)
        return True

    def on_files_dropped(self, paths):
        return self.add_files(paths)

    def start_run(self):
        if self.job.busy:
            return False
        ok, reason = self.model.can_run()
        if not ok:
            self.error = reason
            return False
        self.error = ""
        # SnapshotJob detaches settings; these additional mutable values are
        # detached before launch so edits/context cannot alter a running fit.
        self.model.irf_files = list(self.model.irf_files)
        self.model._model_params = copy.deepcopy(self.model._model_params)
        self.model.cancel_event = threading.Event()
        return self.job.start("run")

    def cancel(self):
        if self.job.busy and self.model.cancel_event is not None:
            self.model.cancel_event.set()
            self.job.progress = "Cancelling after the current file fit…"

    def choose(self, action):
        self.action = action
        save = action in ("csv", "hdf5")
        self.dialog = FileDialog(
            "Export pixel results" if save else "Select photon data",
            mode="save" if save else "open",
            filters="All files (*)",
            filename="pixel_mle.csv" if action == "csv" else "pixel_mle.h5" if save else "",
        )
        self.dialog_window = DialogWindow(self.dialog.title, size=(700, 540), key="pixel_mle_files")
        self.dialog_window.show()

    def button(self, label, tip, callback):
        if im.button(tr(label)):
            try:
                callback()
            except Exception as exc:
                self.error = str(exc)
        im.set_item_tooltip(tr(tip))

    def paths(self, title, target, action):
        im.text_unformatted(tr(title))
        self.button(
            "Add files##" + action,
            "Select photon files; drag files onto the window to add imaging sources.",
            lambda: self.choose(action),
        )
        im.same_line()
        self.button("Clear##" + action, "Remove all selected files from this list.", target.clear)
        for i, path in enumerate(list(target)):
            if im.small_button("×##" + action + str(i)):
                target.remove(path)
            im.set_item_tooltip(tr("Remove this file from the analysis."))
            im.same_line()
            im.text_wrapped(path)

    def sections(self, sections):
        """Render the authored Qt schema, keeping control limits/tooltips identical."""
        for section in sections:
            kind = section["type"]
            attr = section.get("attr", "")
            label = tr(section.get("label", section.get("title", attr)))
            if kind == "panel":
                opened = im.collapsing_header(
                    label,
                    im.TreeNodeFlags.DEFAULT_OPEN
                    if section.get("title", "").startswith("Fit parameters")
                    else 0,
                )
                im.set_item_tooltip(
                    tr(
                        section.get(
                            "description", "Configure " + section.get("title", "settings") + "."
                        )
                    )
                )
                if opened:
                    self.sections(section.get("sections", []))
                continue
            if kind not in ("value", "choice", "toggle"):
                continue
            value = getattr(self.model, attr)
            key = "##" + attr
            if kind == "toggle":
                changed, value = im.checkbox(label, value)
            else:
                im.text_unformatted(label)
                if kind == "choice":
                    options = section["options"]
                    index = options.index(value) if value in options else 0
                    changed, index = im.combo(
                        key, index, [tr(x) for x in section.get("labels", options)]
                    )
                    value = options[index]
                elif section.get("kind") == "int":
                    changed, value = bounded_int(
                        key,
                        value,
                        minimum=section.get("minimum", 0),
                        maximum=section.get("maximum", 1000000),
                    )
                elif section.get("kind") == "float":
                    changed, value = bounded_float(
                        key,
                        value,
                        minimum=section.get("minimum", -1e9),
                        maximum=section.get("maximum", 1e9),
                    )
                else:
                    changed, value = im.input_text(key, value)
            im.set_item_tooltip(tr(section.get("description", label)))
            if section.get("kind") == "file":
                self.button(
                    "Browse##" + attr, section.get("description", label), lambda: self.choose("roi")
                )
            if changed:
                setattr(self.model, attr, value)
                if section.get("call"):
                    getattr(self.model, section["call"])(value)

    def controls(self, box):
        self.button(
            "Help", "Explain fit models, calibration, ROI and output columns.", self.help.show
        )
        im.same_line()
        self.button(
            "Guide",
            "Walk through file selection, calibration and lifetime fitting.",
            self.tour.start,
        )
        im.begin_disabled(self.job.busy)
        self.paths("CLSM imaging files", self.model.files, "files")
        self.paths("IRF file", self.model.irf_files, "irf")
        self.button(
            "MMFDB dataset",
            "Resolve a registered TTTR dataset to local photon files.",
            lambda: self.open_picker(False),
        )
        self.button(
            "MMFDB IRF",
            "Resolve an IRF photon measurement from the database.",
            lambda: self.open_picker(True),
        )
        spec = json.loads(Path(__file__).with_name("pixel_mle.view.json").read_text())
        panel = self.model._analysis_panel(spec)
        self.sections([self.model._fit_model_choice_dict(), self.model._fit_param_panel_dict()])
        self.sections(panel["sections"])
        for attr, label, minimum, maximum in [
            ("g_factor", "G factor", 0.0001, 100),
            ("l1", "Mixing l1", 0, 1),
            ("l2", "Mixing l2", 0, 1),
        ]:
            im.text_unformatted(tr(label))
            changed, value = bounded_float(
                "##" + attr, getattr(self.model.settings, attr), minimum=minimum, maximum=maximum
            )
            im.set_item_tooltip(
                tr(
                    "Polarization correction adopted from detector setup; editable for standalone analysis."
                )
            )
            if changed:
                setattr(self.model.settings, attr, value)
        self.button(
            "Run",
            "Fit all selected images; results use the same MLE estimator as Qt.",
            self.start_run,
        )
        for label, action in [("Export CSV", "csv"), ("Export HDF5", "hdf5")]:
            self.button(
                label,
                "Export the currently selected per-pixel table without changing fit values.",
                lambda a=action: self.choose(a),
            )
        self.button(
            "Save container",
            "Store the current pixel map artifact beside its source photon stream.",
            self.save_container,
        )
        self.button("ndX", "Explore the current per-pixel table in native ndX.", self.open_ndx)
        self.button(
            "Next",
            "Advance the imaging pipeline with this source and result artifact.",
            self.next_step,
        )
        im.end_disabled()
        if self.job.busy:
            self.button(
                "Cancel",
                "Stop after the current C++ file fit; discard its unpublished result.",
                self.cancel,
            )
        im.text_wrapped(
            self.job.progress or self.error or self.job.error or self.model.status_text or "Ready"
        )

    def open_picker(self, irf):
        self.picker_irf = irf
        self.picker.open()

    def current_result(self):
        return self.model.results[self.model._current_index()] if self.model.results else None

    def map_view(self, box):
        names = self.model.result_names
        if names:
            changed, index = im.combo("##Result file", self.model._current_index(), names)
            im.set_item_tooltip(
                tr("Choose an analysed file; maps and result table share this selection.")
            )
            if changed:
                self.model.select_result(names[index])
                self.canvas.reset()
        changed, index = im.combo(
            "##Map parameter",
            ["tau", "rho"].index(self.map_kind),
            [tr("Lifetime τ (ns)"), tr("Rotation ρ (ns)")],
        )
        im.set_item_tooltip(
            tr("Rotation is available for fit23; other estimators return zero rotation maps.")
        )
        if changed:
            self.map_kind = ["tau", "rho"][index]
            self.canvas.reset()
        result = self.current_result()
        _, self.playing = im.checkbox(tr("Play movie"), self.playing)
        im.set_item_tooltip(tr("Cycle through scanner frames of the fitted image."))
        _, self.fps = bounded_float("##Movie speed", self.fps, minimum=0.1, maximum=60)
        im.set_item_tooltip(tr("Movie playback speed in frames per second."))
        if (
            result is not None
            and self.playing
            and time.monotonic() - self._last_frame >= 1 / self.fps
        ):
            self.canvas.z = (self.canvas.z + 1) % len(result.tau)
            self._last_frame = time.monotonic()
        self.canvas.image_label = "τ" if self.map_kind == "tau" else "ρ"
        self.canvas.draw(
            getattr(result, self.map_kind) if result is not None else None, pick_enabled=False
        )

    def table_view(self, box):
        result = self.current_result()
        if result is None:
            im.text_wrapped(tr("Run an analysis to display per-pixel results."))
            return
        table = result.dataframe
        im.text_unformatted(f"{row_count(table)} pixels · {result.n_pixels_fit} fitted")
        # A bounded preview prevents millions of pixel rows blocking repaint.
        names = column_names(table)
        columns = [numeric_column(table, name) for name in names]
        flags = (
            im.TableFlags.BORDERS
            | im.TableFlags.ROW_BG
            | im.TableFlags.SCROLL_X
            | im.TableFlags.SCROLL_Y
            | im.TableFlags.SIZING_FIXED_FIT
        )
        if im.begin_table("pixel_mle_rows", len(names), flags, (0, max(90, box[3] - 70))):
            for name in names:
                im.table_setup_column(
                    name,
                    flags=im.TableColumnFlags.WIDTH_FIXED,
                    init_width_or_weight=max(85, len(name) * 8),
                )
            im.table_headers_row()
            for row in range(min(100, row_count(table))):
                im.table_next_row()
                for index, values in enumerate(columns):
                    im.table_set_column_index(index)
                    im.text_unformatted(f"{values[row]:.4g}")
            im.end_table()

    def result_parameters(self):
        index = self.model._current_index()
        if index < len(self.model.result_parameters):
            return self.model.result_parameters[index]
        return dataclasses.asdict(self.model.settings)

    def export_table(self, path, action):
        result = self.current_result()
        if result is None:
            self.error = "Run an analysis before exporting."
            return False
        if action == "csv":
            write_csv_table(path, result.dataframe, delimiter=",")
        else:
            write_table(
                path,
                result.dataframe,
                group="results",
                meta={
                    "settings": self.result_parameters(),
                },
            )
        self.error = "Saved: " + str(path)
        return True

    def save_container(self):
        result = self.current_result()
        if result is None:
            self.error = "Run an analysis before saving a container."
            return
        from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact

        self.output_path = write_burst_artifact(
            self.model.result_paths[self.model._current_index()],
            result.dataframe,
            name="pixel_mle",
            artifact_kind="pixel_map",
            operation_type="pixel_mle",
            row_grain="pixel",
            parameters=self.result_parameters(),
            derived_from=(),
            deinterleave=False,
        )
        self.error = "Saved: " + self.output_path

    def open_ndx(self):
        result = self.current_result()
        if result is None:
            self.error = "Run an analysis before opening ndX."
        elif self.ndx_callback:
            self.ndx_callback(result.dataframe)
        else:
            from chisurf.plugins.microscopy.imaging_common.base import build_ndx_data_source
            from chisurf.plugins.ndxplorer.gui.app import make_app

            if not hasattr(self, "ndx"):
                self.ndx = make_app()
            self.ndx.model.set_source(build_ndx_data_source(result.dataframe))
            from emtk.native import NativeHost

            self.ndx_host = NativeHost(self.ndx, title="Pixel MLE — ndX", size=(1100, 800))

    def next_step(self):
        if self.coordinator is None:
            self.error = "Open inside the native Imaging Tools pipeline to use Next."
            return
        self.coordinator.set_pipeline(
            source=self.model.files[0] if self.model.files else None,
            hdf5=getattr(self, "output_path", None),
        )
        self.coordinator.advance_from("pixel_mle")

    def _context(self, key, payload):
        if self.job.busy:
            self._pending[key] = copy.deepcopy(payload)
        else:
            getattr(self.model, "apply_" + key)(payload)

    def apply_setup_settings(self, payload):
        self._context("setup_settings", payload)

    def apply_calibration(self, payload):
        self._context("calibration", payload)

    def apply_pipeline_context(self, payload):
        self._context("pipeline_context", payload)

    def export_settings(self):
        return {
            "files": list(self.model.files),
            "irf_files": list(self.model.irf_files),
            "settings": dataclasses.asdict(self.model.settings),
            "fit_model": self.model.fit_model,
            "model_params": copy.deepcopy(self.model._model_params),
            "roi_path": self.model.roi_path,
            "map_kind": self.map_kind,
        }

    def restore_settings(self, state):
        if self.job.busy:
            return False
        self.model.files = list(state.get("files", []))
        self.model.irf_files = list(state.get("irf_files", []))
        for key, value in state.get("settings", {}).items():
            if key in self.model.settings.__dataclass_fields__:
                setattr(self.model.settings, key, value)
        self.model.fit_model = state.get("fit_model", "fit23")
        self.model._model_params = copy.deepcopy(state.get("model_params", {}))
        self.model.roi_path = state.get("roi_path", "")
        self.map_kind = (
            state.get("map_kind", "tau")
            if state.get("map_kind", "tau") in ("tau", "rho")
            else "tau"
        )
        return True

    def animating(self):
        return super().animating() or self.job.busy or self.picker.is_open or self.playing

    def render(self):
        self.job.poll()
        if not self.job.busy and self._pending:
            pending, self._pending = self._pending, {}
            for key, payload in pending.items():
                self._context(key, payload)
        vp = im.get_main_viewport()
        self.docks.draw((0, 0, *vp.size))
        if self.dialog:
            pressed = self.dialog_window.begin((0, 0, *vp.size))
            result = self.dialog.draw()
            if result:
                try:
                    if self.action in ("files", "irf"):
                        self.add_files(result, irf=self.action == "irf")
                    elif self.action == "roi":
                        self.model.roi_path = result[0]
                    else:
                        self.export_table(result[0], self.action)
                except Exception as exc:
                    self.error = str(exc)
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None
            self.dialog_window.end()
        self.picker.render((0, 0, *vp.size))
        self.help.draw((0, 0, *vp.size))
        self.tour.draw(*vp.size)

    def close(self):
        self.cancel()


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    from emtk.i18n import add_translations

    for locale, mapping in json.loads(Path(__file__).with_name("locales.json").read_text()).items():
        add_translations(locale, mapping)
    return PixelMleApp(**kwargs)
