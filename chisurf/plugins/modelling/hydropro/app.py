"""Native HYDROPRO / HYDRO++ window: the Qt tool's parameters, file buttons, run, results table and output pane, without Qt.

The parameter panels are the Qt AutoForm spec (``gui/hydropro.view.json``) drawn by :func:`emtk.view_form.draw_sections`
over :class:`~.gui.model.HydroProModel`; the buttons, the results ``data_table`` and the output pane are
``gui/hydropro_emtk.view.json``. Only what a spec cannot draw is drawn here: the selectable output log, the Help and
Guide buttons and the in-app dialogs (file chooser, "executable required", notices). The calculation is
:func:`~.core.runner.run_hydro` on a worker thread, exactly as the Qt tool, the CLI and the RPC service drive it.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections
from emtk.widgets.text_editor import TextEditor

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import cap_widths

from .gui.model import (
    CSV_FILTER,
    DOWNLOAD_URL,
    EXE_FILTER,
    LOG_FILTER,
    STRUCT_FILTER,
    HydroProModel,
)
from .strings import install_translations, tr

install_translations()

GUI = Path(__file__).parent / "gui"
TABLE = "result_rows"
#: The Qt guide names its targets by the Qt button's text; the native controls answer to the same names.
ALIASES = {"Executable": "select_exe", "Select files": "select_files", "Run": "run", "Save CSV": "save_csv"}
ACTION_TO_ALIAS = {action: alias for alias, action in ALIASES.items()}
#: Width the parameter window needs for two fields per line, and the share of the window it may take.
PARAMS_MIN = 360.0


def build_spec() -> dict:
    """The native spec: the Qt parameter panels (spin arrows, folds) plus the native-only sections."""
    qt = json.loads((GUI / "hydropro.view.json").read_text(encoding="utf-8"))
    extra = json.loads((GUI / "hydropro_emtk.view.json").read_text(encoding="utf-8"))
    panels = []
    for panel in qt["sections"]:
        if panel.get("title") == "Results":  # its Status field moves to the results window
            continue
        panel = copy.deepcopy(panel)
        panel["collapsible"] = True
        panel["n_col"] = 2
        for section in panel["sections"]:
            if section.get("type") == "value" and section.get("kind") in ("int", "float"):
                section["style"] = "spin"
                if section["kind"] == "float" and not section.get("step"):
                    section["step"] = 1.0  # QDoubleSpinBox's default single step, which the Qt AutoForm keeps
            if section.get("type") == "value" and section.get("kind") == "str":
                section["elide"] = "start"
        if panel["title"] == "Executable & input":
            panel["n_col"] = 1
            # Its own grid: a button row sharing the fields' grid starts under their value column and overruns a narrow window.
            panel["sections"].append({"type": "panel", "title": "", "sections": [extra["input_buttons"]]})
        panels.append(panel)
    spec = {"params": panels, "results": extra["results"], "output": extra["output"]}
    for part in spec.values():
        cap_widths(part)
    for section in _walk(spec["params"]):
        if section.get("attr") in ("exe_path", "struct_files"):
            section.pop("width", None)  # paths stay as wide as the window
    return spec


def _walk(sections):
    for section in sections:
        yield section
        yield from _walk(section.get("sections", []))


def soft_wrap(text: str, columns: int) -> str:
    """*text* with every line broken at *columns* characters, for a view without word wrap (the log itself is unchanged)."""
    out = []
    for line in text.split("\n"):
        while len(line) > columns:
            cut = line.rfind(" ", 0, columns)
            cut = cut if cut > columns // 2 else columns
            out.append(line[:cut])
            line = line[cut:].lstrip(" ") if line[cut:cut + 1] == " " else line[cut:]
        out.append(line)
    return "\n".join(out)


class MessageWindow:
    """A titled in-app message with one OK button (the Qt ``QMessageBox``)."""

    def __init__(self) -> None:
        self.window = DialogWindow("Message", size=(460.0, 170.0), key="hydropro_notice", fit_height=True)

    def draw(self, notices: list, box: tuple, rects: dict) -> bool:
        """Draw the first notice; True when it was dismissed (OK, close or Escape)."""
        title, text = notices[0]
        self.window.title = tr(title)
        self.window.open = True
        closed = self.window.begin(box) == "close"
        im.text_wrapped(tr(text))
        im.spacing()
        pressed = im.button(f"{tr('OK')}##notice_ok")
        rects["notice_ok"] = im.get_item_rect()
        im.set_item_tooltip(tr("Close this message."))
        self.window.end()
        return bool(pressed or closed)


class HydroProApp(ImApp):
    """Run HYDROPRO / HYDRO++ over structure files and read the diffusion coefficients."""

    window_title = "HYDRO++ / HYDROPRO Diffusion Coefficient Calculator"

    def __init__(self, model: HydroProModel | None = None) -> None:
        self.model = model or HydroProModel()
        self.model.open_url = self._open_url
        spec = build_spec()
        self.panels = spec["params"]
        self.results_sections = spec["results"]
        self.output_sections = spec["output"]
        self.form = FormState(on_used=self._used)
        self.form.custom["output_log"] = self._draw_log
        self.item_rects: dict[str, tuple] = {}
        self._log_editor = TextEditor("")
        self._log_editor.config.show_line_numbers = False
        self._log_editor.config.read_only = True
        self._log_seen = ""
        self._sized: tuple | None = None
        self.dialog: FileDialog | None = None
        self.dialog_callback = None
        self.file_window = DialogWindow("Choose files", size=(640.0, 460.0), key="hydropro_files")
        self.prompt_window = DialogWindow("HYDRO executable required", size=(540.0, 250.0), key="hydropro_prompt",
                                          fit_height=True)
        self.message = MessageWindow()
        self.tour = EmTkGuidedTour(
            steps=GUI / "guide.json", owner=self, wait_for_controls=True,
            get_target_rect=self._target_rect,
        )
        self.help_window = EmTkHelpWindow(title="HydroPro - Help", resource=GUI / "help.md", owner=self,
                                          on_start_guide=self.tour.start)
        self.docks = DockManager(Split("h", 0.42, Region("params"), Split("v", 0.55, Region("results"), Region("output"))))
        self.docks.add_window("params", tr("Parameters"), self.draw_params, dock="params", closable=False)
        self.docks.add_window("results", tr("Results"), self.draw_results, dock="results", closable=False)
        self.docks.add_window("output", tr("HYDRO Output"), self.draw_output, dock="output", closable=False)
        super().__init__(self.render)

    # -- the Qt tool's remembered state ---------------------------------------------------------------------------- #
    def export_settings(self) -> dict:
        return self.model.export_settings()

    def restore_settings(self, settings: dict) -> None:
        self.model.restore_settings(settings)

    # -- guide plumbing ------------------------------------------------------------------------------------------------ #
    def _used(self, name: str) -> None:
        self.tour.notify_used(ACTION_TO_ALIAS.get(name, name))

    def _target_rect(self, key: str):
        name = ALIASES.get(key, key)
        return self.item_rects.get(name) or self.form.rects.get(name) or self.form.rects.get(key)

    # -- one frame -------------------------------------------------------------------------------------------------------- #
    def render(self) -> None:
        self.model.poll()
        viewport = im.get_main_viewport()
        box = (*viewport.pos, *viewport.size)
        if self._sized != tuple(viewport.size):
            self._sized = tuple(viewport.size)
            self.docks.set_ratio("root", min(0.6, max(0.36, PARAMS_MIN / float(viewport.size[0]) + 0.0)))
        self.form.rects.clear()
        self.docks.draw(box)
        self._draw_dialogs(box)
        self.help_window.draw(box)
        if self.tour.active and not self._dialog_open():
            if self.tour.awaiting:
                self.tour.draw(*viewport.size)  # the highlighted control must stay clickable
            else:
                # A window of its own over the docks, so the card's buttons are hovered (a button answers only when no
                # other window is under the pointer).
                flags = (im.WindowFlags.NO_DECORATION | im.WindowFlags.NO_BACKGROUND | im.WindowFlags.NO_SAVED_SETTINGS
                         | im.WindowFlags.NO_MOVE | im.WindowFlags.NO_NAV)
                im.begin("##hydropro_tour", (0.0, 0.0, float(viewport.size[0]), float(viewport.size[1])), flags)
                self.tour.draw(*viewport.size)
                im.end()

    def _dialog_open(self) -> bool:
        return bool(self.dialog or self.model.exe_prompt or self.model.notices)

    def _serve_requests(self) -> None:
        """A request the model made (a button asked for a chooser)."""
        if self.model.dialog and self.dialog is None:
            self._open_chooser(self.model.dialog)
            self.model.dialog = None

    def _draw_dialogs(self, box: tuple) -> None:
        model = self.model
        self._serve_requests()
        if model.exe_prompt:
            self._draw_prompt(box)
            self._serve_requests()
        if model.notices and self.message.draw(model.notices, box, self.item_rects):
            model.notices.pop(0)
        if self.dialog is not None:
            closed = self.file_window.begin(box) == "close"
            result = self.dialog.draw()
            self.file_window.end()
            if closed or result is False:
                self.dialog = None
                self.dialog_callback = None
            elif result:
                callback, self.dialog, self.dialog_callback = self.dialog_callback, None, None
                callback(result)

    def _open_chooser(self, kind: str) -> None:
        home = str(Path.home())
        model = self.model
        if kind == "files":
            self.dialog = FileDialog(tr("Select structural files"), mode="open", multiselect=True, directory=home,
                                     filters=STRUCT_FILTER)
            self.dialog_callback = lambda paths: model.files_chosen(paths)
        elif kind in ("exe", "prompt_exe"):
            self.dialog = FileDialog(tr("Select HYDRO executable"), mode="open", directory=home, filters=EXE_FILTER)
            self.dialog_callback = (lambda paths: model.exe_chosen(paths[0])) if kind == "exe" \
                else (lambda paths: model.prompt_exe_chosen(paths[0]))
        elif kind == "csv":
            self.dialog = FileDialog(tr("Save CSV"), mode="save", directory=home, filename=model.csv_name(), filters=CSV_FILTER)
            self.dialog_callback = lambda paths: model.write_csv(paths[0])
        elif kind == "log":
            self.dialog = FileDialog(tr("Save output log"), mode="save", directory=home, filename=model.log_name(),
                                     filters=LOG_FILTER)
            self.dialog_callback = lambda paths: model.write_log(paths[0])
        self.file_window.title = self.dialog.title if self.dialog else ""
        self.file_window.pos = None
        self.file_window.show()

    def _draw_prompt(self, box: tuple) -> None:
        """Qt ``DownloadInfoDialog``: where to get the program, and a way to point at it."""
        model = self.model
        self.prompt_window.open = True
        closed = self.prompt_window.begin(box) == "close"
        im.text_wrapped(tr("HYDROPRO / HYDRO++ executable is not configured.\n\n"
                           "Please download the official ZIP archive and select the executable\n"
                           "(hydropro10.exe or hydro++10.exe) before running calculations."))
        im.spacing()
        im.set_next_item_width(-1)
        im.input_text("##prompt_path", str(model.prompt_path or ""), hint=tr("no executable selected"),
                      flags=im.InputTextFlags.READ_ONLY)
        self.item_rects["prompt_path"] = im.get_item_rect()
        im.set_item_tooltip(tr("The executable chosen here; it is used for this run when you press Close."))
        if im.button(f"{tr('Select executable…')}##prompt_select"):
            if self.dialog is None:
                model.dialog = "prompt_exe"
        self.item_rects["prompt_select"] = im.get_item_rect()
        im.set_item_tooltip(tr("Pick the HYDROPRO or HYDRO++ program with the file chooser."))
        im.same_line()
        if im.button(f"{tr('Open download page')}##prompt_download"):
            model.download_page()
        self.item_rects["prompt_download"] = im.get_item_rect()
        im.set_item_tooltip(tr("Open the download page in your web browser."))
        im.same_line()
        pressed = im.button(f"{tr('Close')}##prompt_close")
        self.item_rects["prompt_close"] = im.get_item_rect()
        im.set_item_tooltip(tr("Continue with the chosen executable, or stop if none was chosen."))
        self.prompt_window.end()
        if pressed or closed:
            model.close_exe_prompt()

    # -- windows ------------------------------------------------------------------------------------------------------------- #
    def draw_params(self, box: Any) -> None:
        if im.button(f"{tr('Help')}##help"):
            self.help_window.show()
        im.set_item_tooltip(tr("Explain the settings that decide the answer and what comes out."))
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button(f"{tr('Guide')}##guide"):
            self.tour.start()
        im.set_item_tooltip(tr("Walk through choosing the program and structures, the settings and a run."))
        self.item_rects["guide"] = im.get_item_rect()
        draw_sections(self.panels, self.model, self.form, titles=True)

    def draw_results(self, box: Any) -> None:
        draw_sections(self.results_sections, self.model, self.form, titles=False)

    def draw_output(self, box: Any) -> None:
        draw_sections(self.output_sections, self.model, self.form, titles=False)

    def _draw_log(self, section: dict, model: Any, state: FormState, width: float) -> None:
        char = max(1.0, float(im.calc_text_size("M" * 20)[0]) / 20.0)
        columns = max(20, int((width - 44.0) / char))
        text = soft_wrap(model.log_text, columns)
        if text != self._log_seen:
            self._log_seen = text
            self._log_editor.set_text(text)
        top = im.get_cursor_screen_pos()
        height = max(60.0, im.get_content_region_avail()[1] - 36.0)
        im.text_editor("##hydro_log", self._log_editor, (0, height))
        state.rects["output_log"] = (top[0], top[1], width, height)
        im.set_item_tooltip(str(section.get("description", "")))

    # -- misc ---------------------------------------------------------------------------------------------------------------- #
    def _open_url(self, url: str) -> None:
        from chisurf.emtk.doc_links import open_link

        open_link(url)

    def files_dropped(self, paths) -> bool:
        """Structure files dropped on the window replace the list (the Qt window accepted drops and ignored them)."""
        files = [str(p) for p in paths if Path(p).is_file()]
        if not files:
            return False
        self.model.files_chosen(files)
        return True

    on_files_dropped = files_dropped

    def draw(self, painter, x: float, y: float, w: float, h: float) -> None:
        super().draw(painter, x, y, w, h)
        # A spin field steps by the wheel without consuming it, and emtk keeps an unconsumed wheel until a window takes
        # it: every further frame would step the field again (a notch became a run-away). One notch is one pass.
        self.io.mouse_wheel = self.io.mouse_wheel_h = 0.0

    def animating(self) -> bool:
        return self.model.running or super().animating()

    def close(self) -> None:
        self.model.close()


def make_app() -> HydroProApp:
    """Build the HydroPro app (the manifest's ``entrypoints.emtk``)."""
    from chisurf.emtk.i18n import install

    install()
    return HydroProApp()


__all__ = ["HydroProApp", "HydroProModel", "build_spec", "make_app", "DOWNLOAD_URL"]
