"""Native emtk VV/VH anisotropy calculator.

The parameter form and the batch window are the view spec ``vv_vh_emtk.view.json``
drawn by :func:`emtk.view_form.draw_sections`; the batch queue and its results are its
``data_table`` sections. Only the two plots, the file dialogs, Help and Guide are drawn
here. All state and work is in :class:`~.model.AnisotropyModel`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from .model import AnisotropyModel
from .strings import tr

HERE = Path(__file__).parent
#: Series colours carry data (the Qt plot's blue VV, red VH, magenta r(t)).
VV_COLOUR = (70, 130, 255, 255)
VH_COLOUR = (255, 80, 80, 255)
R_COLOUR = (230, 70, 230, 255)
REGION_COLOUR = (60, 205, 100, 255)
R_LIMITS = (0.0, 0.45)
#: Height of the parameter form at its widest (the wide layout), in pixels.
CONTROLS_HEIGHT = 330.0
DATA_FILTERS = "VV/VH data (*.dat *.txt);;All files (*)"
RESULT_FILTERS = "Results (*.dat *.txt *.csv);;All files (*)"


def _translated(node: Any) -> Any:
    """The spec with its labels, titles, texts and descriptions through :func:`tr`."""
    if isinstance(node, dict):
        return {
            key: (
                tr(value)
                if key in ("label", "title", "text", "description", "tooltip")
                and isinstance(value, str)
                else _translated(value)
            )
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_translated(item) for item in node]
    return node


class AnisotropyApp(ImApp):
    """VV/VH anisotropy decay r(t), r-infinity and a batch of files."""

    def __init__(self, model: AnisotropyModel | None = None) -> None:
        self.model = model or AnisotropyModel()
        spec = _translated(json.loads((HERE / "vv_vh_emtk.view.json").read_text(encoding="utf-8")))
        self.panels = {panel["name"]: panel for panel in spec["sections"]}
        self.form = FormState()
        self.item_rects: dict[str, tuple] = {}
        self.dialog: FileDialog | None = None
        self.dialog_request = ""
        self.file_window = DialogWindow(tr("Choose files"), size=(760.0, 520.0), key="vv-vh-file")
        self.batch_window = DialogWindow(
            tr("VV/VH Anisotropy Batch Processor"), size=(880.0, 560.0), key="vv-vh-batch"
        )
        self.picker = DatasetPicker(formats=None, on_paths=self.add_batch_paths)
        self._plot_signature = None
        self.help_window = EmTkHelpWindow(
            title="VV/VH Anisotropy Decay — Help",
            resource=HERE / "help.md",
            owner=self,
            size=(700.0, 560.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(
            Split(
                "v",
                0.34,
                Region("controls"),
                Split("h", 0.5, Region("decays"), Region("anisotropy")),
            )
        )
        self.docks.add_window(
            "controls", tr("VV/VH anisotropy"), self.draw_controls, dock="controls", closable=False
        )
        self.docks.add_window(
            "decays", tr("Decays (VV, VH)"), self.draw_decays, dock="decays", closable=False
        )
        self.docks.add_window(
            "anisotropy",
            tr("Anisotropy r(t)"),
            self.draw_anisotropy,
            dock="anisotropy",
            closable=False,
        )
        super().__init__(gui=self.render, continuous=True)

    # -- actions the window takes for the model --------------------------------
    def action(self, operation) -> bool:
        """Run *operation*; a failure becomes the status line instead of an exception."""
        try:
            operation()
            return True
        except Exception as exc:  # noqa: BLE001 - shown to the user
            if not self.model.message.startswith("Could not"):
                self.model.message = f"{type(exc).__name__}: {exc}"
            return False

    def load_file(self, path) -> bool:
        return self.action(lambda: self.model.load(path))

    def add_batch_paths(self, paths) -> int:
        return self.model.add_batch_paths([str(p) for p in paths or []])

    def files_dropped(self, paths: Any) -> bool:
        """Host hook (native, web and Qt hosts): files go to the batch queue while its window is
        open, otherwise the first one is loaded."""
        paths = [str(p) for p in paths or []]
        if not paths:
            return False
        if self.model.batch_open:
            return self.add_batch_paths(paths) > 0
        return self.load_file(paths[0])

    on_files_dropped = files_dropped
    on_paths_dropped = files_dropped

    # -- windows ----------------------------------------------------------------
    def draw_controls(self, box: Any) -> None:
        """The top window: the parameter form, then Help and Guide."""
        draw_sections(self.panels["controls"]["sections"], self.model, self.form)
        if im.button(tr("Guide")):
            self.tour.start()
        im.set_item_tooltip(tr("A step-by-step walk through the tool."))
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if im.button(tr("Help")):
            self.help_window.show()
        im.set_item_tooltip(tr("The short help page."))
        self.item_rects["help"] = im.get_item_rect()

    def draw_decays(self, box: Any) -> None:
        model = self.model
        if implot.begin_plot("##vvvh_decays", (-1, -1)):
            implot.setup_axes(tr("Channel"), tr("Intensity"))
            vv, vh = model.corrected_channels()
            if vv is not None:
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
                implot.setup_legend()
                apply_bg = model.apply_bg
                implot.set_next_line_style(VV_COLOUR, 2.0)
                implot.plot_line(
                    "VV (BG corrected)" if apply_bg else "VV",
                    model.time_axis,
                    np.where(vv > 0, vv, np.nan),
                )
                implot.set_next_line_style(VH_COLOUR, 2.0)
                implot.plot_line(
                    f"VH (shift {model.shift:.3f} ch, BG corrected)"
                    if apply_bg
                    else f"VH (shift {model.shift:.3f} ch)",
                    model.time_axis + model.shift,
                    np.where(vh > 0, vh, np.nan),
                )
            else:
                implot.plot_dummy(tr("Load a VV/VH file"))
            implot.end_plot()
        im.set_item_tooltip(
            tr("Background-corrected VV and shifted VH on a logarithmic intensity scale.")
        )
        self.item_rects["decays"] = im.get_item_rect()

    def draw_anisotropy(self, box: Any) -> None:
        model = self.model
        if implot.begin_plot("##anisotropy", (-1, -1)):
            implot.setup_axes(tr("Channel"), "r(t)")
            if model.r_t is not None:
                signature = id(model.time_axis)
                implot.setup_axis_limits(implot.AXIS_Y1, *R_LIMITS, cond=implot.COND_ALWAYS)
                implot.setup_axis_limits(
                    implot.AXIS_X1,
                    0.0,
                    max(1.0, len(model.r_t) - 1.0),
                    cond=implot.COND_ALWAYS
                    if signature != self._plot_signature
                    else implot.COND_ONCE,
                )
                self._plot_signature = signature
                implot.setup_legend()
                implot.set_next_line_style(R_COLOUR, 2.0)
                implot.plot_line("r(t)", model.time_axis, model.r_t)
                implot.set_next_fill_style(REGION_COLOUR, 0.2)
                implot.plot_shaded(
                    "##region",
                    np.array([model.region_min, model.region_max]),
                    np.array([R_LIMITS[1]] * 2),
                    np.array([R_LIMITS[0]] * 2),
                )
                for index in range(2):
                    result = implot.drag_line_x(
                        200 + index, model.region_bounds[index], col=REGION_COLOUR
                    )
                    if result.modified:
                        model.region_bounds[index] = float(result.value)
                        model.compute()
                    # where the line is on screen: what a person (or a test) grabs
                    lx, ly = implot.plot_to_pixels(model.region_bounds[index], 0.5 * sum(R_LIMITS))
                    self.item_rects[f"region_line_{index}"] = (lx - 3.0, ly - 3.0, 6.0, 6.0)
            else:
                implot.plot_dummy(tr("Load a VV/VH file"))
            implot.end_plot()
        im.set_item_tooltip(tr("Drag the green lines to choose the r∞ region."))
        self.item_rects["anisotropy"] = im.get_item_rect()

    # -- one frame --------------------------------------------------------------
    def render(self) -> None:
        viewport = im.get_main_viewport()
        box = (*viewport.pos, *viewport.size)
        self.form.rects.clear()
        if self.model.forget_selection:
            # the table keeps its selection by row key: a removed file that is queued again
            # would otherwise come back highlighted while the model has nothing selected
            self.form.tables.pop("batch_file_rows", None)
            self.model.forget_selection = False
        # The form needs about CONTROLS_HEIGHT pixels; a small window gives it a larger share.
        self.docks.layout.ratio = min(
            0.6, max(0.3, CONTROLS_HEIGHT / max(float(viewport.size[1]), 1.0))
        )
        self.docks.draw(box)
        self._requests()
        self._draw_batch(box)
        self._draw_file_dialog(box)
        self.picker.render(box)
        self.help_window.draw(box)
        self.tour.draw(*viewport.size)

    def _requests(self) -> None:
        """Act on the model's ``request``: open the file dialog or the database picker."""
        request, self.model.request = self.model.request, ""
        if not request or self.dialog is not None:
            return
        if request == "database":
            self.picker.open()
            return
        if request == "save" and not self.model.has_data:
            self.model.message = "Load a VV/VH file before saving outputs."
            return
        if request == "save_batch" and not self.model.has_batch_results:
            self.model.message = "Run batch before saving CSV."
            return
        titles = {
            "load": "Load VV/VH file",
            "save": "Save outputs",
            "add_files": "Add VV/VH files",
            "add_folder": "Add a folder of VV/VH files",
            "save_batch": "Save batch CSV",
        }
        if request not in titles:
            return
        mode = {"save": "save", "save_batch": "save", "add_folder": "folder"}.get(request, "open")
        self.dialog_request = request
        self.dialog = FileDialog(
            tr(titles[request]),
            mode=mode,
            multiselect=request == "add_files",
            filters=DATA_FILTERS if mode == "open" else RESULT_FILTERS,
        )
        self.file_window = DialogWindow(tr(titles[request]), size=(760.0, 520.0), key="vv-vh-file")

    def _draw_file_dialog(self, box: Any) -> None:
        if self.dialog is None:
            return
        pressed = self.file_window.begin(box)
        result = self.dialog.draw()
        self.file_window.end()
        if result:
            request, self.dialog = self.dialog_request, None
            paths = [str(p) for p in result]
            model = self.model
            if request == "load":
                self.load_file(paths[0])
            elif request == "save":
                self.action(lambda: model.save(paths[0]))
            elif request in ("add_files", "add_folder"):
                self.add_batch_paths(paths)
            elif request == "save_batch":
                self.action(lambda: model.save_batch(paths[0]))
        elif result is False or pressed == "close":
            self.dialog = None

    def _draw_batch(self, box: Any) -> None:
        """The batch window, drawn over the tool while ``model.batch_open``."""
        if not self.model.batch_open:
            self.batch_window.hide()
            return
        self.batch_window.show()
        im.begin_disabled(self.dialog is not None)
        pressed = self.batch_window.begin(box)
        draw_sections(self.panels["batch"]["sections"], self.model, self.form, titles=False)
        self.batch_window.end()
        im.end_disabled()
        if pressed == "close":
            self.model.close_batch()

    # -- persistence ------------------------------------------------------------
    def export_settings(self) -> dict:
        """The settings, the region, the loaded file and the batch queue."""
        return self.model.export_settings()

    def restore_settings(self, state: dict) -> None:
        """Restore :meth:`export_settings`; an unreadable file is reported on the status line."""
        self.action(lambda: self.model.restore_settings(state))
        self.form.buffers.clear()

    def close(self) -> None:
        self.picker.close()


def create_app() -> AnisotropyApp:
    """Build the app (the manifest's ``entrypoints.emtk``)."""
    return AnisotropyApp()
