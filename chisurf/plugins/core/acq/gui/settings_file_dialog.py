"""The Record tool's *Load …* chooser for acquisition settings files.

A real emtk file chooser (``emtk.file_dialog.FileDialog`` in an
``emtk.dialog_window.DialogWindow``, the same pair the save dialog uses) over ``.json`` settings
files, ``.ptu`` measurements and ``.pto`` containers. It is a small helper between the view and
the model:

* the model asks for it -- :meth:`~chisurf.plugins.core.acq.gui.record_settings.LaserSettingsMixin.request_settings_file`
  sets :attr:`~chisurf.plugins.core.acq.gui.record_app.RecordModel.settings_file_requested`;
* the host app draws it -- one call, ``helper.draw(box)``, every frame;
* nothing loads while the user browses -- the chosen file reaches the model
  (:meth:`~chisurf.plugins.core.acq.gui.record_settings.LaserSettingsMixin.load_settings_path`,
  which reads and adopts it) only on the frame *Open* is pressed. *Cancel* and the window's ``×``
  read nothing and connect nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from emtk.i18n import tr

#: What the chooser lists first, and what the model reads behind each pattern: a settings
#: document (``settings_file.load``), a PTU measurement or a PTO container
#: (``settings_file.from_address``).
FILTERS = (
    (tr("Settings & measurements"), ("*.json", "*.ptu", "*.pto")),
)


class SettingsFileDialog:
    """The open-file chooser for acquisition settings, driven by the model's request flag.

    The host keeps one instance and calls :meth:`draw` once a frame with its frame box. While
    :meth:`draw` returns True the chooser is on screen and the host must draw nothing clickable
    beneath it: the chooser is a modal DialogWindow (its backdrop washes and blurs what is
    behind), but it cannot keep a host table that shares the frame from taking the click -- draw
    the background inert (a separate ``emtk.frame`` with its own storage and
    ``im.begin_disabled()``), then this on top, or draw only the chooser while it is open.
    """

    def __init__(self, model: Any, directory: str | Path | None = None) -> None:
        self.model = model
        #: where the chooser starts; the model's output folder unless told otherwise
        self.directory = None if directory is None else Path(directory)
        self.dialog: Any | None = None
        self.window: Any | None = None

    @property
    def open(self) -> bool:
        """Whether the chooser is on screen."""
        return self.dialog is not None

    def draw(self, box: tuple[float, float, float, float]) -> bool:
        """One frame of the chooser. Opens on the model's request, loads on Open.

        Returns True while the chooser is on screen (see the modal note in the class
        docstring), False otherwise.
        """
        if getattr(self.model, "settings_file_requested", False):
            self.model.settings_file_requested = False
            if self.dialog is None:  # a repeated request must not discard the open browse
                self._open_dialog()
        if self.dialog is None:
            return False
        pressed = self.window.begin(box)
        result = self.dialog.draw()
        self.window.end()
        if result:
            path = result[0]
            self._close()
            apply_path = getattr(self.model, "load_settings_path_async", None)
            (apply_path or self.model.load_settings_path)(path)  # async: never block the frame
        elif result is False or pressed == "close":
            self._close()
        return self.open

    # ------------------------------------------------------------------------------------------ #
    def _open_dialog(self) -> None:
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        previous = getattr(self.model, '_simulation_previous', {})
        directory = str(self.directory or previous.get('output_dir')
                        or getattr(self.model, "output_dir", "") or "")
        title = tr("Load acquisition settings")
        self.dialog = FileDialog(
            title,
            mode="open",
            filters=[(label, list(patterns)) for label, patterns in FILTERS],
            directory=directory,
        )
        self.window = DialogWindow(title, size=(720.0, 500.0))
        self.window.show()

    def _close(self) -> None:
        self.dialog = None
        self.window = None
