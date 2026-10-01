"""Standalone EMTK VV/VH anisotropy calculator."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from .model import AnisotropyModel
from .strings import tr


class AnisotropyApp(ImApp):
    def __init__(self):
        self.model = AnisotropyModel()
        self.dialog = None
        self.dialog_callback = None
        self.batch_open = False
        self.docks = DockManager(Split("v", .22, Region("controls"),
                                        Split("h", .5, Region("decays"), Region("anisotropy"))))
        self.docks.add_window("controls", tr("VV/VH anisotropy"), self.draw_controls,
                              dock="controls", closable=False)
        self.docks.add_window("decays", tr("Decays (VV, VH)"), self.draw_decays,
                              dock="decays", closable=False)
        self.docks.add_window("anisotropy", tr("Anisotropy r(t)"), self.draw_anisotropy,
                              dock="anisotropy", closable=False)
        super().__init__(gui=self.render, continuous=True)

    def button(self, label, tooltip, callback):
        if im.button(tr(label)):
            callback()
        im.set_item_tooltip(tr(tooltip))

    def numeric(self, key, value, tooltip, minimum=None, maximum=None):
        im.text(tr(key) + ":")
        im.set_next_item_width(-1)
        changed, result = im.input_float("##" + key, float(value), step=0)
        im.set_item_tooltip(tr(tooltip))
        if changed:
            result = max(minimum, result) if minimum is not None else result
            result = min(maximum, result) if maximum is not None else result
        return changed, result

    def inline_numeric(self, key, value, tooltip, minimum=None, maximum=None):
        im.text(tr(key) + ":")
        im.same_line()
        im.set_next_item_width(95)
        changed, result = im.input_float("##" + key, float(value), step=0)
        im.set_item_tooltip(tr(tooltip))
        if changed:
            result = max(minimum, result) if minimum is not None else result
            result = min(maximum, result) if maximum is not None else result
        return changed, result

    def choose(self, title, callback, *, mode="open", multiple=False):
        self.dialog = FileDialog(tr(title), mode=mode, multiselect=multiple,
                                 filters="VV/VH data (*.dat *.txt);;All files (*)" if mode == "open"
                                         else "Results (*.dat *.txt *.csv);;All files (*)")
        self.dialog_callback = callback

    def action(self, operation):
        try:
            operation()
        except Exception as exc:
            self.model.message = f"{type(exc).__name__}: {exc}"

    def draw_controls(self, box):
        model = self.model
        im.text_wrapped("⛔ " + tr("VV/VH Anisotropy Decay is deprecated/obsolete. Use the VV/VH G-Factor plugin and reader-integrated anisotropy workflow instead."))
        self.button("Load VV/VH file…", "Load a paired parallel/perpendicular decay.",
                    lambda: self.choose("Load VV/VH file…", lambda paths: self.action(lambda: model.load(paths[0]))))
        im.same_line()
        self.button("Save outputs…", "Save shifted VV/VH, anisotropy trace and r∞ metadata.",
                    lambda: self.choose("Save outputs…", lambda paths: self.action(lambda: model.save(paths[0])), mode="save"))
        im.same_line()
        self.button("Batch files", "Queue VV/VH decays for the same current settings.",
                    lambda: setattr(self, "batch_open", True))
        im.same_line()
        im.text(Path(model.loaded_file).name if model.loaded_file else tr("No file loaded"))
        im.set_item_tooltip(model.loaded_file or tr("No file loaded"))
        changed = False
        for index, (attr, label, tooltip, minimum, maximum) in enumerate((
            ("g_factor", "G-factor", "Detector sensitivity correction applied to VH.", 0, 10),
            ("bg_vv", "BG VV", "Constant background to subtract from VV.", -1e9, 1e9),
            ("bg_vh", "BG VH", "Constant background to subtract from VH.", -1e9, 1e9),
            ("shift", "Shift VH (channels)", "Shift VH by a fractional channel using interpolation.", -150, 150),
            ("region_start", "Region start", "First channel in the r∞ averaging region.", None, None),
            ("region_end", "Region end", "Last boundary of the r∞ averaging region.", None, None),
        )):
            narrow = im.get_main_viewport().size[0] < 900
            if index not in ((0, 3, 5) if narrow else (0, 3)):
                im.same_line()
            value = model.region_bounds[0 if attr == "region_start" else 1] if attr.startswith("region_") else getattr(model, attr)
            edit, value = self.inline_numeric(label, value, tooltip, minimum, maximum)
            if edit:
                if attr.startswith("region_"):
                    model.region_bounds[0 if attr == "region_start" else 1] = value
                else:
                    setattr(model, attr, value)
                changed = True
        for attr, label, tooltip in (
            ("apply_bg", "Apply backgrounds", "Subtract constant VV and VH backgrounds before calculation."),
            ("flip", "Flip VV↔VH", "Swap channels when the source file has reversed polarization."),
        ):
            if attr == "flip":
                im.same_line()
            edit, value = im.checkbox(tr(label), getattr(model, attr))
            im.set_item_tooltip(tr(tooltip))
            if edit:
                setattr(model, attr, value)
                changed = True
        if changed:
            model.compute()
        im.same_line()
        im.text(f"r∞: {model.r_infty:.5f}" if np.isfinite(model.r_infty) else "r∞: N/A")
        im.text_wrapped(model.message)

    def draw_batch(self):
        model = self.model
        if not im.begin(tr("Batch files")):
            im.end()
            return
        self.button("Close batch", "Close the batch panel and retain its queued files and results.",
                    lambda: setattr(self, "batch_open", False))
        im.text(tr("Batch files"))
        self.button("Add batch files…", "Queue VV/VH decays for the same current settings.",
                    lambda: self.choose("Add batch files…", lambda paths: model.batch_files.extend(
                        str(path) for path in paths if str(path) not in model.batch_files), multiple=True))
        for index, path in enumerate(model.batch_files):
            im.text(f"{index + 1}. {Path(path).name}")
            im.set_item_tooltip(path)
        self.button("Run batch", "Compute r∞ for each queued VV/VH file.",
                    lambda: self.action(model.run_batch))
        im.same_line()
        self.button("Save batch CSV…", "Export filenames, r∞, settings and per-file errors.",
                    lambda: self.choose("Save batch CSV…", lambda paths: self.action(
                        lambda: model.save_batch(paths[0])), mode="save"))
        for row in model.batch_results:
            im.text_wrapped(f"{row[0]}: r∞={row[1]:.5f}" if np.isfinite(row[1]) else f"{row[0]}: {row[-1]}")
        im.end()

    def draw_decays(self, box):
        if implot.begin_plot("##vvvh_decays", (-1, -1)):
            implot.setup_axes(tr("Channel"), tr("Intensity"))
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            model = self.model
            vv, vh = model.corrected_channels()
            if vv is not None:
                implot.plot_line("VV", model.time_axis, np.where(vv > 0, vv, np.nan))
                implot.plot_line("VH", model.time_axis + model.shift,
                                 np.where(vh > 0, vh, np.nan))
            implot.end_plot()
        im.set_item_tooltip(tr("Background-corrected VV and shifted VH on a logarithmic intensity scale."))

    def draw_anisotropy(self, box):
        if implot.begin_plot("##anisotropy", (-1, -1)):
            implot.setup_axes(tr("Channel"), "r(t)")
            model = self.model
            if model.r_t is not None:
                implot.setup_axes_limits(0, max(1, len(model.r_t)-1), 0, .45,
                                         cond=implot.COND_ALWAYS)
                implot.plot_line("r(t)", model.time_axis, model.r_t)
                for index, bound in enumerate(model.region_bounds):
                    result = implot.drag_line_x(200 + index, bound, col=(60, 205, 100, 255))
                    if result.modified:
                        model.region_bounds[index] = result.value
                        model.compute()
            implot.end_plot()
        im.set_item_tooltip(tr("Drag the green lines to choose the r∞ region."))

    def render(self):
        viewport = im.get_main_viewport()
        frame = (0.0, 0.0, *viewport.size)
        self.docks.layout.ratio = .30 if viewport.size[0] < 900 else .19
        self.docks.draw(frame)
        if self.batch_open:
            self.draw_batch()
        if self.dialog:
            if im.begin("VV/VH file chooser"):
                result = self.dialog.draw()
                if result:
                    callback = self.dialog_callback
                    self.dialog = None
                    callback(result)
                elif result is False:
                    self.dialog = None
            im.end()

    def on_paths_dropped(self, paths):
        if paths:
            self.action(lambda: self.model.load(paths[0]))

    def export_settings(self):
        return self.model.export_settings()

    def restore_settings(self, state):
        self.action(lambda: self.model.restore_settings(state))


def create_app():
    return AnisotropyApp()
