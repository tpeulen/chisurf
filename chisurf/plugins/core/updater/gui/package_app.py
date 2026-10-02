"""Native emtk package manager: installed packages, search and install, environments, channels, and the operation log.

Each page of the Qt tab widget is a panel of the view spec ``packages.view.json`` drawn by
:func:`emtk.view_form.draw_sections` (tables are ``data_table`` sections, selection through ``selected_call``); only the
tab bar, the environment line, the scrolling log, Help / Guide and the file choosers are drawn here. All state and work is in
:class:`~.package_model.PackageManagerModel`; the solver calls run on a :class:`~chisurf.emtk.jobs.SnapshotJob`.

:class:`PackagePanel` draws into whatever window the host gives it (the updater's package window, or the standalone
:class:`PackageApp`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.jobs import SnapshotJob

from .package_model import TABS, PackageManagerModel

HERE = Path(__file__).parent
_NAMES = ("installed", "search", "envs", "channels")
LOG_HEIGHT = 100.0


class PackagePanel:
    """The package manager's content: tab bar, the page, the log, and its dialogs."""

    def __init__(self, model: PackageManagerModel | None = None, owner: Any = None) -> None:
        self.model = model or PackageManagerModel()
        self.job = SnapshotJob(self.model)
        self.model.runner = self.start_job
        spec = json.loads((HERE / "packages.view.json").read_text(encoding="utf-8"))
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        self.form.custom["env_line"] = self._draw_env
        self.form.custom["operation_log"] = self._draw_log
        self.dialog_form = FormState()
        self.dialog: FileDialog | None = None
        self.dialog_purpose = ""
        self.message_window = DialogWindow("ChiSurf Package Manager", size=(520.0, 190.0), key="packages_dialog", fit_height=True)
        self.item_rects: dict[str, tuple] = {}
        self.pending_tab: int | None = None
        self._reported_error = ""
        self._logged = 0
        self.loaded = False
        #: Called with the name of a form action (the app's tour listens).
        self.on_used = None
        self.form.on_used = lambda name: self.on_used(name) if self.on_used else None

    def start_job(self, method: str, *args: Any) -> bool:
        """Run the model method *method* on a snapshot in a worker thread."""
        self._reported_error = ""
        return self.job.start(method, *args)

    # -- one frame --------------------------------------------------------------------------------------------------------- #
    def draw(self, box: Any) -> None:
        """Draw the panel in the current window and its dialogs over *box*."""
        self.draw_content()
        self.draw_overlays(box)

    def draw_overlays(self, box: Any) -> None:
        """The file chooser and the question window (windows of their own: call outside the panel's window)."""
        self._requests()
        self._draw_file_dialog()
        self._draw_message(box)

    def draw_content(self) -> None:
        """The tab bar, the page and the log, in the current window."""
        model = self.model
        self.job.poll()
        model.busy = self.job.busy
        if self.job.error and self.job.error != self._reported_error:
            self._reported_error = self.job.error
            model.append_log(f"Failed: {self.job.error}")
        if not self.loaded:
            self.loaded = True
            model.refresh_all()             # the Qt widget loaded its lists when it was created
        self.form.rects.clear()
        self._tabs()
        name = _NAMES[model.tab]
        im.begin_disabled(model.dialog_blocks)
        draw_sections(self.panels[name]["sections"], model, self.form, titles=False)
        im.separator()
        draw_sections(self.panels["footer"]["sections"], model, self.form, titles=False)
        im.end_disabled()

    def _tabs(self) -> None:
        model = self.model
        if im.begin_tab_bar("package_pages"):
            for index, label in enumerate(TABS):
                flag = im.TabItemFlags.SET_SELECTED if self.pending_tab == index else 0
                if im.begin_tab_item(label, flag):
                    if model.tab != index and self.pending_tab is None:
                        model.tab = index
                        if self.on_used:
                            self.on_used(f"tab_{_NAMES[index]}")
                    im.end_tab_item()
                im.set_item_tooltip(str(self.panels[_NAMES[index]]["description"]))
                self.item_rects[f"tab_{_NAMES[index]}"] = im.get_item_rect()
            im.end_tab_bar()
            self.pending_tab = None

    def select_tab(self, index: int) -> None:
        """Show page *index* (a restored setting or a guide step)."""
        self.model.tab = index
        self.pending_tab = index

    # -- custom sections --------------------------------------------------------------------------------------------------- #
    def _draw_env(self, section: dict, model: Any, state: FormState, width: float) -> None:
        im.text("Current Environment:")
        im.same_line()
        im.text(model.current_env_text)
        im.set_item_tooltip(str(section.get("description", "")))
        state.rects["current_env"] = im.get_item_rect()

    def _draw_log(self, section: dict, model: Any, state: FormState, width: float) -> None:
        im.text(str(section.get("title", "")))
        avail_w, _ = im.get_content_region_avail()
        x, y = im.get_cursor_screen_pos()
        im.begin_child("##operation_log", (float(avail_w), LOG_HEIGHT))
        for line in model.log:
            im.text_wrapped(line)
        if len(model.log) != self._logged:
            self._logged = len(model.log)
            im.set_scroll_here_y(1.0)
        im.end_child()
        rect = (float(x), float(y), float(avail_w), LOG_HEIGHT)
        state.rects["log"] = rect
        self.item_rects["log"] = rect

    # -- file dialogs ------------------------------------------------------------------------------------------------------ #
    def _requests(self) -> None:
        model = self.model
        request, model.request = model.request, ""
        if request and self.dialog is None:
            home = str(Path.home())
            if request == "export":
                self.dialog, self.dialog_purpose = FileDialog(
                    "Export Environment", mode="save", filename="environment.yaml", directory=home,
                    filters="YAML files (*.yaml *.yml)"), "export"
            elif request == "import":
                self.dialog, self.dialog_purpose = FileDialog(
                    "Import Environment", directory=home, filters="YAML files (*.yaml *.yml)"), "import"

    def _draw_file_dialog(self) -> None:
        if self.dialog is None:
            return
        result = None
        if im.begin(self.dialog.title):
            result = self.dialog.draw()
        im.end()
        purpose = self.dialog_purpose
        if result:
            self.dialog = None
            if purpose == "export":
                self.model.export_to(result[0])
            elif purpose == "import":
                self.model.import_from(result[0])
        elif result is False:
            self.dialog = None

    def _draw_message(self, box: Any) -> None:
        model = self.model
        window = self.message_window
        if model.dialog and not window.open:
            window.show()
        if not model.dialog and window.open:
            window.hide()
        if not window.open:
            return
        window.title = model.dialog_title
        pressed = window.begin(box)
        draw_sections(self.panels["dialog"]["sections"], model, self.dialog_form, titles=False)
        window.end()
        if pressed == "close":
            model.dialog_cancel() if model._dialog_cancel else model.dialog_ok()

    def close(self) -> None:
        """Detach the model's observers."""
        self.model._observers.clear()


class PackageApp(ImApp):
    """The package manager as a window of its own (and what the Settings panel embeds)."""

    window_title = "ChiSurf Package Manager"

    def __init__(self, model: PackageManagerModel | None = None) -> None:
        self.panel = PackagePanel(model)
        self.model = self.panel.model
        self.item_rects = self.panel.item_rects
        self.help_window = EmTkHelpWindow(title="ChiSurf Package Manager - Help", resource=HERE / "packages_help.md", owner=self)
        self.tour = EmTkGuidedTour(
            steps=HERE / "packages_guide.json", owner=self, wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.panel.form.rects.get(key))
        self.panel.on_used = self.tour.notify_used
        super().__init__(self.render, continuous=True)

    @property
    def form(self) -> FormState:
        return self.panel.form

    @property
    def job(self) -> SnapshotJob:
        return self.panel.job

    def render(self) -> None:
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        im.set_next_window_pos(vp.pos, im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin("ChiSurf Package Manager", box):
            if im.button("Help"):
                self.help_window.show()
            im.set_item_tooltip("Explain the four pages and what each button runs.")
            self.item_rects["help"] = im.get_item_rect()
            im.same_line()
            if im.button("Guide"):
                self.tour.start()
            im.set_item_tooltip("Walk through finding and installing a package.")
            self.item_rects["guide"] = im.get_item_rect()
            im.separator()
            self.panel.draw(box)
        im.end()
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def export_settings(self) -> dict:
        return self.model.export_settings()

    def restore_settings(self, settings: dict) -> None:
        self.model.restore_settings(settings)
        self.panel.select_tab(self.model.tab)

    def close(self) -> None:
        self.panel.close()


def make_package_app() -> PackageApp:
    """Build the package manager as an app of its own."""
    from chisurf.emtk.i18n import install

    install()
    return PackageApp()
