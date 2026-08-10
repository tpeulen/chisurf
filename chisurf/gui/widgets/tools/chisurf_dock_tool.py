"""The one base class every ChiSurf tool window is built on.

`ChisurfDockTool` factors the boilerplate every tool re-implemented (drag-drop
of file/folder paths, a `DockArea` central widget, window-geometry persistence,
and metadata-store connectivity status) into one base, so fixes propagate and the
per-tool widget stays a thin view. `PathDropListWidget` is the byte-identical
drag-drop list the tools had copied.

A window that subclasses `QMainWindow` directly gets none of that and cannot be
reached by a fix to any of it, so `test/test_tool_window_base.py` fails on a new
one; its allowlist holds only the windows that are genuinely not tools (the
application's own main window, and the games).

The base performs **no** I/O or DB work on construction: it only
wires Qt widgets. MMFDB access is via the overridable `acquire_mmfdb_connection`
hook, called lazily on demand — never in `__init__`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.widgets.messages import MessagesMixin, Msg  # noqa: F401 (re-exported)
from chisurf.gui.widgets.tools.help_guide import HelpGuideMixin

#: A predicate over a local path string deciding whether a dropped path is accepted.
PathFilter = Callable[[str], bool]


def local_paths_from_event(
    event: QtGui.QDropEvent,
    *,
    require_exists: bool = False,
    path_filter: PathFilter | None = None,
) -> list[Path]:
    """Return local filesystem paths from a drop event's URLs.

    ``require_exists`` drops non-existent paths; ``path_filter`` (a predicate over
    the local path string) drops paths it rejects (e.g. unsupported extensions).
    """
    paths: list[Path] = []
    for url in event.mimeData().urls():
        local_path = url.toLocalFile()
        if not local_path:
            continue
        if path_filter is not None and not path_filter(local_path):
            continue
        path = Path(local_path)
        if require_exists and not path.exists():
            continue
        paths.append(path)
    return paths


class PathDropListWidget(QtWidgets.QListWidget):
    """List widget that accepts dropped file and folder paths.

    Emits :attr:`pathsDropped` with the dropped local paths (existing only).
    Pass ``path_filter`` to accept only matching paths (e.g. supported file
    extensions); without it, every existing dropped path is accepted. Existing
    paths the filter *rejects* are reported on :attr:`pathsRejected` so a host can
    warn about them (e.g. files that need a manual type selection) instead of
    silently discarding them. Previously duplicated verbatim in each transformer tool.
    """

    pathsDropped = QtCore.Signal(list)
    #: existing dropped paths rejected by ``path_filter`` (empty when none).
    pathsRejected = QtCore.Signal(list)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        path_filter: PathFilter | None = None,
    ) -> None:
        super().__init__(parent)
        self._path_filter = path_filter
        # A QListWidget starts with drops disabled, so without this the
        # overridden drag/drop handlers below are never reached and every drop
        # is silently rejected. DropOnly keeps the list from also starting
        # internal item drags; the viewport is what actually receives the OS
        # drag events an item view forwards to these handlers.
        self.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        """Accept URL drops (only when at least one passes the filter)."""
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        if self._path_filter is None:
            event.acceptProposedAction()
            return
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local and self._path_filter(local):
                event.acceptProposedAction()
                return
        event.ignore()

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        """Accept URL moves."""
        event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        """Emit accepted local paths, and any filter-rejected ones separately."""
        accepted: list[Path] = []
        rejected: list[Path] = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if not local:
                continue
            path = Path(local)
            if not path.exists():
                continue
            if self._path_filter is not None and not self._path_filter(local):
                rejected.append(path)
            else:
                accepted.append(path)
        if accepted:
            self.pathsDropped.emit(accepted)
        if rejected:
            self.pathsRejected.emit(rejected)
        event.acceptProposedAction()

    def supportedDropActions(self) -> QtCore.Qt.DropAction:
        """Return supported drop actions."""
        return QtCore.Qt.DropAction.CopyAction


class ChisurfDockTool(HelpGuideMixin, MessagesMixin, QtWidgets.QMainWindow):
    """Base for dockable transformer tools (drag-drop, docks, MMFDB status).

    Subclasses build their own widgets/docks/toolbar in ``__init__`` as before;
    this base adds window-level path drag-drop (dispatched to
    :meth:`on_paths_dropped`), window-geometry persistence helpers, lazy
    MMFDB-connectivity accessors, and declared non-modal messages. It accepts and
    forwards ``*args``/``**kwargs`` to ``QMainWindow`` so existing
    ``super().__init__(*args, **kwargs)`` calls keep working.

    Messages
    --------
    A tool declares the conditions it can be in as :class:`~chisurf.gui.widgets.messages.Msg`
    attributes on nested ``Error``/``Warning``/``Information`` classes, and raises
    or retracts them by name::

        class MyTool(ChisurfDockTool):
            class Error(ChisurfDockTool.Error):
                no_file = Msg("Load a TTTR file first.")

            def compute(self):
                if self.path is None:
                    self.Error.no_file()
                    return
                self.Error.no_file.clear()

    The messages appear in the tool's own status bar, which is created on first
    use, and stay there until retracted. Use :mod:`chisurf.gui.dialogs` for the
    other kind of message — a question, or an event the user must acknowledge
    now. See :mod:`chisurf.gui.widgets.messages`.
    """

    #: QSettings application key for window-geometry persistence; override per tool.
    tool_settings_name: str = "ChisurfDockTool"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)

    # -- drag & drop ----------------------------------------------------------

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        """Accept file URL drops on the main window."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        """Dispatch dropped local paths to :meth:`on_paths_dropped`."""
        paths = local_paths_from_event(event)
        if paths:
            self.on_paths_dropped(paths)
        event.acceptProposedAction()

    def on_paths_dropped(self, paths: list[Path]) -> None:
        """Handle paths dropped on the window.

        Default: forward to ``self._add_paths`` when the subclass defines it
        (the established convention); otherwise no-op. Override to customise.
        """
        add_paths = getattr(self, "_add_paths", None)
        if callable(add_paths):
            add_paths(paths)

    # -- toolbar help and guide ------------------------------------------------
    #
    # ``add_toolbar_help`` / ``add_toolbar_guide`` come from ``HelpGuideMixin``.
    # They used to be defined here, which made the ``?`` and **Guide** buttons a
    # feature of this base class rather than of ChiSurf: a tool built on a plain
    # ``QMainWindow`` or on ``NavigationPanelTool`` could not have them at all.
    # See :mod:`chisurf.gui.widgets.tools.help_guide`.

    # -- MMFDB connectivity (lazy; never on construction) ----------------------

    def acquire_mmfdb_connection(self) -> Any | None:
        """Return an MMFDB connection, or ``None``. Override per tool.

        The base returns ``None`` (no connection). Tools override to delegate to
        their api-layer connection helper. Called lazily — never in ``__init__``.
        """
        return None

    def mmfdb_connection(self) -> Any | None:
        """Return the active MMFDB connection (via :meth:`acquire_mmfdb_connection`)."""
        try:
            return self.acquire_mmfdb_connection()
        except Exception:
            return None

    def mmfdb_connected(self) -> bool:
        """Return whether an MMFDB connection is currently available."""
        return self.mmfdb_connection() is not None

    # -- window geometry persistence ------------------------------------------

    def save_window_geometry(self) -> None:
        """Persist the main-window geometry to QSettings."""
        try:
            settings = QtCore.QSettings("chisurf", self.tool_settings_name)
            settings.setValue("geometry", self.saveGeometry())
            settings.sync()
        except Exception:
            pass

    def restore_window_geometry(self) -> None:
        """Restore the main-window geometry from QSettings, if present."""
        try:
            settings = QtCore.QSettings("chisurf", self.tool_settings_name)
            geometry = settings.value("geometry")
            if geometry is not None:
                self.restoreGeometry(geometry)
        except Exception:
            pass
