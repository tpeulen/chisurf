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
from chisurf.gui import dialogs

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

    ``checkable`` (option) gives every entry a tick box (default *checked*), adds
    ☑️ All / ☐ None buttons, exposes :meth:`checked_paths` and emits
    :attr:`checkChanged` — for tools that batch-process a user-selected subset.

    ``allow_duplicates`` (option) keeps repeated paths instead of de-duplicating
    (e.g. a homodimer that reuses one structure for two rigid bodies whose order
    encodes body id); removal is then by row position. It cannot be combined with
    ``checkable``. Use :meth:`set_paths` to load a stored list verbatim.
    """

    #: marker so a hosting dock panel gives this section the spare vertical space.
    _autoform_expanding = True

    #: ``AutoForm.sync_fields()`` re-reads this widget from its model. Without it
    #: a list filled programmatically -- a workflow handing a panel the files it
    #: produced, a restored project -- stayed empty on screen while the model
    #: held the paths, which reads as "the hand-off did not happen".
    AUTOFORM_REFRESH = True

    #: emitted with the list of currently-selected path strings on any change.
    selectionChanged = QtCore.Signal(list)
    #: emitted (checkable mode) with the list of checked path strings when a tick changes.
    checkChanged = QtCore.Signal(list)
    #: emitted with dropped path strings the ``path_filter`` rejected (for host warnings).
    rejectedPaths = QtCore.Signal(list)

    def __init__(self, model, target: str, **options):
        super().__init__()
        self._model = model
        self._target = target
        self._exts = {e.lower() for e in (options.get("extensions") or [])}
        # Optional host predicate ``path_filter(str) -> bool`` deciding whether a
        # file is accepted; overrides the extension check (e.g. to accept
        # compressed ``*.ptu.gz`` that a plain suffix test would miss).
        self._path_filter = options.get("path_filter")
        self._add_folders = bool(options.get("add_folders", True))
        self._dialog_filter = options.get("dialog_filter") or self._default_filter()
        self._mmfdb = bool(options.get("mmfdb", True))
        self._mmfdb_kinds = options.get("mmfdb_kinds")
        self._mmfdb_scope = options.get("mmfdb_scope", "all")
        self._select_first = bool(options.get("select_first", False))
        self._checkable = bool(options.get("checkable", False))
        # When True the same path may appear more than once (e.g. a homodimer that
        # reuses one structure for two rigid bodies) and removal is by row position
        # rather than path identity. Incompatible with ``checkable`` (tick state is
        # keyed on the path text), so the two must not be combined.
        self._allow_duplicates = bool(options.get("allow_duplicates", False))
        if self._allow_duplicates and self._checkable:
            raise ValueError("path_list: 'allow_duplicates' cannot be combined with 'checkable'")
        # When True a drop *replaces* the list (clear + add) instead of appending.
        self._replace_on_drop = bool(options.get("replace_on_drop", False))
        # Optional host hook: ``folder_expander(pathlib.Path) -> list[str]`` replaces
        # the default recursive extension-filtered scan when a folder is added
        # (e.g. a burst-analysis folder that maps to specific BUR/BST index files).
        self._folder_expander = options.get("folder_expander")
        # In checkable mode entries default to *checked*; only unchecked paths are
        # tracked, so the check state survives the widget's full-list refreshes.
        self._unchecked: set[str] = set()

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
        self._list.pathsRejected.connect(
            lambda paths: self.rejectedPaths.emit([str(p) for p in paths])
        )
        self._list.itemSelectionChanged.connect(self._emit_selection)
        if self._checkable:
            self._list.itemChanged.connect(self._on_item_changed)
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
                    "🗄️ Database",
                    "Select a dataset from the MMFDB database "
                    "(including S3-backed object stores).",
                    self._add_from_mmfdb,
                )
            )
        if self._checkable:
            bar.addWidget(_tool_button("☑️ All", "Check all entries.", lambda: self._set_all_checked(True)))
            bar.addWidget(_tool_button("☐ None", "Uncheck all entries.", lambda: self._set_all_checked(False)))
        bar.addWidget(_tool_button("➖ Remove", "Remove selected entries.", self._remove_selected))
        bar.addWidget(_tool_button("🗑️ Clear", "Clear the list.", self._clear))
        bar.addStretch(1)
        layout.addLayout(bar)

        self._refresh_from_model()

    # ── filtering / expansion ───────────────────────────────────────────
    def _accepts(self, local_path: str) -> bool:
        p = pathlib.Path(local_path)
        if p.is_dir():
            return self._add_folders
        if self._path_filter is not None:
            return bool(self._path_filter(local_path))
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
                if self._folder_expander is not None:
                    out.extend(str(x) for x in self._folder_expander(p))
                else:
                    out.extend(
                        str(f) for f in sorted(p.rglob("*")) if f.is_file() and self._accepts(str(f))
                    )
        return out

    # ── model binding ───────────────────────────────────────────────────
    def _current(self) -> list[str]:
        value = getattr(self._model, self._target, None)
        return list(value) if isinstance(value, list) else []

    def _commit(self, paths: list[str]) -> None:
        if self._allow_duplicates:
            committed = list(paths)
        else:
            # de-duplicate while preserving order
            seen: set[str] = set()
            committed = [p for p in paths if not (p in seen or seen.add(p))]
        setattr(self._model, self._target, committed)
        # forget check state for paths no longer present
        self._unchecked &= set(committed)
        self._refresh_list(committed)
        try:
            self._model.update()
        except Exception:
            pass

    def _add(self, paths: list[str]) -> None:
        self._commit(self._current() + self._expand(paths))

    def sync(self) -> None:
        """Re-read the bound list from the model (see ``AUTOFORM_REFRESH``)."""
        self._refresh_from_model()

    def _refresh_from_model(self) -> None:
        self._refresh_list(self._current())

    def _refresh_list(self, paths: list[str]) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        if self._checkable:
            for p in paths:
                item = QtWidgets.QListWidgetItem(p)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(
                    QtCore.Qt.Unchecked if p in self._unchecked else QtCore.Qt.Checked
                )
                self._list.addItem(item)
        else:
            self._list.addItems(paths)
        self._list.blockSignals(False)
        if self._select_first and paths and not self._list.selectedItems():
            # setCurrentRow re-enables signals' effect and emits itemSelectionChanged.
            self._list.setCurrentRow(0)

    def _emit_selection(self) -> None:
        self.selectionChanged.emit(self.selected_paths())

    # ── checkable mode ──────────────────────────────────────────────────
    def _on_item_changed(self, item) -> None:
        """Track an item's tick (default-checked model) and notify."""
        text = item.text()
        if item.checkState() == QtCore.Qt.Checked:
            self._unchecked.discard(text)
        else:
            self._unchecked.add(text)
        self.checkChanged.emit(self.checked_paths())

    def _set_all_checked(self, checked: bool) -> None:
        if checked:
            self._unchecked.clear()
        else:
            self._unchecked = set(self._current())
        self._refresh_list(self._current())
        self.checkChanged.emit(self.checked_paths())

    def checked_paths(self) -> list[str]:
        """Return the checked paths in order (all paths when not in checkable mode)."""
        return [p for p in self._current() if p not in self._unchecked]

    # ── actions ─────────────────────────────────────────────────────────
    def _on_dropped(self, paths: list) -> None:
        strs = [str(p) for p in paths]
        if self._replace_on_drop:
            self._commit(self._expand(strs))  # replace the list with the dropped set
        else:
            self._add(strs)

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
            dialogs.information(
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
        # Remove by row position so a duplicated path (allow_duplicates) drops only
        # the selected occurrence; positions map 1:1 to the current list because the
        # displayed items mirror it in order.
        rows = sorted((self._list.row(it) for it in self._list.selectedItems()), reverse=True)
        if rows:
            current = self._current()
            for r in rows:
                if 0 <= r < len(current):
                    del current[r]
            self._commit(current)

    def _clear(self) -> None:
        self._commit([])

    # ── public API (for standalone hosts / tests) ───────────────────────
    def add_paths(self, paths: list) -> None:
        """Add files/folders (folders expanded, extension-filtered, de-duplicated)."""
        self._add([str(p) for p in paths])

    def set_paths(self, paths: list) -> None:
        """Replace the list with *paths* verbatim.

        Unlike :meth:`add_paths` the paths are neither folder-expanded nor
        existence-filtered — order (and, when ``allow_duplicates`` is set,
        repeats) is preserved exactly. Use it to load a stored list (e.g. a saved
        project's file set) where entries must round-trip even if a referenced
        file is momentarily missing.
        """
        self._commit([str(p) for p in paths])

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
