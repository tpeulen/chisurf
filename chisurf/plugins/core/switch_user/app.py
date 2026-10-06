"""Native emtk switch-user window: sign in to the MMFDB as another account.

The form, the buttons and the status line are the view spec ``switch_user_emtk.view.json``
drawn by :func:`emtk.view_form.draw_sections`; only the logo header, the Help / Guide buttons
and the message-box window are drawn here. State and work are in
:class:`~.model.SwitchUserModel`; the sign-in runs on a :class:`~chisurf.emtk.jobs.SnapshotJob`
because the server may take seconds to answer.
"""

from __future__ import annotations

import json
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.jobs import SnapshotJob

from .model import SwitchUserModel
from .strings import install_translations

install_translations()

HERE = Path(__file__).parent


def _logo() -> Path:
    import chisurf

    return Path(chisurf.__file__).parent / "gui" / "resources" / "icons" / "cs_logo.png"


class SwitchUserApp(ImApp):
    """The MMFDB login as an emtk window."""

    def __init__(self, model: SwitchUserModel | None = None, client=None) -> None:
        if model is None:
            factory = (lambda mode, server, port: client) if client is not None else None
            model = SwitchUserModel(client_factory=factory)
        self.model = model
        self.job = SnapshotJob(self.model)
        spec = json.loads((HERE / "switch_user_emtk.view.json").read_text(encoding="utf-8"))
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        self.notice_form = FormState()
        self.notice_window = DialogWindow(
            "Notice", size=(380.0, 110.0), key="switch_user_notice", fit_height=True
        )
        self.item_rects: dict = {}
        self._reported_error = ""
        self.help_window = EmTkHelpWindow(
            title="Switch User — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        self.model.runner = self.start_job
        super().__init__(self.render, continuous=True)

    # -- jobs -------------------------------------------------------------
    def start_job(self, method: str) -> bool:
        """Run the model method *method* on a snapshot in a worker thread."""
        self._reported_error = ""
        return self.job.start(method)

    # -- one frame --------------------------------------------------------
    def render(self) -> None:
        self.job.poll()
        self.model.busy = self.job.busy
        if self.job.error and self.job.error != self._reported_error:
            self._reported_error = self.job.error
            self.model.notices.append(("error", "Error", f"Login failed: {self.job.error}"))
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        if im.begin("Switch User", box):
            self._header()
            draw_sections(self.panels["login"]["sections"], self.model, self.form, titles=False)
        im.end()
        self._draw_notice(box)
        if self.model.closed and not self.close_requested:
            self.request_close()
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _header(self) -> None:
        if _logo().exists():
            im.image(_logo(), size=(48.0, 48.0))
            im.same_line()
        im.heading("ChiSurf", level=1)
        im.text("Sign in to the MMFDB workspace")
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip(
            "Explain the fields, the two remember options and what happens on Login."
        )
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through signing in as another account.")
        self.item_rects["guide"] = im.get_item_rect()
        im.separator()

    def _draw_notice(self, box) -> None:
        model = self.model
        if model.notices and not self.notice_window.open:
            self.notice_window.show()
        if not model.notices and self.notice_window.open:
            self.notice_window.hide()
        if not self.notice_window.open:
            return
        self.notice_window.title = model.notice_title or "Notice"
        pressed = self.notice_window.begin(box)
        draw_sections(self.panels["notice"]["sections"], model, self.notice_form, titles=False)
        self.notice_window.end()
        if pressed == "close":
            model.dismiss_notice()

    # -- persistence ------------------------------------------------------
    def export_settings(self) -> dict:
        """Nothing is kept here: the account and server live in the ``mmfdb`` settings, as with Qt.

        The password is never stored.
        """
        return {}

    def restore_settings(self, settings: dict) -> None:
        """Accept (and ignore) state saved by earlier versions; settings come from ``mmfdb``."""

    def close(self) -> None:
        """Forget a typed password and detach observers."""
        self.model.password = ""
        self.model._observers.clear()


def make_app() -> SwitchUserApp:
    """Build the switch-user app (the manifest's ``entrypoints.emtk``)."""
    return SwitchUserApp()
