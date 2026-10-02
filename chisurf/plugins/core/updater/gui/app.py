"""Native emtk ChiSurf updater: the installed version, the update check, the changelog and Update Now.

The whole form -- the version and status lines, the startup switches, the version list, the three actions and
the in-app confirmation -- is the view spec ``updater.view.json`` drawn by :func:`emtk.view_form.draw_sections`.
Only what a spec cannot express is drawn here: the Markdown changelog and the Help / Guide buttons. All state
and work is in :class:`~.model.UpdaterModel`; the network and the update itself run on a
:class:`~chisurf.emtk.jobs.SnapshotJob`. The update ends the process through the model's ``exit_requested``
(the update script takes over; the real runner calls ``sys.exit``), which the app turns into ``exit_hook``.
"""

from __future__ import annotations

import json
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Callable

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.emtk_layout import layout_spec

from .model import UpdaterModel
from .package_app import PackagePanel

HERE = Path(__file__).parent

#: ``name`` of the panels of the spec.
_UPDATER, _DIALOG, _UPDATING = "updater", "dialog", "updating"
#: Widest the changelog is drawn: a line of commit text reads badly wider than this, and the room beside it is
#: where the tour card can stand without covering what it points at.
CHANGELOG_WIDTH = 640.0
#: Seconds between the first frame and the check that runs when the window opens.
AUTO_CHECK_DELAY = 0.6


class UpdaterApp(ImApp):
    """Check for updates and install one without a Qt host."""

    window_title = "ChiSurf Updater"

    def __init__(self, model: UpdaterModel | None = None, auto_check: bool = True,
                 exit_hook: Callable[[], None] | None = None, auto_check_delay: float = AUTO_CHECK_DELAY) -> None:
        self.model = model or UpdaterModel()
        self.job = SnapshotJob(self.model)
        self.model.runner = self.start_job
        #: Start the check that runs when the window opens, as the Qt tool did (its timer fired 150 ms after show):
        #: ``auto_check_delay`` seconds after the first frame, so that a window only drawn (a screenshot, a
        #: proof that no Qt is imported) never reaches for the network.
        self.auto_check = auto_check
        self.auto_check_delay = float(auto_check_delay)
        self._first_frame: float | None = None
        #: Called (from a frame) when the update script took the process over; ChiSurf has to end.
        self.exit_hook = exit_hook or (lambda: sys.exit(0))
        spec = json.loads((HERE / "updater.view.json").read_text(encoding="utf-8"))
        self.panels = {p["name"]: layout_spec(p) if p["name"] == _UPDATER else p for p in spec["sections"]}
        self.form = FormState()
        self.form.custom["changelog"] = self._draw_changelog
        self.form.custom["version_line"] = self._draw_version
        self.dialog_form = FormState()
        self.progress_form = FormState()
        self.message_window = DialogWindow("ChiSurf Updater", size=(520.0, 190.0), key="updater_dialog", fit_height=True)
        self.progress_window = DialogWindow("Updating ChiSurf", size=(520.0, 130.0), key="updater_progress",
                                            fit_height=True, escape_closes=False)
        #: The package manager window (the panel is built when it is first opened).
        self.packages: PackagePanel | None = None
        self.package_window = DialogWindow("ChiSurf Package Manager", size=(780.0, 560.0), key="updater_packages", escape_closes=False)
        self.item_rects: dict[str, tuple] = {}
        self._reported_error = ""
        self.exited = False
        #: Opens a link of the changelog in the system browser (a test replaces it).
        self.open_link: Callable[[str], None] = webbrowser.open
        self.help_window = EmTkHelpWindow(title="ChiSurf Updater - Help", resource=HERE / "help.md", owner=self)
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        super().__init__(self.render, continuous=True)

    # -- jobs ------------------------------------------------------------------------------------------------------ #
    def start_job(self, method: str, *args: Any) -> bool:
        """Run the model method *method* on a snapshot in a worker thread."""
        self._reported_error = ""
        return self.job.start(method, *args)

    # -- one frame --------------------------------------------------------------------------------------------------- #
    def render(self) -> None:
        self.job.poll()
        model = self.model
        model.busy = self.job.busy
        if model.updating and self.job.busy and self.job.progress and self.job.progress != "Do update\u2026":
            model.update_message = self.job.progress                 # the latest step the update's worker reported
        if self.job.error and self.job.error != self._reported_error:
            self._reported_error = self.job.error
            model.set_status(f"Failed: {self.job.error}")
            model.updating = False
        if self._first_frame is None:
            self._first_frame = time.monotonic()
        if (self.auto_check and model.auto_check_pending and not self.job.busy
                and time.monotonic() - self._first_frame >= self.auto_check_delay):
            model.auto_check_pending = False
            model.status = "Checking for updates..."
            model._run("auto_check")
        if model.exit_requested and not self.exited:
            self.exited = True
            self.request_close()
            self.exit_hook()
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        im.set_next_window_pos(vp.pos, im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin("ChiSurf Updater", box):
            self._toolbar()
            im.begin_disabled(model.dialog_blocks)
            draw_sections(self.panels[_UPDATER]["sections"], model, self.form, titles=True)
            im.end_disabled()
        im.end()
        self._draw_packages(box)
        self._draw_progress(box)
        self._draw_message(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _toolbar(self) -> None:
        """Help and Guide (a spec cannot draw the tour's entry points)."""
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Explain the version list, the changelog and what Update Now does.")
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through checking for an update and reading what changed.")
        self.item_rects["guide"] = im.get_item_rect()
        im.separator()

    def _draw_version(self, section: dict, model: Any, state: FormState, width: float) -> None:
        """The ``version_line`` custom section: the installed version next to its caption."""
        im.text("Current version:")
        left = im.get_item_rect()
        im.set_item_tooltip(str(section.get("description", "")))
        im.same_line()
        im.text(model.current_version_text)
        im.set_item_tooltip(str(section.get("description", "")))
        right = im.get_item_rect()
        state.rects["current_version_text"] = (left[0], left[1], right[0] + right[2] - left[0], max(left[3], right[3]))

    def _draw_changelog(self, section: dict, model: Any, state: FormState, width: float) -> None:
        """The ``changelog`` custom section: the Markdown changes in a scrolling area that takes the room left."""
        im.text(str(section.get("title", "")))
        avail_w, avail_h = im.get_content_region_avail()
        x, y = im.get_cursor_screen_pos()
        height = max(80.0, float(avail_h) - 4.0)
        width = min(float(avail_w), CHANGELOG_WIDTH)
        im.begin_child("##changelog", (width, height))
        if model.changelog_blocks:
            self._draw_blocks(model.changelog_blocks)
        else:
            im.text_disabled(model.changelog_text)
        im.end_child()
        rect = (float(x), float(y), width, height)
        state.rects["changelog"] = rect
        self.item_rects["changelog"] = rect

    def _draw_blocks(self, blocks: list) -> None:
        """The changelog blocks as plain text: a header, bulleted items, paragraphs and links (opened by ``open_link``)."""
        for kind, text, url in blocks:
            if kind == "header":
                im.heading(text, 4)
            elif kind == "item":
                im.bullet()
                im.text_wrapped(text)
            elif kind == "link":
                im.text(f"{text}:")
                im.same_line()
                if im.text_link(url):
                    self.open_link(url)
                im.set_item_tooltip("Open the page in your browser.")
            elif kind == "empty":
                im.text_disabled(text)
            else:
                im.text_wrapped(text)

    # -- dialogs -------------------------------------------------------------------------------------------------------- #
    def _draw_message(self, box: Any) -> None:
        """The dialog that asks before Update Now starts and reports what the check found."""
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
        draw_sections(self.panels[_DIALOG]["sections"], model, self.dialog_form, titles=False)
        window.end()
        if pressed == "close":
            model.dialog_cancel() if model._dialog_cancel else model.dialog_ok()

    def _draw_packages(self, box: Any) -> None:
        """The package manager window, opened by the Package Manager button."""
        model = self.model
        if model.request == "package_manager":
            model.request = ""
            if self.packages is None:
                self.packages = PackagePanel()
                self.packages.on_used = self.tour.notify_used
            self.package_window.show()
        if self.packages is None or not self.package_window.open:
            return
        if self.package_window.begin(box) == "close":
            self.package_window.hide()
        else:
            self.packages.draw_content()
        self.package_window.end()
        self.packages.draw_overlays(box)

    def _draw_progress(self, box: Any) -> None:
        """The window that shows the update's latest step while it is prepared (the Qt progress dialog)."""
        model = self.model
        window = self.progress_window
        if model.updating and not window.open:
            window.show()
        if not model.updating and window.open:
            window.hide()
        if not window.open:
            return
        window.begin(box)
        draw_sections(self.panels[_UPDATING]["sections"], model, self.progress_form, titles=False)
        window.end()

    # -- persistence ---------------------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict:
        """What is remembered: the two startup switches."""
        return self.model.export_settings()

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        self.model.restore_settings(settings)

    def close(self) -> None:
        """Detach the model's observers."""
        self.model._observers.clear()
        if self.packages is not None:
            self.packages.close()


def make_app() -> UpdaterApp:
    """Build the updater app (the manifest's ``entrypoints.emtk``)."""
    from chisurf.emtk.i18n import install

    install()
    return UpdaterApp()
