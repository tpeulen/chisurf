"""Plugin Check GUI tool."""

from __future__ import annotations

from typing import Any

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.autoform.sections.progress_section import InlineProgressWidget
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.progress import ChiSurfProgress


class PluginCheckTool(QtWidgets.QWidget):
    """Plugin startup-check tool with toolbar controls."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the plugin check tool."""
        super().__init__(parent)
        self.test_runner = None
        self.plugin_results: dict[str, dict[str, Any]] = {}
        self.setWindowTitle(f"{Glyphs.TEST} ChiSurf Plugin Check")
        self.setMinimumSize(940, 560)

        self._build_ui()
        self.destroyed.connect(lambda: self.cleanup())
        self.refresh_plugins()

    def _build_ui(self) -> None:
        """Build the main user interface."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self._setup_toolbar(layout)

        title_label = QtWidgets.QLabel(f"{Glyphs.TEST} ChiSurf Plugin Check")
        title_font = QtGui.QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        desc_label = QtWidgets.QLabel(
            f"Tests all plugins for startup errors. {Glyphs.SUCCESS} success, {Glyphs.ERROR} failure, {Glyphs.WARNING} skipped."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(desc_label)

        # The shared inline bar, so a plugin sweep looks like every other long
        # run in ChiSurf (and can be cancelled the same way). The message goes to
        # the status label above it, so the bar does not repeat it.
        self.progress_bar = InlineProgressWidget(show_text=False)
        self.progress_bar.bar.setMaximumHeight(18)
        layout.addWidget(self.progress_bar)
        self._task = None

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        self.plugin_tree = QtWidgets.QTreeWidget()
        self.plugin_tree.setHeaderLabels(
            ["Plugin", "Status", "Source", "Depends on", "Error"]
        )
        self.plugin_tree.setColumnWidth(0, 250)
        self.plugin_tree.setColumnWidth(1, 80)
        self.plugin_tree.setColumnWidth(2, 80)
        self.plugin_tree.setColumnWidth(3, 160)
        self.plugin_tree.itemClicked.connect(self.on_plugin_selected)
        self.plugin_tree.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        splitter.addWidget(self.plugin_tree)

        details_group = QtWidgets.QGroupBox("Plugin Details")
        details_group.setMinimumWidth(400)
        details_group.setMaximumWidth(400)
        details_group.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        details_layout = QtWidgets.QVBoxLayout(details_group)
        details_layout.setContentsMargins(5, 5, 5, 5)
        details_layout.setSpacing(3)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll_area.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        content_widget = QtWidgets.QWidget()
        content_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(3)

        self.details_label = QtWidgets.QLabel("Select a plugin to view details")
        self.details_label.setWordWrap(True)
        self.details_label.setTextFormat(QtCore.Qt.RichText)
        self.details_label.setStyleSheet("font-size: 11px;")
        self.details_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        content_layout.addWidget(self.details_label)

        self.error_text = QtWidgets.QTextEdit()
        self.error_text.setMaximumHeight(120)
        self.error_text.setPlaceholderText("Error details will appear here...")
        self.error_text.setStyleSheet("font-size: 10px;")
        self.error_text.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        content_layout.addWidget(self.error_text)

        scroll_area.setWidget(content_widget)
        details_layout.addWidget(scroll_area)
        splitter.addWidget(details_group)
        splitter.setSizes([540, 400])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        layout.addWidget(splitter, 1)

        self.status_label = QtWidgets.QLabel(f"Ready {Glyphs.SPARKLE}")
        self.status_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(self.status_label)

    def _setup_toolbar(self, layout) -> None:
        """Create the plugin check toolbar."""
        toolbar = QtWidgets.QToolBar("Plugin Check")
        toolbar.setObjectName("plugin_check_toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QtCore.QSize(18, 18))
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        layout.addWidget(toolbar)

        self.test_all_action = QtWidgets.QAction(f"{Glyphs.TEST} Test All Plugins", self)
        self.test_all_action.setToolTip("Run startup checks for every plugin")
        self.test_all_action.triggered.connect(self.start_testing)
        toolbar.addAction(self.test_all_action)

        self.test_safe_action = QtWidgets.QAction("🛡️ Test Safe Plugins", self)
        self.test_safe_action.setToolTip("Test a few plugins with aggressive filtering and short timeouts")
        self.test_safe_action.triggered.connect(self.start_safe_testing)
        toolbar.addAction(self.test_safe_action)

        self.refresh_action = QtWidgets.QAction(f"{Glyphs.REFRESH} Refresh", self)
        self.refresh_action.setToolTip("Refresh the plugin list")
        self.refresh_action.triggered.connect(self.refresh_plugins)
        toolbar.addAction(self.refresh_action)

        toolbar.addSeparator()

        self.clear_blacklist_action = QtWidgets.QAction(f"{Glyphs.DELETE} Clear Blacklist", self)
        self.clear_blacklist_action.setToolTip("Remove all plugins from the blacklist")
        self.clear_blacklist_action.triggered.connect(self.clear_blacklist)
        toolbar.addAction(self.clear_blacklist_action)

        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        toolbar.addWidget(spacer)

        self.delay_spinbox = QtWidgets.QDoubleSpinBox()
        self.delay_spinbox.setRange(0.0, 5.0)
        self.delay_spinbox.setSingleStep(0.1)
        self.delay_spinbox.setValue(0.5)
        self.delay_spinbox.setSuffix(" sec")
        self.delay_spinbox.setToolTip("Delay between plugin tests to prevent GUI overload")
        self.delay_spinbox.setMaximumWidth(80)
        toolbar.addWidget(QtWidgets.QLabel("Delay:"))
        toolbar.addWidget(self.delay_spinbox)

        self.skip_blacklisted_checkbox = QtWidgets.QCheckBox("Skip blacklisted")
        self.skip_blacklisted_checkbox.setChecked(True)
        self.skip_blacklisted_checkbox.setToolTip("Automatically skip plugins blacklisted due to frequent failures")
        toolbar.addWidget(self.skip_blacklisted_checkbox)

    def refresh_plugins(self) -> None:
        """Refresh the plugin list."""
        self.plugin_tree.clear()
        self.plugin_results = {}
        self.details_label.setText("Select a plugin to view details")
        self.error_text.setVisible(False)

        try:
            from chisurf.plugins import invalidate_plugin_cache, iter_plugins

            # Explicit user-triggered refresh: re-scan rather than reuse cache.
            invalidate_plugin_cache()
            plugins = list(iter_plugins())

            for plugin_info in plugins:
                plugin_name = plugin_info.get("plugin_name", "Unknown")
                source = plugin_info.get("source", "Unknown")

                requires = plugin_info.get("requires") or {}
                optional = plugin_info.get("optional_requires") or {}

                item = QtWidgets.QTreeWidgetItem(self.plugin_tree)
                item.setText(0, plugin_name)
                item.setText(1, Glyphs.PENDING)
                item.setText(2, source)
                item.setText(3, self._dependency_summary(requires, optional))
                item.setText(4, "")
                item.setData(0, QtCore.Qt.UserRole, plugin_info)

                if source == "user":
                    item.setForeground(2, QtGui.QColor("blue"))

            problems = self._dependency_problems(plugins)
            if problems:
                self.status_label.setText(
                    f"{len(plugins)} plugin(s) found — "
                    f"{len(problems)} dependency problem(s); select a plugin for details"
                )
            else:
                self.status_label.setText(f"Ready ✨ {len(plugins)} plugin(s) found")
        except Exception as exc:
            self.status_label.setText(f"Error loading plugins: {exc}")

    @staticmethod
    def _dependency_summary(requires: dict, optional: dict) -> str:
        """One cell describing what a plugin depends on.

        Hard dependencies are named because they are few and they decide load
        order; optional ones are counted because a hub can have a dozen and the
        names would not fit.
        """
        parts = []
        if requires:
            parts.append(", ".join(sorted(requires)))
        if optional:
            parts.append(f"(+{len(optional)} optional)")
        return " ".join(parts)

    def _dependency_problems(self, plugins: list[dict[str, Any]]) -> list[str]:
        """Resolve the discovered plugins and keep the problems for the details pane."""
        try:
            from chisurf.core.plugin.dependencies import resolve

            report = resolve(
                {
                    "id": p.get("manifest_id") or "",
                    "version": p.get("manifest_version") or "",
                    "requires": p.get("requires") or {},
                    "optional_requires": p.get("optional_requires") or {},
                }
                for p in plugins
            )
        except Exception:
            self._dependency_report = None
            return []
        self._dependency_report = report
        return report.problems()

    def start_safe_testing(self) -> None:
        """Start testing a few plugins with aggressive filtering and short timeouts."""
        if self.test_runner and self.test_runner.is_running:
            return

        plugins = []
        for index in range(self.plugin_tree.topLevelItemCount()):
            item = self.plugin_tree.topLevelItem(index)
            plugin_info = item.data(0, QtCore.Qt.UserRole)
            if plugin_info:
                plugins.append(plugin_info)
                if len(plugins) >= 10:
                    break

        if not plugins:
            self.status_label.setText(f"No plugins to test {Glyphs.PENDING}")
            return

        self._setup_runner(plugins, safe_mode=True)
        self._set_test_buttons_enabled(False)
        self._task = ChiSurfProgress(self, "Testing safe plugins…", len(plugins))
        self.status_label.setText("🛡️ Testing safe plugins (aggressive filtering)...")
        self.test_runner.start_testing()

    def start_testing(self) -> None:
        """Start testing all plugins."""
        if self.test_runner and self.test_runner.is_running:
            return

        plugins = []
        for index in range(self.plugin_tree.topLevelItemCount()):
            item = self.plugin_tree.topLevelItem(index)
            plugin_info = item.data(0, QtCore.Qt.UserRole)
            if plugin_info:
                plugins.append(plugin_info)

        if not plugins:
            self.status_label.setText(f"No plugins to test {Glyphs.PENDING}")
            return

        self._setup_runner(plugins, safe_mode=False)
        self._set_test_buttons_enabled(False)
        self._task = ChiSurfProgress(self, "Testing plugins…", len(plugins))
        self.status_label.setText(f"{Glyphs.TEST} Testing plugins...")
        self.test_runner.start_testing()

    def _set_test_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable testing actions."""
        self.test_all_action.setEnabled(enabled)
        self.test_safe_action.setEnabled(enabled)

    def _setup_runner(self, plugins: list[dict[str, Any]], safe_mode: bool = False) -> None:
        """Set up the test runner with callbacks."""
        try:
            from chisurf.macros.plugin_check import PluginTestRunner
        except ImportError:
            import importlib.util

            spec = importlib.util.spec_from_file_location("plugin_check", "cs/macros/plugin_check.py")
            plugin_check_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(plugin_check_module)
            PluginTestRunner = plugin_check_module.PluginTestRunner

        self.test_runner = PluginTestRunner()
        self.test_runner.set_plugins(plugins)
        self.test_runner.set_safe_mode(safe_mode)
        self.test_runner.set_skip_blacklisted(self.skip_blacklisted_checkbox.isChecked())
        self.test_runner.set_delay_between_plugins(self.delay_spinbox.value())
        self.test_runner.set_callbacks(
            progress_callback=self.update_progress,
            result_callback=self.update_plugin_result,
            finished_callback=self.testing_finished,
        )

    def update_progress(self, current: int, total: int) -> None:
        """Update progress bar."""
        if self._task is not None:
            self._task.update_progress(current, f"Testing plugins… {current}/{total}")
        self.status_label.setText(f"🧪 Testing plugins... {current}/{total}")

    def update_plugin_result(self, plugin_name: str, success: bool, error_message: str | None) -> None:
        """Update the result for a single plugin."""
        for index in range(self.plugin_tree.topLevelItemCount()):
            item = self.plugin_tree.topLevelItem(index)
            if item.text(0) == plugin_name:
                error = error_message or ""
                if success:
                    item.setText(1, Glyphs.SUCCESS)
                    item.setForeground(1, QtGui.QColor("green"))
                elif any(skip_word in error.lower() for skip_word in ["skipped", "gui execution blocked"]):
                    item.setText(1, Glyphs.WARNING)
                    item.setForeground(1, QtGui.QColor("orange"))
                else:
                    item.setText(1, Glyphs.ERROR)
                    item.setForeground(1, QtGui.QColor("red"))

                # column 3 is "Depends on"; the error belongs in column 4
                item.setText(4, error[:50] + "..." if len(error) > 50 else error)

                self.plugin_results[plugin_name] = {
                    "success": success,
                    "skipped": any(skip_word in error.lower() for skip_word in ["skipped", "gui execution blocked"]),
                    "error": error,
                    "item": item,
                }
                break

    def testing_finished(self) -> None:
        """Called when all plugins have been tested."""
        self._set_test_buttons_enabled(True)
        if self._task is not None:
            self._task.close()
            self._task = None

        total = len(self.plugin_results)
        successful = sum(1 for result in self.plugin_results.values() if result["success"])
        skipped = sum(1 for result in self.plugin_results.values() if result.get("skipped"))
        failed = total - successful - skipped

        if total == 0:
            self.status_label.setText(f"No plugins tested {Glyphs.PENDING}")
        else:
            self.status_label.setText(
                f"Testing complete ✨ {successful} ✅ success, {failed} ❌ failed, {skipped} ⚠️ skipped"
            )

    def cleanup(self) -> None:
        """Clean up runner when the window is closed."""
        if self.test_runner and self.test_runner.is_running:
            self.test_runner.stop_testing()
            self.test_runner = None

    def clear_blacklist(self) -> None:
        """Clear all blacklisted plugins."""
        if self.test_runner:
            self.test_runner.blacklisted.clear()
        self.status_label.setText(f"Blacklist cleared {Glyphs.CLEAR}")

    def _dependency_details(self, plugin_info: dict) -> list[str]:
        """Detail rows describing this plugin's declared dependencies."""
        def _render(mapping: dict) -> str:
            # "*" means "any version, it just has to be there" -- printing it
            # beside every name is noise that hides the real bounds.
            return ", ".join(
                name if str(bound).strip() in ("", "*") else f"{name} {bound}"
                for name, bound in sorted(mapping.items())
            )

        rows = []
        requires = plugin_info.get("requires") or {}
        optional = plugin_info.get("optional_requires") or {}
        if requires:
            rows.append("<b>Requires (load order):</b> " + _render(requires))
        if optional:
            rows.append("<b>Optional:</b> " + _render(optional))
        report = getattr(self, "_dependency_report", None)
        plugin_id = plugin_info.get("manifest_id")
        if report is not None and plugin_id:
            mine = [line for line in report.problems() if line.startswith(f"{plugin_id}:")]
            if mine:
                rows.append("<b>Problems:</b><br>" + "<br>".join(mine))
        return rows

    def on_plugin_selected(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """Handle plugin selection to show details."""
        del column
        plugin_name = item.text(0)

        if plugin_name in self.plugin_results:
            result = self.plugin_results[plugin_name]
            plugin_info = item.data(0, QtCore.Qt.UserRole)

            details = [
                f"<b>Plugin:</b> {plugin_name}",
                f"<b>Module:</b> {plugin_info.get('module_path', 'Unknown')}",
                f"<b>Source:</b> {plugin_info.get('source', 'Unknown')}",
                f"<b>Status:</b> {f'{Glyphs.SUCCESS} Success' if result['success'] else f'{Glyphs.ERROR} Failed'}",
            ]

            details.extend(self._dependency_details(plugin_info))

            if plugin_info.get("description"):
                description = plugin_info["description"]
                formatted_desc = description.replace(". ", ".<br><br>")
                formatted_desc = formatted_desc.replace(" - ", "<br>- ")
                formatted_desc = formatted_desc.replace("Features:", "<br><br><b>Features:</b>")
                details.append(f"<b>Description:</b><br>{formatted_desc}")

            self.details_label.setText("<br>".join(details))

            if not result["success"] and result["error"]:
                self.error_text.setText(result["error"])
                self.error_text.setVisible(True)
            else:
                self.error_text.setVisible(False)
        else:
            self.details_label.setText("Select a plugin to view details")
            self.error_text.setVisible(False)


PluginCheckWidget = PluginCheckTool
