"""New-style GUI entrypoint for the TTTR Split / Convert tool.

:class:`PTUSplitter` is a thin :class:`~qtpy.QtWidgets.QWidget` hosting the EMTK
app in :mod:`.app` (:class:`SplitterApp`) over the Qt-free
:class:`~..gui.view_model.SplitterViewModel`. OS file drops on this window load
the input file.
"""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtWidgets

from .view_model import SplitterViewModel

logger = logging.getLogger(__name__)


class PTUSplitter(QtWidgets.QWidget):
    """TTTR file splitter / container converter with an inline batch panel."""

    name = "TTTR Split / Convert"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TTTR Split / Convert")
        self.setMinimumWidth(420)

        self._model = SplitterViewModel()
        #: 0–100 percentage of the single-file split run.
        self.run_progress: int = 0
        self.run_running: bool = False
        #: (files done, files total) of the batch run.
        self.batch_progress: tuple[int, int] = (0, 0)
        self.batch_running: bool = False

        from emtk.qt_host import ControlHost

        from .app import WINDOW_BG, SplitterApp

        self.app = SplitterApp(
            self,
            on_browse_input=self._browse_input,
            on_browse_output=self._browse_output,
            on_run=self._run,
            on_add_batch_files=self._add_batch_files,
            on_add_batch_folder=self._add_batch_folder,
            on_clear_batch=self._clear_batch,
            on_run_batch=self._start_batch,
        )
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.host)

        # The input line edit accepted a dropped file; the whole window does now.
        self.setAcceptDrops(True)

    # ── drag & drop ──────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if len(urls) == 1:
            path = urls[0].toLocalFile()
            if pathlib.Path(path).is_file():
                self.load_input(path)

    # ── loading ──────────────────────────────────────────────────────

    def load_input(self, path: str) -> None:
        """Load *path* as the TTTR input, as the old picker row did."""
        if not path:
            return
        p = pathlib.Path(path)
        if not p.is_file():
            from chisurf.gui import dialogs

            dialogs.warning(self, "Invalid file", f"'{path}' is not a valid file.")
            return
        import tttrlib

        from chisurf.gui.widgets.staged_loading import load_with_progress

        tttr_type = self._model.tttr_type

        def _load(local_path):
            if tttr_type is None:
                return tttrlib.TTTR(local_path)
            return tttrlib.TTTR(local_path, tttr_type)

        tttr = load_with_progress(self, _load, str(p), title="Loading TTTR file")
        if tttr is None:
            return
        self._model.set_tttr(tttr, str(p))
        self.host.update()

    def _browse_input(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select TTTR file")
        if path:
            self.load_input(path)

    def _browse_output(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self._model.output_folder = folder
            self.host.update()

    # ── the single-file run ──────────────────────────────────────────

    def _run(self) -> None:
        if self.run_running:
            return
        from chisurf.gui import dialogs

        reason = self._model.can_split()
        if reason is not None:
            dialogs.warning(self, "Cannot split", reason)
            return
        self.run_running = True

        def progress_cb(percent: int) -> None:
            self.run_progress = int(percent)
            self.host.update()

        try:
            self._model.do_split(progress_cb=progress_cb)
        except Exception as exc:  # noqa: BLE001
            dialogs.error(self, "Split failed", str(exc))
        finally:
            self.run_running = False
            self.run_progress = 100
            self.host.update()

    # ── the batch run ────────────────────────────────────────────────

    def _add_batch_files(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select PTU files")
        self._queue_batch_paths(paths or [])
        self.host.update()

    def _add_batch_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select a folder of PTU files")
        if not folder:
            return
        self._queue_batch_paths(sorted(pathlib.Path(folder).rglob("*")))
        self.host.update()

    def _queue_batch_paths(self, paths) -> None:
        known = set(self._model.batch_files)
        for path in paths:
            text = str(path)
            if pathlib.Path(text).suffix.lower() == ".ptu" and text not in known:
                self._model.batch_files.append(text)
                known.add(text)

    def _add_batch_database(self) -> None:
        from chisurf.gui import dialogs
        from chisurf.gui.widgets.mmfdb import picker

        client = picker.inprocess_client()
        if client is None:
            dialogs.information(self, "MMFDB", "No MMFDB database is available in this session.")
            return
        self._queue_batch_paths(picker.pick_local_paths(parent=self, client=client))
        self.host.update()

    def _clear_batch(self) -> None:
        self._model.batch_files = []
        self.batch_progress = (0, 0)
        self.host.update()

    def _start_batch(self) -> None:
        if self.batch_running:
            return
        from chisurf.gui import dialogs

        if not self._model.batch_files:
            dialogs.information(self, "No files", "Add PTU files or folders first.")
            return
        self.batch_running = True
        count = 0

        def file_progress_cb(index: int, total: int, path: str) -> None:
            self.batch_progress = (index, total)
            self.host.update()

        try:
            count = self._model.run_batch(file_progress_cb=file_progress_cb)
            dialogs.information(self, "Batch complete", f"Processed {count} file(s).")
        except Exception as exc:  # noqa: BLE001
            dialogs.error(self, "Batch failed", str(exc))
        finally:
            self.batch_running = False
            self.host.update()

    # ── the AutoForm-era surface ─────────────────────────────────────

    @property
    def auto_form(self):
        """A shim whose sync/refresh repaint the canvas."""
        return self

    def sync_fields(self) -> None:
        if hasattr(self, "host"):
            self.host.update()

    def refresh_plots(self) -> None:
        if hasattr(self, "host"):
            self.host.update()
