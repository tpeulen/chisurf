"""Native blind IRF estimation: the Qt IRFEstimatorTool's toolbar, parameters, plot and results.

The form is ``irf_estimator_emtk.view.json`` drawn by :func:`emtk.view_form.draw_form` over
:class:`_Form` (the view model's fields, this app's actions). The estimate runs on a worker
thread; the plot and the results are their own dock windows, laid out as in the Qt tool
(parameters left, plot right, results under the plot).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import LabelColumn, labelled, layout_spec

from ..core.estimation import estimate_irf
from .view_model import IRFViewModel

HERE = Path(__file__).parent
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="irf-estimation")
ERROR = (230, 90, 90, 255)
DATA_FILTERS = "VV/VH Files (*.dat);;All Files (*)"
#: The Qt plot's pens, by curve: colour and dash.
PENS = {
    "Measured Decay": ((0, 110, 255, 255), None),
    "BG Corrected": ((0, 220, 220, 255), (6.0, 4.0)),
    "Estimated IRF (scaled)": ((0, 220, 0, 255), None),
    "IRF \u2297 Exp (Forward Model)": ((255, 165, 0, 255), (6.0, 4.0)),
}
#: guide.json is shared with the Qt tour, which names the toolbar actions by caption and
#: the spin boxes by objectName; the spec's names are mapped onto those.
TOUR_KEYS = {
    "request_load": "Load Decay",
    "request_estimate": "Estimate IRF",
    "manual_background": "irf_background",
    "rl_iterations": "irf_rl_iterations",
}
#: Fields whose change makes an existing IRF stale (auto-update re-estimates on them).
ESTIMATION_INPUTS = {
    "window_length",
    "polyorder",
    "rl_iterations",
    "regularization",
    "manual_background",
    "use_range_selection",
    "first_channel",
    "last_channel",
}


def open_datasets():
    """The decay curves open in this ChiSurf process; a group contributes each member."""
    import chisurf
    from chisurf.core.data import DataGroup

    curves = []

    def collect(dataset):
        if isinstance(dataset, (list, tuple, DataGroup)):
            for member in dataset:
                collect(member)
        elif (hasattr(dataset, "y") and hasattr(dataset, "x")) or hasattr(dataset, "data"):
            curves.append(dataset)

    for dataset in chisurf.imported_datasets:
        collect(dataset)
    return curves


def _spec():
    return json.loads((HERE / "irf_estimator_emtk.view.json").read_text(encoding="utf-8"))


class _Form:
    """What the spec reads and writes: the view model's fields and the app's actions."""

    def __init__(self, app):
        object.__setattr__(self, "_app", app)

    def __getattr__(self, name):
        return getattr(self._app.model, name)

    def __setattr__(self, name, value):
        app, m = self._app, self._app.model
        if name == "dt":
            app.guard(lambda: m.set_bin_width(value))
        elif name in ("first_channel", "last_channel"):
            bounds = list(m.range_bounds)
            bounds[name == "last_channel"] = float(value)
            m.range_bounds = sorted(bounds)
        else:
            setattr(m, name, value)
        if name in ESTIMATION_INPUTS:
            app.parameter_changed()

    @property
    def first_channel(self):
        return int(self._app.model.range_bounds[0])

    @property
    def last_channel(self):
        return int(self._app.model.range_bounds[1])

    def bounds(self, name):
        axis = self._app.model.channel_axis
        if name in ("first_channel", "last_channel") and axis is not None:
            return (0, len(axis) - 1)
        return None

    def enabled(self, name):
        """The Qt tool's control states: estimate needs data, save and transfer an IRF."""
        app, m = self._app, self._app.model
        if app.future is not None:
            return name in ("request_help", "request_guide")
        if name in ("request_estimate", "dt"):
            return m.decay_data_original is not None
        if name in ("request_save", "request_transfer"):
            return m.result is not None
        return True

    def request_load(self):
        self._app.choose_file()

    def request_dataset(self):
        self._app.refresh_datasets()

    def request_save(self):
        self._app.choose_file(save=True)

    def request_transfer(self):
        self._app.transfer()

    def request_estimate(self):
        self._app.start_estimate()

    def request_help(self):
        self._app.help_window.show()

    def request_guide(self):
        self._app.tour.start()


class IRFEstimatorApp(ImApp):
    def __init__(self, model=None, dataset_provider=None, dataset_sink=None):
        self.model = model or IRFViewModel()
        self.dataset_provider = dataset_provider or open_datasets
        self.dataset_sink = dataset_sink
        self.datasets = []
        self.dataset_index = 0
        self.show_datasets = False
        self.dialog = None
        self.file_window = None
        self.file_action = ""
        self.future = None
        self.rerun = False
        self.error = ""
        self.item_rects = {}
        self.pointer_text = ""
        self.spec = layout_spec(_spec())
        self.labels = LabelColumn()  # one caption column for the parameter fields
        self.form_model = _Form(self)
        self.form = FormState(on_used=self._used)
        self.form.custom["datasets"] = self.draw_datasets
        self.form.custom["status"] = self.draw_status
        self.help_window = EmTkHelpWindow(
            title="Blind IRF estimation — help",
            resource=HERE / "help.md",
            owner=self,
            on_start_guide=lambda: self.tour.start(),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda key: self.item_rects.get(key),
            owner=self,
            wait_for_controls=True,
        )
        self.docks = DockManager(
            Split(
                "h", 0.32, Region("settings"), Split("v", 0.72, Region("plot"), Region("results"))
            )
        )
        self.docks.add_window(
            "settings", "IRF Est Parameters", self.controls, dock="settings", closable=False
        )
        self.docks.add_window("plot", "Plots", self.plot, dock="plot", closable=False)
        self.docks.add_window(
            "results", "Est Results", self.results, dock="results", closable=False
        )
        self.native_layouts = {"main": self.docks}
        super().__init__(self.render, continuous=False)

    # -- actions -----------------------------------------------------------------------
    def guard(self, action):
        """Run *action*; a failure becomes the red error line instead of an exception."""
        try:
            result = action()
        except Exception as exc:  # noqa: BLE001 - every failure is shown to the user
            self.error = str(exc)
            return None
        self.error = ""
        return result

    def _used(self, name):
        # Loading counts when a decay has loaded (load_file, load_selected_dataset), not when
        # the dialog opens: a cancelled dialog has not done the step.
        if name != "request_load":
            self.tour.notify_used(TOUR_KEYS.get(name, name))

    def choose_file(self, save=False):
        title = "Save IRF" if save else "Load Decay File"
        self.dialog = FileDialog(
            title,
            mode="save" if save else "open",
            filename="estimated_irf.dat" if save else "",
            filters=DATA_FILTERS,
        )
        self.file_window = DialogWindow(title, size=(760, 540))
        self.file_action = "save" if save else "load"

    def file_chosen(self, path):
        if self.file_action == "save":
            self.guard(lambda: self.model.save(path))
        else:
            self.load_file(path)

    def load_file(self, path):
        if self.guard(lambda: self.model.load_file(path) or True):
            self.show_datasets = False
            self.tour.notify_used("Load Decay")
        else:
            self.model.source_text = f"Error: {self.error}"

    def refresh_datasets(self):
        self.datasets = list(self.dataset_provider())
        self.dataset_index = min(self.dataset_index, max(0, len(self.datasets) - 1))
        self.show_datasets = True
        self.error = (
            "" if self.datasets else "No datasets are open in ChiSurf; load a decay file instead."
        )

    def load_selected_dataset(self):
        if not self.datasets:
            self.error = "No dataset selected."
            return
        if self.guard(lambda: self.model.load_dataset(self.datasets[self.dataset_index]) or True):
            self.show_datasets = False
            self.tour.notify_used("Load Decay")

    def transfer(self):
        self.guard(lambda: self.model.transfer(self.dataset_sink))

    def files_dropped(self, paths):
        if paths and self.future is None:
            self.load_file(str(paths[0]))
            return True
        return False

    def start_estimate(self, quick=False):
        """Start the estimate on the worker; full RL iterations, or 50 for an auto-update."""
        m = self.model
        if m.decay_data_original is None:
            self.error = "Please load a decay file first."
            return False
        if self.future is not None:
            self.rerun = self.rerun or bool(quick)
            return False
        self.future = _EXECUTOR.submit(
            estimate_irf,
            m.decay_data_original.copy(),
            m.dt,
            m.settings(quick),
            m.channel_axis.copy(),
        )
        self.error = ""
        m.status = "Estimating IRF..."
        return True

    def parameter_changed(self):
        if self.model.auto_update_enabled and (
            self.model.result is not None or self.future is not None
        ):
            self.start_estimate(quick=True)

    def poll(self):
        if self.future is not None and self.future.done():
            future, self.future = self.future, None
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                self.error = str(exc)
                self.model.status = "IRF estimation failed"
            else:
                dt = self.model.dt
                result_dt, self.model.result = result.dt, result
                if result_dt != dt:  # the bin width changed while it ran
                    self.model.set_bin_width(dt)
                self.model.status = "IRF estimation completed"
            if self.rerun:
                self.rerun = False
                self.start_estimate(quick=True)

    def animating(self):
        return self.future is not None or super().animating()

    def close(self):
        """Drop a pending estimate (a running one finishes on the worker, unread) and the windows."""
        if self.future is not None:
            self.future.cancel()
            self.future = None
        self.rerun = False
        self.dialog = None
        self.help_window.open = False
        self.tour.active = False

    # -- windows -----------------------------------------------------------------------
    def controls(self, box):
        self.item_rects["controls"] = tuple(box)
        if not self.labels.ready:
            self.labels.measure([f["label"] for f in labelled(self.spec["sections"])])
            self.labels.pad(self.spec["sections"])
        self.form.rects.clear()
        draw_form(self.spec, self.form_model, self.form)
        self.item_rects.update(self.form.rects)
        for name, key in TOUR_KEYS.items():
            if name in self.form.rects:
                self.item_rects[key] = self.form.rects[name]

    def draw_datasets(self, section, model, state, width):
        if not self.show_datasets or not self.datasets:
            return
        names = [
            getattr(ds, "name", None) or f"Dataset {i + 1}" for i, ds in enumerate(self.datasets)
        ]
        im.set_next_item_width(max(80.0, width - 160.0))
        _, self.dataset_index = im.combo("Dataset##irf_dataset", self.dataset_index, names)
        im.set_item_tooltip(str(section.get("description")))
        state.rects["dataset"] = im.get_item_rect()
        im.same_line()
        if im.button("Load selected##irf_dataset_load"):
            self.load_selected_dataset()
        im.set_item_tooltip("Use the chosen curve's time axis and counts for the estimate.")
        state.rects["dataset_load"] = im.get_item_rect()

    def draw_status(self, section, model, state, width):
        im.separator()
        im.text_wrapped(self.model.status)
        if self.error:
            im.text_colored(ERROR, self.error)
        im.push_style_color(im.Col.TEXT, im.get_style().color(im.Col.TEXT_DISABLED))
        im.text_wrapped(self.model.time_axis_text())
        im.pop_style_color()

    def results(self, box):
        for label, text in self.model.result_rows():
            im.text(f"{label}:")
            im.same_line(150.0)
            im.text(text)
        if self.pointer_text:
            im.text_disabled(self.pointer_text)

    def plot(self, box):
        m = self.model
        if implot.begin_plot("IRF Estimation Results", size=(-1.0, -1.0)):
            implot.setup_axes("Time (ns)", "Intensity (counts/channel)")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            if m.decay_data_original is None:  # nothing loaded: sensible empty axes, not 1e-4 .. 1
                implot.setup_axes_limits(0.0, 1000.0, 1.0, 1000.0, cond=implot.COND_ONCE)
            for curve in m.plot_series():
                values = np.asarray(curve["y"], dtype=float)
                colour, dash = PENS.get(curve["name"].split(" (BG=")[0], (None, None))
                implot.set_next_line_style(colour, 2.0, dash)
                implot.plot_line(curve["name"], curve["x"], np.where(values > 0.0, values, np.nan))
            if m.use_range_selection and m.channel_axis is not None:
                lower, upper = [
                    int(np.clip(bound, 0, len(m.channel_axis) - 1)) for bound in m.range_bounds
                ]
                limits = implot.get_plot_limits()
                region = implot.drag_rect(
                    1,
                    float(m.channel_axis[lower]),
                    max(limits.y_min, 1e-12),
                    float(m.channel_axis[upper]),
                    max(limits.y_max, 1e-12),
                    col=(70, 200, 90, 180),
                    flags=implot.DRAG_TOOL_FLAGS_NO_FIT,
                )
                if region.modified:
                    m.range_bounds = sorted(
                        float(np.argmin(np.abs(m.channel_axis - value)))
                        for value in (region.x_min, region.x_max)
                    )
                    self.parameter_changed()
            if implot.is_plot_hovered() and m.channel_axis is not None:
                mouse = implot.get_plot_mouse_pos()
                index = int(np.argmin(np.abs(m.channel_axis - mouse.x)))
                self.pointer_text = (
                    f"Time: {m.channel_axis[index]:.2f} ns, Intensity: {m.decay_data[index]:.1f}"
                )
                pos, size = implot.get_plot_pos(), implot.get_plot_size()
                pixel = implot.plot_to_pixels(mouse.x, mouse.y)
                draw = implot.get_plot_draw_list()
                draw.add_line(
                    (pixel[0], pos[1]), (pixel[0], pos[1] + size[1]), (180, 180, 180, 180)
                )
                draw.add_line(
                    (pos[0], pixel[1]), (pos[0] + size[0], pixel[1]), (180, 180, 180, 180)
                )
                im.set_tooltip(self.pointer_text)
            implot.end_plot()
        self.item_rects["plot"] = tuple(box)

    def render(self):
        self.poll()
        viewport = im.get_main_viewport()
        box = (*viewport.pos, *viewport.size)
        im.begin_disabled(self.dialog is not None)
        self.docks.draw(box)
        im.end_disabled()
        if self.dialog is not None:
            pressed = self.file_window.begin(box)
            result = self.dialog.draw()
            if result:
                self.dialog = None
                self.file_chosen(str(result[0]))
            elif result is False or pressed == "close":
                self.dialog = None
            self.file_window.end()
        self.help_window.draw(box)
        self.tour.draw(*viewport.size)


def make_app():
    return IRFEstimatorApp()
