"""Reusable left-navigation stacked tool shell."""

from __future__ import annotations

import importlib
import json
import logging
import pathlib
import traceback
from collections.abc import Mapping, Sequence
from typing import Any

from qtpy import QtCore, QtWidgets


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


def load_panels_json(path: str | pathlib.Path) -> tuple[dict, list[dict]]:
    """Load a data-driven ``panels.json`` spec into NavigationPanelTool panels.

    The spec is a dict with a ``title`` and a ``panels`` list; each entry names
    a tool by its GUI entrypoint (``"module:Class"``) plus ``name`` / ``icon`` /
    ``description`` / ``role``. Set ``"embed": true`` for ``QMainWindow`` tools
    that must be flattened via :func:`embed_mainwindow`; ``{"separator": true}``
    inserts a group separator. Panels import lazily inside their factories.

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
                "factory": _make_panel_factory(
                    entry["entrypoint"], bool(entry.get("embed", False))
                ),
            }
        )
    return spec, panels


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
        self._build_ui(navigation_width)
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
        self._btn_next.setToolTip("Go to the next workflow step")
        self._btn_next.clicked.connect(self.goto_next_step)
        bar.addPermanentWidget(self._btn_prev)
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
        QtCore.QCoreApplication.processEvents()

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
        QtCore.QCoreApplication.processEvents()

    def report_progress(self, value: int, maximum: int, message: str | None = None) -> None:
        """Show determinate progress (``value`` of ``maximum``)."""
        if message is not None:
            self._status_message.setText(str(message))
        self._status_progress.setRange(0, int(maximum))
        self._status_progress.setValue(int(value))
        self._status_progress.setVisible(True)
        QtCore.QCoreApplication.processEvents()

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
        QtCore.QCoreApplication.processEvents()

    def _task_set_message(self, task: _StatusTask, message: str) -> None:
        if task is not self._active_task:
            return
        self._status_message.setText(message)
        QtCore.QCoreApplication.processEvents()

    def _task_set_range(self, task: _StatusTask, a: int, b: int) -> None:
        if task is not self._active_task:
            return
        self._status_progress.setRange(a, b)
        QtCore.QCoreApplication.processEvents()

    def _task_set_value(self, task: _StatusTask, v: int) -> None:
        if task is not self._active_task:
            return
        self._status_progress.setValue(v)
        QtCore.QCoreApplication.processEvents()

    def _deactivate_task(self, task: _StatusTask) -> None:
        if task is not self._active_task:
            return
        self._active_task = None
        # Hide the progress/Cancel widgets but leave the last message on the bar
        # (e.g. a tool's final "Done – N bursts", logged just before close).
        self._status_progress.setVisible(False)
        self._status_cancel.setVisible(False)

    # ── Next/Back stepper ───────────────────────────────────────────────────
    def goto_next_step(self) -> bool:
        """Select the next non-separator panel; return ``True`` if one exists."""
        cur = self.nav_list.currentRow()
        for i in range(cur + 1, len(self.panels)):
            if not self.panels[i].get("separator"):
                self.nav_list.setCurrentRow(i)
                return True
        return False

    def goto_prev_step(self) -> bool:
        """Select the previous non-separator panel; return ``True`` if one exists."""
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
        """Return the selector label for a panel (flagged when experimental)."""
        icon = str(panel.get("icon") or "").strip()
        name = str(panel.get("name") or "").strip()
        label = f"{icon} {name}".strip()
        if panel.get("experimental"):
            label = f"{label}  ⚠️"
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
        """Load and show the selected panel."""
        if index < 0 or index >= len(self.panels):
            return

        was_active = self.window().isActiveWindow()
        panel = self.panels[index]
        if panel.get("separator"):
            return
        if panel["instance"] is None:
            panel["instance"] = self._load_panel(panel, index)

        self.stacked_widget.setCurrentWidget(panel["instance"])
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
        """Wrap a panel widget with margins, child-window flags and an experimental banner.

        For panels flagged experimental, a prominent warning banner is prepended.
        """
        wrapper = QtWidgets.QWidget()
        self._prepare_embedded_widget(widget, wrapper)
        layout = QtWidgets.QVBoxLayout(wrapper)
        layout.setContentsMargins(*self._panel_margins)
        if panel is not None and panel.get("experimental"):
            layout.addWidget(self._experimental_banner(panel))
        layout.addWidget(widget)
        return wrapper

    def _experimental_banner(self, panel: Mapping[str, Any]) -> QtWidgets.QLabel:
        """Build the red 'experimental / untested' banner for an experimental panel."""
        msg = panel.get("experimental_message") or (
            f"{panel.get('name', 'This tool')} is EXPERIMENTAL and UNTESTED — "
            "results are not validated"
        )
        banner = QtWidgets.QLabel(f"⚠️  {msg}")
        banner.setAlignment(QtCore.Qt.AlignCenter)
        banner.setWordWrap(True)
        banner.setStyleSheet(
            "QLabel { background-color: #b30000; color: white; font-weight: bold; "
            "font-size: 14px; padding: 5px; border-bottom: 2px solid #7d0000; }"
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
        widget.setWindowFlags(QtCore.Qt.Widget)
        widget.setParent(parent)

    def _restore_active_window(self) -> None:
        """Keep the hosting tool active after a lazy page is embedded."""
        window = self.window()
        window.raise_()
        window.activateWindow()
        self.nav_list.setFocus(QtCore.Qt.OtherFocusReason)

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
