"""Native ALEX conversion, live phase preview and batch conversion/merge."""

from __future__ import annotations

import json
from pathlib import Path

from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.i18n import get_locale, tr

from chisurf.core.settings.path_utils import get_path
from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.i18n import install
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .. import core
from ..api import AlexRequest, run
from .translations import HELP, install_translations
from .view_model import AlexViewModel

EXTENSIONS = {".sm", ".ptu", ".ht3", ".spc", ".hdf", ".h5", ".raw"}
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


class AlexApp(ImApp):
    """Use the same scientific operations as Qt, publishing workers on the UI thread."""

    def __init__(self, state_path=None):
        install()
        install_translations()
        self.model = AlexViewModel()
        self.job = BackgroundJob()
        self.histogram = []
        self.preview_signature = None
        self.message = ""
        self.outputs = []
        self.dialog = self.dialog_callback = None
        self.item_rects = {}
        self.file_window = DialogWindow("ALEX file chooser", size=(600.0, 420.0), key="alex_files")
        self.dataset_picker = DatasetPicker(on_paths=self.add_paths)
        self.state_path = (
            Path(state_path) if state_path else get_path("settings") / "alex-emtk.json"
        )
        self.docks = DockManager(
            Split("h", 0.36, Split("v", 0.50, Region("controls"), Region("batch")), Region("plot"))
        )
        self.docks.add_window("controls", tr("Conversion"), self.draw_controls, dock="controls")
        self.docks.add_window("batch", tr("Batch"), self.draw_batch, dock="batch")
        self.docks.add_window("plot", tr("ALEX micro-time histogram"), self.draw_plot, dock="plot")
        self.help = EmTkHelpWindow(
            title=tr("ALEX Creator"),
            resource=Path(__file__).with_name("help.md"),
            on_start_guide=self.start_guide,
        )
        self.guide = EmTkGuidedTour(
            steps=Path(__file__).with_name("guide.json"),
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self,
            wait_for_controls=True,
        )
        self.guide_steps = list(self.guide.steps)
        try:
            self.set_state(json.loads(self.state_path.read_text()))
        except (OSError, ValueError, TypeError):
            pass
        super().__init__(gui=self.render, continuous=True)

    def get_state(self):
        return {
            "version": 1,
            "settings": {key: getattr(self.model, key) for key in FIELDS},
            "docks": self.docks.state(),
        }

    def set_state(self, state):
        values = state.get("settings", {})
        for key in FIELDS:
            if key in values:
                setattr(self.model, key, values[key])
        self.model.alex_period = max(1, min(1000000, int(self.model.alex_period)))
        self.model.period_shift = max(-1000000, min(1000000, int(self.model.period_shift)))
        if self.model.input_format not in self.model.input_format_options():
            self.model.input_format = "Auto"
        if self.model.output_format not in self.model.output_format_options():
            self.model.output_format = "PTU"
        if self.model.batch_mode not in {"convert", "merge"}:
            self.model.batch_mode = "convert"
        self.model.batch_files = [str(p) for p in self.model.batch_files]
        self.docks.restore(state.get("docks"))

    def close(self):
        self.job.close()
        self.dataset_picker.close()
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(self.get_state(), indent=2))
        except OSError:
            pass

    def error(self, exc):
        self.message = str(exc)

    def signature(self):
        m = self.model
        return (m.input_file, m.input_format, int(m.alex_period), int(m.period_shift))

    def load(self, path):
        if self.job.running:
            return False
        path = str(path)
        if not Path(path).is_file():
            self.error(ValueError(tr("Please choose an existing TTTR file.")))
            return False
        m = self.model
        kind = core.resolve_filetype(m.input_format, path)
        period, shift = int(m.alex_period), int(m.period_shift)
        signature = (path, m.input_format, period, shift)

        def work():
            return core.load(path, kind), core.alex_histogram(path, period, shift, kind)

        def publish(data):
            self.model.set_tttr(data[0], path)
            self.histogram = data[1]
            self.preview_signature = signature
            self.message = tr("Loaded") + ": " + Path(path).name

        self.message = tr("Loading…")
        return self.job.start(work, publish, self.error)

    def preview(self):
        if not self.model.has_data or self.job.running:
            return False
        signature = self.signature()
        path, fmt, period, shift = signature

        def publish(hist):
            self.histogram = hist
            self.preview_signature = signature

        # Mark a failed signature too, avoiding a failing read on every frame.
        self.preview_signature = signature
        return self.job.start(
            lambda: core.alex_histogram(path, period, shift, core.resolve_filetype(fmt, path)),
            publish,
            self.error,
        )

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
        self.message = tr("Written files") + ": " + "\n".join(self.outputs)

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

    def on_files_dropped(self, paths):
        if len(paths) == 1 and Path(paths[0]).is_file():
            self.load(paths[0])
        else:
            self.add_paths(paths)
        return True

    def choose(self, callback, mode="open", multiple=False):
        self.dialog = FileDialog(
            tr("TTTR files"),
            mode=mode,
            multiselect=multiple,
            filters="TTTR (*.sm *.ptu *.ht3 *.spc *.hdf *.h5 *.raw);;All files (*)",
            filename=self.model.default_save_name() if mode == "save" else "",
        )
        self.dialog_callback = callback
        self.file_window.title = tr("TTTR files")
        self.file_window.show()

    def button(self, label, tip, callback, key=None):
        pressed = im.button(tr(label))
        im.set_item_tooltip(tr(tip))
        if key:
            self.item_rects[key] = im.get_item_rect()
        if pressed:
            callback()
            if key:
                self.guide.notify_used(key)

    def show_help(self):
        self.help = EmTkHelpWindow(
            title=tr("ALEX Creator"),
            text=HELP.get(get_locale(), ""),
            resource=Path(__file__).with_name("help.md"),
            on_start_guide=self.start_guide,
        )
        self.help.show()

    def start_guide(self):
        """Start the tour from ``guide.json``; the texts go through the translation table."""
        self.guide.steps = [
            {**step, "title": tr(step["title"]), "text": tr(step["text"])} for step in self.guide_steps
        ]
        self.guide.start()

    def draw_controls(self, box):
        m = self.model
        self.button(
            "Open…",
            "Load a TTTR file and preview its folded ALEX phase.",
            lambda: self.choose(lambda p: self.load(p[0])),
            "input",
        )
        im.same_line()
        im.begin_disabled(not m.has_data)
        self.button(
            "Save as…",
            "Write converted photon data without changing the input.",
            lambda: self.choose(lambda p: self.save(p[0]), "save"),
            "save",
        )
        im.end_disabled()
        self.button("Guide", "Walk through loading, timing and conversion.", self.start_guide, "guide")
        im.same_line()
        self.button("Help", "Read ALEX conversion and batch workflow help.", self.show_help, "help")
        im.separator()
        im.text(tr("Input file"))
        im.set_next_item_width(-1)
        _, m.input_file = im.input_text("##input", m.input_file)
        im.set_item_tooltip(
            tr("Enter a TTTR path, then press Load; dropping a file also loads it.")
        )
        self.button("Load", "Read the file entered above.", lambda: self.load(m.input_file))
        for attr, label, options, tip in (
            (
                "input_format",
                "Input format",
                m.input_format_options(),
                "Auto detects the container; choose a format to override detection.",
            ),
            (
                "output_format",
                "Output format",
                m.output_format_options(),
                "Select the file container used for single and batch output.",
            ),
        ):
            im.set_next_item_width(-1)
            changed, index = im.combo(tr(label), options.index(getattr(m, attr)), options)
            im.set_item_tooltip(tr(tip))
            if changed:
                setattr(m, attr, options[index])
        for attr, label, lo, hi, tip in (
            (
                "alex_period",
                "Period",
                1,
                1000000,
                "Alternation period in macro-time units; maps phase to micro-time.",
            ),
            (
                "period_shift",
                "Shift",
                -1000000,
                1000000,
                "Phase offset applied before folding macro-time into micro-time.",
            ),
        ):
            im.set_next_item_width(-1)
            _, value = im.drag_int(tr(label), getattr(m, attr), 1.0, lo, hi)  # one count per pixel; input_int(step=0) moves 0.01 per pixel
            im.set_item_tooltip(tr(tip))
            value = max(lo, min(hi, int(value)))
            if value != getattr(m, attr):
                self.guide.notify_used("timing")
            setattr(m, attr, value)
        self.item_rects["timing"] = im.get_item_rect()
        if m.has_data:
            im.text_disabled(f"{len(m._tttr):,} " + tr("events"))

    def draw_batch(self, box):
        m = self.model
        self.button(
            "Add files…",
            "Queue TTTR files; duplicate paths are ignored.",
            lambda: self.choose(self.add_paths, multiple=True),
            "batch",
        )
        im.same_line()
        self.button(
            "Folder…",
            "Queue supported TTTR files recursively from a folder.",
            lambda: self.choose(self.add_paths, mode="folder"),
        )
        self.button(
            "Database", "Queue TTTR data from the session database.", self.dataset_picker.open
        )
        im.same_line()
        self.button("Clear", "Empty the queue without deleting files.", m.clear_batch)
        im.same_line()
        self.button(
            "Run batch",
            "Convert each file or merge the queue using the current timing.",
            self.run_batch,
            "run_batch",
        )
        im.set_next_item_width(-1)
        changed, index = im.combo(
            tr("Mode"),
            0 if m.batch_mode == "convert" else 1,
            [tr("Convert each"), tr("Merge into one")],
        )
        im.set_item_tooltip(tr("Choose separate output files or one merged photon stream."))
        if changed:
            m.batch_mode = ["convert", "merge"][index]
        im.set_next_item_width(-1)
        _, m.batch_output_folder = im.input_text(tr("Output folder"), m.batch_output_folder)
        im.set_item_tooltip(
            tr("Convert requires a folder; merge defaults to the first input folder.")
        )
        self.button(
            "Browse…",
            "Choose the output directory.",
            lambda: self.choose(
                lambda p: setattr(m, "batch_output_folder", str(p[0])), mode="folder"
            ),
        )
        im.separator()
        avail = im.get_content_region_avail()
        im.begin_child(
            (*im.get_cursor_screen_pos(), avail[0], max(65, min(150, box[3] - 235))),
            child_id="alex-queue",
            scrollable=True,
        )
        for i, path in enumerate(list(m.batch_files)):
            im.selectable(Path(path).name + f"##file{i}")
            im.set_item_tooltip(path)
            if im.begin_popup_context_item(f"alex-file{i}"):
                if im.menu_item(tr("Remove")):
                    m.batch_files.remove(path)
                im.set_item_tooltip(tr("Remove this file from the queue; keep it on disk."))
                im.end_popup()
        im.end_child()

    def draw_plot(self, box):
        im.text_wrapped(self.message or tr("Load a file to preview ALEX phase."))
        if self.job.running:
            im.text_disabled(tr("Working…"))
        if implot.begin_plot("##alex-phase", (-1, -1)):
            implot.setup_axes(tr("Micro-time bin"), tr("Counts"))
            if len(self.histogram):
                implot.plot_line(tr("ALEX phase"), list(range(len(self.histogram))), self.histogram)
            implot.end_plot()

    def render(self):
        self.job.poll()
        if self.model.has_data and self.signature() != self.preview_signature:
            self.preview()
        vp = im.get_main_viewport()
        im.begin_disabled(self.job.running)
        self.docks.draw((0, 0, *vp.size))
        im.end_disabled()
        if self.guide.active:
            if self.guide.awaiting:
                self.guide.draw(*vp.size)  # the highlighted control must stay clickable
            else:
                # A window of its own over the docks, so the card's buttons are hovered (a button answers only when no other
                # window is under the pointer).
                flags = (im.WindowFlags.NO_DECORATION | im.WindowFlags.NO_BACKGROUND | im.WindowFlags.NO_SAVED_SETTINGS
                         | im.WindowFlags.NO_MOVE | im.WindowFlags.NO_NAV)
                im.begin("##alex_tour", (0.0, 0.0, float(vp.size[0]), float(vp.size[1])), flags)
                self.guide.draw(*vp.size)
                im.end()
        if self.dialog:
            closed = self.file_window.begin((0, 0, *vp.size)) == "close"
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
        self.dataset_picker.render((0, 0, *vp.size))
        if self.help.open:
            self.help.draw((0, 0, *vp.size))


def make_app(**kwargs):
    return AlexApp(**kwargs)
