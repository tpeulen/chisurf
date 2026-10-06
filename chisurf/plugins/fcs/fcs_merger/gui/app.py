"""Native FCS curve merger: the Qt WizardFcsMerger page's screening table, plots and save.

The controls are ``fcs_merger_emtk.view.json`` drawn by :func:`emtk.view_form.draw_form` over
:class:`_Form` (the :class:`.model.MergerModel`'s fields and table, this app's actions). Reading
a folder and writing the merge run on a worker; the individual curves and the merge are plotted
in their own dock windows, as the Qt page's FCS and FCS Merged plots.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .model import MergerModel, read_folder

HERE = Path(__file__).parent
PLUGIN = HERE.parent
ERROR = (230, 90, 90, 255)
UNUSED = (150, 150, 150, 255)
#: guide.json is shared with the Qt tour, which names the page's widgets by objectName.
TOUR_KEYS = {"lineEdit": "folder", "tableWidget": "curve_rows", "toolButton_3": "request_save"}


def _palette():
    """The Qt page's curve colours (ChiSurf's plot palette), as RGBA."""
    try:
        from chisurf.core import settings

        colours = [c["hex"].lstrip("#") for c in settings.colors]
    except Exception:  # noqa: BLE001 - a missing palette falls back to one colour
        colours = ["78DBE2"]
    return [tuple(int(h[i : i + 2], 16) for i in (0, 2, 4)) + (255,) for h in colours]


class _Form:
    """What the spec reads and writes: the model's fields and table, the app's actions."""

    def __init__(self, app):
        object.__setattr__(self, "_app", app)

    def __getattr__(self, name):
        return getattr(self._app.model, name)

    def __setattr__(self, name, value):
        setattr(self._app.model, name, value)

    @property
    def busy(self):
        return self._app.job.running

    def enabled(self, name):
        app, m = self._app, self._app.model
        if name in ("request_stop", "request_guide", "request_help"):
            return True
        if app.job.running:
            return False
        if name in ("request_save", "request_save_as", "request_add"):
            return bool(m.correlations)
        if name == "request_clear":
            return bool(m.correlations or m.folder)
        return True

    def folder_entered(self, value):
        self._app.load_folder(value)

    def request_open(self):
        self._app.choose("folder")

    def request_clear(self):
        self._app.clear()

    def request_save(self):
        self._app.save()

    def request_save_as(self):
        self._app.choose("save")

    def request_add(self):
        self._app.save(add=True)

    def request_stop(self):
        self._app.job.stop()

    def request_help(self):
        self._app.help.show()

    def request_guide(self):
        self._app.tour.start()


class MergerApp(ImApp):
    def __init__(self, add_dataset=None, model=None):
        self.model = model or MergerModel()
        self.add_dataset = add_dataset
        self.restored_selection = None
        self.job = BackgroundJob()
        self.dialog = None
        self.dialog_window = None
        self.dialog_mode = ""
        self.item_rects = {}
        self.palette = _palette()
        self.spec = json.loads((HERE / "fcs_merger_emtk.view.json").read_text(encoding="utf-8"))
        self.form_model = _Form(self)
        self.form = FormState(on_used=self._used)
        self.form.custom["status"] = self.draw_status
        self.help = EmTkHelpWindow(
            title="FCS curve merger — help",
            resource=PLUGIN / "help.md",
            owner=self,
            on_start_guide=lambda: self.tour.start(),
        )
        self.tour = EmTkGuidedTour(
            steps=PLUGIN / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(TOUR_KEYS.get(key, key)),
        )
        self.docks = DockManager(
            Split("h", 0.44, Region("files"), Split("v", 0.5, Region("curves"), Region("mean")))
        )
        self.docks.add_window(
            "files", "Curves and target", self.draw_files, dock="files", closable=False
        )
        self.docks.add_window("curves", "FCS", self.draw_curves, dock="curves", closable=False)
        self.docks.add_window("mean", "FCS Merged", self.draw_mean, dock="mean", closable=False)
        self.native_layouts = {"main": self.docks}
        super().__init__(gui=self.render, continuous=False)

    # -- the stream's API, kept for its tests and the host ------------------------------
    @property
    def correlations(self):
        return self.model.correlations

    @property
    def labels(self):
        return self.model.labels

    @property
    def use(self):
        return self.model.use

    @use.setter
    def use(self, values):
        self.model.use = list(values)
        self.model._rebuild()

    @property
    def selected(self):
        return self.model.selected

    @selected.setter
    def selected(self, index):
        self.model.selected = int(index)

    @property
    def output(self):
        return self.model.output

    @property
    def mean_correlation(self):
        return self.model.mean_correlation

    def set_correlations(self, correlations, source_folder=None, labels=None):
        self.model.set_correlations(correlations, source_folder, labels)

    # -- actions -----------------------------------------------------------------------
    def _used(self, name):
        # The folder step counts when a folder has loaded (load_folder's publish), not on a
        # typed path that may not exist.
        if name != "folder":
            self.tour.notify_used(next((k for k, v in TOUR_KEYS.items() if v == name), name))

    def _fail(self, message):
        self.model.error = message

    def load_folder(self, folder):
        """Read *folder* on the worker; its curves replace the list when it is done."""
        if self.job.running or not str(folder or "").strip():
            return False
        folder = str(folder)
        self.model.error, self.model.status = "", f"Reading {Path(folder).name}…"

        def publish(result):
            curves, paths, skipped = result
            self.model.set_correlations(curves, folder, paths)
            state, self.restored_selection = self.restored_selection, None
            if state is not None:
                if len(state.get("use", [])) == len(self.model.use):
                    self.use = list(state["use"])
                self.model.output = str(state.get("output") or self.model.output)
                self.model.selected = min(
                    int(state.get("selected", 0)), len(self.model.correlations) - 1
                )
            self.model.status = f"Loaded {len(curves)} curves." + (
                f" Skipped: {'; '.join(skipped)}" if skipped else ""
            )
            self.tour.notify_used("lineEdit")

        return self.job.start(
            lambda: read_folder(folder),
            publish,
            lambda exc: self._fail(f"Could not read {Path(folder).name}: {exc}"),
        )

    def save(self, filename=None, add=False):
        """Write the merge on the worker; with *add*, then add it to ChiSurf as an FCS dataset."""
        if self.job.running:
            return False
        if self.model.mean_correlation is None:
            self._fail("Load curves before saving a merge.")
            return False
        target = filename or self.model.output
        if not str(target or "").strip():
            self._fail("Set a target file first.")
            return False
        n = self.model.n_used()

        def publish(path):
            self.model.error, self.model.status = "", f"Saved the merge of {n} curves to {path}."
            if add:
                if self.add_dataset:
                    self.add_dataset(path)
                else:
                    from chisurf.core.actions import dispatch

                    dispatch(name="experiment.set", payload={"name": "FCS"})
                    dispatch(name="setup.select", payload={"name": "Seidel Kristine"})
                    dispatch(
                        name="dataset.add",
                        payload={"filename": str(path), "experiment_reader": None},
                    )
                self.model.status += " Added to ChiSurf."

        return self.job.start(
            lambda: self.model.save(target),
            publish,
            lambda exc: self._fail(f"Saving failed: {exc}"),
        )

    def choose(self, mode):
        title = "Correlation folder" if mode == "folder" else "Save merged correlation"
        self.dialog = FileDialog(
            title,
            mode=mode,
            filters="Correlation (*.cor);;All files (*)",
            filename=Path(self.model.output).name if mode == "save" and self.model.output else "",
        )
        self.dialog_window = DialogWindow(title, size=(720, 520))
        self.dialog_mode = mode

    def path_chosen(self, path):
        self.dialog = None
        if self.dialog_mode == "folder":
            self.model.folder = str(path)
            self.load_folder(path)
        else:
            self.model.output = str(path)
            self.save(path)

    def files_dropped(self, paths):
        """A dropped folder is read, as on the Qt page's folder field; a dropped file reads its folder."""
        if not paths or self.job.running:
            return False
        path = Path(str(paths[0]))
        folder = path if path.is_dir() else path.parent
        self.model.folder = str(folder)
        return self.load_folder(folder)

    def clear(self):
        self.job.stop()
        self.model.clear()

    def export_state(self):
        return self.model.export_state()

    def restore_state(self, state):
        self.model.folder = str(state.get("folder", ""))
        self.model.output = str(state.get("output", ""))
        self.restored_selection = dict(state)
        if self.model.folder and Path(self.model.folder).is_dir():
            self.load_folder(self.model.folder)
        else:
            if len(state.get("use", [])) == len(self.model.use):
                self.use = list(state["use"])
            self.restored_selection = None

    def animating(self):
        return self.job.running or super().animating()

    def close(self):
        self.job.close()
        self.dialog = None
        self.help.open = False
        self.tour.active = False

    # -- drawing -----------------------------------------------------------------------
    def draw_status(self, section, model, state, width):
        if self.model.error:
            im.push_style_color(im.Col.TEXT, ERROR)  # wrapped: a path does not fit a dock
            im.text_wrapped(self.model.error)
            im.pop_style_color()
        else:
            im.text_wrapped(self.model.status)
        m = self.model
        if m.correlations and not any(m.use):
            im.text_disabled(
                "No curve ticked: the merge averages all of them, as the Qt page does."
            )

    def draw_files(self, box):
        self.item_rects["files"] = tuple(box)
        self.form.rects.clear()
        draw_form(self.spec, self.form_model, self.form)
        self.item_rects.update(self.form.rects)

    def draw_curves(self, box):
        m = self.model
        if implot.begin_plot("FCS##individual", (-1, -1)):
            implot.setup_axes("Lag time (s)", "G(τ)")
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            for i, curve in enumerate(m.correlations):
                used = m.use[i]
                colour = self.palette[i % len(self.palette)] if used else UNUSED
                implot.set_next_line_style(
                    colour, 3.0 if used and i == m.selected else 1.0, None if used else (5.0, 4.0)
                )
                implot.plot_line(
                    f"{m.labels[i]}##{i}",
                    np.asarray(curve["x"], float),
                    np.asarray(curve["y"], float),
                )
            implot.end_plot()
        self.item_rects["curves"] = tuple(box)

    def draw_mean(self, box):
        mean = self.model.mean_correlation
        if implot.begin_plot("FCS Merged##merged", (-1, -1)):
            implot.setup_axes("Lag time (s)", "G(τ)")
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            if mean is not None:
                implot.plot_line(
                    f"Merge of {self.model.n_used()}",
                    np.asarray(mean["x"], float),
                    np.asarray(mean["y"], float),
                )
            implot.end_plot()
        self.item_rects["mean"] = tuple(box)

    def render(self):
        self.job.poll()
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        im.begin_disabled(self.dialog is not None)
        self.docks.draw(frame)
        im.end_disabled()
        if self.dialog is not None:
            pressed = self.dialog_window.begin(frame)
            result = self.dialog.draw()
            if result:
                self.path_chosen(str(result[0]))
            elif result is False or pressed == "close":
                self.dialog = None
            self.dialog_window.end()
        self.help.draw(frame)
        self.tour.draw(*vp.size)


def create_app(add_dataset=None):
    return MergerApp(add_dataset=add_dataset)
