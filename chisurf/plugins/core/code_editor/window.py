from __future__ import annotations

import pathlib

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.tools.chisurf_dock import ChisurfDock
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool
from chisurf.plugins.core.code_editor.editor import (
    CodeEditor,
    get_editor_settings,
    save_editor_settings,
)
from chisurf.plugins.icon_utils import create_emoji_icon


class CodeEditorWindow(ChisurfDockTool):
    """Full code editor plugin window built around the shared ``CodeEditor``."""

    #: Keyword arguments that belong to the embedded editor, not to the window.
    _EDITOR_KWARGS = ("language", "can_load", "enable_lsp", "show_tab_bar")

    def __init__(
        self,
        *args,
        filename: str = None,
        project_root: str | pathlib.Path | None = None,
        **kwargs,
    ):
        # The editor's own options must not reach QMainWindow, which raises
        # TypeError on the first one it does not recognise.
        editor_kwargs = {
            name: kwargs.pop(name) for name in self._EDITOR_KWARGS if name in kwargs
        }
        super().__init__(*args, **kwargs)
        self.setWindowTitle("Code Editor")
        self.resize(1200, 800)

        self.editor = CodeEditor(
            filename=filename, project_root=project_root, **editor_kwargs, **kwargs
        )
        self.setCentralWidget(self.editor)
        self.actions = self.editor.create_actions(self)

        self._create_docks()
        self._create_menus()
        self._create_toolbar()
        self._create_status_bar()

        self.editor.statusChanged.connect(self._update_status)
        self.editor.lspStatusChanged.connect(self._update_lsp_status)

    def _create_docks(self) -> None:
        """Create the window's panels, all of them ChiSurf docks.

        Every panel the editor shows beside the tabs is a :class:`ChisurfDock`
        so they share one title bar, one set of features and one object-name
        scheme -- including the notebook kernel terminal, which is a panel of
        this window like Diagnostics and Output rather than something bolted
        under one tab's cells.
        """
        self.file_dock = ChisurfDock(
            "Project", self.editor.project_browser_widget(), self, namespace="code_editor"
        )
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.file_dock)

        self.symbol_dock = ChisurfDock(
            "Symbols", self.editor.symbol_outline_widget(), self, namespace="code_editor"
        )
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.symbol_dock)
        self.tabifyDockWidget(self.file_dock, self.symbol_dock)
        self.file_dock.raise_()

        self.diagnostics_dock = ChisurfDock(
            "Diagnostics", self.editor.diagnostics_widget(), self, namespace="code_editor"
        )
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.diagnostics_dock)

        self.output_dock = ChisurfDock(
            "Output", self.editor.output_console_widget(), self, namespace="code_editor"
        )
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.output_dock)
        self.tabifyDockWidget(self.diagnostics_dock, self.output_dock)

        self._kernel_stack = QtWidgets.QStackedWidget(self)
        self._kernel_placeholder = QtWidgets.QLabel(
            "Open a notebook to get a kernel terminal.", self._kernel_stack
        )
        self._kernel_placeholder.setAlignment(QtCore.Qt.AlignCenter)
        self._kernel_placeholder.setEnabled(False)
        self._kernel_stack.addWidget(self._kernel_placeholder)
        self.kernel_dock = ChisurfDock(
            "Kernel", self._kernel_stack, self, namespace="code_editor"
        )
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.kernel_dock)
        self.tabifyDockWidget(self.output_dock, self.kernel_dock)
        self.output_dock.raise_()  # show output by default

        self.agent_dock = ChisurfDock(
            "Agent", self.editor.agent_panel, self, namespace="code_editor"
        )
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.agent_dock)
        self.agent_dock.hide()

        self._adopt_notebook_terminals()
        try:
            self.actions["agent"].triggered.disconnect()
        except (TypeError, RuntimeError):
            pass
        self.actions["agent"].triggered.connect(
            lambda _checked=False: self.agent_dock.setVisible(not self.agent_dock.isVisible())
        )

    def _create_menus(self) -> None:
        """Create the editor menu bar."""
        file_menu = self.menuBar().addMenu("File")
        for name in ["new", "open", "open_folder", "save", "save_as", "reload"]:
            file_menu.addAction(self.actions[name])
        file_menu.addSeparator()
        self._populate_notebooks_menu(file_menu)
        file_menu.addSeparator()
        file_menu.addAction("Close", self.close)

        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction(self.actions["find"])
        edit_menu.addSeparator()
        edit_menu.addAction(self.actions["completion"])

        settings_menu = self.menuBar().addMenu("Settings")
        settings_menu.addAction(self.actions["settings"])
        settings_menu.addSeparator()
        settings_menu.addAction(self.actions["toggle_line_numbers"])
        settings_menu.addAction(self.actions["toggle_whitespace"])
        settings_menu.addAction(self.actions["toggle_lsp"])

        navigate_menu = self.menuBar().addMenu("Navigate")
        for name in ["back", "forward", "definition"]:
            navigate_menu.addAction(self.actions[name])

        view_menu = self.menuBar().addMenu("View")
        for dock in [
            self.file_dock,
            self.symbol_dock,
            self.diagnostics_dock,
            self.output_dock,
            self.kernel_dock,
            self.agent_dock,
        ]:
            view_menu.addAction(dock.toggle_action())

        run_menu = self.menuBar().addMenu("Run")
        run_menu.addAction(self.actions["run"])
        run_menu.addAction(self.actions["ruff"])

    # ------------------------------------------------------------------
    # the notebook kernel terminal, hosted as a dock
    # ------------------------------------------------------------------

    def _adopt_notebook_terminals(self) -> None:
        """Follow the tab bar so the Kernel dock always shows the live kernel.

        Each notebook owns its own in-process shell, so there is one terminal
        per notebook tab and the dock shows whichever tab is in front.
        """
        self.editor.tab_widget.currentChanged.connect(
            lambda _index: self._sync_kernel_dock()
        )
        self.editor.tab_widget.tabCloseRequested.connect(
            lambda _index: QtCore.QTimer.singleShot(0, self._sync_kernel_dock)
        )
        self._sync_kernel_dock()

    def _sync_kernel_dock(self) -> None:
        """Show the current notebook tab's terminal in the Kernel dock."""
        from chisurf.plugins.core.code_editor.notebook_editor import NotebookEditor

        current = self.editor.tab_widget.currentWidget()
        if not isinstance(current, NotebookEditor):
            self._kernel_stack.setCurrentWidget(self._kernel_placeholder)
            self.kernel_dock.setEnabled(False)
            return
        self.kernel_dock.setEnabled(True)
        terminal = current.take_terminal()
        if self._kernel_stack.indexOf(terminal) < 0:
            self._kernel_stack.addWidget(terminal)
            current.terminalVisibilityRequested.connect(self._on_kernel_requested)
        self._kernel_stack.setCurrentWidget(terminal)
        current.set_terminal_checked(self.kernel_dock.isVisible())

    def _on_kernel_requested(self, visible: bool) -> None:
        """Show or hide the Kernel dock from a notebook's toolbar toggle."""
        if visible:
            self.kernel_dock.show_raised()
        else:
            self.kernel_dock.hide()

    def _populate_notebooks_menu(self, file_menu: QtWidgets.QMenu) -> None:
        """Add the File > Open Notebook submenu listing shipped notebooks."""
        from chisurf.plugins.core.code_editor.notebook_editor import shipped_notebooks

        notebooks = shipped_notebooks()
        menu = file_menu.addMenu("Open Notebook")
        if not notebooks:
            empty = menu.addAction("No shipped notebooks found")
            empty.setEnabled(False)
            return
        groups: dict[str, list[pathlib.Path]] = {}
        for path in notebooks:
            group = path.name.split("_", 1)[0] if "_" in path.name else "Other"
            groups.setdefault(group, []).append(path)
        for group in sorted(groups):
            submenu = menu.addMenu(group)
            for path in sorted(groups[group], key=lambda p: p.name):
                action = submenu.addAction(path.stem)
                action.setToolTip(str(path))
                action.triggered.connect(
                    lambda _checked=False, p=path: self.editor.open_file(str(p))
                )

    def _create_toolbar(self) -> None:
        """Create the main editor toolbar."""
        toolbar = QtWidgets.QToolBar("Editor", self)
        toolbar.setObjectName("code_editor_toolbar")
        toolbar.setMovable(True)
        toolbar.setIconSize(QtCore.QSize(18, 18))
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)

        for name in ["new", "open", "open_folder", "save"]:
            toolbar.addAction(self.actions[name])
        toolbar.addSeparator()
        for name in ["back", "forward", "definition", "completion"]:
            toolbar.addAction(self.actions[name])
        toolbar.addSeparator()

        run_btn = QtWidgets.QToolButton(toolbar)
        run_btn.setIcon(create_emoji_icon("▶", size=24))
        run_btn.setText("Run")
        run_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        run_btn.setToolTip("Run the current script in the selected endpoint")
        run_btn.clicked.connect(lambda _checked=False: self.editor.run_macro(None))
        toolbar.addWidget(run_btn)

        stop_btn = QtWidgets.QToolButton(toolbar)
        stop_btn.setIcon(create_emoji_icon("⏹", size=24))
        stop_btn.setText("Stop")
        stop_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        stop_btn.setToolTip("Stop the running script")
        stop_btn.setEnabled(False)
        stop_btn.clicked.connect(self.editor.stop_macro)
        toolbar.addWidget(stop_btn)

        self.editor.runStateChanged.connect(
            lambda running: (
                run_btn.setEnabled(not running),
                stop_btn.setEnabled(running),
                self.output_dock.raise_() if running else None,
            )
        )

        endpoint = QtWidgets.QComboBox(toolbar)
        # Two endpoints, not three. "Console" and "IPython" were the same
        # thing once the console stopped being a Jupyter kernel: both ran the
        # file in-process with `cs` in scope. "ipython" is still accepted on
        # load, because it is in users' saved settings and in script shebangs.
        _endpoint_keys = ["console", "process"]
        endpoint.addItem(create_emoji_icon("🖥", size=16), "In ChiSurf")
        endpoint.addItem(create_emoji_icon(Glyphs.SETTINGS, size=16), "Separate process")
        settings = get_editor_settings()
        current = settings.get("run_endpoint", "console")
        if current == "ipython":
            current = "console"
        endpoint.setCurrentIndex(_endpoint_keys.index(current) if current in _endpoint_keys else 0)
        endpoint.setToolTip(
            "In ChiSurf — runs in this process, so cs and the open fits are in scope\n"
            "Separate process — runs isolated; a crash cannot take ChiSurf down"
        )
        endpoint.currentIndexChanged.connect(
            lambda idx: self._set_run_endpoint(_endpoint_keys[idx])
        )
        toolbar.addWidget(endpoint)
        self._endpoint_combo = endpoint
        self._endpoint_keys = _endpoint_keys

        # When the active file has a shebang, pre-select the matching endpoint.
        # The user can still change the combo before pressing Run.
        self.editor.endpointHint.connect(self._apply_endpoint_hint)

        toolbar.addSeparator()
        toolbar.addAction(self.actions["ruff"])
        toolbar.addAction(self.actions["toggle_whitespace"])
        ws_btn = toolbar.widgetForAction(self.actions["toggle_whitespace"])
        if ws_btn is not None:
            ws_btn.setStyleSheet(
                "QToolButton:checked { background-color: palette(highlight);"
                " color: palette(highlighted-text); border-radius: 3px; }"
            )
        toolbar.addAction(self.actions["settings"])

        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        toolbar.addWidget(spacer)

        toolbar.addSeparator()
        toolbar.addAction(self.actions["agent"])
        self.addToolBar(toolbar)

    def _set_run_endpoint(self, mode: str) -> None:
        """Persist the selected execution endpoint."""
        settings = get_editor_settings()
        settings["run_endpoint"] = mode
        save_editor_settings(settings)

    def _apply_endpoint_hint(self, endpoint: str) -> None:
        """Pre-select the endpoint combo to match a script's shebang (user can still override)."""
        if endpoint == "ipython":
            # Scripts in the wild still carry `# !chisurf: ipython`, including
            # some shipped in examples/. It names the in-process endpoint.
            endpoint = "console"
        if endpoint not in self._endpoint_keys:
            return
        idx = self._endpoint_keys.index(endpoint)
        # Block the combo's signal so this doesn't overwrite the persisted preference.
        self._endpoint_combo.blockSignals(True)
        self._endpoint_combo.setCurrentIndex(idx)
        self._endpoint_combo.blockSignals(False)

    def _create_status_bar(self) -> None:
        """Create status labels for editor state."""
        self.file_status = QtWidgets.QLabel("Untitled", self)
        self.position_status = QtWidgets.QLabel("Ln 1, Col 0", self)
        self.dirty_status = QtWidgets.QLabel("", self)
        self.lsp_status = QtWidgets.QLabel("LSP idle", self)
        self.statusBar().addPermanentWidget(self.file_status, 1)
        self.statusBar().addPermanentWidget(self.position_status)
        self.statusBar().addPermanentWidget(self.dirty_status)
        self.statusBar().addPermanentWidget(self.lsp_status)
        self.statusBar().showMessage("Ready")

    def _update_status(self, status: dict) -> None:
        """Update the status bar from shared editor status."""
        if "file" in status:
            self.file_status.setText(str(status.get("file") or "Untitled"))
        if "line" in status:
            self.position_status.setText(
                f"Ln {status.get('line', 1)}, Col {status.get('column', 0)}"
            )
        if "modified" in status:
            self.dirty_status.setText("Modified" if status.get("modified") else "")
        if "lsp" in status:
            self._update_lsp_status(str(status["lsp"]))

    def _update_lsp_status(self, status: str) -> None:
        """Update the status bar LSP state."""
        self.lsp_status.setText(status)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Stop editor services when the window closes."""
        if self.editor._lsp_client is not None:
            self.editor._lsp_client.stop()
        if self.editor._rpc_server is not None:
            self.editor._rpc_server.stop()
        super().closeEvent(event)


__all__ = ["CodeEditorWindow"]
