"""AutoForm ``data_source`` section: pick one input file — from disk or the database.

Every analysis tool starts the same way: *which measurement do I analyse?* The
plain ``value``/``file`` field only answers half of that, because a dataset may
live on disk **or** be registered in the MMFDB object store (possibly on an
S3-compatible endpoint). This section is the single control for both, the
one-file counterpart of the ``path_list`` section:

* a path field (typeable, remembers the last directory),
* **📂 Browse** — a file dialog,
* **🗄 Database** — the shared MMFDB dataset picker, which resolves the chosen
  artifact to a *local* path (the database is the only place object-store/S3
  access lives), and
* drag-and-drop of a file onto the field.

Declare it in a view spec::

    {"type": "custom", "key": "data_source",
     "options": {"attr": "filename", "call": "set_filename",
                 "label": "Image", "filter": "Images and photon data (*.pto *.tif *.ptu);;All files (*)",
                 "mmfdb_kinds": ["raw_measurement"]}}

Options:

* ``attr`` (str) — model attribute receiving the chosen path.
* ``call`` (str) — model method invoked with the path after a pick (e.g.
  ``set_filename``); when the model has one, it is the only writer that needs to
  react (it may itself set ``attr``).
* ``label`` (str, default ``"File"``) — caption left of the field (``""`` hides it).
* ``description`` (str) — tooltip for the whole control.
* ``filter`` (str) — file-dialog filter string.
* ``extensions`` (list of str) — accepted drop suffixes (default: everything).
* ``mmfdb`` (bool, default ``True``) — show the database button.
* ``mmfdb_kinds`` (list) / ``mmfdb_scope`` (str) — pre-filter the dataset picker.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from qtpy import QtCore, QtWidgets

from chisurf.gui.glyphs import Glyphs

from .registry import register_section
from chisurf.gui import dialogs

logger = logging.getLogger(__name__)


@register_section("data_source")
class DataSourceSection(QtWidgets.QWidget):
    """One-file input: path field + browse + MMFDB picker + drag-and-drop."""

    #: marker so ``AutoForm.sync_fields``/``refresh_plots`` re-read this widget.
    AUTOFORM_REFRESH = True
    is_form_field = False

    def __init__(self, model=None, target: str | None = None, **options: Any):
        super().__init__()
        self._model = model
        self._attr = options.get("attr") or target or ""
        self._call = options.get("call") or ""
        self._filter = str(options.get("filter", "All files (*)"))
        self._extensions = tuple(
            str(e).lower() if str(e).startswith(".") else f".{str(e).lower()}"
            for e in (options.get("extensions") or ())
        )
        self._mmfdb = bool(options.get("mmfdb", True))
        self._mmfdb_kinds = options.get("mmfdb_kinds")
        self._mmfdb_scope = str(options.get("mmfdb_scope", "all"))

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = str(options.get("label", "File"))
        if label:
            caption = QtWidgets.QLabel(label)
            layout.addWidget(caption)

        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText(
            str(options.get("placeholder", "pick a file, drop one here, or load from the database"))
        )
        self.edit.editingFinished.connect(lambda: self._commit(self.edit.text()))
        layout.addWidget(self.edit, 1)

        self.btn_browse = QtWidgets.QToolButton()
        self.btn_browse.setText(Glyphs.OPEN)
        self.btn_browse.setToolTip("Browse for a file on disk")
        self.btn_browse.clicked.connect(self._browse)
        layout.addWidget(self.btn_browse)

        self.btn_mmfdb: QtWidgets.QToolButton | None = None
        if self._mmfdb:
            self.btn_mmfdb = QtWidgets.QToolButton()
            self.btn_mmfdb.setText(Glyphs.DATABASE)
            self.btn_mmfdb.setToolTip(
                "Load a dataset registered in the database. The database resolves it "
                "to a local file, wherever its object store keeps the data."
            )
            self.btn_mmfdb.clicked.connect(self._from_mmfdb)
            layout.addWidget(self.btn_mmfdb)

        description = str(options.get("description", ""))
        if description:
            for widget in (self, self.edit):
                widget.setToolTip(description)

        self.setAcceptDrops(True)
        self.sync()

    # ── value plumbing ──
    def _current(self) -> str:
        """Return the model's current path (empty when unset)."""
        if self._model is None or not self._attr:
            return ""
        return str(getattr(self._model, self._attr, "") or "")

    def _commit(self, path: str) -> None:
        """Write *path* to the model, preferring the model's own setter."""
        path = str(path or "")
        if path == self._current():
            return
        if self._model is None:
            return
        fn = getattr(self._model, self._call, None) if self._call else None
        if callable(fn):
            try:
                fn(path)
            except Exception:
                logger.debug("data_source: %r failed", self._call, exc_info=True)
                return
        elif self._attr:
            try:
                setattr(self._model, self._attr, path)
            except Exception:
                logger.debug("data_source: cannot set %r", self._attr, exc_info=True)
                return
        self.sync()

    def sync(self) -> None:
        """Re-read the model value into the field without firing signals."""
        current = self._current()
        if current != self.edit.text():
            self.edit.blockSignals(True)
            self.edit.setText(current)
            self.edit.setCursorPosition(len(current))
            self.edit.blockSignals(False)

    def refresh(self) -> None:
        """Alias of :meth:`sync`."""
        self.sync()

    # ── pickers ──
    def _browse(self) -> None:
        """Open a file dialog starting in the current file's directory."""
        start = ""
        current = self._current()
        if current:
            start = str(pathlib.Path(current).parent)
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select a file", start, self._filter)
        if path:
            self._commit(path)

    def _from_mmfdb(self) -> None:
        """Pick a registered dataset and adopt the local path the database returns."""
        from chisurf.gui.widgets.mmfdb import picker

        client = picker.inprocess_client()
        if client is None:
            dialogs.information(
                self, "Database", "No MMFDB database is available in this session."
            )
            return
        paths = picker.pick_local_paths(
            parent=self, kinds=self._mmfdb_kinds, scope=self._mmfdb_scope, client=client
        )
        if paths:
            self._commit(str(paths[0]))

    # ── drag & drop ──
    def _accepts(self, path: str) -> bool:
        """Return whether *path* passes the configured extension filter."""
        return not self._extensions or pathlib.Path(path).suffix.lower() in self._extensions

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        """Accept a dragged local file that passes the extension filter."""
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(u.isLocalFile() and self._accepts(u.toLocalFile()) for u in urls):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        """Adopt the first dropped file."""
        for url in event.mimeData().urls():
            if url.isLocalFile() and self._accepts(url.toLocalFile()):
                self._commit(url.toLocalFile())
                break
        event.acceptProposedAction()

    def supportedDropActions(self) -> QtCore.Qt.DropAction:
        """Return the supported drop actions."""
        return QtCore.Qt.DropAction.CopyAction


__all__ = ["DataSourceSection"]
