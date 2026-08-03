"""Reusable left-navigation stacked tool shell."""

from __future__ import annotations

import importlib
import json
import logging
import pathlib
import traceback
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

from qtpy import QtCore, QtWidgets

from chisurf.core.plugin.manifest import load_manifest
from chisurf.gui.event_pump import pump_ui


class _StatusLogHandler(logging.Handler):
    """Logging handler that shows records in a shell's shared status bar.

    Lets embedded tools report status with *normal logging* — ``logger.info(...)``
    — instead of bespoke status plumbing. The shell installs one of these scoped
    to a logger name (e.g. ``chisurf.plugins.burst``) while its window is open.
    Records are marshalled onto the GUI thread via a queued signal, so worker
    threads can log safely.
    """

    def __init__(self, shell: NavigationPanelTool) -> None:
        super().__init__()
        self._shell = shell

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:
            return
        self._shell.status_logged.emit(msg)


def embed_mainwindow(mw: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Return an embeddable plain-``QWidget`` view of a ``QMainWindow`` tool.

    If ``mw`` is not a ``QMainWindow`` it is returned unchanged. Otherwise its
    central widget is reparented into a container, prefixed by a button row that
    mirrors the window's toolbar actions (or, if it has none, its top-level menu
    actions). A reference to the original window is kept on the container so its
    Python object (and any signal connections) stays alive.

    Reparenting a ``QMainWindow`` into a stacked panel area is a fragile Qt
    pattern — on macOS a nested main window's tab bars stop receiving mouse
    clicks — so aggregator tools flatten sub-tools with this helper instead.
    """
    if not isinstance(mw, QtWidgets.QMainWindow):
        return mw

    container = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    # Re-expose actions: prefer the window's OWN toolbars (not toolbars that
    # belong to nested panels inside the central widget), fall back to the menu.
    actions: list[QtWidgets.QAction] = []
    for tb in mw.findChildren(QtWidgets.QToolBar):
        if tb.parent() is mw:
            actions.extend(tb.actions())
    if not actions:
        mbar = mw.menuBar()
        if mbar is not None:
            for menu_action in mbar.actions():
                menu = menu_action.menu()
                if menu is not None:
                    actions.extend(menu.actions())
    seen: set[int] = set()
    button_row = QtWidgets.QHBoxLayout()
    button_row.setContentsMargins(6, 4, 6, 0)
    n_buttons = 0
    for act in actions:
        if act is None or act.isSeparator() or not act.text().strip():
            continue
        if id(act) in seen:
            continue
        seen.add(id(act))
        btn = QtWidgets.QToolButton()
        btn.setDefaultAction(act)
        btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        button_row.addWidget(btn)
        n_buttons += 1
    if n_buttons:
        button_row.addStretch(1)
        layout.addLayout(button_row)

    central = mw.centralWidget()
    if central is not None:
        central.setParent(container)
        layout.addWidget(central, 1)

    # Keep the originating window alive (owns the model/signals).
    container._embedded_mainwindow = mw  # type: ignore[attr-defined]
    return container


def find_status_reporter(widget: QtWidgets.QWidget | None):
    """Return the nearest hosting shell that exposes the status-bar API.

    Embedded tools call this to route progress into the shared status bar instead
    of popping their own dialog. The check is ``begin_task`` (the status-bar
    contract of :class:`NavigationPanelTool`). Returns ``None`` when the tool runs
    standalone in its own window, so standalone behaviour is unchanged.
    """
    if widget is None:
        return None
    try:
        win = widget.window()
    except Exception:
        win = None
    if win is not None and callable(getattr(win, "begin_task", None)):
        return win
    # Fallback: walk the parent chain (covers widgets not yet in a top-level).
    node = getattr(widget, "parent", lambda: None)()
    seen: set[int] = set()
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        if callable(getattr(node, "begin_task", None)):
            return node
        node = getattr(node, "parent", lambda: None)()
    return None


class _TaskLabel:
    """``.label`` shim so a status task duck-types the old popup dialog's label."""

    def __init__(self, task: _StatusTask) -> None:
        self._task = task

    def setText(self, text: str) -> None:  # noqa: N802 (Qt-style)
        self._task.setLabelText(text)

    def text(self) -> str:
        return self._task._shell._status_message.text()


class _TaskProgress:
    """``.progress`` shim so a status task duck-types the old popup dialog's bar."""

    def __init__(self, task: _StatusTask) -> None:
        self._task = task

    def setRange(self, a: int, b: int) -> None:  # noqa: N802
        self._task.setRange(a, b)

    def setValue(self, v: int) -> None:  # noqa: N802
        self._task.set_value(v)

    def setMaximum(self, m: int) -> None:  # noqa: N802
        self._task.setRange(0, m)

    def value(self) -> int:
        return int(self._task._shell._status_progress.value())

    def maximum(self) -> int:
        return int(self._task._shell._status_progress.maximum())


class _StatusTask:
    """Status-bar-backed progress handle that duck-types the popup dialog API.

    Obtained from :meth:`NavigationPanelTool.begin_task`. It renders into the one
    shared status bar (message + inline bar + Cancel) rather than a modal popup,
    while exposing the small surface embedded tools and burst cores already call
    on their old dialogs (``label``, ``progress``, ``set_value``, ``wasCanceled``,
    ``update_progress``, ``close``). Migration is therefore near-mechanical: a tool
    only swaps *where the handle comes from*, not how it drives it.
    """

    def __init__(self, shell: NavigationPanelTool, message: str, maximum: int = 0,
                 cancel=None) -> None:
        self._shell = shell
        self._cancel_cb = cancel
        self._canceled = False
        self.label = _TaskLabel(self)
        self.progress = _TaskProgress(self)
        shell._activate_task(self, message, maximum, bool(cancel))

    # -- popup-dialog-compatible surface --------------------------------------
    def set_value(self, v: int) -> None:
        self._shell._task_set_value(self, int(v))

    def setValue(self, v: int) -> None:  # noqa: N802
        self.set_value(v)

    def setLabelText(self, text: str) -> None:  # noqa: N802
        self._shell._task_set_message(self, str(text))

    def setRange(self, a: int, b: int) -> None:  # noqa: N802
        self._shell._task_set_range(self, int(a), int(b))

    def update_progress(self, value: int, text: str | None = None) -> None:
        if text is not None:
            self._shell._task_set_message(self, str(text))
        self.set_value(value)

    def update_text(self, text: str) -> None:
        self._shell._task_set_message(self, str(text))

    def wasCanceled(self) -> bool:  # noqa: N802
        return self._canceled

    def cancel(self) -> None:
        """Mark canceled and fire the cancel callback (Cancel-button path)."""
        self._canceled = True
        if callable(self._cancel_cb):
            try:
                self._cancel_cb()
            except Exception:
                pass

    def finish(self, *args, **kwargs) -> None:
        self.close()

    def close(self) -> None:
        self._shell._deactivate_task(self)

    # QDialog / QProgressDialog-ish no-ops some callers use on a progress object.
    def show(self) -> None:
        pass

    def setWindowTitle(self, *args) -> None:  # noqa: N802
        pass

    def setWindowModality(self, *args) -> None:  # noqa: N802
        pass

    def setAutoClose(self, *args) -> None:  # noqa: N802
        pass

    def setAutoReset(self, *args) -> None:  # noqa: N802
        pass

    def setMinimumDuration(self, *args) -> None:  # noqa: N802
        pass

    def setCancelButton(self, *args) -> None:  # noqa: N802
        pass


def _resolve_entrypoint(entrypoint: str):
    """Import ``"pkg.module:Attr"`` and return the referenced attribute."""
    module_name, _, attr = entrypoint.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def _make_panel_factory(entrypoint: str, embed: bool):
    """Build a lazy panel factory from an entrypoint string + embed flag."""

    def factory(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        widget = _resolve_entrypoint(entrypoint)()
        return embed_mainwindow(widget) if embed else widget

    return factory


class _MaturityFlag(NamedTuple):
    """How one manifest maturity flag is presented by the panel shell."""

    #: Appended to the navigation label of a flagged panel.
    marker: str
    #: Panel/manifest key holding the tool-specific message, if any.
    message_key: str
    #: Banner text when the manifest carries no message of its own.
    default_message: str
    #: Banner background / bottom-border colours.
    background: str
    border: str


#: The maturity flags a panel may carry, in the order they are rendered. Both are
#: written by :func:`apply_manifest_flags` from the plugin manifest, so a tool's
#: maturity is declared once — in its manifest — and surfaced here.
MATURITY_FLAGS: dict[str, _MaturityFlag] = {
    "deprecated": _MaturityFlag(
        marker="⛔",
        message_key="deprecation_message",
        default_message="{name} is DEPRECATED — it will be removed, do not build new work on it",
        background="#8a5300",
        border="#5c3700",
    ),
    "experimental": _MaturityFlag(
        marker="⚠️",
        message_key="experimental_message",
        default_message="{name} is EXPERIMENTAL and UNTESTED — results are not validated",
        background="#b30000",
        border="#7d0000",
    ),
}

#: ``chisurf/plugins`` — a panel's ``"manifest"`` path is relative to this.
_PLUGINS_DIR = pathlib.Path(__file__).resolve().parents[2] / "plugins"


def maturity_markers(meta: Mapping[str, Any]) -> list[str]:
    """Return the marker glyph of every maturity flag *meta* sets, in render order.

    *meta* is anything carrying the manifest's flags under their own names — a
    panel definition, or a plugin discovery record. Keeping the lookup here means
    the ribbon entry and the navigation entry of the same tool are marked from
    one table.

    Parameters
    ----------
    meta : Mapping
        Panel definition or discovery record.

    Returns
    -------
    list of str
        One marker per set flag; empty when the tool declares no maturity flag.
    """
    return [spec.marker for flag, spec in MATURITY_FLAGS.items() if meta.get(flag)]


def maturity_message(meta: Mapping[str, Any], flag: str, name: str = "This tool") -> str:
    """Return the warning sentence for one maturity *flag* set on *meta*.

    Parameters
    ----------
    meta : Mapping
        Panel definition or discovery record, optionally carrying the flag's own
        message under ``MATURITY_FLAGS[flag].message_key``.
    flag : str
        Key in :data:`MATURITY_FLAGS` — ``"deprecated"`` or ``"experimental"``.
    name : str, optional
        Tool name filled into the fallback wording when the manifest carries no
        message of its own.

    Returns
    -------
    str
        The tool's own wording when it has one, else the flag's default sentence.
    """
    spec = MATURITY_FLAGS[flag]
    return str(meta.get(spec.message_key) or spec.default_message.format(name=name))


def maturity_warnings(meta: Mapping[str, Any], name: str = "This tool") -> list[str]:
    """Return ``marker + message`` for every maturity flag set on *meta*.

    Parameters
    ----------
    meta : Mapping
        Panel definition or discovery record.
    name : str, optional
        Tool name filled into any fallback wording.

    Returns
    -------
    list of str
        One line per set flag, hardest warning first; empty when none is set.
    """
    return [
        f"{spec.marker}  {maturity_message(meta, flag, name)}"
        for flag, spec in MATURITY_FLAGS.items()
        if meta.get(flag)
    ]


def apply_manifest_flags(panels: list[dict]) -> list[dict]:
    """Copy the maturity flags of each panel's plugin manifest onto the panel.

    A panel may declare ``"manifest": "<path under chisurf/plugins>"``; that
    manifest's ``experimental`` / ``deprecated`` flags (and their messages) then
    drive the navigation marker and the banner above the panel. The flag lives in
    one place — the manifest — instead of being duplicated in every host that
    embeds the tool. Panels naming no (or an unreadable) manifest are untouched.

    Parameters
    ----------
    panels : list of dict
        Panel definitions, modified in place.

    Returns
    -------
    list of dict
        The same list, for use directly in a module-level panel definition.
    """
    for panel in panels:
        rel = panel.get("manifest")
        if not rel:
            continue
        manifest = load_manifest(_PLUGINS_DIR / rel / "manifest.json")
        if manifest is None:
            continue
        for flag, spec in MATURITY_FLAGS.items():
            if getattr(manifest, flag, False):
                panel[flag] = True
                message = getattr(manifest, spec.message_key, "")
                if message:
                    panel[spec.message_key] = message
    return panels


def load_panels_json(path: str | pathlib.Path) -> tuple[dict, list[dict]]:
    """Load a data-driven ``panels.json`` spec into NavigationPanelTool panels.

    The spec is a dict with a ``title`` and a ``panels`` list; each entry names
    a tool by its GUI entrypoint (``"module:Class"``) plus ``name`` / ``icon`` /
    ``description`` / ``role``. Set ``"embed": true`` for ``QMainWindow`` tools
    that must be flattened via :func:`embed_mainwindow`; ``{"separator": true}``
    inserts a group separator; ``"optional": true`` marks a step the pipeline
    works without, which *Next* and the fast-forward therefore pass over without
    running (see :meth:`NavigationPanelTool.process_current_step`). An entry may also name the tool's ``manifest`` so
    :func:`apply_manifest_flags` surfaces its maturity flags. Panels import
    lazily inside their factories.

    Returns
    -------
    tuple[dict, list[dict]]
        The raw spec dict and the translated panel definitions.
    """
    spec = json.loads(pathlib.Path(path).read_text())
    panels: list[dict] = []
    for entry in spec.get("panels", []):
        if entry.get("separator"):
            panels.append(
                {
                    "name": "────────",
                    "icon": "",
                    "separator": True,
                    "role": entry.get("role", "separator"),
                }
            )
            continue
        panels.append(
            {
                "name": entry["name"],
                "icon": entry.get("icon", ""),
                "description": entry.get("description", ""),
                "role": entry["role"],
                "manifest": entry.get("manifest", ""),
                "factory": _make_panel_factory(
                    entry["entrypoint"], bool(entry.get("embed", False))
                ),
            }
        )
    return spec, apply_manifest_flags(panels)


class NavigationPanelTool(QtWidgets.QMainWindow):
    """Main-window shell with a left selector and lazy-loaded right panels."""

    #: Emitted (possibly from a worker thread) by the scoped log handler; the
    #: connected slot updates the status bar on the GUI thread.
    status_logged = QtCore.Signal(str)

    def __init__(
        self,
        *,
        title: str,
        panels: Sequence[Mapping[str, Any]],
        parent: QtWidgets.QWidget | None = None,
        minimum_size: tuple[int, int] = (850, 550),
        initial_size: tuple[int, int] = (1020, 680),
        navigation_width: int = 220,
        navigation_min_width: int | None = None,
        panel_margins: tuple[int, int, int, int] = (12, 12, 12, 12),
        searchable: bool = True,
        settings_key: str | None = None,
        status_logger: str | None = None,
    ) -> None:
        """Create a navigation shell.

        ``searchable`` (default ``True``) adds a search box at the top of the left
        pane that filters the navigation list to matching panels.

        ``settings_key`` (when given) makes the window remember its geometry, the
        left/right splitter sizes and the selected panel across sessions under
        that plugin-unique key.

        ``status_logger`` (when given, a logger name) installs a logging handler
        scoped to that logger, so embedded panels can report status via *normal
        logging* (``logger.info(...)``) and have it appear in the shared status
        bar. The handler is removed when the window closes.
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(*initial_size)
        self.setMinimumSize(*minimum_size)

        self.panels: list[dict[str, Any]] = [dict(panel) for panel in panels]
        self._panel_margins = panel_margins
        self._searchable = searchable
        self._navigation_min_width = navigation_min_width or navigation_width
        self._settings_key = settings_key
        self._status_logger_name = status_logger
        self._status_log_handler: _StatusLogHandler | None = None
        #: Walking the whole pipeline: every completion takes the next step off
        #: the queue below.
        self._fast_forward = False
        #: Rows the running fast-forward has still to process, decided when it
        #: was started so the walk cannot drift under it.
        self._ff_queue: list[int] = []
        #: How many rows that queue started with, for "3/6" in the status line.
        self._ff_total = 0
        #: Set by a Next click that had to wait for the step's run to finish.
        self._pending_advance = False
        #: True while the current step has background work in flight.
        self._steps_blocked = False
        #: Row currently shown, so a refused switch can be snapped back.
        self._shown_index = -1
        self._build_ui(navigation_width)
        # Bound methods of a QObject: PyQt drops these connections when this
        # window is destroyed, so a late task cannot call into a dead shell.
        from chisurf.gui.task import task_events

        events = task_events()
        events.started.connect(self._on_task_started)
        events.finished.connect(self._on_task_finished)
        if status_logger:
            self._install_status_log_handler(status_logger)
        if settings_key:
            self._restore_window_state()
            self.splitter.splitterMoved.connect(lambda *_: self._save_window_state())
            self.nav_list.currentRowChanged.connect(lambda *_: self._save_window_state())

    # ── window-state persistence (opt-in via ``settings_key``) ──────────
    def _settings(self):
        return QtCore.QSettings("chisurf", f"NavigationPanelTool/{self._settings_key}")

    def _save_window_state(self) -> None:
        """Persist geometry, splitter sizes and the selected panel."""
        if not self._settings_key:
            return
        try:
            s = self._settings()
            s.setValue("geometry", self.saveGeometry())
            s.setValue("splitter", self.splitter.saveState())
            s.setValue("current_row", int(self.nav_list.currentRow()))
            s.sync()
        except Exception:
            pass

    def _restore_window_state(self) -> None:
        """Restore geometry, splitter sizes and the selected panel, if saved."""
        try:
            s = self._settings()
            geometry = s.value("geometry")
            if geometry is not None:
                self.restoreGeometry(geometry)
            splitter = s.value("splitter")
            if splitter is not None:
                self.splitter.restoreState(splitter)
            row = s.value("current_row")
            if row is not None:
                row = int(row)
                item = self.nav_list.item(row)
                if item is not None and (item.flags() & QtCore.Qt.ItemIsSelectable):
                    self.nav_list.setCurrentRow(row)
        except Exception:
            pass

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Save the window state on close when persistence is enabled."""
        self._save_window_state()
        self._remove_status_log_handler()
        super().closeEvent(event)

    def _build_ui(self, navigation_width: int) -> None:
        """Build the navigation and stacked panel area."""
        central_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QtWidgets.QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # Left pane: a search box on top of the navigation list.
        left_pane = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.nav_search: QtWidgets.QLineEdit | None = None
        if self._searchable:
            self.nav_search = QtWidgets.QLineEdit()
            self.nav_search.setPlaceholderText("Search…")
            self.nav_search.setClearButtonEnabled(True)
            self.nav_search.setStyleSheet(
                "QLineEdit { margin: 6px 0px 2px 0px; padding: 4px 10px; }"
            )
            self.nav_search.textChanged.connect(self._on_search_changed)
            left_layout.addWidget(self.nav_search)

        self.nav_list = QtWidgets.QListWidget()
        self.nav_list.setMinimumWidth(self._navigation_min_width)
        self.nav_list.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum,
            QtWidgets.QSizePolicy.Expanding,
        )
        self.nav_list.setIconSize(QtCore.QSize(20, 20))
        self.nav_list.setSpacing(4)
        self.nav_list.setStyleSheet(
            """
            QListWidget {
                border: none;
                border-right: 1px solid rgba(128, 128, 128, 0.3);
                padding-top: 5px;
            }
            QListWidget::item {
                height: 32px;
                padding-left: 10px;
                border-radius: 8px;
                margin: 2px 10px;
                font-weight: bold;
                font-size: 14px;
            }
            /* Styling ``::item`` at all hands item painting to the stylesheet
               style, which then draws no selection background — leaving the
               current step's label as white-on-white (only its emoji visible).
               Both states have to be spelled out, from the palette so the
               light and dark themes each stay legible. */
            QListWidget::item:selected {
                background: palette(highlight);
                color: palette(highlighted-text);
            }
            QListWidget::item:hover:!selected {
                background: rgba(128, 128, 128, 0.18);
            }
            """
        )

        for panel in self.panels:
            item = QtWidgets.QListWidgetItem(self._panel_label(panel))
            description = panel.get("description")
            if description:
                item.setToolTip(str(description))
            if panel.get("separator"):
                item.setFlags(QtCore.Qt.NoItemFlags)
            self.nav_list.addItem(item)

        left_layout.addWidget(self.nav_list, 1)
        self.splitter.addWidget(left_pane)

        self.stacked_widget = QtWidgets.QStackedWidget()
        for panel in self.panels:
            placeholder = self._placeholder_widget(panel)
            self.stacked_widget.addWidget(placeholder)
            panel["instance"] = None

        self.splitter.addWidget(self.stacked_widget)
        self.splitter.setCollapsible(0, False)
        self.splitter.setSizes(
            [
                max(navigation_width, self._navigation_min_width),
                max(600, self.width() - navigation_width),
            ]
        )
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        assert self.nav_list.minimumWidth() >= self._navigation_min_width

        self._build_status_bar()

        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        if self.panels:
            self.nav_list.setCurrentRow(0)

    # ── shared status bar (message + inline progress + Cancel + stepper) ────
    def _build_status_bar(self) -> None:
        """Build the one shared status bar used by every embedded panel.

        Left: a message label + a hidden inline progress bar + a hidden Cancel
        button (shown only for cancellable tasks). Right (permanent corner): a
        ``◀ Back`` / ``Next ▶`` stepper that walks non-separator panels. Embedded
        tools drive this via :meth:`begin_task` instead of popping their own
        modal progress dialogs, so the whole workflow reads as one calm window.
        """
        self._active_task: _StatusTask | None = None
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)

        self._status_message = QtWidgets.QLabel("Ready")
        self._status_message.setStyleSheet("color: #888; padding: 0 6px;")
        bar.addWidget(self._status_message, 1)

        self._status_progress = QtWidgets.QProgressBar()
        self._status_progress.setMaximumWidth(220)
        self._status_progress.setMaximumHeight(16)
        self._status_progress.setTextVisible(True)
        self._status_progress.setVisible(False)
        bar.addWidget(self._status_progress)

        self._status_cancel = QtWidgets.QToolButton()
        self._status_cancel.setText("Cancel")
        self._status_cancel.setVisible(False)
        self._status_cancel.clicked.connect(self._on_status_cancel)
        bar.addWidget(self._status_cancel)

        self._btn_prev = QtWidgets.QToolButton()
        self._btn_prev.setText("◀ Back")
        self._btn_prev.setToolTip("Go to the previous workflow step")
        self._btn_prev.clicked.connect(self.goto_prev_step)
        self._btn_next = QtWidgets.QToolButton()
        self._btn_next.setText("Next ▶")
        self._btn_next.setToolTip(
            "Process all loaded files in this step, then go to the next step"
        )
        self._btn_next.clicked.connect(self._on_next_clicked)
        self._btn_ff = QtWidgets.QToolButton()
        self._btn_ff.setText("⏩")
        self._btn_ff.setToolTip(
            "Fast-forward — run every remaining step of the pipeline in order, "
            "waiting for each to finish. Click again to stop after the current "
            "step; Back or picking a step by hand also stops it."
        )
        self._btn_ff.clicked.connect(self._on_fast_forward_clicked)
        bar.addPermanentWidget(self._btn_prev)
        bar.addPermanentWidget(self._btn_ff)
        bar.addPermanentWidget(self._btn_next)

        self.status_logged.connect(self._on_log_status)

    def _install_status_log_handler(self, logger_name: str) -> None:
        """Route ``logger_name`` (INFO+) into the shared status bar."""
        handler = _StatusLogHandler(self)
        handler.setLevel(logging.INFO)
        logging.getLogger(logger_name).addHandler(handler)
        self._status_log_handler = handler

    def _remove_status_log_handler(self) -> None:
        """Detach the status-bar log handler (on close)."""
        handler = self._status_log_handler
        if handler is not None and self._status_logger_name:
            logging.getLogger(self._status_logger_name).removeHandler(handler)
        self._status_log_handler = None

    def _on_log_status(self, msg: str) -> None:
        """Show a logged status line on the bar's message label.

        Only the message text is touched — never the progress bar — so a line
        logged during a running task updates the caption without disturbing the
        task's progress/Cancel widgets, and a final message logged just before a
        task closes survives (see :meth:`_deactivate_task`).
        """
        first = (msg or "").splitlines()[0][:200] if msg else ""
        self._status_message.setText(first)
        # Log lines arrive from anywhere, including worker threads and the
        # middle of another status update, and none of them needs a click:
        # repaint only.
        self._pump_status(allow_input=False)

    def _pump_status(self, *, allow_input: bool = True) -> None:
        """Repaint the status bar mid-operation, via the shared guarded pump.

        Task progress keeps user input (its Cancel button has to stay
        clickable); the log-driven caption update does not, so a click cannot be
        delivered into a running analysis and delete the widgets it is still
        writing to. Nesting is prevented process-wide — see
        :mod:`chisurf.gui.event_pump` for the crash this fixes.
        """
        pump_ui(allow_input=allow_input)

    # ── status-bar API (used by embedded tools via find_status_reporter) ────
    def begin_task(self, message: str, maximum: int = 0, cancel=None) -> _StatusTask:
        """Start one status-bar task and return a popup-compatible handle.

        ``maximum=0`` shows an indeterminate (busy) bar. Pass ``cancel`` (a
        callable) to reveal the Cancel button and have it fire that callback and
        flip ``handle.wasCanceled()``.
        """
        return _StatusTask(self, message, maximum, cancel)

    def report_status(self, message: str, *, busy: bool = False) -> None:
        """Show a one-off status message (optionally with a busy bar)."""
        self._status_message.setText(str(message))
        if busy:
            self._status_progress.setRange(0, 0)
            self._status_progress.setVisible(True)
        else:
            self._status_progress.setVisible(False)
        self._pump_status()

    def report_progress(self, value: int, maximum: int, message: str | None = None) -> None:
        """Show determinate progress (``value`` of ``maximum``)."""
        if message is not None:
            self._status_message.setText(str(message))
        self._status_progress.setRange(0, int(maximum))
        self._status_progress.setValue(int(value))
        self._status_progress.setVisible(True)
        self._pump_status()

    def clear_status(self) -> None:
        """Reset the status bar to idle."""
        self._status_message.setText("Ready")
        self._status_progress.setVisible(False)
        self._status_cancel.setVisible(False)

    def _on_status_cancel(self) -> None:
        """Cancel the active task from the status-bar Cancel button."""
        task = self._active_task
        if task is not None:
            task.cancel()

    # -- _StatusTask back-end (only the active task may write the bar) --------
    def _activate_task(self, task: _StatusTask, message: str, maximum: int,
                       has_cancel: bool) -> None:
        self._active_task = task
        self._status_message.setText(message or "")
        self._status_progress.setRange(0, int(maximum))
        self._status_progress.setValue(0)
        self._status_progress.setVisible(True)
        self._status_cancel.setVisible(bool(has_cancel))
        self._pump_status()

    def _task_set_message(self, task: _StatusTask, message: str) -> None:
        if task is not self._active_task:
            return
        self._status_message.setText(message)
        self._pump_status()

    def _task_set_range(self, task: _StatusTask, a: int, b: int) -> None:
        if task is not self._active_task:
            return
        self._status_progress.setRange(a, b)
        self._pump_status()

    def _task_set_value(self, task: _StatusTask, v: int) -> None:
        if task is not self._active_task:
            return
        self._status_progress.setValue(v)
        self._pump_status()

    def _deactivate_task(self, task: _StatusTask) -> None:
        if task is not self._active_task:
            return
        self._active_task = None
        # Hide the progress/Cancel widgets but leave the last message on the bar
        # (e.g. a tool's final "Done – N bursts", logged just before close).
        self._status_progress.setVisible(False)
        self._status_cancel.setVisible(False)

    # ── Next/Back stepper ───────────────────────────────────────────────────
    def _current_panel_instance(self) -> QtWidgets.QWidget | None:
        """Return the loaded wrapper widget of the current panel, if any."""
        idx = self.nav_list.currentRow()
        if 0 <= idx < len(self.panels):
            return self.panels[idx].get("instance")
        return None

    def process_current_step(self) -> bool:
        """Run the current step's canonical Run action (process all loaded files).

        Every plugin's primary action is the canonical ``toolAction_run`` button,
        wired to a *process-all-loaded* handler — so the shell can trigger a step's
        batch processing generically, without knowing the tool. Returns ``True`` if
        a Run action was found and triggered.

        A panel declared ``optional`` is **never** run this way. Walking past a
        step must not silently change the analysis: an optional step is one the
        pipeline works without, so *Next* and the fast-forward pass over it and
        it acts only when the user presses its own button. Returns ``False``, so
        the walk advances immediately rather than waiting for work that will
        never start.
        """
        idx = self.nav_list.currentRow()
        if 0 <= idx < len(self.panels) and self.panels[idx].get("optional"):
            return False
        inst = self._current_panel_instance()
        if inst is None:
            return False
        btn = inst.findChild(QtWidgets.QToolButton, "toolAction_run")
        if btn is not None and btn.isEnabled():
            btn.click()
            return True
        return False

    def _on_next_clicked(self) -> None:
        """Next button: process all loaded files in this step, then advance.

        "Then" is literal. Starting the step's run and switching panel in the
        same turn left the finished analysis plotting into a panel the shell had
        already left while the next one was being built, which crashes the
        application (SIGSEGV inside ``QCoreApplication::postEvent``, reached
        through pyqtgraph's Python-level signals). So the click starts the run
        and *arms* the advance; :meth:`_on_task_finished` performs it when the
        work is done. The GUI is never blocked — the step's own progress and
        Cancel keep working — but step changes are.
        """
        if self._step_is_busy():
            # Already working (a panel re-computes on its own when settings or
            # the folder change, so this is the common case for a quick click):
            # take the click as "go on when this finishes" rather than dropping
            # it, and do not start a second run on top of the first.
            self._pending_advance = True
            return
        self.process_current_step()
        if self._step_is_busy():
            self._pending_advance = True
            return
        # Nothing to wait for. Re-assert activation after any processing
        # dialog/embed churn (macOS can drop the window behind others when a
        # panel is (re)shown).
        self._restore_active_window()
        self.goto_next_step()

    def _on_fast_forward_clicked(self) -> None:
        """Queue the rest of the pipeline and run it, one step at a time.

        The click decides *what* will run: the steps from here to the end of the
        numbered pipeline become a queue, taken one at a time. Deciding once
        means the walk cannot drift with whatever the running steps do to the
        panel list, and it is what lets the status line say how far along it is.

        Never two at once: a step's run is asynchronous, and starting the next
        before the previous has finished is the crash the armed advance exists to
        avoid — so a step that is working simply leaves the queue armed until it
        reports done. A second click stops after the step in flight, so the
        button is its own cancel.
        """
        if self._fast_forward:
            self._stop_fast_forward("Fast-forward stopped — finishing this step")
            return
        self._ff_queue = self._pipeline_queue()
        if not self._ff_queue:
            return
        self._fast_forward = True
        self._ff_total = len(self._ff_queue)
        self._btn_ff.setText("⏸")
        self._btn_ff.setToolTip("Stop fast-forward after the running step")
        self._run_queued_step()

    def _pipeline_queue(self) -> list:
        """Rows the fast-forward will process: here to the end of *this* section.

        The numbered pipeline is the run of panels before the separator; what
        follows it are tools you reach *with* the result (Browser, Accurate FRET)
        or that feed it from the raw files (Background, IRF & Background), which
        are not steps of the walk. So the queue stops at the separator — and,
        started below one, covers only that group.
        """
        rows = []
        for i in range(max(self.nav_list.currentRow(), 0), len(self.panels)):
            if self.panels[i].get("separator"):
                break
            rows.append(i)
        return rows

    def _stop_fast_forward(self, message: str = "") -> None:
        """Leave fast-forward mode (the running step is left to finish)."""
        if not self._fast_forward:
            return
        self._fast_forward = False
        self._pending_advance = False
        self._ff_queue = []
        self._btn_ff.setText("⏩")
        self._btn_ff.setToolTip(
            "Fast-forward — run the remaining numbered steps in order, waiting "
            "for each to finish. It stops at the end of the pipeline, not at the "
            "tools below the separator. Click again to stop after the current "
            "step; Back or picking a step by hand also stops it."
        )
        if message:
            self.report_status(message)

    def _run_queued_step(self) -> None:
        """Take the next step off the queue and run it, or finish.

        Reached both synchronously (a step that needed no background work) and
        from :meth:`_on_task_finished` (one that did), so it is the single place
        that decides what happens next.
        """
        if not self._fast_forward:
            return
        if not self._ff_queue:
            self._stop_fast_forward("Fast-forward finished — the pipeline is done")
            return
        row = self._ff_queue.pop(0)
        done = self._ff_total - len(self._ff_queue)
        if self.nav_list.currentRow() != row:
            self.nav_list.setCurrentRow(row)
        name = str(self.panels[row].get("name") or "").strip()
        self.report_status(f"Fast-forward {done}/{self._ff_total}: {name}")
        # Panels that compute on arrival are already working by now; that run is
        # this step's run, so wait for it rather than starting a second one.
        if not self._step_is_busy():
            self._restore_active_window()
            self.process_current_step()
        if self._step_is_busy():
            self._pending_advance = True  # its completion comes back here
            return
        self._run_queued_step()

    # ── busy gating ─────────────────────────────────────────────────────────
    def _step_is_busy(self) -> bool:
        """Whether the current step has background work in flight."""
        from chisurf.gui.task import running_tasks_under

        return bool(running_tasks_under(self._current_panel_instance()))

    def _on_task_started(self, task) -> None:
        """Block step changes while this shell's panel is working."""
        if self._step_is_busy():
            self._set_steps_blocked(True)

    def _on_task_finished(self, task) -> None:
        """Unblock, and perform the advance a Next click armed."""
        if self._step_is_busy():
            return  # something else in this step is still going
        self._set_steps_blocked(False)
        if self._pending_advance:
            self._pending_advance = False
            self._restore_active_window()
            if self._fast_forward:
                # The queue decides where to go next, including *not* going
                # anywhere when this was the last step of the pipeline.
                self._run_queued_step()
            else:
                self.goto_next_step()

    def _set_steps_blocked(self, blocked: bool) -> None:
        """Enable/disable the step selector and the stepper buttons.

        Switching step *while a run is in flight* is the crash above, and the
        user can reach it by hand as easily as by clicking Next — so the shell
        simply refuses it for the duration, rather than leaving a way to walk
        into it. Everything else (the panel, its Cancel button, the status bar)
        stays live — including ⏩, which must stay clickable while a step runs
        because it is the only way to stop the walk it started.
        """
        self._steps_blocked = bool(blocked)
        enabled = not blocked
        for widget in (getattr(self, "nav_list", None),
                       getattr(self, "_btn_prev", None),
                       getattr(self, "_btn_next", None)):
            if widget is not None:
                widget.setEnabled(enabled)
        if blocked:
            self._btn_next.setToolTip("Working — the next step unlocks when this one finishes")
        else:
            self._btn_next.setToolTip(
                "Process all loaded files in this step, then go to the next step"
            )
            self._update_stepper()

    def goto_next_step(self) -> bool:
        """Select the next non-separator panel; return ``True`` if one exists.

        Refused while the current step is working — see :meth:`_on_nav_changed`.
        """
        if self._steps_blocked:
            return False
        cur = self.nav_list.currentRow()
        for i in range(cur + 1, len(self.panels)):
            if not self.panels[i].get("separator"):
                self.nav_list.setCurrentRow(i)
                return True
        return False

    def goto_prev_step(self) -> bool:
        """Select the previous non-separator panel; return ``True`` if one exists.

        Refused while the current step is working — see :meth:`_on_nav_changed`.
        """
        if self._steps_blocked:
            return False
        # Going back is a change of mind; it ends a fast-forward.
        self._stop_fast_forward("Fast-forward stopped")
        cur = self.nav_list.currentRow()
        for i in range(cur - 1, -1, -1):
            if not self.panels[i].get("separator"):
                self.nav_list.setCurrentRow(i)
                return True
        return False

    def _update_stepper(self) -> None:
        """Enable/disable the stepper buttons at the workflow ends."""
        if not hasattr(self, "_btn_next"):
            return
        cur = self.nav_list.currentRow()
        self._btn_next.setEnabled(
            any(not p.get("separator") for p in self.panels[cur + 1:])
        )
        self._btn_prev.setEnabled(
            any(not p.get("separator") for p in self.panels[:max(cur, 0)])
        )

    def _on_search_changed(self, text: str) -> None:
        """Filter the nav list to panels whose name matches ``text``.

        Leaf panels are shown when the (case-insensitive) query is a substring of
        their name; a separator group header is shown only while at least one of
        its child panels is still visible. An empty query restores everything.
        """
        query = (text or "").strip().lower()

        # First pass: leaf visibility (separators hidden, decided in pass two).
        for i, panel in enumerate(self.panels):
            item = self.nav_list.item(i)
            if item is None:
                continue
            if panel.get("separator"):
                item.setHidden(bool(query))
            else:
                name = str(panel.get("name") or "").lower()
                item.setHidden(bool(query) and query not in name)

        if not query:
            return

        # Second pass: reveal a group header only if its group has a visible child.
        sep_row: int | None = None
        group_has_visible = False
        for i, panel in enumerate(self.panels):
            if panel.get("separator"):
                if sep_row is not None:
                    self.nav_list.item(sep_row).setHidden(not group_has_visible)
                sep_row = i
                group_has_visible = False
            elif not self.nav_list.item(i).isHidden():
                group_has_visible = True
        if sep_row is not None:
            self.nav_list.item(sep_row).setHidden(not group_has_visible)

    def _panel_label(self, panel: Mapping[str, Any]) -> str:
        """Return the selector label for a panel (flagged when deprecated/experimental)."""
        icon = str(panel.get("icon") or "").strip()
        name = str(panel.get("name") or "").strip()
        label = f"{icon} {name}".strip()
        for marker in maturity_markers(panel):
            label = f"{label}  {marker}"
        return label

    def _placeholder_widget(self, panel: Mapping[str, Any]) -> QtWidgets.QWidget:
        """Create an unloaded placeholder widget."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(*self._panel_margins)

        label = QtWidgets.QLabel(f"Select {panel.get('name', 'panel')} to load.")
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label, 1)
        return widget

    def show_panel_by_role(self, role: str) -> bool:
        """Navigate to the (non-separator) panel with the given ``role``.

        Lets one panel deep-link to another (e.g. the Correlator's lifetime-filter
        controls jumping to the Filter Calculator). Returns ``True`` if found.
        """
        for i, panel in enumerate(self.panels):
            if not panel.get("separator") and panel.get("role") == role:
                self.nav_list.setCurrentRow(i)
                return True
        return False

    def _on_nav_changed(self, index: int) -> None:
        """Load and show the selected panel, unless the step is still working."""
        if index < 0 or index >= len(self.panels):
            return
        if self._steps_blocked and index != self._shown_index:
            # Disabling the widgets is not enough: a programmatic
            # ``setCurrentRow`` (the stepper, a workflow handoff) still gets
            # here, and switching panel while a run is in flight is the crash
            # this gate exists for. Snap the selection back instead.
            blocker = QtCore.QSignalBlocker(self.nav_list)
            self.nav_list.setCurrentRow(self._shown_index)
            del blocker
            self.report_status("Working — the step changes when this run finishes")
            return

        was_active = self.window().isActiveWindow()
        panel = self.panels[index]
        if panel.get("separator"):
            return
        if panel["instance"] is None:
            panel["instance"] = self._load_panel(panel, index)

        self.stacked_widget.setCurrentWidget(panel["instance"])
        self._shown_index = index
        self._update_stepper()
        if was_active:
            QtCore.QTimer.singleShot(0, self._restore_active_window)

    def _load_panel(self, panel: dict[str, Any], index: int) -> QtWidgets.QWidget:
        """Load a panel and replace its placeholder in the stack."""
        try:
            widget = self._create_panel_widget(panel)
            wrapper = self._wrap_panel(widget, panel)
        except Exception as exc:  # pragma: no cover - GUI error path
            traceback.print_exc()
            wrapper = self._error_widget(panel, exc)

        placeholder = self.stacked_widget.widget(index)
        self.stacked_widget.removeWidget(placeholder)
        placeholder.deleteLater()
        self.stacked_widget.insertWidget(index, wrapper)
        return wrapper

    def _create_panel_widget(self, panel: Mapping[str, Any]) -> QtWidgets.QWidget:
        """Instantiate a panel widget from its definition."""
        factory = panel.get("factory")
        if factory is not None:
            widget = factory(self)
        else:
            module = importlib.import_module(str(panel["class_path"]))
            widget_class = getattr(module, str(panel["class_name"]))
            widget = widget_class(parent=self)

        if not isinstance(widget, QtWidgets.QWidget):
            raise TypeError(f"Panel {panel.get('name')!r} did not create a QWidget")
        return widget

    def _wrap_panel(
        self, widget: QtWidgets.QWidget, panel: Mapping[str, Any] | None = None
    ) -> QtWidgets.QWidget:
        """Wrap a panel widget with margins, child-window flags and maturity banners.

        For panels flagged deprecated or experimental, a prominent warning banner
        is prepended for each flag.
        """
        wrapper = QtWidgets.QWidget()
        self._prepare_embedded_widget(widget, wrapper)
        layout = QtWidgets.QVBoxLayout(wrapper)
        layout.setContentsMargins(*self._panel_margins)
        if panel is not None:
            for flag in MATURITY_FLAGS:
                if panel.get(flag):
                    layout.addWidget(self._maturity_banner(panel, flag))
        layout.addWidget(widget)
        return wrapper

    def _maturity_banner(self, panel: Mapping[str, Any], flag: str) -> QtWidgets.QLabel:
        """Build the warning banner a deprecated or experimental panel is topped with.

        Parameters
        ----------
        panel : Mapping
            The panel definition carrying the flag and (optionally) its message.
        flag : str
            Key in :data:`MATURITY_FLAGS` — ``"deprecated"`` or ``"experimental"``.

        Returns
        -------
        QtWidgets.QLabel
            The banner label, styled for the flag.
        """
        spec = MATURITY_FLAGS[flag]
        msg = maturity_message(panel, flag, str(panel.get("name") or "This tool"))
        banner = QtWidgets.QLabel(f"{spec.marker}  {msg}")
        banner.setAlignment(QtCore.Qt.AlignCenter)
        banner.setWordWrap(True)
        banner.setStyleSheet(
            f"QLabel {{ background-color: {spec.background}; color: white; "
            "font-weight: bold; font-size: 14px; padding: 5px; "
            f"border-bottom: 2px solid {spec.border}; }}"
        )
        return banner

    def _prepare_embedded_widget(
        self,
        widget: QtWidgets.QWidget,
        parent: QtWidgets.QWidget,
    ) -> None:
        """Force lazily-loaded tools to behave as child widgets."""
        widget.setAttribute(QtCore.Qt.WA_QuitOnClose, False)
        widget.setAttribute(QtCore.Qt.WA_DontCreateNativeAncestors, True)
        # A tool built as a QMainWindow is a window until these flags are
        # changed, and on macOS the window it briefly is can take activation on
        # the way to becoming a child. Then it must at least not take activation
        # with it — this attribute is what the raise/activate dance below has
        # been racing against.
        widget.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        widget.setWindowFlags(QtCore.Qt.Widget)
        widget.setParent(parent)

    def _may_take_activation(self) -> bool:
        """Whether raising this window now would *restore* focus rather than steal it.

        Restoring activation is only ever right while the user is still here.
        Two cases where it is not, and where raising is exactly the "windows do
        not stay where I put them" behaviour:

        * **another application is in front** — the user alt-tabbed away while a
          fit ran, and a run finishing must not pull them back;
        * **another window of ours is active** — they moved to the main window,
          or to a second tool, and a background task completing here must not
          jump in front of it.

        ``activeWindow()`` alone cannot tell "the user left" from "activation is
        in flight while a panel is being embedded" — both read as ``None`` — so
        the application state answers the first question and the active window
        the second. A window *of ours* holding activation is not a reason to
        stop: the case this whole dance exists for is a tool that is briefly its
        own native window on the way to becoming a child, and that window is a
        descendant of ours.
        """
        app = QtWidgets.QApplication.instance()
        if app is None:
            return False
        if not self._application_is_frontmost():
            return False
        active = app.activeWindow()
        window = self.window()
        if active is None:
            return True
        # Walk the parent chain rather than asking ``isAncestorOf``: that answers
        # false for a child that is *itself* a window, which is precisely the
        # transient tool window this exists to take activation back from.
        node = active
        while node is not None:
            if node is window:
                return True
            node = node.parentWidget()
        return False

    @staticmethod
    def _application_is_frontmost() -> bool:
        """Whether this application is the one the user is currently in.

        Separated out because it is the only part of the activation rule that
        cannot be arranged in a test: ``QGuiApplication.applicationState`` is
        implemented in C++ and ignores patching, and offscreen reports the
        application as inactive whatever it does.
        """
        try:
            from qtpy.QtGui import QGuiApplication

            return QGuiApplication.applicationState() == QtCore.Qt.ApplicationActive
        except Exception:
            return True  # no state to consult: behave as before

    def _restore_active_window(self) -> None:
        """Keep the hosting tool active/foreground after a page is (re)shown.

        Embedding or first-showing a tool that was built as a ``QMainWindow`` can,
        on macOS, briefly create a native window that steals activation and drops
        this window behind others — the long-standing "window goes to background
        when I click Next" bug. Raising + activating once often loses the race with
        that late native window, so re-assert once more on the next event-loop
        turn.

        Both passes are conditional on :meth:`_may_take_activation`: this is a
        *restore*, and steps now start work on their own and finish minutes
        later, so an unconditional raise would drag the user back out of
        whatever they moved on to.
        """
        if not self._may_take_activation():
            return
        window = self.window()
        window.raise_()
        window.activateWindow()
        self.nav_list.setFocus(QtCore.Qt.OtherFocusReason)
        # Second pass after pending show/activation events settle.
        QtCore.QTimer.singleShot(60, self._reassert_active_window)

    def _reassert_active_window(self) -> None:
        """Second, delayed activation pass (see :meth:`_restore_active_window`)."""
        window = self.window()
        if window is not None and window.isVisible() and self._may_take_activation():
            window.raise_()
            window.activateWindow()

    def _error_widget(self, panel: Mapping[str, Any], exc: Exception) -> QtWidgets.QWidget:
        """Create an error panel for failed lazy imports."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(*self._panel_margins)

        label = QtWidgets.QLabel(f"Failed to load {panel.get('name', 'panel')}:\n{exc}")
        label.setWordWrap(True)
        label.setStyleSheet("color: red; font-size: 13px; font-weight: bold;")
        layout.addWidget(label)
        layout.addStretch()
        return widget
