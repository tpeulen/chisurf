"""The reader control for MFD burst folders.

Almost all of it is the declarative form from ``mfd.view.json``. The one thing this
controller has to supply itself is the *file dialog*: an MFD dataset is a burst
**folder**, not a file, so the ordinary open-files dialog would ask for the wrong
thing and return a path the reader cannot use.
"""

from __future__ import annotations

import pathlib

from qtpy import QtWidgets

import chisurf as cs
from chisurf.gui.widgets.experiments import reader


class MFDController(reader.ExperimentReaderController, QtWidgets.QWidget):
    """Pick a burst-analysis folder and edit the reader's settings."""

    def __init__(self, *args, **kwargs):
        """Build the form over the reader's own view spec."""
        super().__init__(*args, **kwargs)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        label = QtWidgets.QLabel(
            "MFD: choose a burst-analysis folder (the one holding <code>bi4_bur</code>)."
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        reader_obj = getattr(self, "experiment_reader", None)
        self._settings_form = None
        if reader_obj is not None and hasattr(reader_obj, "view_spec"):
            from chisurf.gui.autoform import AutoForm

            self._settings_form = AutoForm(reader_obj, parent=self)
            layout.addWidget(self._settings_form)
        layout.addStretch(1)

    def get_filename(self) -> pathlib.Path:
        """Return the burst-analysis folder to load.

        A directory chooser rather than a file one: the dataset is a folder of
        ``.bur`` tables plus the measurements they point back into, and the reader
        accepts the analysis folder, its ``bi4_bur`` directory, or a ``.bur`` inside
        it.
        """
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Burst-analysis folder",
            "",
            QtWidgets.QFileDialog.ShowDirsOnly,
        )
        return pathlib.Path(directory) if directory else pathlib.Path("")

    @property
    def filename(self) -> str:
        """Return the chosen folder as a string."""
        return str(self.get_filename())

    def updateUI(self):
        """Refresh the settings form from the reader."""
        if self._settings_form is not None:
            try:
                self._settings_form.sync_fields()
            except Exception as exc:  # pragma: no cover - surfaced, not swallowed
                cs.logging.warning("MFD reader form could not refresh: %s", exc)
