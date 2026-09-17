"""Main TTTR Image Browser GUI entrypoint with toolbar and dock layout."""

from __future__ import annotations

from pathlib import Path

from qtpy.QtWidgets import (
    QAction,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QPlainTextEdit,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from chisurf.core.support import i18n
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.dock_area.dock_area import DockArea
from chisurf.gui.widgets.messages import Msg
from chisurf.gui.widgets.tools import ChisurfDockTool
from chisurf.plugins.tttr.tttr_image_browser import TTTRImageBrowser
from chisurf.plugins.tttr.tttr_image_browser.gui.client import TTTRImageBrowserClient

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:

    def _persist_plugin_state(_name: str):
        def decorator(cls):
            return cls

        return decorator

    persist_plugin_state = _persist_plugin_state


@persist_plugin_state("tttr_image_browser")
class TTTRImageBrowserTool(ChisurfDockTool):
    """Toolbar-backed TTTR Image Browser window.

    A :class:`~chisurf.gui.widgets.tools.ChisurfDockTool` (PRD-23 / PRD-36), so
    the window-level path drag-drop, the geometry helpers, the lazy MMFDB
    accessors and the declared-message status bar come from the shared base
    instead of being re-implemented here.
    """

    #: QSettings key for the base's geometry helpers (PRD-36 recipe step 1). The
    #: manifest declares window statefulness, and that mechanism owns geometry
    #: for this tool, so ``save/restore_window_geometry`` are left uncalled and
    #: the two do not both write a geometry key.
    tool_settings_name: str = "TTTRImageBrowserTool"

    class Information(ChisurfDockTool.Information):
        """Conditions worth reporting that do not stop the tool."""

        no_folder_dropped = Msg("Drop a folder of TTTR files, not a single file.")

    def __init__(self, parent=None):
        """Create the toolbar/dock shell and embed the TTTR Image Browser workspace.

        Parameters
        ----------
        parent : QWidget, optional
            The parent widget, by default None.
        """
        super().__init__(parent)
        self.setWindowTitle(f"🖼 {i18n.tr('TTTR Image Browser')}")
        self._workspace = TTTRImageBrowser(self)
        self.client = TTTRImageBrowserClient()
        self._dock_area = DockArea(self)
        self._dock_area.addTab(self._workspace, f"{Glyphs.CHART_UP} {i18n.tr('Images')}")
        self.setCentralWidget(self._dock_area)
        self._setup_toolbar()
        # When embedded in Image Tools, selecting an image proactively warms the
        # imaging pipeline (background prefill) so later steps are ready.
        try:
            self._workspace.model.add_observer(
                lambda event: self._on_image_selected() if event == "select" else None
            )
        except Exception:
            pass

    def _on_image_selected(self) -> None:
        """Tell the imaging pipeline which image is selected (triggers prefill)."""
        coordinator = getattr(self, "_coordinator", None)
        if coordinator is None:
            return
        source = getattr(self._workspace, "_current_file", None)
        if source is None:
            try:
                paths = self._workspace._selected_paths()
                source = paths[0] if paths else None
            except Exception:
                source = None
        if source:
            try:
                coordinator.set_pipeline(source=str(source))
            except Exception:
                pass

    def __getattr__(self, name: str):
        """Delegate workspace attributes for legacy tests and callers.

        The workspace is looked up in ``__dict__`` rather than through ``self``:
        a plain ``self._workspace`` here recurses without end for every attribute
        missed before ``__init__`` has assigned it — which is exactly when the
        base class initialises itself.

        Parameters
        ----------
        name : str
            Attribute name.

        Returns
        -------
        Any
            The workspace attribute.

        Raises
        ------
        AttributeError
            If the workspace does not exist yet, or does not carry *name*.
        """
        workspace = self.__dict__.get("_workspace")
        if workspace is None:
            raise AttributeError(name)
        return getattr(workspace, name)

    def on_paths_dropped(self, paths: list[Path]) -> None:
        """Open the first dropped folder in the browser.

        The base enables window-level path drag-drop for every dock tool, so a
        drop that lands on the toolbar or the window chrome — rather than on the
        workspace, which handles its own folder drops — reaches here. This tool
        browses a *folder*, so anything else is reported in the status bar
        instead of being accepted and dropped on the floor.
        """
        if any(path.is_dir() for path in paths):
            self.Information.no_folder_dropped.clear()
            self._workspace.model.on_drop(paths)
            return
        if paths:
            self.Information.no_folder_dropped()

    def _on_next_step(self) -> None:
        """Send the current/selected image to the imaging pipeline (Intensity step)."""
        coordinator = getattr(self, "_coordinator", None)
        if coordinator is None:
            return
        source = None
        try:
            source = getattr(self._workspace, "_current_file", None)
            if source is None:
                paths = self._workspace._selected_paths()
                source = paths[0] if paths else None
        except Exception:
            source = None
        if source:
            coordinator.set_pipeline(source=str(source))
        coordinator.goto_role("pixel_intensity")
        # Auto-compute + auto-create the intensity HDF5 (the browser already
        # showed the image, so no separate manual Run is needed).
        try:
            coordinator.autorun_role("pixel_intensity")
        except Exception:
            pass

    def show(self):
        """Show the window."""
        super().show()

    def raise_(self):
        """Raise the window."""
        super().raise_()

    def activateWindow(self):
        """Activate the window."""
        super().activateWindow()

    def _setup_toolbar(self) -> None:
        """Create emoji toolbar actions backed by the workspace."""
        toolbar = QToolBar(f"{Glyphs.TOOLBOX} {i18n.tr('TTTR Image Browser')}", self)
        toolbar.setObjectName("tttrImageBrowserMainToolbar")
        actions = [
            (
                f"{Glyphs.OPEN} {i18n.tr('Open')}",
                self._workspace._on_pick_folder,
                i18n.tr("Pick a folder with TTTR images"),
            ),
            (
                f"{Glyphs.CLEAR} {i18n.tr('Clear')}",
                self._workspace._on_clear,
                i18n.tr("Clear the file list"),
            ),
            (
                f"{Glyphs.RESET} {i18n.tr('Caches')}",
                self._workspace._on_clear_caches,
                i18n.tr("Clear image caches"),
            ),
            (
                f"{Glyphs.EXPORT} {i18n.tr('Export')}",
                self._workspace._on_export,
                i18n.tr("Export selected image files"),
            ),
            (
                "TIFF",
                self._workspace._on_save_tiff,
                i18n.tr("Save intensity images as TIFF stacks"),
            ),
            ("DOCX", self._workspace._on_export_docx, i18n.tr("Export selected images as DOCX")),
        ]
        for text, slot, tooltip in actions:
            action = QAction(text, self)
            action.setToolTip(tooltip)
            action.triggered.connect(slot)
            toolbar.addAction(action)

        # Hand the browsed image off to the imaging pipeline (when embedded in
        # the Image Tools shell). Steps remain freely navigable on the left.
        toolbar.addSeparator()
        next_action = QAction(f"{i18n.tr('Next')} ▶ {i18n.tr('Intensity')}", self)
        next_action.setToolTip(
            i18n.tr("Send the current image to the imaging pipeline (Intensity step).")
        )
        next_action.triggered.connect(self._on_next_step)
        toolbar.addAction(next_action)

        chk_subfolders = QCheckBox(i18n.tr("Subfolders"), self)
        chk_subfolders.setChecked(self._workspace.model.recursive)
        chk_subfolders.setToolTip(i18n.tr("Include subfolders when opening a folder"))
        chk_subfolders.toggled.connect(self._workspace._on_subfolders_toggled)
        toolbar.addWidget(chk_subfolders)
        toolbar.addSeparator()

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        help_action = QAction(f"❔ {i18n.tr('Help')}", self)
        help_action.setToolTip(
            i18n.tr(
                "Show what TTTR Image Browser does, how the toolbar works, and how to use the CLI"
            )
        )
        help_action.triggered.connect(self._show_help)
        toolbar.addAction(help_action)
        self.addToolBar(toolbar)

    def _show_help(self) -> None:
        """Show TTTR Image Browser usage and CLI help."""
        dialog = QDialog(self)
        dialog.setWindowTitle(i18n.tr("TTTR Image Browser Help"))
        dialog.resize(760, 520)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(dialog)
        text.setReadOnly(True)
        text.setPlainText(
            i18n.tr(
                "TTTR Image Browser\n\n"
                "Browse TTTR files in a folder and preview intensity images for all DetectorWizard-defined "
                "detector windows. The toolbar replaces the old inline buttons:\n\n"
                "• 📂 Open: choose a folder containing TTTR images\n"
                "• 🧹 Clear: clear the current file list\n"
                "• ♻️ Caches: clear in-memory and on-disk image caches\n"
                "• 📤 Export: copy selected raw image files\n"
                "• TIFF: export intensity images as TIFF stacks\n"
                "• DOCX: export selected images and annotations as a DOCX report\n\n"
                "The GUI talks to the TTTR Image Browser backend through RPC for file listing, metadata, "
                "and image loading. The command line interface uses Click:\n\n"
                "  tttr-image-browser list FOLDER [--recursive]\n"
                "  tttr-image-browser load FILE [--max-side 512]\n"
                "  tttr-image-browser export-tiff FILE [FILE ...] --output-dir DIR\n"
                "  tttr-image-browser contract\n"
            )
        )
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, dialog)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()
