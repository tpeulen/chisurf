"""Shared dockable-tool base for transformer GUIs (PRD-23 Task 1).

`ChisurfDockTool` factors the boilerplate every transformer tool re-implemented
(drag-drop of file/folder paths, a `DockArea` central widget, window-geometry
persistence, and MMFDB-connectivity status) into one base, so fixes propagate and
the per-tool widget stays a thin view. `PathDropListWidget` is the byte-identical
drag-drop list both tools had copied.

The base performs **no** I/O or DB work on construction (PRD-23 Task 4): it only
wires Qt widgets. MMFDB access is via the overridable `acquire_mmfdb_connection`
hook, called lazily on demand — never in `__init__`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.widgets.messages import MessagesMixin, Msg  # noqa: F401 (re-exported)

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


class ChisurfDockTool(MessagesMixin, QtWidgets.QMainWindow):
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

    # -- toolbar help ----------------------------------------------------------

    def add_toolbar_help(
        self,
        toolbar: QtWidgets.QToolBar,
        *,
        resource: str = "",
        text: str = "",
        title: str = "Help",
        model: Any | None = None,
    ) -> QtWidgets.QWidget:
        """Right-align a ``?`` button in *toolbar* that opens the help modal.

        The house rule is that long help lives behind a small ``?`` button, not in
        an inline text block that eats panel space. This puts that button where it
        belongs — the far right of the tool's own toolbar — reusing the same modal
        the AutoForm ``help`` section uses. Markdown links in that help are live:
        a documentation page opens in the ChiSurf documentation browser, a URL or
        a DOI in the system browser (:mod:`chisurf.gui.widgets.tools.doc_links`).

        It also adds a **Guide** button to the left of the ``?`` whenever the tool
        ships a ``guide.json`` beside its view spec, so a tool gets a guided tour
        by writing one file and changing no code — see
        :meth:`add_toolbar_guide`.

        Parameters
        ----------
        toolbar : QtWidgets.QToolBar
            Toolbar to append the spacer + button to.
        resource : str
            Help file (``.md``/``.txt``/``.html``). A *relative* path is resolved
            next to the model's view spec, so a plugin ships it beside its
            ``view.json``.
        text : str
            Inline help body; wins over ``resource`` when given.
        title : str
            Modal window title.
        model : object, optional
            Model used to resolve a relative ``resource`` (defaults to
            ``self.model``).

        Returns
        -------
        QtWidgets.QWidget
            The button widget added to the toolbar.
        """
        from chisurf.gui.autoform.sections.help_section import HelpButton

        # Every tool that has a help button gets a guide button too, provided it
        # ships a tour — so adding one to a tool is a matter of writing
        # ``guide.json`` beside its view spec, with no code change anywhere. That
        # is what makes this a ChiSurf-wide facility rather than a feature of
        # whichever plugin remembered to ask for it.
        if getattr(self, "_guide_button", None) is None:
            self.add_toolbar_guide(toolbar, model=model)
        self._add_toolbar_right_spacer(toolbar)
        button = HelpButton(
            model if model is not None else getattr(self, "model", None),
            resource=resource,
            text=text,
            title=title,
            align="right",
        )
        toolbar.addWidget(button)
        return button

    def add_toolbar_guide(
        self,
        toolbar: QtWidgets.QToolBar,
        *,
        resource: str = "guide.json",
        steps: Any = None,
        label: str = "Guide",
        tooltip: str = "Walk me through this tool, one control at a time",
        model: Any | None = None,
    ) -> QtWidgets.QWidget | None:
        """Add a guide button that walks the user through this tool.

        The companion to :meth:`add_toolbar_help`, and the answer to a different
        question. Help explains what a control *means*; a guide says which
        control to touch **first**, points at it, and offers to do the step. A
        dense panel of well-documented settings is still unusable if nothing
        says where to start.

        The button sits immediately left of the ``?``, so the two live together
        at the top right of every tool. Call it before :meth:`add_toolbar_help`;
        the right-aligning stretch is added once per toolbar by whichever runs
        first, so the two buttons stay adjacent instead of being pushed to
        opposite ends by two competing stretches.

        Parameters
        ----------
        toolbar : QtWidgets.QToolBar
            Toolbar to append the button to.
        resource : str
            Tour definition file. A *relative* path is resolved next to the
            model's view spec, so a plugin ships ``guide.json`` beside its
            ``view.json``. See
            :mod:`chisurf.gui.widgets.tools.guided_tour` for the format.
        steps : sequence, optional
            Ready-made steps, used in preference to *resource*.
        label : str
            Button text. Plain text rather than a glyph on purpose: the compass
            emoji is not in every fallback font and renders as a missing-glyph
            box, which is worse than a word next to the ``?``.
        tooltip : str
            Button tooltip.
        model : object, optional
            Model used to resolve a relative *resource* and a step's ``action``
            (defaults to ``self.model``).

        Returns
        -------
        QtWidgets.QWidget or None
            The button, or ``None`` when no tour could be found — a tool with no
            tour gets no button rather than a button that does nothing.
        """
        from chisurf.gui.widgets.tools.guided_tour import GuidedTour, load_tour

        owner = model if model is not None else getattr(self, "model", None)
        tour_steps = list(steps) if steps else []
        if not tour_steps and resource:
            path = self._resolve_tool_resource(resource, owner)
            if path is not None:
                tour_steps = load_tour(path)
        if not tour_steps:
            return None

        self._add_toolbar_right_spacer(toolbar)
        button = QtWidgets.QToolButton()
        button.setText(str(label))
        button.setToolTip(str(tooltip))
        button.setAutoRaise(True)
        toolbar.addWidget(button)

        def _start() -> None:
            tour = getattr(self, "_guided_tour", None)
            if tour is not None:
                tour.stop()
            tour = GuidedTour(self, tour_steps, model=owner)
            self._guided_tour = tour
            tour.start()

        button.clicked.connect(_start)
        self._guide_button = button
        return button

    @staticmethod
    def _add_toolbar_right_spacer(toolbar: QtWidgets.QToolBar) -> None:
        """Add the expanding spacer that right-aligns the trailing buttons, once.

        Two stretches in one toolbar do not stack — they share the slack, which
        would put the guide button in the middle of the bar instead of beside
        the help button. The flag lives on the toolbar so the rule holds however
        many trailing buttons a tool adds.
        """
        if toolbar.property("_chisurf_right_spacer"):
            return
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        toolbar.addWidget(spacer)
        toolbar.setProperty("_chisurf_right_spacer", True)

    def _resolve_tool_resource(self, resource: str, model: Any) -> Any | None:
        """Resolve a tool resource path relative to the model's view spec.

        Parameters
        ----------
        resource : str
            Absolute, CWD-relative, or view-spec-relative path.
        model : object
            Model whose ``_view_json`` (else module directory) anchors a
            relative path.

        Returns
        -------
        pathlib.Path or None
            The existing file, or ``None``.
        """
        import pathlib
        import sys

        path = pathlib.Path(resource)
        if path.is_file():
            return path
        if path.is_absolute():
            return None
        bases: list[pathlib.Path] = []
        view_json = getattr(model, "_view_json", None)
        if view_json:
            bases.append(pathlib.Path(view_json).parent)
        module = getattr(type(model), "__module__", "") if model is not None else ""
        module_file = getattr(sys.modules.get(module, None), "__file__", None)
        if module_file:
            bases.append(pathlib.Path(module_file).parent)
        for base in bases:
            candidate = base / path
            if candidate.is_file():
                return candidate
        return None

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
