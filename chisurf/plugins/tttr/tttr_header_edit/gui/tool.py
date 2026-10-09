"""New-style GUI entrypoint for the TTTR Header Editor tool.

:class:`TagsEditor` is a thin :class:`~qtpy.QtWidgets.QWidget` hosting the EMTK
app in :mod:`.app` (:class:`HeaderEditorApp`) over the Qt-free
:class:`~..gui.view_model.HeaderEditorViewModel`. The editor reads any
``tttrlib`` container (PTU/HT3/SPC/HDF5) and saves the edited header as PTU.
``TagsEditor`` keeps a compatible no-arg / optional-``json_data`` signature,
and a dropped file is opened.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from . import sections  # noqa: F401  (side effect: register the custom section)
from .view_model import HeaderEditorViewModel

logger = logging.getLogger(__name__)


class TagsEditor(QtWidgets.QWidget):
    """View and edit TTTR (PTU/HT3/SPC/HDF5) header tags, then write a PTU."""

    def __init__(self, json_data: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TTTR Header Editor")
        self.setMinimumSize(640, 480)

        self.model = HeaderEditorViewModel()
        if json_data:
            try:
                self.model.load_json(json_data)
            except Exception:
                logger.warning("TTTR header: could not load initial json_data", exc_info=True)

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, HeaderEditorApp

        self.app = HeaderEditorApp(self, on_open=self._open, on_save=self._save)
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.host)

        # A dropped file is opened, like the old section's drop target.
        self.setAcceptDrops(True)

        self.model.add_observer(self._on_model_event)

    # ── the AutoForm-era surface ─────────────────────────────────────

    @property
    def auto_form(self):
        """A shim whose sync repaints the canvas."""
        return self

    def sync_fields(self) -> None:
        if hasattr(self, "host"):
            self.host.update()

    # ── model events ─────────────────────────────────────────────────

    def _on_model_event(self, event: str) -> None:
        if event == "loaded" and hasattr(self, "app"):
            # A new header arrived (Open or a drop): rebuild the editors.
            self.app.header_gui.rebuild_rows()
        if hasattr(self, "host"):
            self.host.update()

    # ── drag & drop ──────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if urls:
            self._load_file(urls[0].toLocalFile())
            event.acceptProposedAction()

    # ── actions ──────────────────────────────────────────────────────

    def _open(self) -> None:
        from .view_model import OPEN_FILTER

        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open TTTR File", "", OPEN_FILTER)
        if path:
            self._load_file(path)

    def _load_file(self, path: str) -> None:
        from chisurf.gui import dialogs

        try:
            self.model.load_file(path)
        except Exception as exc:  # noqa: BLE001
            dialogs.warning(self, "Error", f"Failed to open file:\n{exc}")

    def _save(self) -> None:
        from chisurf.gui import dialogs

        reason = self.model.can_save()
        if reason is not None:
            dialogs.warning(self, "Cannot save", reason)
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save edited header as PTU", "", "PTU Files (*.ptu);;All Files (*)"
        )
        if not path:
            return
        try:
            self.model.save(path)
            dialogs.information(self, "Success", "Edited header saved as PTU.")
        except Exception as exc:  # noqa: BLE001
            dialogs.warning(self, "Error", f"Failed to save:\n{exc}")
