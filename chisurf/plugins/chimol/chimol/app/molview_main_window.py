"""Protein structure viewer (Chimol) plugin."""

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

import chisurf as cs
from chisurf.gui import dialogs
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

# These are imported independently on purpose: the structure reader is pure
# core code, while `open_files` drags in the whole Qt widget stack. Sharing one
# try/except made any GUI-side import failure silently disable the reader, which
# degraded every load to a raw coordinate blob (no residues, sequence or Rg).
try:  # moview can run inside or outside cs
    import chisurf.core.settings as _cs_settings
except Exception:  # pragma: no cover - standalone moview
    _cs_settings = None

try:
    from chisurf.core.structure import Structure as _ChiSurfStructure

    _STRUCTURE_IMPORT_ERROR: Optional[BaseException] = None
except Exception as _exc:  # pragma: no cover - standalone moview
    # Kept, not just logged: "the reader is unavailable" is useless on its own,
    # and the log line is easy to miss during startup. The message shown when a
    # file degrades names this exception.
    _STRUCTURE_IMPORT_ERROR = _exc
    logging.getLogger(__name__).warning(
        "chisurf.core.structure.Structure is unavailable; Chimol will fall back "
        "to raw coordinates and cannot show residues, sequence or Rg.",
        exc_info=True,
    )
    _ChiSurfStructure = None

try:
    from chisurf.gui.widgets.general import open_files as _cs_open_files
except Exception:  # pragma: no cover - standalone moview
    _cs_open_files = None


def _qt_open_files(*, description: str = "Open file", file_type: str = "All files (*.*)"):
    """A plain Qt file chooser, for when ChiSurf's own is unavailable.

    This lives **here**, in the Qt window, rather than in ``io.structure``
    where it used to. A structure reader's job is parsing PDB and mmCIF, and it
    had a ``QFileDialog`` in it -- so importing the reader pulled in a window
    system, in a plugin that now runs in two hosts without one.

    Parameters
    ----------
    description, file_type : str, optional
        Dialog title and filter.

    Returns
    -------
    list of str
    """
    from qtpy import QtWidgets  # noqa: PLC0415

    files, _ = QtWidgets.QFileDialog.getOpenFileNames(None, description, "", file_type)
    return [str(f) for f in files]

from .. import config as _config
from ..analysis import (
    assign_ss_c3_from_atoms,
    assign_ss_c3_from_file,
    build_residue_alignment,
)
from ..cmd import cmd as _cmd
from ..colors import _OBJECT_ID_ROLE, _SEQ_COLOR_ROLE
from ..config import _DISPLAY_CONFIG
from ..io import (
    TrajectoryFormatError,
    load_mrc_as_points,
    load_structure_payload,
    load_trajectory_frames,
    open_structure_files,
)
from ..renderer.internal_gui import GuiRow as InternalGuiRow
from ..renderer.internal_gui import SequenceRow as InternalSequenceRow
from ..renderer.view import MolView
from .controls_panel import ControlsToolbar
from .menu_bar import MENU_BAR, TOOLBAR, build_menu_bar
from .objects_panel import ObjectsDock
from .rmf_panel import RmfPanel
from .sequence_dock import SequenceDock
from .volume_panel import VolumeViewModel

try:
    from chisurf.gui.misc_helpers import get_plugin_settings_path, persist_plugin_state
except ImportError:
    persist_plugin_state = lambda n: lambda c: c
    get_plugin_settings_path = lambda n: Path.home() / ".chisurf" / f"plugin_{n}_settings.ini"

try:
    from chisurf.gui.widgets.dock_area import DockArea
except ImportError:
    DockArea = None


_SEQ_INDEX_ROLE = QtCore.Qt.UserRole + 150

_DEFAULT_DOCK_AREA_STATE: dict = {
    "version": 1,
    "root": {
        "type": "splitter",
        "orientation": "vertical",
        # The 3-D view, then the command console under it across the full
        # width. PyMOL keeps a prompt and a line of feedback on screen at all
        # times (`internal_prompt` and `internal_feedback`, both default on,
        # drawn at the bottom of the viewport) because typing commands *is* the
        # interface. Ours was a background tab in a side stack, so the first
        # thing a PyMOL user reaches for was two clicks away and invisible until
        # found.
        "sizes": [700, 170],
        "children": [
            {
                "type": "splitter",
                "orientation": "horizontal",
                # Pixels, like every other "sizes" here -- not a 3:1 ratio.
                # QSplitter takes these literally, so [3, 1] asked for a 3-pixel
                # viewport, got clamped to the children's minimum widths, and
                # left the 3D view with about 40% of the window instead of 75%.
                "sizes": [1200, 400],
                "children": [
                    {
                        "type": "tab",
                        "tabs": [
                            {
                                "widget_key": "3D View",
                                "tab_name": "3D View",
                                "tab_text": "3D View",
                            },
                        ],
                        "current_index": 0,
                    },
                    {
                        "type": "tab",
                        "tabs": [
                            {"widget_key": "Hierarchy", "tab_name": "Hierarchy", "tab_text": "Hierarchy"},
                            {"widget_key": "RMF", "tab_name": "RMF", "tab_text": "RMF"},
                            {"widget_key": "Map", "tab_name": "Map", "tab_text": "Map"},
                        ],
                        "current_index": 0,
                    },
                ],
            },
        ],
    },
    "active_tab_widget": [0],
    "current_index": 0,
}


#: Docks the viewport panel replaced. A saved layout still names them, and a
#: layout is applied verbatim, so without this they come back the moment anyone
#: reopens the window -- looking exactly like the removal never happened.
_RETIRED_DOCKS = frozenset({"Sequence", "State", "Timeline"})

#: Side panels that start hidden because they have nothing to show yet. Each is
#: empty until a file supplies its content, and an empty panel that takes a
#: third of the window is worse than no panel: it reads as a broken layout.
#: ``Objects`` is permanently hidden (the list is in the viewport); the other
#: three appear by themselves once they have something -- see
#: :meth:`MolViewPluginWindow._reveal_panel_with_content`.
_INITIALLY_HIDDEN_DOCKS = frozenset({"Hierarchy", "RMF", "Map"})


def _without_retired_docks(state):
    """Return *state* with every reference to a retired dock removed.

    Walks the structure rather than assuming its shape: the layout is nested
    areas and tab lists, and a saved one from an older version may be nested
    differently from what this version writes.
    """
    if isinstance(state, dict):
        name = state.get("tab_name") or state.get("widget_key") or state.get("tab_text")
        if isinstance(name, str) and name in _RETIRED_DOCKS:
            return None
        cleaned = {}
        for key, value in state.items():
            pruned = _without_retired_docks(value)
            if pruned is not None:
                cleaned[key] = pruned
        return cleaned
    if isinstance(state, list):
        return [
            item for item in (_without_retired_docks(v) for v in state)
            if item is not None
        ]
    return state


@persist_plugin_state("chimol")
class MolViewPluginWindow(ChisurfDockTool):
    """Chimol main window — toolbar, statusbar, DockArea panels, and 3D view."""

    #: How many chains the sequence strip will draw before it stops and says
    #: how many it left out. An integrative model is not a protein with four
    #: chains — the NPC has hundreds, and a row each fills the viewport and
    #: leaves no molecule. The strip is *reference material*; a structure with
    #: 250 chains is read from the hierarchy, not from 250 rows of letters.
    MAX_SEQUENCE_ROWS = 12

    def __init__(
        self,
        parent=None,
        *,
        button_overrides: Optional[dict[str, dict[str, Any]]] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Chimol - Protein Viewer")
        self._dock_area_restored = False

        self._object_store: dict[str, dict[str, Any]] = {}
        self._block_object_list_signals = False
        self._active_object_id: Optional[str] = None
        self._scroll_targets: list[QtWidgets.QScrollBar] = []
        self._scroll_updating = False
        self._scroll_master: Optional[QtWidgets.QScrollBar] = None
        self._content_scrollbar: Optional[QtWidgets.QScrollBar] = None

        layout_cfg = _DISPLAY_CONFIG.get("layout", {})
        margins = layout_cfg.get("root_margins", [4, 4, 4, 4])
        if not isinstance(margins, (list, tuple)) or len(margins) != 4:
            margins = [4, 4, 4, 4]
        try:
            l, t, r, b = (int(m) for m in margins)
        except Exception:
            l, t, r, b = 4, 4, 4, 4
        spacing = layout_cfg.get("root_spacing", 4)
        try:
            spacing = int(spacing)
        except Exception:
            spacing = 4
        dock_margins = (l, t, r, b)

        self.viewer = MolView(self)

        # ── Toolbar ───────────────────────────────────────────────────
        # Built but **not added to the window**: the toolbar is drawn in the
        # viewport now (`menu_bar.TOOLBAR`), where every button is a command
        # rather than a Qt slot, so the same row serves the browser. The widget
        # survives only because a handful of call sites still read
        # `button_info.isChecked()`; nothing puts it on screen.
        self.controls = ControlsToolbar(
            self, button_overrides=button_overrides,
        )
        # Off the window entirely, not merely hidden: a `QToolBar` whose parent
        # is a `QMainWindow` is shown again by Qt's own layout the moment the
        # window is, so `hide()` alone left it on screen. The object stays alive
        # through `self.controls`, which is all the remaining call sites need.
        self.controls.toolbar.setParent(None)

        self.button_open = self.controls.button_open
        self.button_plane = self.controls.button_plane
        self.button_color = self.controls.button_color
        self.button_color_ss = self.controls.button_color_ss
        self.button_color_sequence = self.controls.button_color_sequence
        self.button_surface = self.controls.button_surface
        self.button_info = self.controls.button_info
        self.button_display_cfg = self.controls.button_display_cfg

        # ── Status ────────────────────────────────────────────────────
        # The chrome's own status line, not the toolkit's: the QStatusBar was
        # a native strip under the viewport that the browser build cannot
        # have, the settings cannot hide, and the window cannot theme. Kept
        # constructed (code hands messages to it) but never shown; the text
        # goes to the in-viewport line instead.
        self.status_bar = self.statusBar()
        self.status_bar.hide()
        try:
            self.viewer.statusMessage.connect(self._flash_status)
        except Exception:
            pass
        self._status_label = QtWidgets.QLabel("Ready")
        self._status_timer = QtCore.QTimer(self)
        self._status_timer.timeout.connect(self._update_status_bar)
        self._status_timer.start(2000)

        # ── Single DockArea (all panels as tabs) ──────────────────────
        self.objects = ObjectsDock(
            self,
            margins=dock_margins,
            spacing=spacing,
            # The A/S/H/L/C menus drive the same command layer the command line
            # does, so every menu action is reproducible as a typed command and
            # shows up in the command log.
            run_command=self._run_object_menu_command,
        )
        self.object_list = self.objects.object_list
        self.object_list.itemSelectionChanged.connect(
            self.on_object_selection_changed,
        )
        self.object_list.itemChanged.connect(self.on_object_item_changed)
        self.object_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.object_list.customContextMenuRequested.connect(
            self._on_object_list_context_menu,
        )

        # The Qt volume/map dock is gone: density controls live in the
        # viewport (`renderer/density_window.py`). The pure-Python model remains.
        self.volume_panel = VolumeViewModel(self.viewer)

        # The object list is a view of the viewer's registry, and this window
        # used to keep it in step by calling `sync_internal_gui` from four
        # places it happened to remember -- so every command that creates an
        # object without loading a file (`load_map`, `molmap`, `create`,
        # `delete`) left the list stale. It consumes the registry's revision
        # now, like the other two hosts; see
        # `chimol.host.app.consume_object_changes`.
        try:
            from ..host.app import consume_object_changes

            consume_object_changes(_cmd, self.viewer, self.sync_internal_gui)
        except Exception:  # noqa: BLE001 - a stale panel beats a dead window
            logging.getLogger(__name__).debug(
                "could not subscribe to object changes", exc_info=True
            )
        self.rmf_panel = RmfPanel(self, self.viewer)
        self.sequence = SequenceDock(
            self,
            margins=dock_margins,
            spacing=spacing,
        )
        # Built but not docked: the strip in the viewport replaced its tab, and
        # a widget with no parent and no layout is a *top-level window* in Qt --
        # so it floated over the app as a stray "Seq nbr" box. Parented and
        # hidden until the ~100 call sites that still feed it are unwound.
        try:
            self.sequence.widget.setParent(self)
            self.sequence.widget.hide()
        except Exception:
            pass

        self.seq_label = self.sequence.seq_label
        self.seq_numbers_label = self.sequence.seq_numbers_label
        self.seq_numbers_list = self.sequence.seq_numbers_list
        self.seq_scrollbar = self.sequence.seq_scrollbar
        self.seq_list = self.sequence.seq_list
        self._extra_seq_container = self.sequence.extra_seq_container
        self._extra_seq_layout = self.sequence.extra_seq_layout
        self._sequence_number_font = self.sequence.sequence_number_font
        self._sequence_number_bold_font = self.sequence.sequence_number_bold_font
        self._sequence_font = self.sequence.sequence_font

        # A COMMAND-role chinsole, not a bespoke dock. It takes chimol's own
        # commands *and* Python at one prompt -- the command line had no Python
        # at all before -- and brings completion, calltips and persistent
        # history that the hand-rolled panel did not have.
        from chisurf.gui.chinsole import Chinsole, ConsoleConfig, ConsoleRole

        from .command_dispatch import ChimolDispatcher
        from .command_history import resolve_history_path

        self.command_panel = Chinsole(
            ConsoleConfig(
                role=ConsoleRole.COMMAND,
                history_path=resolve_history_path(),
                session_log=None,
                banner="",
                namespace={"cmd": _cmd, "do": _cmd.do, "window": self},
            ),
            parent=self,
        )
        self.command_panel.set_dispatcher(ChimolDispatcher(_cmd))

        # The 3-D view **is** the window. Everything that used to sit beside
        # it -- the object list, the command prompt, the hierarchy, the density
        # controls, the menus and the toolbar -- is drawn inside the viewport
        # by `InternalGui`, so a second widget would be a second copy of
        # something already on screen and one that no browser has.
        #
        # There is deliberately no `DockArea` any more: a dock is a promise
        # that the thing inside it is a separate panel, and none of them are.
        self.dock_area: Optional[DockArea] = None
        self.setCentralWidget(self.viewer)
        self._detach_orphan_widgets()

        # ── View menu (after DockArea creation) ───────────────────────
        # No Qt menu bar. The menus are drawn in the viewport
        # (`InternalGui.layout_menubar`, built from the same `MENU_BAR` table),
        # so a Qt one is the same menu twice -- and only one of the two exists
        # in a browser. `_build_view_menu` and `_install_menu_bar` are kept for
        # a host that wants a native bar; nothing here calls them.
        self.menuBar().hide()

        self._sequence_visible = True
        self._sequence_rows: dict[str, dict[str, Any]] = {}
        self._sequence_alignment_axis: Optional[np.ndarray] = None
        self._sequence_alignment_maps: dict[str, Optional[np.ndarray]] = {}
        try:
            self.seq_label.toggled.connect(self.on_seq_label_toggled)
        except Exception:
            pass

        self._reset_scroll_targets()

        # ── Viewer signal connections ─────────────────────────────────
        try:
            self.viewer.objectResidueSelectionChanged.connect(
                self.on_viewer_residue_selection_changed,
            )
        except Exception:
            pass

        # ── Button signal connections ─────────────────────────────────
        self.button_open.clicked.connect(self.on_open_structure)
        self.button_plane.toggled.connect(self.viewer.set_plane_visible)
        self.button_color.toggled.connect(self.on_color_aa_toggled)
        self.button_color_ss.toggled.connect(self.on_color_ss_toggled)
        self.button_color_sequence.toggled.connect(self.on_color_sequence_toggled)
        self.button_surface.toggled.connect(self.viewer.set_surface_visible)
        self.button_info.toggled.connect(self.on_toggle_info_panel)
        self.button_display_cfg.clicked.connect(self.on_open_display_config)

        # Sync initial color-mode toggles with viewer default
        try:
            mode = getattr(self.viewer, "_color_mode", "single") or "single"
        except Exception:
            mode = "single"
        try:
            self.button_color.blockSignals(True)
            self.button_color_ss.blockSignals(True)
            self.button_color_sequence.blockSignals(True)
            self.button_color.setChecked(mode == "by_residue")
            self.button_color_ss.setChecked(mode == "by_secondary_structure")
            self.button_color_sequence.setChecked(mode == "by_sequence")
        except Exception:
            pass
        finally:
            try:
                self.button_color.blockSignals(False)
                self.button_color_ss.blockSignals(False)
                self.button_color_sequence.blockSignals(False)
            except Exception:
                pass

        self.seq_list.itemSelectionChanged.connect(
            self.on_sequence_selection_changed,
        )

        self._default_object_name_counter = 0

        try:
            self.viewer.set_system_info_visible(self.button_info.isChecked())
        except Exception:
            pass

        try:
            _cmd.set_window(self)
            # Both prompts hear everything. The docked console is the external
            # command line and the one in the viewport is the internal one --
            # PyMOL's split -- and output that reached only one of them would
            # make whichever the user is looking at the wrong one.
            _cmd.set_message_callback(
                self._fan_out(self.command_panel.append_message, "message")
            )
            _cmd.set_error_callback(
                self._fan_out(self.command_panel.append_error, "error")
            )
            # commandEntered is *not* connected to an executor any more: the
            # console's dispatcher runs the command and then emits it. Wiring
            # both would run every command twice.
        except Exception:
            pass

        # After the command layer is wired: every menu entry runs through it.
        # The demos are part of `MENU_BAR` now, generated from the same `DEMOS`
        # table, so they reach the viewport bar and the Qt one from a single
        # definition. The separate `build_demo_menu` call that used to follow
        # this was the same list a second time -- and it had its own hazard,
        # recorded here because it will recur for anything else bolted on after:
        # `build_menu_bar` starts with `bar.clear()`, so a menu added *before*
        # the rebuild is silently wiped.
        self._update_sequence_view()
        self._update_system_info()
        # PyMOL's object panel is there from startup, with `all` and `sele` in
        # it and nothing loaded. Ours was only filled when an object arrived, so
        # a fresh window showed an empty column -- and, worse, one that had not
        # been handed its `run_command` yet, so the panel that did appear on the
        # first load ran nothing until something refreshed it.
        self.sync_internal_gui()
        # The in-viewport windows come back where the last session left them.
        # Enabled here, in the shipped app, and deliberately not in the panel's
        # constructor: a bare panel in a test must never read -- or on its
        # first drag rewrite -- the real preferences of whoever runs the suite.
        try:
            gui = getattr(getattr(self.viewer, "_renderer", None),
                          "_internal_gui", None)
            if gui is not None:
                gui.enable_persistence()
        except Exception:
            logging.getLogger(__name__).debug(
                "chimol: window persistence unavailable", exc_info=True
            )

    # ── View menu ─────────────────────────────────────────────────────

    # ------------------------------------------------------------------ #
    # Demos and scripts
    # ------------------------------------------------------------------ #
    def run_script_text(self, text: str) -> None:
        """Run ChiMOL script text, one command per line.

        The same rule ``@file`` uses: blank lines and ``#`` comments skipped, and
        every other line handed to the command layer. Kept here rather than in
        the editor so the editor, the Demo menu and ``@`` all execute a script
        exactly the same way.
        """
        for line in str(text).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            self._run_object_menu_command(stripped)

    def run_demo(self, key: str) -> None:
        """Run a shipped demo script by name."""
        from .demo_data import DemoDataUnavailable
        from .demos import read_demo, resolve_structure

        text = read_demo(key)
        if not text:
            logging.getLogger(__name__).warning("chimol: no demo named %r", key)
            return
        # Start from an empty viewer. Without this each demo adds its structure
        # to the last one's, so by the seventh the scene is a pile of seven
        # molecules and nothing demonstrates anything. A demo is a *scene*, not
        # an increment.
        # A demo says `load 148l.pdb` so it reads like something a person would
        # type. Resolving the name here is what lets that work from any working
        # directory without the script carrying a machine-specific path.
        #
        # Every command whose first argument names a shipped file belongs in
        # this tuple. `load_traj` was added to a demo and missed, and the demo
        # then failed on a file that was sitting right there -- the resolver
        # only knew the one verb it was written for.
        loaders = ("load", "load_traj")
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            verb, _, rest = stripped.partition(" ")
            if verb in loaders and rest.strip() and "," not in stripped:
                try:
                    resolved = resolve_structure(rest.strip())
                except DemoDataUnavailable as exc:
                    # One demo's material is computed rather than downloaded, so
                    # it can fail for a reason no file dialog explains. Say the
                    # reason: "cannot read file" would send whoever hit it
                    # looking for a missing download.
                    dialogs.warning(self, "Demo unavailable", str(exc))
                    return
                lines.append(f"{verb} " + resolved)
            else:
                lines.append(line)
        self.run_script_text("delete all\n" + "\n".join(lines))

    def edit_demo_script(self, blank: bool = False) -> None:
        """Open a demo in the script editor, or a blank one."""
        from .demos import DEMOS, demo_path, open_script_editor, read_demo

        if blank:
            open_script_editor(self, text="# ChiMOL script\n")
            return
        key = DEMOS[0][0]
        open_script_editor(self, text=read_demo(key), path=demo_path(key))

    def show_settings_table(self) -> None:
        """Open the filterable table of every registered setting.

        Kept as a window rather than a dock: it is consulted and closed, and a
        dock would take a column from the viewer permanently for something used
        occasionally.
        """
        from .settings_table import show_settings_table

        existing = getattr(self, "_settings_table", None)
        if existing is not None:
            try:
                existing.show()
                existing.raise_()
                return
            except RuntimeError:
                pass  # the window was closed and deleted; make another
        self._settings_table = show_settings_table(
            self, on_changed=self._redraw_after_setting
        )

    def _redraw_after_setting(self) -> None:
        """Repaint the viewer after a setting changed in the table."""
        viewer = getattr(self, "viewer", None)
        if viewer is None:
            return
        try:
            viewer._update_view()
        except Exception:
            logging.getLogger(__name__).debug(
                "chimol: could not redraw after a setting change", exc_info=True
            )

    def _build_view_menu(self) -> None:
        menu_bar = self.menuBar()
        view_menu = menu_bar.addMenu("&View")
        self._view_menu_actions: list[QtGui.QAction] = []

        # 85 settings, and until this the only way to reach one was to know its
        # name and type `set`. PyMOL keeps the same thing behind its Settings
        # menu, which is where anyone coming from it will look.
        self._act_settings = view_menu.addAction("\U0001f39b Settings\u2026")
        self._act_settings.triggered.connect(self.show_settings_table)
        self._view_menu_actions.append(self._act_settings)
        view_menu.addSeparator()

        if self.dock_area is not None:
            self._act_toggle_sequence = view_menu.addAction(
                "\U0001f9ec Toggle Sequence",
            )
            self._act_toggle_sequence.setCheckable(True)
            self._act_toggle_sequence.setChecked(True)
            # `seq_view`, not a dock. The sequence moved into the viewport, and
            # this action kept toggling the tab it used to live in -- a name no
            # tab has answered to since, so `_set_tab_visible` looped over every
            # tab, matched none, and returned. The menu entry ticked and
            # unticked and the strip never moved.
            self._act_toggle_sequence.triggered.connect(self._set_sequence_visible)
            self._view_menu_actions.append(self._act_toggle_sequence)

            view_menu.addSeparator()
            sub = view_menu.addMenu("\U0001f4cb Panel Tabs")
            sub.addAction("Hierarchy").triggered.connect(
                lambda: self._show_tab("Hierarchy"),
            )
            sub.addAction("RMF").triggered.connect(
                lambda: self._show_tab("RMF"),
            )

            view_menu.addSeparator()
            reset_action = view_menu.addAction("\U0001f504 Reset Layout")
            reset_action.triggered.connect(self._reset_panel_layout)

    def _set_tab_visible(self, name: str, visible: bool) -> None:
        if self.dock_area is None:
            return
        for idx in range(self.dock_area.count()):
            if self.dock_area.tabText(idx) == name:
                if visible:
                    self.dock_area.showTab(idx)
                else:
                    self.dock_area.hideTab(idx)
                return

    def _show_tab(self, name: str) -> None:
        if self.dock_area is None:
            return
        for idx in range(self.dock_area.count()):
            if self.dock_area.tabText(idx) == name:
                self.dock_area.showTab(idx)
                self.dock_area.setCurrentIndex(idx)
                return

    def _set_sequence_visible(self, visible: bool) -> None:
        """Show or hide the sequence strip in the viewport.

        The strip reads the ``seq_view`` setting when the panel is rebuilt (see
        ``_refresh_sequence_rows``), so setting it is what moves the strip, and
        `set` from the command line and this menu entry stay in agreement
        because they write the same place.

        Parameters
        ----------
        visible : bool
            Whether the strip should be drawn.
        """
        try:
            from ..settings import set_setting

            set_setting("seq_view", bool(visible))
        except Exception:
            logger.debug("could not set seq_view", exc_info=True)
            return
        try:
            self.viewer.update()
        except Exception:
            logger.debug("could not repaint after toggling the sequence", exc_info=True)

    def _reveal_panel_with_content(self, name: str, has_content: bool) -> None:
        """Show a side panel once it has something to show, and only then.

        The panel starts hidden (:data:`_INITIALLY_HIDDEN_DOCKS`) so an ordinary
        PDB gets the whole window for the molecule. It appears by itself when a
        file finally gives it content, because a panel nobody can see is as
        useless as an empty one that takes a third of the window -- and nothing
        else tells the user their integrative model *has* a hierarchy to browse.

        It is not hidden again when the content goes away: closing a panel is
        the user's decision, and a panel that vanished on its own while they
        were using it would be the more surprising behaviour.

        Parameters
        ----------
        name : str
            Tab text of the panel.
        has_content : bool
            Whether the panel now has something in it.
        """
        if not has_content or self.dock_area is None:
            return
        try:
            self._show_tab(name)
        except Exception:
            logger.debug("could not reveal the %s panel", name, exc_info=True)

    def _reset_panel_layout(self) -> None:
        if self.dock_area is not None:
            self.dock_area.set_layout_state(
                dict(_DEFAULT_DOCK_AREA_STATE), emit_change=True,
            )

    # ── DockArea state persistence ────────────────────────────────────

    def _save_dock_area_state(self) -> None:
        if self.dock_area is None:
            return
        try:
            ini_path = get_plugin_settings_path("chimol")
            settings = QtCore.QSettings(
                str(ini_path), QtCore.QSettings.IniFormat,
            )
            state = self.dock_area.get_layout_state()
            settings.setValue("main_dock_area", json.dumps(state))
        except Exception:
            pass

    def _restore_dock_area_state(self) -> None:
        if self.dock_area is None:
            return
        try:
            ini_path = get_plugin_settings_path("chimol")
            if not ini_path.exists():
                return
            settings = QtCore.QSettings(
                str(ini_path), QtCore.QSettings.IniFormat,
            )
            raw = settings.value("main_dock_area")
            if raw is None:
                return
            state = _without_retired_docks(json.loads(str(raw)))
            self.dock_area.set_layout_state(state, emit_change=True)
        except Exception:
            pass

    def closeEvent(self, event: QtCore.QEvent) -> None:
        try:
            self._save_dock_area_state()
        except Exception:
            pass
        super().closeEvent(event)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        if not self._dock_area_restored:
            self._dock_area_restored = True
            try:
                self._restore_dock_area_state()
            except Exception:
                pass
            # Deferred, so the window is on screen before anything modal is: a
            # dialog raised inside the first showEvent has nothing behind it.
            QtCore.QTimer.singleShot(0, self._offer_package_display_defaults)
        super().showEvent(event)

    def _offer_package_display_defaults(self) -> None:
        """Ask whether to take the shipped display defaults, once per start.

        The settings file is the user's, so it is never rewritten behind their
        back -- but it also must not strand them. A default that moved twice
        inside one released version left copies holding a value nobody intended
        and no migration could name, and the only symptom was that the viewer
        looked wrong in a way the person reporting it could not have diagnosed.
        Comparing against the package says what actually differs, whatever the
        version stamp claims.

        Declining is remembered only if asked for: the tick box writes the
        preference, and the Config editor turns it back on.
        """
        try:
            if not _config.get_update_prompt_enabled():
                return
            differences = _config.diff_against_package()
            if not differences:
                return
        except Exception:
            logging.getLogger(__name__).debug(
                "Could not compare the display config with the package", exc_info=True
            )
            return

        listed = "\n".join(
            f"  {name}: {yours!r} → {shipped!r}"
            for name, (yours, shipped) in sorted(differences.items())
        )
        count = len(differences)
        answer = dialogs.choice(
            self,
            "ChiMOL display settings",
            f"{count} display setting{'s' if count != 1 else ''} "
            "differ from the ones this version ships with.",
            {"update": "Use the new defaults", "keep": "Keep mine"},
            default="keep",
            informative=(
                "Settings you changed on purpose are worth keeping. These are "
                "listed below so you can tell which is which."
            ),
            detail=listed,
            checkbox="Don't ask again",
        )

        if answer.checked:
            _config.set_update_prompt_enabled(False)
        if answer.key != "update":
            return

        adopted = _config.adopt_package_values(differences)
        if adopted:
            _config.reload_display_config()
            self.status_bar.showMessage(
                f"Adopted {len(adopted)} display default"
                f"{'s' if len(adopted) != 1 else ''} from this version",
                5000,
            )

    # ── Status bar ────────────────────────────────────────────────────

    def _status_gui(self):
        """The in-viewport chrome the status line is drawn by, or ``None``."""
        return getattr(getattr(self.viewer, "_renderer", None),
                       "_internal_gui", None)

    def _flash_status(self, text: str) -> None:
        """Show a transient message on the in-viewport status line.

        The periodic refresh overwrites it with the standing counts a few
        seconds later, which is the old QStatusBar timeout by other means.
        """
        gui = self._status_gui()
        if gui is not None:
            gui.status_text = str(text)
            try:
                self.viewer.update()
            except Exception:
                pass

    def _update_status_bar(self) -> None:
        parts = ["Chimol"]
        try:
            obj_count = len(self._object_store)
            parts.append(f"{obj_count} object{'s' if obj_count != 1 else ''}")
        except Exception:
            pass
        try:
            oid = self.viewer.get_active_object_id()
            if oid is not None:
                n_atoms = self.viewer.get_atom_count(oid)
                parts.append(f"{n_atoms} atoms")
                n_res = len(self.viewer.get_sequence_arrays(oid)[0] or [])
                parts.append(f"{n_res} residues")
        except Exception:
            pass
        try:
            frame = self.viewer.get_current_frame()
            total = self.viewer.get_total_frames()
            if total > 1:
                parts.append(f"frame {frame + 1}/{total}")
        except Exception:
            pass
        line = " \u00b7 ".join(parts)
        self._status_label.setText(line)
        gui = self._status_gui()
        if gui is not None and gui.status_text != line:
            gui.status_text = line
            try:
                self.viewer.update()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------


    def _on_command_entered(self, line: str) -> None:
        """Note that *line* has been run by the console.

        Parameters
        ----------
        line : str

        Notes
        -----
        Execution moved to the console's command dispatcher, which reports what
        fails instead of swallowing it -- this used to be a bare
        ``except: pass``, so a mistyped command did nothing and said nothing.
        """
        logging.getLogger(__name__).debug("command executed: %s", line)

    def on_open_structure(self):
        """Open a structure file and display it in the viewer."""

        filenames = open_structure_files(
            self,
            opener=_cs_open_files or _qt_open_files,
            description="Open structure file",
            file_type=(
                "Structure / map files (*.pdb *.ent *.gro *.cif *.mmcif *.mrc *.map *.ccp4 *.mrc.gz *.map.gz *.ccp4.gz);;"
                "All files (*.*)"
            ),
        )
        if not filenames:
            return

        loaded_any = False
        for path in filenames:
            try:
                self._load_structure_from_path(Path(path))
                loaded_any = True
            except Exception as e:
                try:
                    cs.logging.warning(
                        "MolViewPluginWindow.on_open_structure: failed to load '%s': %s",
                        path,
                        e,
                    )
                except Exception:
                    pass
                try:
                    dialogs.warning(
                        self,
                        "Failed to load structure",
                        f"Could not load structure from:\n{path}\n\n{e}",
                    )
                except Exception:
                    pass

        if loaded_any:
            current_id = self.viewer.get_active_object_id()
            self._select_object_in_ui(current_id)

    def on_toggle_info_panel(self, checked: bool) -> None:
        try:
            self.viewer.set_system_info_visible(bool(checked))
        except Exception:
            return

        # When turning the info panel on, refresh the system summary so the
        # overlay is immediately populated for the currently loaded structure.
        if checked:
            try:
                self._update_system_info()
            except Exception:
                pass

    def on_color_aa_toggled(self, checked: bool) -> None:
        """Toggle coloring by amino-acid type in the 3D view."""

        # Turning AA-coloring on should turn SS-coloring off to avoid
        # conflicting modes.
        if checked and self.button_color_ss.isChecked():
            self.button_color_ss.blockSignals(True)
            self.button_color_ss.setChecked(False)
            self.button_color_ss.blockSignals(False)
        if checked and self.button_color_sequence.isChecked():
            self.button_color_sequence.blockSignals(True)
            self.button_color_sequence.setChecked(False)
            self.button_color_sequence.blockSignals(False)

        try:
            self.viewer.set_color_mode("by_residue" if checked else "single")
            self._update_sequence_view()
        except Exception:
            pass

    def on_color_ss_toggled(self, checked: bool) -> None:
        """Toggle coloring by secondary structure in both sequence and 3D."""

        # Turning SS-coloring on disables plain AA-coloring.
        if checked and self.button_color.isChecked():
            self.button_color.blockSignals(True)
            self.button_color.setChecked(False)
            self.button_color.blockSignals(False)
        if checked and self.button_color_sequence.isChecked():
            self.button_color_sequence.blockSignals(True)
            self.button_color_sequence.setChecked(False)
            self.button_color_sequence.blockSignals(False)

        if not checked:
            # When disabling SS coloring, fall back to AA or single.
            try:
                if self.button_color_sequence.isChecked():
                    mode = "by_sequence"
                elif self.button_color.isChecked():
                    mode = "by_residue"
                else:
                    mode = "single"
                self.viewer.set_color_mode(mode)
                self._update_sequence_view()
            except Exception:
                pass
            return

        # Ensure we have secondary-structure codes; _get_secondary_structure_codes
        # will cache them the first time it's called.
        active_id = self.viewer.get_active_object_id()
        if active_id is None:
            return

        seq_codes, res_names = self.viewer.get_sequence_arrays(active_id)
        n = 0
        if seq_codes is not None:
            n = len(seq_codes)
        elif res_names is not None:
            n = len(res_names)
        ss_codes = self._get_secondary_structure_codes(active_id, n) if n > 0 else None

        if ss_codes is None:
            return

        try:
            self.viewer.set_secondary_structure_codes(ss_codes)
            self.viewer.set_color_mode("by_secondary_structure")
            self._update_sequence_view()
        except Exception:
            pass

    def on_color_sequence_toggled(self, checked: bool) -> None:
        """Toggle coloring by sequence index gradient."""

        if checked:
            if self.button_color.isChecked():
                self.button_color.blockSignals(True)
                self.button_color.setChecked(False)
                self.button_color.blockSignals(False)
            if self.button_color_ss.isChecked():
                self.button_color_ss.blockSignals(True)
                self.button_color_ss.setChecked(False)
                self.button_color_ss.blockSignals(False)
            try:
                self.viewer.set_color_mode("by_sequence")
                self._update_sequence_view()
            except Exception:
                pass
            return

        # When disabling the sequence gradient, respect other toggles.
        try:
            if self.button_color_ss.isChecked():
                self.viewer.set_color_mode("by_secondary_structure")
            elif self.button_color.isChecked():
                self.viewer.set_color_mode("by_residue")
            else:
                self.viewer.set_color_mode("single")
            self._update_sequence_view()
        except Exception:
            pass

    def on_open_display_config(self) -> None:
        """Open the settings editor inside the 3-D view.

        Kept as a method because a Qt button and the menu builder both hold a
        reference to it; what it does is now the `config` command, which is
        the panel. The modal JSON dialog it used to raise is gone -- see
        `renderer/settings_window.py`.
        """
        self._run_internal_gui_command("settings_panel on")

    @staticmethod
    def _widget_alive(widget) -> bool:
        """Whether a Qt widget's C++ side still exists.

        Touching a widget whose C++ object has been deleted raises
        ``RuntimeError: wrapped C/C++ object ... has been deleted``, and here that
        happened inside a *selection-changed* handler -- so clicking an object
        killed the window. The dock bug that deleted the widgets is fixed
        upstream in ``dock_area.cleanup_empty_tab_widget``, but a signal handler
        should not be one stray deletion away from taking the application down,
        so it checks rather than assumes.
        """
        if widget is None:
            return False
        try:
            widget.objectName()
        except RuntimeError:
            return False
        return True

    def _update_sequence_view(self, object_id: Optional[str] = None) -> None:
        active_id = object_id or self.viewer.get_active_object_id()

        seq_cfg = self.sequence.sequence_config()
        seq_view_enabled = bool(seq_cfg.get("seq_view", True))
        self._set_tab_visible("Sequence", seq_view_enabled)
        if not seq_view_enabled:
            return

        if not (
            self._widget_alive(self.seq_numbers_list)
            and self._widget_alive(self.seq_list)
        ):
            # The sequence dock is gone. Say so once rather than raise out of a
            # signal handler: the rest of the window is still usable.
            logging.getLogger(__name__).warning(
                "chimol: the sequence dock's widgets have been deleted; "
                "skipping the sequence update"
            )
            return

        self.seq_numbers_list.clear()
        self.seq_numbers_list.setEnabled(False)
        self.seq_list.clear()
        self._clear_extra_sequence_rows()

        if active_id is None:
            self._sequence_visible = True
            self._sequence_alignment_axis = None
            self._sequence_alignment_maps = {}
            try:
                self.seq_label.blockSignals(True)
                self.seq_label.setText("No molecule selected")
                self.seq_label.setChecked(True)
                self.seq_label.blockSignals(False)
            except Exception:
                pass
            self.seq_list.addItem("(no molecule selected)")
            self.seq_list.setEnabled(False)
            self.seq_numbers_list.addItem("(no molecule selected)")
            self.seq_numbers_list.setEnabled(False)
            self._reset_scroll_targets()
            return

        if not self._object_store:
            self._sequence_alignment_axis = None
            self._sequence_alignment_maps = {}
            self.seq_list.addItem("(no molecules loaded)")
            self.seq_list.setEnabled(False)
            self.seq_numbers_list.addItem("(no molecules loaded)")
            self.seq_numbers_list.setEnabled(False)
            self._reset_scroll_targets()
            return

        seq_data: dict[str, tuple[Optional[np.ndarray], Optional[np.ndarray]]] = {}
        lengths: dict[str, int] = {}
        residue_numbers_map: dict[str, Optional[np.ndarray]] = {}
        residue_colors_map: dict[str, Optional[np.ndarray]] = {}
        for obj_id in self._object_store.keys():
            seq_codes, res_names = self.viewer.get_sequence_arrays(obj_id)
            seq_data[obj_id] = (seq_codes, res_names)
            lengths[obj_id] = self._sequence_length(seq_codes, res_names)
            try:
                residue_numbers_map[obj_id] = self.viewer.get_residue_numbers(obj_id)
            except Exception:
                residue_numbers_map[obj_id] = None
            try:
                residue_colors_map[obj_id] = self.viewer.get_residue_colors(obj_id)
            except Exception:
                residue_colors_map[obj_id] = None

        # Build a shared residue-number axis across all loaded molecules. When
        # PDB residue ids are available, this aligns sequences by residue
        # number and exposes explicit gaps; otherwise it falls back to a
        # simple 1..N index axis matching the longest sequence.
        gap_mode = int(seq_cfg.get("seq_view_gap_mode", 1))
        try:
            if gap_mode > 0:
                axis, maps = build_residue_alignment(residue_numbers_map, lengths)
                if axis is not None:
                    axis, maps = self._collapse_alignment_gaps(axis, maps)
            else:
                axis = None
                maps = {}
        except Exception:
            axis = None
            maps = {}

        axis_len = 0
        if axis is not None:
            try:
                axis_arr = np.asarray(axis)
                if axis_arr.ndim == 1:
                    axis_len = int(axis_arr.shape[0])
            except Exception:
                axis_len = 0

        if axis_len > 0:
            max_len = axis_len
            try:
                self._sequence_alignment_axis = np.asarray(axis, dtype=int)
            except Exception:
                self._sequence_alignment_axis = None
            try:
                self._sequence_alignment_maps = {
                    str(k): (np.asarray(v) if v is not None else None)
                    for k, v in maps.items()
                }
            except Exception:
                self._sequence_alignment_maps = {}
        else:
            max_len = max(lengths.values()) if lengths else 0
            self._sequence_alignment_axis = None
            self._sequence_alignment_maps = {str(k): None for k in self._object_store.keys()}

        entry = self._object_store.get(active_id)
        label_text = str(active_id)
        visible = True
        if entry is not None:
            label_text = entry.get("name", active_id)
            visible = bool(entry.get("visible", True))

        self._sequence_visible = visible
        try:
            self.seq_label.blockSignals(True)
            self.seq_label.setText(label_text)
            self.seq_label.setChecked(visible)
            self.seq_label.blockSignals(False)
        except Exception:
            pass

        if max_len <= 0:
            self._sequence_alignment_axis = None
            self._sequence_alignment_maps = {}
            placeholder = "(no sequence information)"
            self.seq_list.addItem(placeholder)
            self.seq_list.setEnabled(False)
            self.seq_numbers_list.addItem(placeholder)
            self.seq_numbers_list.setEnabled(False)
            self._reset_scroll_targets()
            return

        ss_codes_map: dict[str, Optional[Sequence[str]]] = {}
        for obj_id, length in lengths.items():
            if length > 0:
                ss_codes_map[obj_id] = self._get_secondary_structure_codes(obj_id, length)
            else:
                ss_codes_map[obj_id] = None

        active_seq_codes, active_res_names = seq_data.get(active_id, (None, None))
        active_len = lengths.get(active_id, 0)
        active_ss = ss_codes_map.get(active_id)

        active_empty_text = "(no sequence information)"
        if (active_seq_codes is not None and len(active_seq_codes) > 0) or (
            active_res_names is not None and len(active_res_names) > 0
        ):
            active_empty_text = ""

        active_items = self._build_sequence_items(
            seq_codes=active_seq_codes,
            res_names=active_res_names,
            ss_codes=active_ss,
            max_len=max_len,
            enable_selection=active_len > 0,
            empty_text=active_empty_text or "(no residues)",
            res_numbers=residue_numbers_map.get(active_id),
            residue_colors=residue_colors_map.get(active_id),
            index_map=self._sequence_alignment_maps.get(active_id),
        )
        for item in active_items:
            self.seq_list.addItem(item)

        self.seq_list.setEnabled(active_len > 0)
        self._apply_sequence_selection_styles(set())

        for obj_id, obj_entry in self._object_store.items():
            if obj_id == active_id:
                continue
            seq_codes, res_names = seq_data.get(obj_id, (None, None))
            ss_codes = ss_codes_map.get(obj_id)
            length = lengths.get(obj_id, 0)
            self._add_sequence_row_for_object(
                object_id=obj_id,
                entry=obj_entry,
                seq_codes=seq_codes,
                res_names=res_names,
                ss_codes=ss_codes,
                length=length,
                max_len=max_len,
                res_numbers=residue_numbers_map.get(obj_id),
                residue_colors=residue_colors_map.get(obj_id),
            )

        seq_cfg = self.sequence.sequence_config()
        number_step = max(1, int(seq_cfg.get("seq_view_label_spacing", seq_cfg.get("number_step", 5))))

        residue_numbers = None
        try:
            if hasattr(self, "viewer") and self.viewer is not None:
                residue_numbers = self.viewer.get_residue_numbers(active_id)
        except Exception:
            residue_numbers = None

        # When a global alignment axis is available, use it for the sequence
        # number row so the labels reflect the shared PDB residue numbers.
        axis_nums = None
        try:
            axis_arr = getattr(self, "_sequence_alignment_axis", None)
            if axis_arr is not None:
                axis_arr = np.asarray(axis_arr)
                if axis_arr.ndim == 1 and axis_arr.shape[0] == max_len:
                    axis_nums = axis_arr
        except Exception:
            axis_nums = None

        if axis_nums is not None:
            numbers_for_row = axis_nums
        else:
            numbers_for_row = residue_numbers

        self._populate_sequence_numbers(
            max_len,
            number_step,
            active_length=active_len,
            residue_numbers=numbers_for_row,
        )
        enabled = max_len > 0
        self.seq_numbers_list.setEnabled(enabled)
        try:
            self.seq_numbers_label.setEnabled(enabled)
        except Exception:
            pass

        self._reset_scroll_targets()

    def _collapse_alignment_gaps(
        self,
        axis: np.ndarray,
        maps: dict[str, Optional[np.ndarray]],
        max_consecutive_gaps: int = 9,
    ) -> tuple[np.ndarray, dict[str, Optional[np.ndarray]]]:
        """Collapse large empty stretches of residue numbers into a 9-column block.

        Parameters
        ----------
        axis : np.ndarray
            1D array representing the global residue numbers alignment axis.
        maps : dict
            Mapping from object ID to 1D array of sequence indices.
        max_consecutive_gaps : int, optional
            Threshold above which a run of consecutive gaps is collapsed.

        Returns
        -------
        new_axis : np.ndarray
            The collapsed residue number axis.
        new_maps : dict
            The collapsed sequence index maps.
        """
        if axis is None or len(axis) == 0:
            return axis, maps

        # Identify objects that have a non-None map of length equal to axis
        valid_keys = [k for k, v in maps.items() if v is not None and len(v) == len(axis)]
        if not valid_keys:
            return axis, maps

        is_empty = np.ones(len(axis), dtype=bool)
        for k in valid_keys:
            is_empty &= (np.asarray(maps[k]) == -1)

        new_axis_list = []
        new_maps_lists = {k: [] for k in maps.keys()}

        i = 0
        N = len(axis)
        while i < N:
            is_run = False
            if is_empty[i]:
                run_end = i
                while run_end + 1 < N and is_empty[run_end + 1]:
                    run_end += 1
                run_len = run_end - i + 1
                if run_len > max_consecutive_gaps:
                    is_run = True

            if is_run:
                # Collapse the run from i to run_end into exactly 9 columns:
                # [-1, -1, -1, -2, -2, -2, -1, -1, -1]
                # For axis, we keep the boundary residue numbers for the non-dot parts
                for offset in range(9):
                    if offset < 3:
                        orig_idx = i + offset
                        axis_val = axis[orig_idx]
                        map_val = -1
                    elif offset < 6:
                        axis_val = -1  # Skip number display
                        map_val = -2  # Render '.' (dot)
                    else:
                        orig_idx = run_end - (8 - offset)
                        axis_val = axis[orig_idx]
                        map_val = -1

                    new_axis_list.append(axis_val)
                    for k in maps.keys():
                        if k in valid_keys:
                            new_maps_lists[k].append(map_val)
                        else:
                            new_maps_lists[k].append(-1)
                i = run_end + 1
            else:
                new_axis_list.append(axis[i])
                for k, v in maps.items():
                    if v is not None and i < len(v):
                        new_maps_lists[k].append(v[i])
                    else:
                        new_maps_lists[k].append(-1)
                i += 1

        new_axis = np.array(new_axis_list, dtype=int)
        new_maps = {}
        for k in maps.keys():
            if maps[k] is not None:
                new_maps[k] = np.array(new_maps_lists[k], dtype=int)
            else:
                new_maps[k] = None

        return new_axis, new_maps

    def _clear_extra_sequence_rows(self) -> None:
        self._sequence_rows.clear()
        layout = getattr(self, "_extra_seq_layout", None)
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _add_sequence_row_for_object(
        self,
        object_id: str,
        entry: dict[str, Any],
        *,
        seq_codes: Optional[Sequence[object]],
        res_names: Optional[Sequence[object]],
        ss_codes: Optional[Sequence[object]],
        length: int,
        max_len: int,
        res_numbers: Optional[np.ndarray] = None,
        residue_colors: Optional[np.ndarray] = None,
    ) -> None:
        container = getattr(self, "_extra_seq_container", None)
        layout = getattr(self, "_extra_seq_layout", None)
        if container is None or layout is None:
            return

        row_widget = QtWidgets.QWidget(container)
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        button = QtWidgets.QToolButton(row_widget)
        button.setMinimumWidth(120)
        label_text = entry.get("name", object_id)
        button.setText(str(label_text))
        button.setCheckable(True)
        visible = bool(entry.get("visible", True))
        button.setChecked(visible)

        seq_list = QtWidgets.QListWidget(row_widget)
        seq_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        seq_list.setFlow(QtWidgets.QListView.LeftToRight)
        seq_list.setWrapping(False)
        seq_list.setUniformItemSizes(True)
        seq_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        seq_list.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        seq_list.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        try:
            seq_font = getattr(self, "_sequence_font", None)
            if isinstance(seq_font, QtGui.QFont):
                seq_list.setFont(seq_font)
            seq_list.setFixedHeight(self.seq_list.height())
            seq_list.setStyleSheet(self.seq_list.styleSheet())
        except Exception:
            pass

        row_layout.addWidget(button, 0, QtCore.Qt.AlignVCenter)
        row_layout.addWidget(seq_list, 1)
        layout.addWidget(row_widget)

        self._sequence_rows[object_id] = {"button": button, "list": seq_list}

        extra_items = self._build_sequence_items(
            seq_codes=seq_codes,
            res_names=res_names,
            ss_codes=ss_codes,
            max_len=max_len,
            enable_selection=False,
            empty_text="(no sequence information)" if length <= 0 else "",
            res_numbers=res_numbers,
            residue_colors=residue_colors,
            index_map=self._sequence_alignment_maps.get(object_id),
        )
        for item in extra_items:
            seq_list.addItem(item)

        seq_list.setEnabled(bool(visible))
        self._update_sequence_row_colors(object_id, visible)

        button.toggled.connect(
            lambda checked, oid=object_id: self.on_seq_row_toggled(oid, checked)
        )

    def _update_sequence_row_colors(self, object_id: str, visible: bool) -> None:
        row_info = self._sequence_rows.get(str(object_id)) if hasattr(self, "_sequence_rows") else None
        if not isinstance(row_info, dict):
            return
        lst = row_info.get("list")
        if not isinstance(lst, QtWidgets.QListWidget):
            return
        if lst.count() == 0:
            return

        gray_bg = QtGui.QColor(200, 200, 200)
        gray_fg = QtGui.QColor(140, 140, 140)

        for i in range(lst.count()):
            item = lst.item(i)
            if item is None:
                continue
            palette = item.data(_SEQ_COLOR_ROLE)
            if isinstance(palette, tuple) and len(palette) == 2:
                base_bg, base_fg = palette
            else:
                base_bg = QtGui.QColor(220, 220, 200)
                base_fg = QtGui.QColor(0, 0, 0)

            if not visible:
                item.setBackground(QtGui.QBrush(gray_bg))
                item.setForeground(QtGui.QBrush(gray_fg))
            else:
                item.setBackground(QtGui.QBrush(base_bg))
                item.setForeground(QtGui.QBrush(base_fg))

    def _sequence_length(
        self,
        seq_codes: Optional[Sequence[object]],
        res_names: Optional[Sequence[object]],
    ) -> int:
        if seq_codes is not None:
            try:
                return len(seq_codes)
            except Exception:
                pass
        if res_names is not None:
            try:
                return len(res_names)
            except Exception:
                pass
        return 0

    def _update_system_info(self, object_id: Optional[str] = None) -> None:
        active_id = object_id or self.viewer.get_active_object_id()
        entry = self._object_store.get(active_id) if active_id else None

        if entry is None:
            lines = ["(no system loaded)"]
        else:
            structure = entry.get("structure")
            if structure is not None:
                try:
                    n_atoms = structure.n_atoms
                except Exception:
                    n_atoms = "?"
                try:
                    n_res = structure.n_residues
                except Exception:
                    n_res = "?"
                try:
                    r_g_val = structure.radius_gyration
                    r_g = f"{r_g_val:.1f}"
                except Exception:
                    r_g = "?"
                system_label = "System: protein"
            else:
                n_atoms = entry.get("n_atoms", "?")
                seq_codes, res_names = self.viewer.get_sequence_arrays(active_id)
                if seq_codes is not None:
                    n_res = len(seq_codes)
                elif res_names is not None:
                    n_res = len(res_names)
                else:
                    n_res = "?"
                r_g_val = entry.get("radius_gyration")
                r_g = "?" if r_g_val is None else f"{r_g_val:.1f}"
                system_label = "System: coordinates"

            lines = [
                system_label,
                "",
                f"File: {entry.get('path', '?')}",
                f"Atoms: {n_atoms}",
                f"Residues: {n_res}",
                f"Radius of gyration: {r_g}",
            ]

            # RMF specifics
            try:
                state = self.viewer._get_active_state()
                if state and getattr(state, "restraints", None):
                    lines.append(f"Restraints: {len(state.restraints)}")
                if state and getattr(state, "rmf_provenance", None):
                    lines.append("")
                    lines.append("RMF Provenance:")
                    for prov in state.rmf_provenance:
                        lines.append(f"  {prov.get('name', '?')}: {prov.get('value', '?')}")
            except Exception:
                pass

            try:
                n_frames = self.viewer.get_frame_count(active_id)
            except Exception:
                n_frames = 0
            if n_frames > 1:
                try:
                    frame_idx = self.viewer.get_active_frame_index(active_id)
                except Exception:
                    frame_idx = 0
                lines.append(f"Frame: {frame_idx + 1} / {n_frames}")

            sel_idx = self._selected_residue_indices()
            if sel_idx:
                seq_codes, res_names = self.viewer.get_sequence_arrays(active_id)
                try:
                    resno_arr = self.viewer.get_residue_numbers(active_id)
                except Exception:
                    resno_arr = None
                desc: list[str] = []
                for i in sel_idx:
                    try:
                        if resno_arr is not None and 0 <= i < len(resno_arr):
                            res_no = int(resno_arr[i])
                        else:
                            res_no = i + 1
                    except Exception:
                        res_no = i + 1
                    name = (
                        str(res_names[i])
                        if res_names is not None and i < len(res_names)
                        else "?"
                    )
                    one = (
                        str(seq_codes[i])
                        if seq_codes is not None and i < len(seq_codes)
                        else "?"
                    )
                    desc.append(f"{res_no}: {name} ({one})")

                lines.append("")
                lines.append("Selected residues:")
                lines.append(", ".join(desc))

        text = "\n".join(str(x) for x in lines)
        try:
            self.viewer.set_system_info_text(text)
        except Exception:
            pass

    def on_sequence_selection_changed(self) -> None:
        """Sync 3D selection and info text when the sequence selection changes."""

        # Map QListWidget selection to residue indices
        idx = self._selected_residue_indices()
        try:
            self._apply_sequence_selection_styles(set(idx))
        except Exception:
            pass
        object_id = self.viewer.get_active_object_id()
        if object_id is None:
            return

        try:
            self.viewer.set_selected_residues(idx, object_id=object_id)
        except Exception:
            pass

        try:
            self._update_system_info(object_id)
        except Exception:
            pass

    def on_viewer_residue_selection_changed(self, object_id, indices) -> None:
        """Update sequence selection to match picks from the 3D viewer."""

        active_id = self.viewer.get_active_object_id()
        if object_id != active_id:
            return

        if not isinstance(indices, (list, tuple)):
            try:
                indices = list(indices)
            except Exception:
                indices = []

        self.seq_list.blockSignals(True)
        try:
            self.seq_list.clearSelection()
            # Map residue indices from the viewer back to visible rows using
            # the stored sequence index role, so alignment gaps are handled
            # correctly.
            try:
                target_idx = {int(i) for i in indices if int(i) >= 0}
            except Exception:
                target_idx = set()
            if target_idx:
                for row in range(self.seq_list.count()):
                    item = self.seq_list.item(row)
                    if item is None:
                        continue
                    seq_idx = item.data(_SEQ_INDEX_ROLE)
                    if isinstance(seq_idx, int) and seq_idx in target_idx:
                        item.setSelected(True)
        finally:
            self.seq_list.blockSignals(False)

        try:
            self._apply_sequence_selection_styles({int(i) for i in indices})
        except Exception:
            pass

        try:
            self._update_system_info(object_id)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Object management helpers
    # ------------------------------------------------------------------

    def _detach_orphan_widgets(self) -> None:
        """Take every widget that is not the viewport off the window.

        The panels that used to live in the dock area are still *constructed* --
        a handful of call sites read a button's checked state or push text at
        the console -- and a `QWidget` whose parent is the window but which no
        layout owns is drawn **at (0, 0), 100 × 30**, on top of the viewport.
        That is the little grey `Command line` box tpeulen photographed sitting
        over the toolbar row: four of them stacked there (`Chinsole`,
        `VolumeDock`, and two bare containers).

        They are **hidden** rather than detached: `hide()` is the smaller
        change and keeps the parent link, so anything that walks the window's
        children still finds them.

        The one exception is a `QToolBar`, where hiding does *not* stick: Qt's
        main-window layout shows it again the moment the window is shown. That
        one has its parent cut, and stays alive through `self.controls`.
        """
        from qtpy import QtWidgets as _QtWidgets

        keep = (self.viewer, self.statusBar(), self.menuBar())
        for child in list(self.children()):
            if not isinstance(child, _QtWidgets.QWidget) or child in keep:
                continue
            if isinstance(child, _QtWidgets.QToolBar):
                child.setParent(None)
            else:
                child.hide()

    def _install_menu_bar(self) -> None:
        """Put PyMOL's menu bar on the window, as far as chimol can honour it."""
        try:
            build_menu_bar(
                self,
                self._run_object_menu_command,
                special={"config": self.on_open_display_config},
            )
        except Exception:
            logging.getLogger(__name__).warning(
                "Could not build the menu bar", exc_info=True
            )

    def _run_object_menu_command(self, line: str) -> None:
        """Run a command from an object menu, echoing it like a typed one.

        Echoing matters more than it looks: it is how a user learns which command
        the menu entry corresponds to, which is the whole path from clicking
        around to writing a script.
        """
        panel = getattr(self, "command_panel", None)
        if panel is not None:
            try:
                panel.append_message(f"> {line}")
            except Exception:
                pass
        try:
            _cmd.do(line)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Object menu command failed: %s", line, exc_info=True
            )
            if panel is not None:
                try:
                    panel.append_error(f"{line}: {exc}")
                except Exception:
                    pass

    def _apply_hidden_rows(self, rows, object_id=None) -> None:
        """Hide exactly the coordinate rows the hierarchy panel has switched off.

        The whole set is applied each time rather than the difference, so the
        picture always matches the check boxes: a partial update would drift out
        of step the first time a signal was missed or a node was re-checked from
        a parent.

        Parameters
        ----------
        rows : sequence of int
            Rows to leave undrawn. Everything else is shown.
        object_id : str, optional
            The object the panel's tree belongs to. The active object used to
            be assumed, and that is the whole of "disabling in the hierarchy
            does nothing": with a map active, the panel showed the structure's
            tree while the hiding was applied to the map.
        """
        viewer = getattr(self, "viewer", None)
        if viewer is None:
            return
        try:
            with viewer._activate_object(object_id):
                coords = viewer._all_atom_coords
                n = 0 if coords is None else int(coords.shape[0])
            if n == 0:
                return
            hidden = set(int(r) for r in rows)
            viewer.set_rows_hidden(range(n), False, object_id=object_id)
            if hidden:
                viewer.set_rows_hidden(sorted(hidden), True, object_id=object_id)
        except Exception:
            logger.debug("could not apply hierarchy visibility", exc_info=True)

    def _report_degraded_load(self, path: Path, exc: Optional[BaseException]) -> None:
        """Tell the user the structure reader gave up, and name the reason.

        The built-in parser now recovers the backbone, secondary structure and
        hetero atoms on its own, so this costs metadata rather than the picture.
        It is still worth saying: a bare "reader unavailable" leaves nobody able
        to act, which is why the import error itself is quoted when there is one.

        Parameters
        ----------
        path : pathlib.Path
            File that fell back to the raw-coordinate parser.
        exc : BaseException or None
            Why the reader failed on this file, when that is known.
        """
        cause = exc if exc is not None else _STRUCTURE_IMPORT_ERROR
        if cause is not None:
            reason = f": {type(cause).__name__}: {cause}"
        else:
            reason = " (the structure reader is unavailable; see the log)"
        message = (
            f"{path.name} loaded with the built-in parser{reason}. "
            "The cartoon, secondary structure and hetero atoms are recovered "
            "from the file, but sequence metadata and the radius of gyration "
            "are not available."
        )
        logging.getLogger(__name__).warning(message)
        try:
            # Attribute lookup itself can fail on a partially built window, so
            # the log above is the channel that is always there.
            panel = getattr(self, "command_panel", None)
            if panel is not None:
                panel.append_error(message)
        except Exception:
            pass

    def _load_structure_from_path(self, path: Path, *, name: Optional[str] = None) -> str:
        """Load a structure or coordinate file and register it as a new object."""

        source_path = str(path)
        if name is not None:
            try:
                fake_path = Path(str(name))
            except Exception:
                fake_path = None
            display_name = self._make_object_name(fake_path)
        else:
            display_name = self._make_object_name(path)

        structure = None
        coords_arr: Optional[np.ndarray] = None
        primary_exc: Optional[Exception] = None

        # Special-case volumetric EM maps (MRC/CCP4/EMDB) and load them as
        # point clouds that can be rendered via the dots representation.
        name_lower = path.name.lower()
        is_map = name_lower.endswith((
            ".mrc",
            ".map",
            ".ccp4",
            ".mrc.gz",
            ".map.gz",
            ".ccp4.gz",
        ))

        if is_map:
            # A real map object with a contour, not a thinned point cloud. The
            # cloud came from a time when there was nothing else to make of a
            # map; it threw the volume away, so the level could not be changed
            # and the Map panel had nothing to show.
            from ..io.mrc import load_mrc_grid

            grid = load_mrc_grid(path)
            grid.name = display_name or grid.name

            digits = re.search(r"\d+", path.name)
            if digits and ("emdb" in path.name.lower() or "emd" in path.name.lower()):
                try:
                    from ..cmd.loader import _fetch_emdb_contour_level

                    rec_lvl = _fetch_emdb_contour_level(digits.group(0))
                    if rec_lvl is not None:
                        grid.recommended_level = rec_lvl
                except Exception:
                    pass

            object_id = self.viewer.add_volume(grid, name=display_name)
            try:
                entry_obj = self.viewer._objects.get(object_id)
                if entry_obj is not None:
                    entry_obj.source_path = source_path
            except Exception:
                pass
            n_atoms: Any = grid.voxel_count

            low, high = grid.value_range()
            entry: dict[str, Any] = {
                "name": display_name,
                "path": source_path,
                "structure": None,
                "ss_codes": None,
                "visible": True,
                "n_atoms": n_atoms,
                "mrc_meta": {
                    "shape": grid.shape,
                    "voxel_size": tuple(float(v) for v in grid.step),
                    "origin": tuple(float(v) for v in grid.origin),
                    "n_voxels": grid.voxel_count,
                    "range": (low, high),
                },
            }
            self._object_store[object_id] = entry
            self._add_object_list_item(object_id, entry)
            self._select_object_in_ui(object_id)
            # The Map panel follows whatever map is loaded.
            panel = getattr(self, "volume_panel", None)
            if panel is not None:
                try:
                    panel.refresh()
                except Exception:
                    pass
            return object_id

        # First try the standard IMP/Structure-based loader for static files.
        backbone = None
        try:
            structure, backbone = load_structure_payload(
                path,
                structure_factory=_ChiSurfStructure,
            )
        except Exception as e:
            primary_exc = e
            structure = None
            backbone = None
        else:
            if backbone is not None:
                coords_arr = np.asarray(backbone.coords, dtype=float)

        object_id: str
        n_atoms: Any

        if structure is not None:
            object_id = self.viewer.add_structure(
                structure,
                name=display_name,
                source_path=source_path,
            )
            n_atoms = getattr(structure, "n_atoms", "?")
        elif coords_arr is not None:
            # Say so. Falling back is legitimate, but the result looks like a
            # bare CA spring with no secondary structure, no sequence and no
            # radius of gyration -- and silently, that reads as a rendering bug
            # rather than as a reader that gave up on this file.
            #
            # An mmCIF is not that case: it is *routed* to the dedicated
            # mmCIF/IHM reader, which then read it. Warning about it told every
            # `fetch` of a `.cif` that it had fallen back to a parser it never
            # touched, which is the reader lying about itself.
            if getattr(backbone, "reader", "pdb") not in ("mmcif", "rmf"):
                self._report_degraded_load(path, primary_exc)
            # The whole payload, in one call. Spelling its fields out here is
            # what let the RMF branch that used to sit above this one fall
            # behind: it passed a different set, and so an RMF got none of the
            # per-bead radii, hierarchy visibility or impostor drawing that
            # arriving through here confers.
            object_id = self.viewer.add_payload(
                backbone,
                name=display_name,
                source_path=source_path,
            )
            n_atoms = 0 if coords_arr is None else coords_arr.shape[0]
        else:
            # No usable static structure/coords: the trajectory codecs, for
            # the formats the structure readers do not cover (DCD).
            #
            # RMF is *not* handled here. It used to be -- a second RMF path,
            # unreachable because the branch above it always returned, which
            # also draped an identity gaussian over every bead. It is read by
            # `load_structure_payload` with everything else now.
            try:
                frames = load_trajectory_frames(path)
            except TrajectoryFormatError:
                # Surface a clear message to GUI/cmd callers. Falling through
                # to `primary_exc` below would report the *structure*
                # reader's complaint about a file it was never the right
                # reader for -- and that message points back here.
                raise
            except Exception:
                if primary_exc is not None:
                    raise primary_exc
                raise

            arr = np.asarray(frames, dtype=float)
            if arr.ndim != 3 or arr.shape[2] != 3 or arr.shape[0] == 0:
                raise ValueError(
                    f"Invalid trajectory array from {path!s}: shape={arr.shape!r}"
                )

            first = arr[0]

            # If the file carries a topology, go in through `set_structure`
            # -- the same path a PDB takes -- rather than `add_coordinates`.
            # That is what builds the residues, the CA trace and the
            # secondary structure a cartoon needs. Without it an all-atom
            # trajectory arrives as bare points, and every feature keyed on
            # atom identity degrades *silently*: the cartoon splines through
            # all 5235 atoms instead of the CAs, `intra_fit polymer` cannot
            # resolve a selection, the sequence view is empty. Nothing
            # errors, which is why it read as "cartoons do not work on
            # trajectories".
            object_id = None
            try:
                from ..io.structure import load_trajectory_atoms

                traj_atoms = load_trajectory_atoms(path, first)
            except Exception:
                traj_atoms = None

            if traj_atoms is not None:
                class _TrajectoryStructure:
                    """The shape :meth:`set_structure` reads."""

                structure = _TrajectoryStructure()
                structure.atoms = traj_atoms
                structure.xyz = np.asarray(traj_atoms["xyz"], dtype=float)
                structure.n_atoms = int(len(traj_atoms))
                try:
                    entry = self.viewer._create_object(name=display_name)
                    entry.source_path = source_path
                    object_id = entry.object_id
                    self.viewer.set_active_object(object_id)
                    self.viewer.set_structure(structure)
                except Exception:
                    logging.getLogger(__name__).warning(
                        "chimol: could not build the trajectory topology; "
                        "falling back to bare coordinates", exc_info=True,
                    )
                    object_id = None

            if object_id is None:
                object_id = self.viewer.add_coordinates(
                    np.asarray(first, dtype=float),
                    name=display_name,
                    source_path=source_path,
                )

            try:
                self.viewer.set_frames(arr, object_id=object_id)
            except Exception:
                # If anything goes wrong, we still keep the first frame as a
                # static coordinate set.
                pass

            n_atoms = int(first.shape[0])

        # Rg is computed here, from the unscaled coordinates, because the viewer
        # only keeps a centred/scaled copy.
        radius_gyration = None
        if structure is None and coords_arr is not None and coords_arr.shape[0] > 0:
            centroid = coords_arr.mean(axis=0)
            radius_gyration = float(
                np.sqrt(((coords_arr - centroid) ** 2).sum(axis=1).mean())
            )

        entry: dict[str, Any] = {
            "name": display_name,
            "path": source_path,
            "structure": structure,
            "ss_codes": None,
            "visible": True,
            "n_atoms": n_atoms,
            "radius_gyration": radius_gyration,
        }
        self._object_store[object_id] = entry
        self._add_object_list_item(object_id, entry)
        self._select_object_in_ui(object_id)
        return object_id

    def _refresh_objects_from_viewer(self) -> None:
        """Rebuild the object list/UI from the viewer's current objects (e.g. after split_chains)."""

        if self.viewer is None:
            return

        objects = self.viewer.list_objects()

        # Reset store and UI list
        self._object_store.clear()
        self._drawn_groups: set[str] = set()
        try:
            self.object_list.blockSignals(True)
            self.object_list.clear()
            self.objects.clear_rows()
        finally:
            self.object_list.blockSignals(False)

        # A group's members must be drawn together under its header, and the
        # viewer's registry does not guarantee they are adjacent: grouping `lig`
        # and `nag` while `pep` sits between them leaves the registry order
        # lig, pep, nag, so walking it directly drew `nag` under whichever
        # header came last. Build the display order first -- each row's position
        # is decided by its group, its group's first appearance decides where
        # the block goes, and the objects themselves are never reordered.
        for obj in self._grouped_display_order(objects):
            oid = str(obj.get("id"))
            name = obj.get("name") or oid
            group = obj.get("group")
            entry = {
                "name": name,
                "path": obj.get("source_path"),
                "structure": None,
                "ss_codes": None,
                "visible": bool(obj.get("visible", True)),
                "n_atoms": obj.get("n_atoms", obj.get("has_geometry")),
                "group": group,
            }
            # The store keeps every object whether or not its row is drawn: a
            # collapsed group hides rows, it does not unload molecules, and code
            # that looks an object up by id must still find it.
            self._object_store[oid] = entry
            if group:
                if group not in self._drawn_groups:
                    self._drawn_groups.add(group)
                    self._add_group_list_item(group, bool(obj.get("group_open", True)))
                if not obj.get("group_open", True):
                    continue
            self._add_object_list_item(oid, entry, indent=12 if group else 0)

        # Reselect the active object if possible
        active_id = self.viewer.get_active_object_id()
        if active_id is None and objects:
            active_id = objects[0].get("id")
        if active_id is not None:
            self._select_object_in_ui(active_id)
        self._update_sequence_view()
        self._update_system_info()

    def _set_object_visible(self, object_id: str, visible: bool) -> None:
        try:
            self.viewer.set_object_visible(object_id, visible)
        except Exception:
            pass

        entry = self._object_store.get(object_id)
        if entry is not None:
            entry["visible"] = bool(visible)

        # The panel shows which objects are on and drops the sequences of the
        # ones that are not, so it has to be told when that changes -- otherwise
        # a switched-off molecule keeps its row bright and its sequence on the
        # strip until something unrelated happens to refresh it.
        self.sync_internal_gui()

    def _make_object_name(self, path: Optional[Path]) -> str:
        if path is None:
            base = f"Molecule {self._default_object_name_counter + 1}"
        else:
            base = path.stem or "Molecule"

        existing = {entry.get("name") for entry in self._object_store.values()}
        if base not in existing:
            return base

        suffix = 2
        while f"{base} ({suffix})" in existing:
            suffix += 1
        return f"{base} ({suffix})"

    def _add_object_list_item(
        self, object_id: str, entry: dict[str, Any], *, indent: int = 0
    ) -> None:
        item = self.objects.create_item(object_id, entry)

        self._block_object_list_signals = True
        try:
            # From the entry, not always Checked. Forcing Checked meant every
            # panel rebuild silently re-showed anything that had been hidden --
            # so `split_chains` hid its source and the very next refresh brought
            # it back, drawing the whole structure on top of every chain copy.
            item.setCheckState(
                QtCore.Qt.Checked
                if bool(entry.get("visible", True))
                else QtCore.Qt.Unchecked
            )
        finally:
            self._block_object_list_signals = False

        self.object_list.addItem(item)
        # The row widget can only be hosted once the item exists in the list.
        self.objects.attach_row(item, object_id, entry, indent=indent)
        entry["item"] = item
        self.sync_internal_gui()

    def sync_internal_gui(self) -> None:
        """Mirror the object list into the panel drawn inside the viewport.

        The docked panel and the in-viewport one are two views of one list, and
        they are fed from the same place so they cannot disagree about what is
        loaded or what is switched on.
        """
        renderer = getattr(self.viewer, "_renderer", None)
        gui = getattr(renderer, "_internal_gui", None)
        if gui is None:
            return

        rows = [InternalGuiRow(name="all", is_header=True)]
        # Groups are drawn here too, and by the same rule as the docked panel:
        # one header where the group's first member sits, its members indented
        # under it, and nothing at all below a collapsed one. Feeding this from
        # `_object_store` instead lost the hierarchy -- the store is flat and
        # keeps collapsed members -- so the viewport panel, which is the one a
        # PyMOL user drives, showed a group's molecules with no group.
        try:
            objects = self._grouped_display_order(self.viewer.list_objects())
        except Exception:
            objects = []
        seen_groups: set[str] = set()
        for obj in objects:
            group = obj.get("group")
            is_open = bool(obj.get("group_open", True))
            if group:
                if group not in seen_groups:
                    seen_groups.add(group)
                    rows.append(
                        InternalGuiRow(
                            name=str(group), is_group=True, group_open=is_open
                        )
                    )
                if not is_open:
                    continue
            rows.append(
                InternalGuiRow(
                    name=str(obj.get("name") or obj.get("id")),
                    enabled=bool(obj.get("visible", True)),
                    indent=1 if group else 0,
                )
            )
        # PyMOL pins the `sele` selection object to the bottom of its object
        # list, below every real object and the `all` header. It is not a
        # molecule: its buttons address the current selection, and it has no
        # on/off state of its own.
        rows.append(InternalGuiRow(name="sele", enabled=True, is_selection=True))
        rows.extend(self._measurement_rows())
        gui.set_rows(rows)
        gui.set_run_command(self._run_internal_gui_command)
        self._wire_internal_command_line(gui)
        gui.on_playback_change = self._apply_playback_settings
        gui.on_frame_change = self._seek_to_frame
        gui.on_prompt_command = self._prefill_command_line
        gui.on_file_prompt = self._menu_file_prompt
        # The menu bar, drawn in the viewport. On macOS a Qt menu bar is taken
        # away to the *system* bar at the top of the screen, so the menus were
        # nowhere near the 3-D view; drawn here they are in the same place on
        # every platform, and in the browser at all.
        gui.menubar = [
            (title, entries) for title, entries in MENU_BAR if entries
        ]
        # The toolbar, migrated from the Qt row: every button is a command, so
        # the same row works in the browser and each press is echoed at the
        # prompt like a typed one.
        gui.toolbar = list(TOOLBAR)
        try:
            gui.stride = int(self.viewer.get_frame_step())
            gui.average = int(self.viewer.get_trajectory_smoothing())
        except Exception:
            pass
        try:
            gui.state = (
                int(self.viewer.get_current_frame()) + 1,
                max(int(self.viewer.get_total_frames()), 1),
            )
        except Exception:
            pass
        # The block's "Selecting" row reads the level back from the viewer
        # rather than owning it, so clicking the row and typing
        # `set mouse_selection_mode, ...` cannot disagree about what a click
        # will select.
        try:
            gui.selecting = str(self.viewer.selection_mode)
        except Exception:
            pass
        self._sync_internal_sequences(gui)
        # Monospace, so the widest name in characters decides the column.
        widest = max((len(row.name) for row in rows), default=4)
        gui.layout(renderer.width(), renderer.height(),
                   name_width=max(60.0, widest * gui.FONT_PT * 0.62 + 8))
        renderer.update()

    def _seek_to_frame(self, frame: int) -> None:
        """Jump to a 1-based frame, from the timeline drawn in the viewport."""
        try:
            self.viewer.set_current_frame(max(int(frame), 1) - 1)
            self.viewer.update()
        except Exception:
            logging.getLogger(__name__).debug("Could not seek", exc_info=True)

    def _apply_playback_settings(self, stride: int, average: int) -> None:
        """Apply the stride and averaging window chosen in the viewport block.

        Neither exists in PyMOL. A long trajectory is otherwise watched at
        whatever rate it was written -- and a noisy one jitters so much that the
        motion everyone is looking for is buried in it.
        """
        try:
            self.viewer.set_frame_step(int(stride))
            self.viewer.set_trajectory_smoothing(int(average))
            self.viewer.update()
        except Exception:
            logging.getLogger(__name__).debug(
                "Could not apply playback settings", exc_info=True
            )

    @staticmethod
    def _sequence_rows_for_object(
        object_id, object_name, codes, numbers, colors, chains
    ):
        """**One row per object**, with the chain id inline — PyMOL's own shape.

        Checked against `Seeker.cpp` rather than assumed: PyMOL creates one row
        per object (`nRow++` closes the per-object loop) and shows chains
        *within* it — `seq_view_format 3` writes the chain id as its own column
        at each boundary. An earlier version here split the strip into a row
        per chain, which reads fine on a four-chain protein and fills the whole
        viewport on an integrative model with two hundred and fifty.

        The chain markers are columns like any other, so they need a residue to
        point at and have none: their ``residue_indices`` entry is **-1**, and
        everything downstream drops negatives. Without that, clicking a chain
        label would select whatever residue happened to share its column index.
        """
        import numpy as np

        codes = [str(c) for c in codes]
        total = len(codes)
        numbers = list(numbers) if numbers is not None else []
        colors = list(colors) if colors is not None else []
        chain_ids = [str(c).strip() for c in chains] if chains is not None else []

        letters: list[str] = []
        row_numbers: list[int] = []
        row_colors: list[tuple] = []
        mapping: list[int] = []
        last_chain = None

        for index in range(total):
            chain = chain_ids[index] if index < len(chain_ids) else ""
            if chain and chain != last_chain:
                last_chain = chain
                # The boundary marker: the chain id, then a space. Columns that
                # name no residue, which is what the -1 records.
                for character in f"{chain} ":
                    letters.append(character)
                    row_numbers.append(0)
                    row_colors.append((0.55, 0.55, 0.6))
                    mapping.append(-1)
            letters.append(codes[index])
            row_numbers.append(int(numbers[index]) if index < len(numbers) else index + 1)
            row_colors.append(
                tuple(float(c) for c in colors[index][:3])
                if index < len(colors) else (0.8, 0.8, 0.85)
            )
            mapping.append(index)

        distinct = len(np.unique(np.asarray(chain_ids))) if chain_ids else 0
        return [
            InternalSequenceRow(
                name=str(object_name),
                object_id=str(object_id),
                chain="" if distinct != 1 else (chain_ids[0] if chain_ids else ""),
                codes="".join(letters),
                numbers=row_numbers,
                colors=row_colors,
                residue_indices=mapping,
            )
        ]

    def _measurement_rows(self) -> list:
        """One row per measurement, under `sele`, the way PyMOL lists them.

        A `distance` **is an object** in PyMOL — it gets a name, a row and an
        on/off switch, and that is how you turn one off without deleting it.
        Here they were drawn into the scene and listed nowhere, so a
        measurement could only ever be removed, and only by knowing its name.

        Below `sele` rather than among the molecules: they are derived from the
        structures above them, and PyMOL keeps its own non-molecule rows at the
        bottom for the same reason.
        """
        try:
            measurements = dict(self.viewer._measurements or {})
        except Exception:
            return []

        rows = []
        for name in sorted(measurements):
            data = measurements[name] or {}
            label = str(data.get("label") or "")
            if not label:
                labels = data.get("labels") or []
                label = f"{len(labels)} contacts" if labels else ""
            rows.append(
                InternalGuiRow(
                    name=str(name),
                    enabled=bool(data.get("visible", True)),
                    is_measurement=True,
                    detail=label,
                )
            )
        return rows

    def _sync_internal_sequences(self, gui) -> None:
        """Give the strip one row per *shown* object.

        Hiding an object hides its sequence with it: the strip describes what is
        on screen, and a row for something invisible is a row you cannot relate
        to anything.
        """
        try:
            from ..settings import get_setting

            gui.sequence_visible = bool(get_setting("seq_view"))
        except Exception:
            gui.sequence_visible = True

        rows = []
        total_chains = 0
        for object_id, entry in self._object_store.items():
            if not bool(entry.get("visible", True)):
                continue
            try:
                codes, _names = self.viewer.get_sequence_arrays(object_id)
                numbers = self.viewer.get_residue_numbers(object_id)
                colors = self.viewer.get_residue_colors(object_id)
                chains = self.viewer.get_residue_chains(object_id)
            except Exception:
                continue
            if codes is None or len(codes) == 0:
                continue
            built = self._sequence_rows_for_object(
                object_id, str(entry.get("name", object_id)),
                codes, numbers, colors, chains,
            )
            rows.extend(built)
            try:
                import numpy as _np

                total_chains += (
                    len(_np.unique(_np.asarray([str(c).strip() for c in chains])))
                    if chains is not None else len(built)
                )
            except Exception:
                total_chains += len(built)
        gui.set_sequences(rows)
        # The chrome truncates again to what fits, so it has to be told how
        # many chains there really are or its "and N more" counts only the ones
        # this method dropped.
        gui.sequence_total = total_chains
        gui.on_select = self._on_internal_sequence_selection
        if not getattr(self, "_sequence_selection_connected", False):
            # The viewer's selection is the single source of truth, and the
            # strip mirrors it. That is what makes clicking empty space clear
            # the highlight too: the miss already empties the selection, and
            # the strip has no business keeping its own idea of it.
            try:
                self.viewer.objectResidueSelectionChanged.connect(
                    self._mirror_selection_in_sequence
                )
                self._sequence_selection_connected = True
            except Exception:
                pass

    def _mirror_selection_in_sequence(self, object_id, indices) -> None:
        """Show the viewer's selection in the strip."""
        renderer = getattr(self.viewer, "_renderer", None)
        gui = getattr(renderer, "_internal_gui", None)
        if gui is None:
            return
        chosen = {int(i) for i in (indices or [])}
        for row in gui.sequences:
            # By object id, and mapped back into the row's own columns: a row
            # is one chain, so the object's residue indices are not its column
            # numbers. Matching on the label would also miss now that the label
            # carries the chain.
            if row.object_id == str(object_id):
                mapping = getattr(row, "residue_indices", None) or []
                if mapping:
                    row.selected = {
                        column for column, residue in enumerate(mapping)
                        if int(residue) in chosen
                    }
                else:
                    row.selected = set(chosen)
            elif not chosen:
                row.selected = set()
        renderer.update()

    def _on_internal_sequence_selection(self, name: str, indices, additive: bool) -> None:
        """Apply a selection made in the strip to the 3-D view.

        Through `set_selected_residues`, which is the same path the docked
        sequence widget uses -- so a residue picked in the strip and one picked
        in the dock end up as the same selection rather than two ideas of one.
        """
        # `name` is the row's object *id* when it has one -- the strip stopped
        # identifying rows by their label once the label gained the chain.
        # Falling back to the name keeps a row built without an id working.
        if name in self._object_store:
            object_id = name
        else:
            object_id = next(
                (oid for oid, entry in self._object_store.items()
                 if str(entry.get("name", oid)) == name),
                None,
            )
        try:
            self.viewer.set_selected_residues(list(indices), object_id=object_id)
            self.viewer.update()
        except Exception:
            logging.getLogger(__name__).debug(
                "Could not apply a sequence-strip selection", exc_info=True
            )

    def _prefill_command_line(self, line: str, placeholder: str = "") -> None:
        """Write a menu entry that needs a value into the command line.

        The in-viewport panel has nowhere to type, so its prompted entries used
        to be skipped -- clicked, and nothing happened. The command line is one
        row below it.
        """
        panel = getattr(self, "command_panel", None)
        if panel is None:
            return
        try:
            panel.prefill(line, placeholder)
        except Exception:
            logging.getLogger(__name__).debug(
                "could not prefill the command line", exc_info=True
            )

    def _menu_file_prompt(self, line: str, mode: str, title: str,
                          name_filter: str) -> None:
        """Open a real file dialog for a viewport-menu entry that names a file.

        The viewport menu bar is the one the user sees (the Qt bar is hidden,
        and on macOS it would live in the system bar anyway), so ``Save
        Molecule As...`` clicked there must open the same dialog the Qt path
        does -- a filename typed blind lands wherever the process is running.
        The command line keeps taking paths as text.
        """
        if mode == "open":
            text, _used = QtWidgets.QFileDialog.getOpenFileName(
                self, title, "", name_filter
            )
        else:
            text, _used = QtWidgets.QFileDialog.getSaveFileName(
                self, title, "", name_filter
            )
        text = str(text).strip()
        if not text:
            return
        self._run_internal_gui_command(line.replace("{text}", text))

    def _fan_out(self, sink, kind: str):
        """Return a callback that reports to the console *and* to the viewport.

        Parameters
        ----------
        sink : callable
            The console's own message or error method.
        kind : str
            ``"message"`` or ``"error"``, which is how the viewport's log
            colours the line.

        Returns
        -------
        callable
            Takes the text. The viewport half is looked up per call rather than
            captured, because the panel is rebuilt whenever the object list
            changes and a captured one would go on writing into a dead log.
        """
        def _report(text: str) -> None:
            try:
                sink(text)
            except Exception:
                logging.getLogger(__name__).debug(
                    "console rejected a message", exc_info=True
                )
            gui = self._viewport_gui()
            if gui is not None:
                gui.command_line.append(str(text), kind)
                try:
                    self.viewer.update()
                except Exception:
                    pass

        return _report

    def _viewport_gui(self):
        """Return the in-viewport chrome, or ``None`` when there is none."""
        renderer = getattr(getattr(self, "viewer", None), "_renderer", None)
        return getattr(renderer, "_internal_gui", None)

    def _wire_internal_command_line(self, gui) -> None:
        """Give the viewport's prompt the command names and the shared history.

        The completions come from the same :class:`ChimolDispatcher` the docked
        console uses, so the two prompts complete identically -- a prompt that
        completes differently from the one beside it is worse than one that does
        not complete at all, because the difference reads as a missing command.
        """
        line = gui.command_line
        if line.completions is None:
            from .command_dispatch import ChimolDispatcher

            line.completions = ChimolDispatcher(_cmd).completions
        if line.history:
            return
        # Seeded from the console's history file, not sharing it: the console
        # owns that file, and two writers appending to one history is how it
        # gains duplicates. So Up in the viewport recalls what was typed in
        # earlier sessions, and this session's two prompts keep their own.
        panel = getattr(self, "command_panel", None)
        entries = getattr(
            getattr(getattr(panel, "shell", None), "history", None), "entries", None
        )
        if entries:
            line.history = [str(item) for item in entries][-line.MAX_HISTORY:]
            line._history_index = len(line.history)

    def _run_internal_gui_command(self, line: str) -> None:
        """Run a command the in-viewport panel produced, echoing it.

        Echoed like a menu click for the same reason: it is how someone learns
        which command the thing they clicked corresponds to.
        """
        self._run_object_menu_command(str(line))
        self.sync_internal_gui()

    @staticmethod
    def _grouped_display_order(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Order objects so each group's members are contiguous.

        A group's block goes where its *first* member sits in the registry, and
        within the block the members keep their registry order. Ungrouped
        objects keep their positions. Nothing is reordered in the viewer -- this
        is only how the rows are laid out, so ``order`` still means what it says.

        Parameters
        ----------
        objects : list of dict
            Entries as returned by ``MolView.list_objects``.

        Returns
        -------
        list of dict
            The same entries, reordered for display.
        """
        blocks: list[tuple[str | None, list[dict[str, Any]]]] = []
        index: dict[str, int] = {}
        for obj in objects:
            group = obj.get("group")
            if not group:
                blocks.append((None, [obj]))
                continue
            slot = index.get(group)
            if slot is None:
                index[group] = len(blocks)
                blocks.append((group, [obj]))
            else:
                blocks[slot][1].append(obj)
        return [obj for _group, members in blocks for obj in members]

    def _add_group_list_item(self, group: str, is_open: bool) -> None:
        """Add the header row that stands for a group."""
        item = self.objects.create_group_item(group, is_open)
        self.object_list.addItem(item)
        self.objects.attach_group_row(item, group, is_open)

    def _select_object_in_ui(self, object_id: Optional[str]) -> None:
        if object_id is None:
            self.object_list.clearSelection()
            self._handle_active_object_change(None)
            return

        self.objects.set_current_object(object_id)

    def _handle_active_object_change(self, object_id: Optional[str]) -> None:
        if object_id is None:
            self._active_object_id = None
            self._update_sequence_view(None)
            self._update_system_info(None)
            if hasattr(self, "rmf_panel"):
                self.rmf_panel.set_state(None)
            return

        self._active_object_id = object_id
        try:
            self.viewer.set_active_object(object_id)
        except Exception:
            pass

        self._update_sequence_view(object_id)
        self._update_system_info(object_id)

        if hasattr(self, "rmf_panel"):
            try:
                state = self.viewer._get_active_state()
                self.rmf_panel.set_state(state)
            except Exception:
                self.rmf_panel.set_state(None)

    def on_object_selection_changed(self) -> None:
        if self._block_object_list_signals:
            return

        item = self.object_list.currentItem()
        if item is None:
            self._handle_active_object_change(None)
            return

        object_id = item.data(_OBJECT_ID_ROLE)
        if not object_id:
            self._handle_active_object_change(None)
            return

        self._handle_active_object_change(str(object_id))

    def on_object_item_changed(self, item: QtWidgets.QListWidgetItem) -> None:
        if self._block_object_list_signals or item is None:
            return

        object_id = item.data(_OBJECT_ID_ROLE)
        if not object_id:
            return

        visible = item.checkState() == QtCore.Qt.Checked
        self._set_object_visible(object_id, visible)

        row_info = self._sequence_rows.get(str(object_id)) if hasattr(self, "_sequence_rows") else None
        if isinstance(row_info, dict):
            btn = row_info.get("button")
            lst = row_info.get("list")
            if isinstance(btn, QtWidgets.QToolButton):
                try:
                    btn.blockSignals(True)
                    btn.setChecked(bool(visible))
                    btn.blockSignals(False)
                except Exception:
                    pass
            if isinstance(lst, QtWidgets.QListWidget):
                lst.setEnabled(bool(visible))
            try:
                self._update_sequence_row_colors(str(object_id), bool(visible))
            except Exception:
                pass

        if object_id == self.viewer.get_active_object_id():
            self._sequence_visible = bool(visible)
            try:
                self.seq_label.blockSignals(True)
                self.seq_label.setChecked(bool(visible))
                self.seq_label.blockSignals(False)
            except Exception:
                pass
            try:
                self._apply_sequence_selection_styles(set(self._selected_residue_indices()))
            except Exception:
                pass

    def _on_object_list_context_menu(self, pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self.object_list)
        action_select_all = menu.addAction("Select All")
        action_clear_selection = menu.addAction("Clear Selection")
        menu.addSeparator()
        action_delete = menu.addAction("Delete Selected")

        chosen = menu.exec_(self.object_list.mapToGlobal(pos))
        if chosen == action_select_all:
            self.object_list.selectAll()
        elif chosen == action_clear_selection:
            self.object_list.clearSelection()
        elif chosen == action_delete:
            self._delete_selected_objects()

    def _delete_selected_objects(self) -> None:
        items = self.object_list.selectedItems()
        if not items:
            return

        object_ids: list[str] = []
        for item in items:
            oid = item.data(_OBJECT_ID_ROLE)
            if oid:
                object_ids.append(str(oid))

        if not object_ids:
            return

        for oid in object_ids:
            try:
                self.viewer.remove_object(oid)
            except Exception:
                pass
            self._object_store.pop(oid, None)

        self._refresh_objects_from_viewer()

    def on_seq_label_toggled(self, checked: bool) -> None:
        active_id = self.viewer.get_active_object_id()
        if active_id is None:
            return

        self._block_object_list_signals = True
        try:
            self._set_object_visible(active_id, checked)
            self.objects.set_item_checked(active_id, checked)
        finally:
            self._block_object_list_signals = False

        self._sequence_visible = bool(checked)
        try:
            self._apply_sequence_selection_styles(set(self._selected_residue_indices()))
        except Exception:
            pass

    def on_seq_row_toggled(self, object_id: str, checked: bool) -> None:
        if not object_id:
            return

        active_id = self.viewer.get_active_object_id()

        self._block_object_list_signals = True
        try:
            self._set_object_visible(object_id, checked)
            self.objects.set_item_checked(object_id, checked)
        finally:
            self._block_object_list_signals = False

        row_info = self._sequence_rows.get(str(object_id)) if hasattr(self, "_sequence_rows") else None
        if isinstance(row_info, dict):
            lst = row_info.get("list")
            if isinstance(lst, QtWidgets.QListWidget):
                lst.setEnabled(bool(checked))
            try:
                self._update_sequence_row_colors(str(object_id), bool(checked))
            except Exception:
                pass

        if active_id == object_id:
            self._sequence_visible = bool(checked)
            try:
                self.seq_label.blockSignals(True)
                self.seq_label.setChecked(bool(checked))
                self.seq_label.blockSignals(False)
            except Exception:
                pass
            try:
                self._apply_sequence_selection_styles(set(self._selected_residue_indices()))
            except Exception:
                pass

    def _selected_residue_indices(self) -> list[int]:
        if self.seq_list.count() == 0:
            return []
        indices: list[int] = []
        for model_idx in self.seq_list.selectedIndexes():
            item = self.seq_list.item(model_idx.row())
            if item is None:
                continue
            seq_idx = item.data(_SEQ_INDEX_ROLE)
            if isinstance(seq_idx, int) and seq_idx >= 0:
                indices.append(seq_idx)
        return sorted(set(indices))

    def _populate_sequence_numbers(
        self,
        max_len: int,
        step: int,
        *,
        active_length: int = 0,
        residue_numbers: Optional[np.ndarray] = None,
    ) -> None:
        self.seq_numbers_list.clear()
        if max_len <= 0:
            return
        digits = len(str(max(1, max_len)))
        seq_cfg = self.sequence.sequence_config()
        fg_rgba = seq_cfg.get("number_color", [0.9, 0.9, 0.9, 1.0])
        bg_rgba = seq_cfg.get("number_bg_color", [0.12, 0.12, 0.12, 1.0])
        fallback_fg = QtGui.QBrush(self.sequence.color_from_rgba(fg_rgba, (0.9, 0.9, 0.9, 1.0)))
        fallback_bg = QtGui.QBrush(self.sequence.color_from_rgba(bg_rgba, (0.12, 0.12, 0.12, 1.0)))

        resno_arr: Optional[np.ndarray]
        try:
            if residue_numbers is not None:
                arr_res = np.asarray(residue_numbers)
                if arr_res.ndim == 1:
                    resno_arr = arr_res
                else:
                    resno_arr = None
            else:
                resno_arr = None
        except Exception:
            resno_arr = None

        color_arr: Optional[np.ndarray]
        try:
            if residue_colors is not None:
                c_arr = np.asarray(residue_colors, dtype=float)
                if c_arr.ndim == 2 and c_arr.shape[1] >= 3:
                    color_arr = c_arr
                else:
                    color_arr = None
            else:
                color_arr = None
        except Exception:
            color_arr = None

        # Build per-position labels so that residue indices are laid out as a
        # single monospaced string like "1   5    10   15   20" where each
        # character aligns with one residue cell in the sequence row below.
        step_val = step if step > 0 else 1
        labels: list[str] = ["·"] * max_len
        if max_len > 0:
            for idx in range(max_len):
                r = -1
                if resno_arr is not None and idx < resno_arr.shape[0]:
                    try:
                        r = int(resno_arr[idx])
                    except Exception:
                        pass
                else:
                    r = idx + 1

                if r <= 0:
                    continue

                if r == 1 or r % step_val == 0:
                    text = str(r)
                    start = idx + 1 - len(text)
                    if start < 0:
                        text = text[-(idx + 1):]
                        start = 0
                    for j, ch in enumerate(text):
                        idx_char = start + j
                        if 0 <= idx_char < max_len:
                            labels[idx_char] = ch

        size_hint = None
        if self.seq_list.count() > 0:
            try:
                idx0 = self.seq_list.model().index(0, 0)
                size_hint = self.seq_list.sizeHintForIndex(idx0)
            except Exception:
                size_hint = None
        normal_font = getattr(self, "_sequence_number_font", None)
        bold_font = getattr(self, "_sequence_number_bold_font", None)

        for idx in range(max_len):
            item = QtWidgets.QListWidgetItem()
            ch = labels[idx] if idx < len(labels) else " "
            text = ch if ch else " "
            item.setText(text)
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            item.setFlags(QtCore.Qt.ItemIsEnabled)

            # Use neutral number coloring; never mirror 3D per-residue colors.
            bg_brush = fallback_bg
            fg_brush = fallback_fg

            item.setBackground(bg_brush)
            item.setForeground(fg_brush)

            # Keep size in sync with sequence row.
            ref_item = self.seq_list.item(idx)
            if ref_item is not None:
                hint = ref_item.sizeHint()
                if hint.isValid():
                    item.setSizeHint(hint)
            elif size_hint is not None:
                item.setSizeHint(size_hint)

            if text.strip() and bold_font is not None:
                item.setFont(bold_font)
            elif normal_font is not None:
                item.setFont(normal_font)
            item.setData(_SEQ_INDEX_ROLE, idx)
            self.seq_numbers_list.addItem(item)

    def _build_sequence_items(
        self,
        *,
        seq_codes: Optional[Sequence[object]],
        res_names: Optional[Sequence[object]],
        ss_codes: Optional[Sequence[object]],
        max_len: int,
        enable_selection: bool,
        empty_text: str,
        res_numbers: Optional[np.ndarray] = None,
        residue_colors: Optional[np.ndarray] = None,
        index_map: Optional[np.ndarray] = None,
    ) -> list[QtWidgets.QListWidgetItem]:
        items: list[QtWidgets.QListWidgetItem] = []
        if max_len <= 0:
            placeholder = QtWidgets.QListWidgetItem(empty_text or "(no sequence)")
            placeholder.setTextAlignment(QtCore.Qt.AlignCenter)
            placeholder.setFlags(QtCore.Qt.ItemIsEnabled)
            placeholder.setData(_SEQ_INDEX_ROLE, -1)
            items.append(placeholder)
            return items

        length = self._sequence_length(seq_codes, res_names)
        seq_codes = tuple(seq_codes) if seq_codes is not None else None
        res_names = tuple(res_names) if res_names is not None else None
        ss_codes = tuple(ss_codes) if ss_codes is not None else None

        # Optional PDB residue numbers aligned with the CA trace; when present
        # they will be shown in tooltips and system-info instead of simple
        # 1-based indices.
        resno_arr: Optional[np.ndarray]
        try:
            if res_numbers is not None:
                arr_res = np.asarray(res_numbers)
                if arr_res.ndim == 1:
                    resno_arr = arr_res
                else:
                    resno_arr = None
            else:
                resno_arr = None
        except Exception:
            resno_arr = None

        tooltip_hint = empty_text or ""

        # Optional mapping from alignment-column index to true sequence index
        # (0-based along the CA trace). When provided, this exposes explicit
        # gaps where the value is negative.
        index_map_arr: Optional[np.ndarray]
        try:
            if index_map is not None:
                arr_map = np.asarray(index_map, dtype=int)
                if arr_map.ndim == 1:
                    index_map_arr = arr_map
                else:
                    index_map_arr = None
            else:
                index_map_arr = None
        except Exception:
            index_map_arr = None

        # Optional per-residue RGBA colors. Matches CA trace colors.
        color_arr: Optional[np.ndarray]
        try:
            if residue_colors is not None:
                arr_col = np.asarray(residue_colors, dtype=float)
                if arr_col.ndim == 2 and arr_col.shape[0] == length:
                    color_arr = arr_col
                else:
                    color_arr = None
            else:
                color_arr = None
        except Exception:
            color_arr = None

        real_cells = 0
        for idx in range(max_len):
            item = QtWidgets.QListWidgetItem()
            # Determine the underlying sequence index for this alignment
            # column. When an alignment map is present, negative values mark
            # gaps for this object at the corresponding residue number.
            if index_map_arr is not None and idx < index_map_arr.shape[0]:
                seq_index = int(index_map_arr[idx])
            else:
                seq_index = idx if idx < length else -1

            orig_seq_index = seq_index

            if 0 <= seq_index < length:
                aa = seq_codes[seq_index] if seq_codes is not None else "?"
                aa_str = str(aa) if aa is not None else "?"
                ss = (
                    ss_codes[seq_index]
                    if ss_codes is not None and seq_index < len(ss_codes)
                    else "C"
                )
                ss_str = str(ss).upper() if ss is not None else "C"
                if (
                    color_arr is not None
                    and seq_index < color_arr.shape[0]
                    and color_arr.shape[1] >= 3
                ):
                    try:
                        r, g, b = color_arr[seq_index, :3]
                        a = color_arr[seq_index, 3] if color_arr.shape[1] >= 4 else 1.0
                        bg = QtGui.QColor.fromRgbF(float(r), float(g), float(b), float(a))
                        lum = 0.299 * float(r) + 0.587 * float(g) + 0.114 * float(b)
                        fg = QtGui.QColor(255, 255, 255) if lum < 0.5 else QtGui.QColor(0, 0, 0)
                    except Exception:
                        bg, fg = SequenceDock.default_sequence_palette(ss_str)
                else:
                    bg, fg = SequenceDock.default_sequence_palette(ss_str)
                res_name = (
                    str(res_names[seq_index])
                    if res_names is not None and seq_index < len(res_names)
                    else "?"
                )
                if resno_arr is not None and seq_index < resno_arr.shape[0]:
                    try:
                        res_no = int(resno_arr[seq_index])
                    except Exception:
                        res_no = seq_index + 1
                else:
                    res_no = seq_index + 1
                tooltip = f"{res_no}: {res_name} ({aa_str}), SS={ss_str}"
                text = aa_str
                real_cells += 1
            else:
                # Explicit gap on the alignment axis for this object. Drawn in a
                # muted grey rather than the coil palette: a gap is not a residue,
                # and on a row that is mostly gaps the few real ones were
                # indistinguishable from the padding around them.
                bg, fg = SequenceDock.gap_palette()
                tooltip = tooltip_hint
                seq_index = -1
                text = "." if orig_seq_index == -2 else "-"

            item.setText(text or " ")
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            item.setData(_SEQ_COLOR_ROLE, (bg, fg))
            item.setData(_SEQ_INDEX_ROLE, seq_index)
            if tooltip:
                item.setToolTip(tooltip)
            flags = QtCore.Qt.ItemIsEnabled
            if enable_selection and seq_index >= 0:
                flags |= QtCore.Qt.ItemIsSelectable
            item.setFlags(flags)
            item.setBackground(QtGui.QBrush(bg))
            item.setForeground(QtGui.QBrush(fg))
            items.append(item)

        if not real_cells:
            # Every cell is padding: this object contributes nothing to the
            # alignment axis. A row of a hundred-odd identical dashes says that
            # far less clearly than saying it, and reads as a broken row.
            note = QtWidgets.QListWidgetItem(empty_text or "(no sequence)")
            note.setTextAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
            note.setFlags(QtCore.Qt.ItemIsEnabled)
            note.setData(_SEQ_INDEX_ROLE, -1)
            note.setForeground(QtGui.QBrush(QtGui.QColor(140, 140, 140)))
            return [note]

        return items

    def _reset_scroll_targets(self) -> None:
        for bar in getattr(self, "_scroll_targets", []):
            try:
                bar.valueChanged.disconnect(self._on_target_scroll_changed)
            except Exception:
                pass
        if getattr(self, "_scroll_master", None) is not None:
            try:
                self._scroll_master.valueChanged.disconnect(self._on_master_scroll_changed)
            except Exception:
                pass
        if getattr(self, "_content_scrollbar", None) is not None:
            try:
                self._content_scrollbar.rangeChanged.disconnect(self._on_content_scroll_range_changed)
            except Exception:
                pass
            try:
                self._content_scrollbar.valueChanged.disconnect(self._on_target_scroll_changed)
            except Exception:
                pass
        self._content_scrollbar = None

        self._scroll_targets = []
        self._scroll_master = None

        master = getattr(self, "seq_scrollbar", None)
        content_bar = self.seq_list.horizontalScrollBar() if hasattr(self, "seq_list") else None
        # Read sequence display configuration to determine whether scrolling
        # should be synchronized across all rows or independent per row.
        seq_cfg = self.sequence.sequence_config()
        raw_independent = seq_cfg.get("independent_scroll", False)
        # Only treat a real boolean True as enabling independent scrolling;
        # avoid truthiness of strings like "False".
        independent = bool(raw_independent) if isinstance(raw_independent, bool) else False

        if master is None or content_bar is None:
            if master is not None:
                master.blockSignals(True)
                master.setRange(0, 0)
                master.setPageStep(0)
                master.setValue(0)
                master.setEnabled(False)
                master.blockSignals(False)
            return

        # When independent scrolling is enabled, hide/disable the shared
        # master scrollbar and allow each row's own horizontal scrollbar to
        # operate normally.
        if independent:
            try:
                master.blockSignals(True)
                master.setRange(0, 0)
                master.setPageStep(0)
                master.setValue(0)
                master.setEnabled(False)
                master.blockSignals(False)
            except Exception:
                pass

            # Enable individual horizontal scrollbars for all sequence lists.
            try:
                if hasattr(self, "seq_list") and self.seq_list is not None:
                    self.seq_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            except Exception:
                pass
            try:
                if hasattr(self, "seq_numbers_list") and self.seq_numbers_list is not None:
                    self.seq_numbers_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            except Exception:
                pass
            try:
                for row in getattr(self, "_sequence_rows", {}).values():
                    lst = row.get("list")
                    if isinstance(lst, QtWidgets.QListWidget):
                        lst.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            except Exception:
                pass

            # No shared-scroll wiring in this mode.
            return

        # Synchronized scrolling mode (default): ensure per-row scrollbars are
        # hidden and driven by the shared master scrollbar.
        try:
            if hasattr(self, "seq_list") and self.seq_list is not None:
                self.seq_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        except Exception:
            pass
        try:
            if hasattr(self, "seq_numbers_list") and self.seq_numbers_list is not None:
                self.seq_numbers_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        except Exception:
            pass
        try:
            for row in getattr(self, "_sequence_rows", {}).values():
                lst = row.get("list")
                if isinstance(lst, QtWidgets.QListWidget):
                    lst.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        except Exception:
            pass
        self._scroll_master = master
        master.valueChanged.connect(self._on_master_scroll_changed)
        self._content_scrollbar = content_bar
        content_bar.rangeChanged.connect(self._on_content_scroll_range_changed)

        targets: list[QtWidgets.QScrollBar] = []
        targets.append(content_bar)
        if hasattr(self, "seq_numbers_list") and self.seq_numbers_list is not None:
            bar = self.seq_numbers_list.horizontalScrollBar()
            if bar is not None and bar is not master:
                targets.append(bar)

        for row in self._sequence_rows.values():
            lst = row.get("list")
            if isinstance(lst, QtWidgets.QListWidget):
                bar = lst.horizontalScrollBar()
                if bar is not None and bar is not master:
                    targets.append(bar)

        self._scroll_targets = targets
        value = content_bar.value()
        for bar in self._scroll_targets:
            bar.setValue(value)
            bar.valueChanged.connect(self._on_target_scroll_changed)

        self._update_shared_scrollbar_range()

    def _on_master_scroll_changed(self, value: int) -> None:
        if self._scroll_updating:
            return
        self._scroll_updating = True
        try:
            for bar in self._scroll_targets:
                if bar.value() != value:
                    bar.setValue(value)
        finally:
            self._scroll_updating = False

    def _on_target_scroll_changed(self, value: int) -> None:
        if self._scroll_updating:
            return
        if self._scroll_master is None:
            return

        # When any target scrollbar moves (including the main sequence row or
        # additional rows), drive the shared master scrollbar and explicitly
        # synchronize all other targets. We do this here instead of relying on
        # _on_master_scroll_changed (which is skipped while _scroll_updating
        # is True) so that scrolling inside any row keeps all rows aligned.
        self._scroll_updating = True
        try:
            if self._scroll_master.value() != value:
                self._scroll_master.setValue(value)
            for bar in self._scroll_targets:
                try:
                    if bar.value() != value:
                        bar.setValue(value)
                except Exception:
                    pass
        finally:
            self._scroll_updating = False

    def _on_content_scroll_range_changed(self, minimum: int, maximum: int) -> None:
        self._update_shared_scrollbar_range()

    def _update_shared_scrollbar_range(self) -> None:
        master = getattr(self, "seq_scrollbar", None)
        content = getattr(self, "_content_scrollbar", None)
        if master is None:
            return
        if content is None:
            master.blockSignals(True)
            master.setRange(0, 0)
            master.setPageStep(0)
            master.setValue(0)
            master.setEnabled(False)
            master.blockSignals(False)
            return
        master.blockSignals(True)
        master.setRange(content.minimum(), content.maximum())
        master.setPageStep(content.pageStep())
        master.setSingleStep(max(1, content.singleStep()))
        master.setEnabled(content.maximum() > content.minimum())
        master.setValue(content.value())
        master.blockSignals(False)

    def _apply_sequence_selection_styles(self, selected_rows: set[int]) -> None:
        if self.seq_list.count() == 0:
            return
        seq_cfg = self.sequence.sequence_config()
        sel_bg = self.sequence.color_from_rgba(
            seq_cfg.get("selection_color", [1.0, 0.95, 0.4, 1.0]),
            [1.0, 0.95, 0.4, 1.0],
        )
        sel_fg = self.sequence.color_from_rgba(
            seq_cfg.get("selection_text_color", [0.1, 0.1, 0.1, 1.0]),
            [0.1, 0.1, 0.1, 1.0],
        )
        for row in range(self.seq_list.count()):
            item = self.seq_list.item(row)
            if item is None:
                continue
            palette = item.data(_SEQ_COLOR_ROLE)
            if isinstance(palette, tuple) and len(palette) == 2:
                base_bg, base_fg = palette
            else:
                base_bg = QtGui.QColor(220, 220, 200)
                base_fg = QtGui.QColor(0, 0, 0)
            seq_idx = item.data(_SEQ_INDEX_ROLE)
            if not getattr(self, "_sequence_visible", True):
                gray_bg = QtGui.QColor(200, 200, 200)
                gray_fg = QtGui.QColor(140, 140, 140)
                item.setBackground(QtGui.QBrush(gray_bg))
                item.setForeground(QtGui.QBrush(gray_fg))
            elif isinstance(seq_idx, int) and seq_idx >= 0 and seq_idx in selected_rows:
                item.setBackground(QtGui.QBrush(sel_bg))
                item.setForeground(QtGui.QBrush(sel_fg))
            else:
                item.setBackground(QtGui.QBrush(base_bg))
                item.setForeground(QtGui.QBrush(base_fg))

    def _apply_representation_to_selection(self, cartoon=None, ball=None) -> None:
        idx = self._selected_residue_indices()
        if not idx:
            return
        try:
            self.viewer.set_residue_representation(idx, cartoon=cartoon, ball=ball)
        except Exception as e:
            try:
                cs.logging.warning(
                    "MolViewPluginWindow._apply_representation_to_selection failed: %s",
                    e,
                )
            except Exception:
                pass

    def _get_secondary_structure_codes(self, object_id: Optional[str], n_res: int) -> list[str] | None:
        """Return a list of secondary-structure codes (H/E/C) for residues.

        Delegates to :func:`assign_ss_c3_from_file` in :mod:`ss`, which
        implements a simplified DSSP-style assignment inspired by PyDSSP.
        If anything fails, returns ``None`` and the sequence view falls back
        to plain coloring.
        """

        if n_res <= 0 or object_id is None:
            return None
        entry = self._object_store.get(object_id)
        if entry is None:
            return None
        if entry.get("ss_codes") is not None:
            return entry["ss_codes"]

        structure = entry.get("structure")
        atoms = getattr(structure, "atoms", None) if structure is not None else None
        if atoms is None:
            return None

        codes = assign_ss_c3_from_atoms(atoms, n_res)
        if not codes:
            return None
        entry["ss_codes"] = codes
        return codes

if __name__ == "plugin":
    # When launched via the ChiSurf plugin system, __name__ is set to
    # "plugin" and a QApplication is already running.
    window = MolViewPluginWindow()
    window.resize(1000, 700)
    window.show()
