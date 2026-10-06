"""Native ALEX Creator: convert ALEX macro-time modulation into micro-time, single, batch or merged.

The left window is the Qt tool's controls as a spec form (``alex_emtk.view.json``, drawn by ``emtk.view_form`` with
this app as the model): the file row, the input / output formats, the Period and Shift spin fields, and the batch
queue (a ``data_table``) with its output folder. The right window is the live ALEX micro-time histogram. Loading,
the preview, saving and the batch run are workers (one at a time) published on the UI thread; the conversion itself
is the plugin's Qt-free :mod:`core` / :mod:`api`, shared with the Qt tool, the CLI and the RPC backend.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.file_dialog import FileDialog
from emtk.i18n import get_locale, tr
from emtk.view_form import FormState, draw_form

from chisurf.core.settings.path_utils import get_path
from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.emtk.i18n import install
from chisurf.plugins.emtk_layout import LabelColumn, button_row, labelled, layout_spec
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .. import core
from ..api import AlexRequest, run
from .translations import HELP, install_translations
from .view_model import AlexViewModel

HERE = Path(__file__).parent
EXTENSIONS = {".sm", ".ptu", ".ht3", ".spc", ".hdf", ".h5", ".raw"}
FILTERS = "TTTR (*.sm *.ptu *.ht3 *.spc *.hdf *.h5 *.raw);;All files (*)"
#: The model attributes kept between sessions (the Qt tool kept only its window geometry).
FIELDS = (
    "input_format",
    "output_format",
    "alex_period",
    "period_shift",
    "input_file",
    "batch_files",
    "batch_mode",
    "batch_output_folder",
)
PERIOD_LIMITS = (1, 1000000)
SHIFT_LIMITS = (-1000000, 1000000)
ERROR_COLOUR = (235, 100, 90, 255)
#: The histogram's line (data colour; the Qt plot drew the same blue).
HISTOGRAM_COLOUR = (68, 136, 255, 255)

#: Spec keys whose text is shown to the user (translated when the spec is loaded, again when the locale changes).
_TEXT_KEYS = ("title", "label", "description", "tooltip", "hint")


def translated(node):
    """A copy of a spec with every text a user reads put through ``tr`` (labels, titles, tooltips, columns, buttons)."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in _TEXT_KEYS and isinstance(value, str):
                out[key] = tr(value) if value else value
            elif key == "labels" and isinstance(value, list):
                out[key] = [tr(v) for v in value]
            else:
                out[key] = translated(value)
        return out
    if isinstance(node, list):
        return [translated(item) for item in node]
    return node


class AlexApp(TourTarget, ImApp):
    """The ALEX Creator window; also the model its spec form reads and writes."""

    def __init__(self, state_path=None):
        install()
        install_translations()
        self.model = AlexViewModel()
        self.job = BackgroundJob()  # load, save, batch: the form is greyed while one runs
        self.preview_job = (
            BackgroundJob()
        )  # the live histogram: edits stay possible while it recomputes
        self.histogram = []
        self.preview_signature = None
        self.loaded_path = ""
        self.message = ""
        self.message_is_error = False
        self.outputs = []
        self.selected_path = ""
        self.dialog = self.dialog_callback = None
        self.item_rects = {}
        self.file_window = DialogWindow("ALEX file chooser", size=(600.0, 420.0), key="alex_files")
        self.dataset_picker = DatasetPicker(on_paths=self.add_paths)
        self.state_path = (
            Path(state_path) if state_path else get_path("settings") / "alex-emtk.json"
        )
        self.form = FormState(on_used=self.used)
        self.spec_source = json.loads((HERE / "alex_emtk.view.json").read_text(encoding="utf-8"))
        self.spec, self.spec_locale = None, None
        self.help = EmTkHelpWindow(
            title=tr("ALEX Creator"),
            resource=HERE / "help.md",
            on_start_guide=self.start_guide,
        )
        self.guide = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda key: self.item_rects.get(key),
            owner=self,
            wait_for_controls=True,
        )
        self.guide_steps = list(self.guide.steps)
        try:
            self.set_state(json.loads(self.state_path.read_text()))
        except (OSError, ValueError, TypeError):
            pass
        super().__init__(gui=self.render, continuous=False)

    # -- the form's model: the Qt view model's fields -------------------------------------------------------- #
    def _field(name):  # noqa: N805 - a descriptor factory used in the class body
        return property(
            lambda self: getattr(self.model, name),
            lambda self, value: setattr(self.model, name, value),
        )

    input_file = _field("input_file")
    input_format = _field("input_format")
    output_format = _field("output_format")
    alex_period = _field("alex_period")
    period_shift = _field("period_shift")
    batch_mode = _field("batch_mode")
    batch_output_folder = _field("batch_output_folder")
    del _field

    def input_format_options(self):
        return self.model.input_format_options()

    def output_format_options(self):
        return self.model.output_format_options()

    def enabled(self, name):
        """Whether the control *name* can be used now (a grey button says what is missing)."""
        if self.job.running:
            return False
        if name == "load_input":
            return bool(str(self.model.input_file).strip())
        if name == "choose_save":
            return self.model.has_data
        if name == "remove_selected":
            return self.selected_path in self.model.batch_files
        if name == "clear_queue":
            return bool(self.model.batch_files)
        return True

    def bounds(self, name):
        return {"alex_period": PERIOD_LIMITS, "period_shift": SHIFT_LIMITS}.get(name, (None, None))

    # -- persistence ------------------------------------------------------------------------------------------ #
    def get_state(self):
        return {"version": 2, "settings": {key: getattr(self.model, key) for key in FIELDS}}

    export_settings = get_state

    def set_state(self, state):
        values = state.get("settings", {}) if isinstance(state, dict) else {}
        for key in FIELDS:
            if key in values:
                setattr(self.model, key, values[key])
        m = self.model
        try:
            m.alex_period = max(PERIOD_LIMITS[0], min(PERIOD_LIMITS[1], int(m.alex_period)))
            m.period_shift = max(SHIFT_LIMITS[0], min(SHIFT_LIMITS[1], int(m.period_shift)))
        except (TypeError, ValueError):
            m.alex_period, m.period_shift = 8000, 0
        if m.input_format not in m.input_format_options():
            m.input_format = "Auto"
        if m.output_format not in m.output_format_options():
            m.output_format = "PTU"
        if m.batch_mode not in {"convert", "merge"}:
            m.batch_mode = "convert"
        m.input_file = str(m.input_file or "")
        m.batch_output_folder = str(m.batch_output_folder or "")
        m.batch_files = [str(p) for p in m.batch_files] if isinstance(m.batch_files, list) else []

    restore_settings = set_state

    def close(self):
        self.job.close()
        self.preview_job.close()
        self.dataset_picker.close()
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(self.get_state(), indent=2))
        except OSError:
            pass

    # -- messages --------------------------------------------------------------------------------------------- #
    def error(self, exc):
        self.message, self.message_is_error = str(exc), True

    def notice(self, text):
        self.message, self.message_is_error = text, False

    def used(self, name):
        """A field was committed or an action pressed: the tour is told, a committed path loads (Qt: editingFinished)."""
        self.guide.notify_used("timing" if name in ("alex_period", "period_shift") else name)
        if name == "input_file":
            path = str(self.model.input_file).strip()
            if path and path != self.loaded_path:
                self.load(path)

    # -- the work ----------------------------------------------------------------------------------------------- #
    def signature(self):
        m = self.model
        return (m.input_file, m.input_format, int(m.alex_period), int(m.period_shift))

    def load(self, path):
        if self.job.running:
            return False
        path = str(path)
        if not Path(path).is_file():
            self.error(ValueError(tr("Please choose an existing TTTR file.") + f" ({path})"))
            return False
        m = self.model
        kind = core.resolve_filetype(m.input_format, path)
        period, shift = int(m.alex_period), int(m.period_shift)
        signature = (path, m.input_format, period, shift)

        def work():
            return core.load(path, kind), core.alex_histogram(path, period, shift, kind)

        def publish(data):
            self.model.set_tttr(data[0], path)
            self.loaded_path = path
            self.histogram = data[1]
            self.preview_signature = signature
            self.notice(tr("Loaded") + ": " + Path(path).name)

        self.notice(tr("Loading…"))
        return self.job.start(work, publish, self.error)

    def preview(self):
        """Fold the loaded file again for the current period and shift (a worker of its own: the form stays usable)."""
        if not self.model.has_data or self.preview_job.running:
            return False
        signature = self.signature()
        path, fmt, period, shift = signature

        def publish(hist):
            if path == self.loaded_path:  # the file may have been replaced while this was folding
                self.histogram = hist
                self.preview_signature = signature

        # Mark a failed signature too, avoiding a failing read on every frame.
        self.preview_signature = signature
        return self.preview_job.start(
            lambda: core.alex_histogram(path, period, shift, core.resolve_filetype(fmt, path)),
            publish,
            self.error,
        )

    @property
    def running(self):
        """Whether a worker (the load / save / batch job or the preview) is running."""
        return self.job.running or self.preview_job.running

    def save(self, path):
        if self.job.running:
            return False
        reason = self.model.can_save()
        if reason:
            self.error(ValueError(tr(reason)))
            return False
        m = self.model
        args = (
            m.input_file,
            str(path),
            int(m.alex_period),
            int(m.period_shift),
            m.output_format,
            m.input_format,
        )
        if Path(args[0]).resolve() == Path(args[1]).resolve():
            self.error(ValueError(tr("Choose a different output file to preserve the source.")))
            return False
        return self.job.start(lambda: core.convert_file(*args), self.completed, self.error)

    def completed(self, paths):
        self.outputs = [str(p) for p in paths] if isinstance(paths, (list, tuple)) else [str(paths)]
        self.notice(tr("Written files") + ": " + "\n".join(self.outputs))

    def run_batch(self):
        if self.job.running:
            return False
        reason = self.model.can_run_batch()
        if reason:
            self.error(ValueError(tr(reason)))
            return False
        m = self.model
        request = AlexRequest(
            files=list(m.batch_files),
            alex_period=int(m.alex_period),
            period_shift=int(m.period_shift),
            input_format=m.input_format,
            output_format=m.output_format,
            mode=m.batch_mode,
            output_dir=m.batch_output_folder.strip(),
        )
        return self.job.start(lambda: run(request).output_paths, self.completed, self.error)

    # -- the queue ---------------------------------------------------------------------------------------------- #
    def add_paths(self, paths):
        expanded = []
        for value in paths:
            path = Path(value)
            if path.is_dir():
                expanded.extend(
                    str(p)
                    for p in sorted(path.rglob("*"))
                    if p.is_file() and p.suffix.lower() in EXTENSIONS
                )
            elif path.is_file() and path.suffix.lower() in EXTENSIONS:
                expanded.append(str(path))
        self.model.add_batch_files(expanded)

    def queue_rows(self):
        """The ``data_table`` source: one record per queued file."""
        return [
            {"file": Path(p).name, "folder": str(Path(p).parent), "path": p}
            for p in self.model.batch_files
        ]

    def select_row(self, record):
        self.selected_path = str(record.get("path", "")) if isinstance(record, dict) else ""

    def remove_row(self, record):
        path = str(record.get("path", "")) if isinstance(record, dict) else ""
        if path in self.model.batch_files and not self.job.running:
            self.model.batch_files.remove(path)
            if self.selected_path == path:
                self.selected_path = ""

    def remove_selected(self):
        self.remove_row({"path": self.selected_path})

    def clear_queue(self):
        self.model.clear_batch()
        self.selected_path = ""

    # -- the form's actions ------------------------------------------------------------------------------------ #
    def choose_input(self):
        self.choose(lambda picked: self.load(picked[0]))

    def load_input(self):
        self.load(str(self.model.input_file).strip())

    def choose_save(self):
        self.choose(lambda picked: self.save(picked[0]), "save")

    def choose_files(self):
        self.choose(self.add_paths, multiple=True)

    def choose_folder(self):
        self.choose(self.add_paths, mode="folder")

    def choose_database(self):
        self.dataset_picker.open()

    def choose_output(self):
        self.choose(
            lambda picked: setattr(self.model, "batch_output_folder", str(picked[0])), mode="folder"
        )

    def choose(self, callback, mode="open", multiple=False):
        start = Path(self.model.input_file).parent if self.model.input_file else None
        self.dialog = FileDialog(
            tr("TTTR files"),
            mode=mode,
            multiselect=multiple,
            filters=FILTERS,
            directory=str(start) if start and start.is_dir() else "",
            filename=self.model.default_save_name() if mode == "save" else "",
        )
        self.dialog_callback = callback
        self.file_window.title = tr("TTTR files")
        self.file_window.show()

    # -- host events ---------------------------------------------------------------------------------------------- #
    def on_files_dropped(self, paths):
        """One file dropped outside the queue loads it (the Qt file row); files, folders or a drop on the queue are queued."""
        paths = [str(p) for p in paths]
        x, y = self.io.mouse_pos
        qx, qy, qw, qh = self.item_rects.get("queue", (0.0, 0.0, 0.0, 0.0))
        over_queue = qx <= x <= qx + qw and qy <= y <= qy + qh
        if len(paths) == 1 and Path(paths[0]).is_file() and not over_queue:
            self.input_file = paths[0]
            self.load(paths[0])
        else:
            self.add_paths(paths)
        return True

    files_dropped = on_files_dropped

    # -- help and tour ------------------------------------------------------------------------------------------- #
    def show_help(self):
        self.help = EmTkHelpWindow(
            title=tr("ALEX Creator"),
            text=HELP.get(get_locale(), ""),
            resource=HERE / "help.md",
            on_start_guide=self.start_guide,
        )
        self.help.show()

    def start_guide(self):
        """Start the tour from ``guide.json``; the texts go through the translation table."""
        self.guide.steps = [
            {
                **step,
                "title": tr(step["title"]),
                "text": tr(step["text"]),
                **(
                    {"await": {**step["await"], "hint": tr(step["await"]["hint"])}}
                    if step.get("await")
                    else {}
                ),
            }
            for step in self.guide_steps
        ]
        self.guide.start()

    # -- drawing ------------------------------------------------------------------------------------------------- #
    def draw_events(self, section, model, state, width):
        """The photon count of the loaded file (nothing until one is loaded)."""
        if self.model.has_data:
            im.text_disabled(f"{len(self.model._tttr):,} " + tr("events"))
        else:
            im.text_disabled(tr("No file loaded."))

    def draw_controls(self, box):
        pressed = button_row(
            [
                {
                    "label": tr("Guide"),
                    "key": "guide",
                    "tip": tr("Walk through loading, timing and conversion."),
                },
                {
                    "label": tr("Help"),
                    "key": "help",
                    "tip": tr("Read ALEX conversion and batch workflow help."),
                },
            ],
            remember=lambda name: self.remember(name),
        )
        if pressed == "guide":
            self.start_guide()
        elif pressed == "help":
            self.show_help()
        locale = get_locale()
        if self.spec is None or locale != self.spec_locale:
            self.spec, self.spec_locale = (
                layout_spec(translated(deepcopy(self.spec_source))),
                locale,
            )
            labels = LabelColumn()  # one caption column for every field of the window
            labels.measure([f["label"] for f in labelled(self.spec["sections"])])
            labels.pad(self.spec["sections"])
        self.form.custom["events"] = self.draw_events
        self.form.rects.clear()
        im.begin_disabled(self.job.running)
        draw_form(self.spec, self, self.form, titles=True)
        im.end_disabled()
        self.item_rects.update(self.form.rects)
        if "queue_rows" in self.form.rects:
            self.item_rects["queue"] = self.form.rects["queue_rows"]
        fields = [
            self.form.rects[k] for k in ("alex_period", "period_shift") if k in self.form.rects
        ]
        if fields:
            x0, y0 = min(r[0] for r in fields), min(r[1] for r in fields)
            x1, y1 = max(r[0] + r[2] for r in fields), max(r[1] + r[3] for r in fields)
            self.item_rects["timing"] = (x0, y0, x1 - x0, y1 - y0)

    def draw_plot(self, box):
        if self.message:
            if self.message_is_error:
                im.push_style_color(im.Col.TEXT, ERROR_COLOUR)
            im.text_wrapped(self.message)
            if self.message_is_error:
                im.pop_style_color(1)
        else:
            im.text_wrapped(tr("Load a file to preview ALEX phase."))
        if self.job.running:
            im.text_disabled(tr("Working…"))
        origin, room = im.get_cursor_screen_pos(), im.get_content_region_avail()
        self.item_rects["plot"] = (origin[0], origin[1], room[0], room[1])
        if implot.begin_plot("##alex-phase", (-1, -1)):
            implot.setup_axes(tr("Micro-time bin"), tr("Counts"))
            if len(self.histogram):
                implot.plot_line(tr("ALEX phase"), list(range(len(self.histogram))), self.histogram)
            implot.end_plot()

    def render(self):
        self.job.poll()
        self.preview_job.poll()
        if self.model.has_data and self.signature() != self.preview_signature:
            self.preview()
        if self.running or self.guide.active:
            from emtk.im_core import get_current_context

            ctx = get_current_context()
            ctx.request_frame_at(ctx.io.now + 0.05)
        vp = im.get_main_viewport()
        width, height = float(vp.size[0]), float(vp.size[1])
        left = min(max(380.0, width * 0.36), 470.0)
        im.set_next_window_pos((4.0, 4.0), im.Cond.ALWAYS)
        im.set_next_window_size((left, height - 8.0), im.Cond.ALWAYS)
        if im.begin("ALEX Creator"):
            self.draw_controls((4.0, 4.0, left, height - 8.0))
        im.end()
        im.set_next_window_pos((left + 8.0, 4.0), im.Cond.ALWAYS)
        im.set_next_window_size((width - left - 12.0, height - 8.0), im.Cond.ALWAYS)
        if im.begin(tr("ALEX micro-time histogram")):
            im.text(tr("ALEX micro-time histogram"))
            self.draw_plot((left + 8.0, 4.0, width - left - 12.0, height - 8.0))
        im.end()
        if self.guide.active:
            if self.guide.awaiting:
                self.guide.draw(width, height)  # the highlighted control must stay clickable
            else:
                # A window of its own over the others, so the card's buttons are hovered (a button answers only when no
                # other window is under the pointer).
                flags = (
                    im.WindowFlags.NO_DECORATION
                    | im.WindowFlags.NO_BACKGROUND
                    | im.WindowFlags.NO_SAVED_SETTINGS
                    | im.WindowFlags.NO_MOVE
                    | im.WindowFlags.NO_NAV
                )
                im.begin("##alex_tour", (0.0, 0.0, width, height), flags)
                self.guide.draw(width, height)
                im.end()
        if self.dialog:
            closed = self.file_window.begin((0, 0, width, height)) == "close"
            result = self.dialog.draw()
            self.file_window.end()
            if closed or result is False:
                self.dialog = None
            elif result:
                callback = self.dialog_callback
                self.dialog = None
                callback(result)
        elif self.file_window.open:
            self.file_window.hide()
        self.dataset_picker.render((0, 0, width, height))
        if self.help.open:
            self.help.draw((0, 0, width, height))
        # One wheel notch is one step: a spin field does not consume the notch it stepped on, and an unconsumed wheel
        # would step it again on every later frame (emtk gap, repro in the report).
        self.io.mouse_wheel = self.io.mouse_wheel_h = 0.0


def make_app(**kwargs):
    return AlexApp(**kwargs)
