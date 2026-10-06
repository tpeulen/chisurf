"""Native Global View: the emtk surface with the host services the Qt window gave it.

``GraphWizard`` (the Qt tool) hosts the same :class:`.surface.GlobalViewSurface`
and answers the model's requests -- a file to save or open, a warning, the help
modal, the guided tour, a refresh when a fit changes, and where the dock layout
is kept. This app answers them in emtk, so the surface works without Qt.

File choices are frame-driven here (an in-app :class:`emtk.file_dialog.FileDialog`)
while the model asks synchronously, as a Qt dialog answers. The ask hook opens
the dialog and answers "nothing yet"; when the user picks a file the action runs
again with a hook that answers the chosen path, so the model's code is the Qt
tool's, unchanged.
"""

from __future__ import annotations

import sys
import typing
from pathlib import Path

from emtk import im
from emtk.dialog_window import DialogWindow
from emtk.docking import LayoutStore
from emtk.file_dialog import FileDialog

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from .model import GlobalViewModel
from .surface import GlobalViewSurface

HERE = Path(__file__).parent

#: The model's file requests, by the title it asks with: (action, dialog mode).
FILE_ACTIONS = {
    "Export parameters": ("export_parameters", "save"),
    "Save network": ("save_network", "save"),
    "Load network": ("load_network", "open"),
}

#: The fitting client lives under ``chisurf.gui``; it is only *used* when the
#: host already loaded it (inside ChiSurf), never imported from here.
_FITTING_CLIENT_MODULE = "chisurf.gui.widgets.fitting.fitting_client"


def _layout_store() -> LayoutStore | None:
    """The dock arrangement, kept where the Qt window keeps it."""
    try:
        from chisurf.core.settings import chisurf_settings_path
    except Exception:  # noqa: BLE001 - no settings folder: the layout is not kept
        return None
    return LayoutStore("globalview", path=chisurf_settings_path / "globalview_layout.json")


class GlobalViewApp(GlobalViewSurface):
    """The Global View window drawn by emtk alone."""

    def __init__(self, model: GlobalViewModel, store: LayoutStore | None = None) -> None:
        super().__init__(model, store=store, on_used=lambda name: self.tour.notify_used(name))
        self.dialog: FileDialog | None = None
        self._dialog_action: str = ""
        self.message: tuple[str, str] | None = None
        self.message_window = DialogWindow(
            "Global View", size=(420.0, 170.0), key="globalview-warning", fit_height=True
        )
        self.file_window = DialogWindow("File", size=(640.0, 460.0), key="globalview-file")
        self.help_window = EmTkHelpWindow(
            title="Global View — help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=self.rect_of,
            on_step_change=lambda _i, step: self.reveal(self.tour._target_key(step.get("target"))),
        )
        model.ask_open_path = self._ask_path
        model.ask_save_path = self._ask_path
        model.warn = self._warn
        model.open_help = self.help_window.show
        model.open_guide = self.tour.start
        self._fits_dirty = False
        self._subscriptions: list[tuple[typing.Any, str, typing.Callable]] = []
        self._subscribe_to_fit_events()

    # -- what the model asks of its host -----------------------------------
    def _ask_path(self, title: str, file_filter: str) -> str:
        action, mode = FILE_ACTIONS.get(title, ("", "save"))
        if not action:
            return ""
        name = {"export_parameters": "parameters.csv", "save_network": "network.gml"}.get(
            action, ""
        )
        self.dialog = FileDialog(title, mode=mode, filename=name, filters=file_filter)
        self._dialog_action = action
        self.file_window.title = title
        self.file_window.show()
        return ""  # nothing yet: the action runs again on the answer

    def answer_file(self, path: str) -> None:
        """Run the pending action with *path*, as if the Qt dialog had returned it."""
        action, self._dialog_action, self.dialog = self._dialog_action, "", None
        self.file_window.hide()
        if not action or not path:
            return
        if action == "load_network":
            self.model.load_network(path)
            return
        ask = self.model.ask_save_path
        self.model.ask_save_path = lambda *_args: path
        try:
            getattr(self.model, action)()
        finally:
            self.model.ask_save_path = ask

    def _warn(self, title: str, message: str) -> None:
        self.message = (str(title), str(message))
        self.message_window.title = str(title)
        self.message_window.show()

    # -- fit events (inside ChiSurf) ----------------------------------------
    def _subscribe_to_fit_events(self) -> None:
        module = sys.modules.get(_FITTING_CLIENT_MODULE)
        client = module.get_fitting_client() if module is not None else None
        if client is None:
            return
        for topic in ("fit.", "parameter."):

            def callback(*_args, **_kwargs):  # any thread: only a flag
                self._fits_dirty = True
                self.request_frame()

            client.subscribe(topic, callback)
            self._subscriptions.append((client, topic, callback))

    def fits_changed(self) -> None:
        """A fit or a parameter changed: catch up on the next frame (thread-safe)."""
        self._fits_dirty = True
        self.request_frame()

    # -- the frame ------------------------------------------------------------
    def _gui(self) -> None:
        if self._fits_dirty:
            self._fits_dirty = False
            self.model.fits_changed()
        super()._gui()
        frame = self.box
        if self.dialog is not None:
            pressed = self.file_window.begin(frame)
            result = self.dialog.draw()
            self.file_window.end()
            if result:
                self.answer_file(str(result[0]))
            elif result is False or pressed == "close":
                self.dialog, self._dialog_action = None, ""
            if self.dialog is None:
                self.file_window.hide()
        self._draw_message(frame)
        self.help_window.draw(frame)
        self.tour.draw(frame[2], frame[3])

    def _draw_message(self, frame) -> None:
        if not self.message_window.open or self.message is None:
            return
        pressed = self.message_window.begin(frame)
        im.text_wrapped(self.message[1])
        if im.button("OK"):
            pressed = "close"
        im.set_item_tooltip("Close this message.")
        self.message_window.end()
        if pressed == "close":
            self.message_window.hide()
            self.message = None

    # -- persistence ------------------------------------------------------------
    def export_settings(self) -> dict:
        """Nothing beyond the dock layout, as the Qt window.

        The Qt window kept its geometry (the host's ``settings_key``) and the
        dock arrangement in ``globalview_layout.json``; this app keeps the same
        layout file (:func:`_layout_store`, saved on close), and the View
        panel's settings start fresh in both.
        """
        return {}

    def restore_settings(self, settings: dict) -> None:
        """Accept and ignore a saved dict (see :meth:`export_settings`)."""
        return None

    def close(self) -> None:
        for client, topic, callback in self._subscriptions:
            try:
                client.unsubscribe(topic, callback)
            except Exception:  # noqa: BLE001 - teardown is best-effort
                pass
        self._subscriptions.clear()
        try:
            self.docks.save()
        except Exception:  # noqa: BLE001 - a layout not kept is not worth an error
            pass
        self.help_window.close()
        self.tour.stop()


def make_app(model: GlobalViewModel | None = None, remember_layout: bool = True) -> GlobalViewApp:
    model = model or GlobalViewModel()
    model.rebuild(force=True)
    return GlobalViewApp(model, store=_layout_store() if remember_layout else None)
