"""General ``path_list`` AutoForm section — a reusable file/folder drop list.

A drag-drop list of file paths bound to a model attribute, usable from any
``.view.json`` (like ``plot`` / ``image`` / ``waterfall``). Replaces the
hand-rolled drop-list widgets each batch tool used to copy.

Declare it with::

    {"type": "custom", "key": "path_list", "target": "batch_files",
     "options": {"extensions": [".sm", ".ptu"], "add_folders": true}}

``target`` names a model attribute holding a ``list[str]`` of paths; the section
reads it to populate and writes it back (then calls ``model.update()``) on every
change. Dropped folders are expanded recursively to files whose extension is in
``extensions`` (case-insensitive; empty ⇒ accept any file). Options: ``extensions``
(list), ``add_folders`` (bool, default True), ``dialog_filter`` (file-dialog
filter string), ``title`` (header label), ``mmfdb`` (bool, default True) — offer a
"select from the MMFDB database" button beside the file/folder buttons, ``mmfdb_kinds``
(list) and ``mmfdb_scope`` (str) to pre-filter that picker.

Because every file selector now routes through this one section, adding the MMFDB
button here is what gives *every* ``path_list`` "select from database" for free —
and since an MMFDB whose object store is S3-backed resolves datasets to a local
path transparently, that database may live behind an S3 endpoint without any
change here.
"""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtWidgets

from chisurf.gui.widgets.tools.chisurf_dock_tool import PathDropListWidget

from .registry import register_section

logger = logging.getLogger(__name__)


def _tool_button(text: str, tooltip: str, slot) -> QtWidgets.QToolButton:
    btn = QtWidgets.QToolButton()
    btn.setText(text)
    btn.setToolTip(tooltip)
    btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
    btn.clicked.connect(slot)
    return btn


class PathListWidget(QtWidgets.QWidget):
    """Drag-drop file/folder list bound to a model ``list[str]`` attribute.

    Emits :attr:`selectionChanged` (a ``list[str]`` of the selected paths) so a
    host can preview the highlighted entry — the mechanism that lets hand-built
    tools (e.g. the micro-time shifter) drop their own file lists and adopt this
    one. ``select_first`` (option) auto-selects the first row after a refresh when
    nothing is selected, so a bound preview always shows something.
    """

    #: marker so a hosting dock panel gives this section the spare vertical space.
    _autoform_expanding = True

    #: emitted with the list of currently-selected path strings on any change.
    selectionChanged = QtCore.Signal(list)

    def __init__(self, model, target: str, **options):
        super().__init__()
        self._model = model
        self._target = target
        self._exts = {e.lower() for e in (options.get("extensions") or [])}
        self._add_folders = bool(options.get("add_folders", True))
        self._dialog_filter = options.get("dialog_filter") or self._default_filter()
        self._mmfdb = bool(options.get("mmfdb", True))
        self._mmfdb_kinds = options.get("mmfdb_kinds")
        self._mmfdb_scope = options.get("mmfdb_scope", "all")
        self._select_first = bool(options.get("select_first", False))

        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        if options.get("title"):
            header = QtWidgets.QLabel(str(options["title"]))
            header.setStyleSheet("font-weight: bold; padding: 2px;")
            layout.addWidget(header)

        self._list = PathDropListWidget(path_filter=self._accepts)
        self._list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self._list.pathsDropped.connect(self._on_dropped)
        self._list.itemSelectionChanged.connect(self._emit_selection)
        layout.addWidget(self._list, 1)

        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(_tool_button("➕ Files", "Add files.", self._add_files))
        if self._add_folders:
            bar.addWidget(
                _tool_button("📁 Folder", "Add a folder (scanned recursively).", self._add_folder)
            )
        if self._mmfdb:
            bar.addWidget(
                _tool_button(
                    "🗄 Database",
                    "Select a dataset from the MMFDB database "
                    "(including S3-backed object stores).",
                    self._add_from_mmfdb,
                )
            )
        bar.addWidget(_tool_button("➖ Remove", "Remove selected entries.", self._remove_selected))
        bar.addWidget(_tool_button("🗑 Clear", "Clear the list.", self._clear))
        bar.addStretch(1)
        layout.addLayout(bar)

        self._refresh_from_model()

    # ── filtering / expansion ───────────────────────────────────────────
    def _accepts(self, local_path: str) -> bool:
        p = pathlib.Path(local_path)
        if p.is_dir():
            return self._add_folders
        return not self._exts or p.suffix.lower() in self._exts

    def _default_filter(self) -> str:
        if not self._exts:
            return "All Files (*)"
        pattern = " ".join(f"*{e}" for e in sorted(self._exts))
        return f"Files ({pattern});;All Files (*)"

    def _expand(self, paths: list[str]) -> list[str]:
        out: list[str] = []
        for item in paths:
            p = pathlib.Path(item)
            if p.is_file():
                out.append(str(p))
            elif p.is_dir() and self._add_folders:
                out.extend(
                    str(f)
                    for f in sorted(p.rglob("*"))
                    if f.is_file() and (not self._exts or f.suffix.lower() in self._exts)
                )
        return out

    # ── model binding ───────────────────────────────────────────────────
    def _current(self) -> list[str]:
        value = getattr(self._model, self._target, None)
        return list(value) if isinstance(value, list) else []

    def _commit(self, paths: list[str]) -> None:
        # de-duplicate while preserving order
        seen: set[str] = set()
        unique = [p for p in paths if not (p in seen or seen.add(p))]
        setattr(self._model, self._target, unique)
        self._refresh_list(unique)
        try:
            self._model.update()
        except Exception:
            pass

    def _add(self, paths: list[str]) -> None:
        self._commit(self._current() + self._expand(paths))

    def _refresh_from_model(self) -> None:
        self._refresh_list(self._current())

    def _refresh_list(self, paths: list[str]) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        self._list.addItems(paths)
        self._list.blockSignals(False)
        if self._select_first and paths and not self._list.selectedItems():
            # setCurrentRow re-enables signals' effect and emits itemSelectionChanged.
            self._list.setCurrentRow(0)

    def _emit_selection(self) -> None:
        self.selectionChanged.emit(self.selected_paths())

    # ── actions ─────────────────────────────────────────────────────────
    def _on_dropped(self, paths: list) -> None:
        self._add([str(p) for p in paths])

    def _add_files(self) -> None:
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Add files", "", self._dialog_filter
        )
        if files:
            self._add(list(files))

    def _add_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Add a folder")
        if folder:
            self._add([folder])

    def _add_from_mmfdb(self) -> None:
        # The database resolves the chosen dataset to a local path (fetching from
        # its object store, local or S3), so the picked path flows through the
        # same _add() as a dropped file — extension filtering and de-duplication
        # included.
        from chisurf.gui.widgets.mmfdb import picker

        client = picker.inprocess_client()
        if client is None:
            QtWidgets.QMessageBox.information(
                self,
                "MMFDB",
                "No MMFDB database is available in this session.",
            )
            return
        paths = picker.pick_local_paths(
            parent=self, kinds=self._mmfdb_kinds, scope=self._mmfdb_scope, client=client
        )
        if paths:
            self._add([str(p) for p in paths])

    def _remove_selected(self) -> None:
        remove = {it.text() for it in self._list.selectedItems()}
        if remove:
            self._commit([p for p in self._current() if p not in remove])

    def _clear(self) -> None:
        self._commit([])

    # ── public API (for standalone hosts / tests) ───────────────────────
    def add_paths(self, paths: list) -> None:
        """Add files/folders (folders expanded, extension-filtered, de-duplicated)."""
        self._add([str(p) for p in paths])

    def paths(self) -> list[str]:
        """Return the current ordered list of file paths."""
        return self._current()

    def clear(self) -> None:
        """Remove all entries."""
        self._clear()

    def selected_paths(self) -> list[str]:
        """Return the paths of the currently-selected entries."""
        return [it.text() for it in self._list.selectedItems()]

    def select_index(self, index: int) -> None:
        """Select the row at *index* (no-op if out of range)."""
        if 0 <= index < self._list.count():
            self._list.setCurrentRow(index)

    def expand(self, paths: list[str]) -> list[str]:
        """Expand *paths* (files + folders) to the accepted file list."""
        return self._expand(paths)


@register_section("path_list")
def _path_list_section_factory(model, target: str, **options):
    """Custom-section factory for the general file/folder drop list."""
    return PathListWidget(model, target, **options)


__all__ = ["PathListWidget"]
