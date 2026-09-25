"""Integrated burst workflow GUI."""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qtpy import QtCore, QtWidgets

import chisurf

logger = logging.getLogger(__name__)
from chisurf.core.fio.staging import TTTR_EXTENSIONS as _TTTR_EXTENSIONS
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.navigation import NavigationPanelTool
from chisurf.gui.widgets.wizard.tttr_channeldefinition.setup_client import (
    DetectorSetupClient,
)


@dataclass
class BurstWorkflowContext:
    """Shared state handed from earlier burst workflow steps to later steps."""

    channel_settings: dict[str, Any] = field(default_factory=dict)
    #: Name of the detector setup ``channel_settings`` was read from — panels
    #: that take a setup by name (rather than a detector table) need it.
    setup_name: str = ""
    raw_files: list[Path] = field(default_factory=list)
    burst_folder: Path | None = None
    bur_files: list[Path] = field(default_factory=list)
    mmfdb_artifacts: dict[str, Any] = field(default_factory=dict)
    raw_mmfdb_artifacts: dict[str, Any] = field(default_factory=dict)
    #: VV/VH-stacked {detector: {"irf", "bg"}} patterns from the IRF/background
    #: tool, applied to the MLE panel when it loads.
    irf_background_patterns: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-compatible workflow context payload."""
        return {
            "channel_settings": self.channel_settings,
            "setup_name": self.setup_name,
            "raw_files": [str(path) for path in self.raw_files],
            "burst_folder": str(self.burst_folder) if self.burst_folder else None,
            "bur_files": [str(path) for path in self.bur_files],
            "mmfdb_artifacts": self.mmfdb_artifacts,
            "raw_mmfdb_artifacts": self.raw_mmfdb_artifacts,
        }


class BurstDataSelectionWidget(QtWidgets.QWidget):
    """Workflow-local raw TTTR file/folder selector."""

    # The reader's list, not a copy of it that drifted: this one had every
    # vendor format and not ChiSurf's own container.
    TTTR_EXTENSIONS = set(_TTTR_EXTENSIONS)

    class _FileListModel:
        """Adapter the shared ``path_list`` widget binds to.

        ``PathListWidget`` reads/writes ``.paths`` (``list[str]``) and calls
        ``.update()`` after each change. It is a separate object — not the
        QWidget — so ``update`` does not shadow ``QWidget.update``.
        """

        def __init__(self, owner: BurstDataSelectionWidget) -> None:
            self._owner = owner
            self.paths: list[str] = []

        def update(self) -> None:
            self._owner._on_paths_committed(list(self.paths))

    #: Drop guards offered on a drag-and-drop. A workflow whose own steps do
    #: the conversion overrides this with ``()`` — see
    #: :class:`~chisurf.plugins.burst.alex_suite.gui.tool.AlexSuiteTool`.
    DROP_GUARDS: tuple[str, ...] = ("tttr_to_pto",)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        guards: tuple[str, ...] | None = None,
    ) -> None:
        """Create the data-selection panel.

        ``guards`` overrides :attr:`DROP_GUARDS` — pass ``()`` when the workflow
        converts the measurements itself, so a drop does not quietly write a
        second container beside the source with the wrong contents.
        """
        super().__init__(parent)
        self._guards = tuple(self.DROP_GUARDS if guards is None else guards)
        self._paths: list[Path] = []
        self._mmfdb_imports: dict[str, dict[str, Any]] = {}
        self._mmfdb_selections: dict[str, dict[str, Any]] = {}
        self._mmfdb_client: Any | None = None
        self._imported: set[str] = set()
        self._model = self._FileListModel(self)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # The shared AutoForm ``path_list`` widget: drag-drop + ➕ Files /
        # 📁 Folder / 🗄️ Database (MMFDB) / ➖ Remove / 🗑️ Clear, one implementation
        # across the app, instead of a hand-rolled list and button row.
        from chisurf.gui.autoform.sections.path_list_section import PathListWidget

        self.file_list = PathListWidget(
            self._model,
            "paths",
            extensions=sorted(self.TTTR_EXTENSIONS),
            add_folders=True,
            mmfdb=True,
            mmfdb_kinds=["raw_data", "raw_measurement", "external_reference"],
            mmfdb_scope="all",
            guards=list(self._guards),
        )
        self.file_list.hide()
        layout.addWidget(self.file_list)

        from emtk.qt_host import ControlHost
        from .data_selection_app import BurstDataSelectionApp, WINDOW_BG

        self.app = BurstDataSelectionApp(self)
        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        layout.addWidget(self.host, 1)

        self.status_label = QtWidgets.QLabel("No TTTR files selected.", self)
        self.status_label.hide()
        layout.addWidget(self.status_label)

    # -- external API kept stable for the workflow ----------------------------

    def paths(self) -> list[Path]:
        """Return selected raw TTTR paths."""
        return list(self._paths)

    def mmfdb_payload(self) -> dict[str, Any]:
        """Return MMFDB import and selection metadata."""
        return {
            "imports": self._mmfdb_imports,
            "selections": self._mmfdb_selections,
        }

    def add_paths(self, paths: list[Path]) -> None:
        """Add files/folders (folders expanded + de-duplicated by the widget)."""
        self.file_list.add_paths([str(Path(p)) for p in paths])
        if hasattr(self, "host"):
            self.host.update()

    def clear(self) -> None:
        """Clear selected data files."""
        self.file_list.clear()
        if hasattr(self, "host"):
            self.host.update()

    def _browse_files(self) -> None:
        ext_filter = "TTTR Files (*." + " *.".join(self.TTTR_EXTENSIONS) + ");;All Files (*)"
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select TTTR Files", "", ext_filter)
        if files:
            self.add_paths([Path(f) for f in files])

    def _browse_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Data Folder")
        if folder:
            self.add_paths([Path(folder)])

    def _browse_mmfdb(self) -> None:
        if hasattr(self.file_list, "_on_add_mmfdb"):
            self.file_list._on_add_mmfdb()

    def _remove_index(self, index: int) -> None:
        if 0 <= index < len(self._paths):
            new_paths = [p for i, p in enumerate(self._paths) if i != index]
            self.clear()
            if new_paths:
                self.add_paths(new_paths)
            if hasattr(self, "host"):
                self.host.update()

    def _on_paths_committed(self, path_strs: list[str]) -> None:
        """Sync canonical state after the ``path_list`` widget commits a change.

        Rebuilds ``self._paths`` (``list[Path]``), imports any newly-added local
        file into MMFDB, refreshes the status label, and notifies the workflow.
        """
        self._paths = [Path(p).resolve() for p in path_strs]
        for path in self._paths:
            key = str(path)
            if key not in self._imported:
                self._imported.add(key)
                self._import_path_to_mmfdb(path)
        self._update_status()

        callback = getattr(self.parent(), "_on_data_selection_changed", None)
        if callable(callback):
            callback()

    def _import_path_to_mmfdb(self, path: Path) -> None:
        """Import a local file into MMFDB object store and raw-data registry."""
        try:
            import base64

            client = self._client()
            # The RPC object store cannot read the client's filesystem, so send
            # the file's bytes as base64 rather than a server-side path.
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            object_result = (
                client.call(
                    "mmfdb.objects.put",
                    {
                        "data": encoded,
                        "filename": path.name,
                        "metadata": {"source": "burst_analysis.data_selection"},
                    },
                )
                or {}
            )
            payload: dict[str, Any] = {"object_result": object_result}
            try:
                raw_result = (
                    client.call(
                        "raw_data.register",
                        {
                            "raw_data": {
                                "file_path": str(path),
                                "data_type": "TTTR",
                                # One of MMFDB's storage_mode vocabulary terms; "file"
                                # is not one, and every registration was rejected.
                                "storage_mode": "local_file",
                                "header_metadata": {
                                    "mmfdb_object": object_result.get("object", {}),
                                    "source": "burst_analysis.data_selection",
                                },
                            }
                        },
                    )
                    or {}
                )
                payload["raw_data_result"] = raw_result
            except Exception as raw_exc:
                payload["raw_data_error"] = str(raw_exc)
            self._mmfdb_imports[str(path)] = payload
        except Exception as exc:
            self._mmfdb_imports[str(path)] = {"error": str(exc)}

    def _client(self) -> Any:
        """Return the shared, process-global MMFDB client for import and selection."""
        if self._mmfdb_client is None:
            # One session shared with every other file selector, not a private
            # embedded server for this widget.
            from chisurf.gui.widgets.mmfdb import picker

            self._mmfdb_client = picker.inprocess_client()
        return self._mmfdb_client

    def _update_status(self) -> None:
        """Update selection status label."""
        imported = len([entry for entry in self._mmfdb_imports.values() if "error" not in entry])
        self.status_label.setText(
            f"{len(self._paths)} TTTR file(s) selected; {imported} imported to MMFDB."
        )


def _data_selection(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the raw data selection panel."""
    widget = BurstDataSelectionWidget(parent=parent)
    _bind(parent, "data", widget)
    return widget


def _burst_selection(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the burst selection panel."""
    from chisurf.plugins.burst.burst_selection import BurstSelectionTool

    widget = BurstSelectionTool(parent=parent, show_channel_selection=True)
    _bind(parent, "selection", widget)
    return widget


def _burst_bva(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the BVA panel."""
    from chisurf.plugins.burst.burst_bva.gui.tool import BVATool

    widget = BVATool(parent=parent, embedded=True)
    _hide_dock_tab_by_name(widget, "Channel Definitions")
    _bind(parent, "bva", widget)
    return widget


def _burst_2cde(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the 2CDE (FRET-2CDE / ALEX-2CDE) panel."""
    from chisurf.plugins.burst.burst_2cde.gui.tool import BurstTwoCdeTool

    widget = BurstTwoCdeTool(parent=parent, embedded=True)
    _bind(parent, "two_cde", widget)
    return widget


def _mle_panel(parent: QtWidgets.QWidget, *, role: str, split_by_state: bool) -> QtWidgets.QWidget:
    """Create an embedded burst-MLE panel, at burst or at segment level.

    Both pipeline MLE steps are the *same* wizard: the burst-level step fits one
    decay per burst, the segment-level step additionally fits one decay per H2MM
    state (``Split by H2MM state``). Only the checkbox differs, so there is one
    implementation, one set of columns, and one companion contract — a separate
    per-state plugin is exactly what produced duplicate ``Tau (green)`` columns
    that every reader silently dropped (see ``okf/subsystems/burst-companions.md``).

    The split control is shown only on the segment step: in the burst-level step
    it sat *before* the segmentation it consumes, so a linear Next-walk met the
    option before the states existed.
    """
    from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

    wizard = MLELifetimeAnalysisWizard(parent=parent)
    _remove_tab_by_name(wizard, "Detector Definition")
    # Inside the workflow the burst files (Data Selection) and IRF/background
    # (IRF & Background -> Send to MLE) are provided upstream, so the MLE panel's
    # own file-drop docks are duplicates — hide them, leaving just the fit.
    wizard._embedded = True
    _set_state_split(wizard, split_by_state)
    _bind(parent, role, wizard)
    # Embed the plain central QWidget, not the QMainWindow. On native macOS an
    # embedded QMainWindow (its menu/status bars and native view layer) swallowed
    # mouse clicks over the panel; hosting just its central content widget avoids
    # every QMainWindow-as-child quirk. The wizard object stays alive as the
    # workflow's "mle" panel (it owns all the logic and widget references); the
    # content carries a back-reference so context application can resolve it.
    central = wizard.takeCentralWidget()
    if central is None:
        return wizard
    central._mle_wizard = wizard
    # Tie the wizard's lifetime to the widget that is actually embedded. Its fit
    # buttons live under ``central`` and are wired to ``wizard`` slots; if the
    # wizard (a QMainWindow) is left parented to the workflow in a separate
    # branch, a window/child cleanup can destroy it while ``central`` — and its
    # buttons — survive, so a later click fires a slot on a deleted C++ object
    # ("wrapped C/C++ object ... has been deleted"). Re-parenting the wizard onto
    # ``central`` puts them in one branch with one lifetime: the wizard can never
    # outlive nor predecease its own content.
    #
    # Reparent as a plain, hidden child widget — NOT a window. Kept as a
    # ``Qt.Window`` it stays a top-level widget that macOS actually shows (an
    # empty little traffic-light window floating over the panel, whose close
    # deletes the wizard and re-triggers the crash). ``Qt.Widget`` + ``hide()``
    # makes it an invisible, laid-out-nowhere child: it never renders, never
    # grabs clicks (the QMainWindow-as-child swallow only happens when visible),
    # and is not a window that can be closed.
    wizard.setParent(central, QtCore.Qt.Widget)
    wizard.hide()
    return central


def _set_state_split(wizard: QtWidgets.QWidget, enabled: bool) -> None:
    """Tick (and show) or hide the wizard's ``Split by H2MM state`` control."""
    box = getattr(wizard, "checkBox_split_by_state", None)
    row = getattr(wizard, "widget_state_split_row", None)
    if box is not None:
        box.setChecked(bool(enabled))
    if row is not None:
        row.setVisible(bool(enabled))


def _burst_mle(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the burst-level MLE panel (one lifetime per burst)."""
    return _mle_panel(parent, role="mle", split_by_state=False)


def _burst_segment_mle(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the segment-level MLE panel (one lifetime per burst *and* state)."""
    return _mle_panel(parent, role="segment_mle", split_by_state=True)


def _burst_h2mm(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the H2MM panel."""
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    widget = H2mmTool(parent=parent, embedded=True)
    _hide_dock_tab_by_name(widget, "Channel Definitions")
    _bind(parent, "h2mm", widget)
    return widget


def _burst_fcs(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the burst-wise FCS panel."""
    from chisurf.plugins.burst.burst_fcs_correlator.gui.tool import BurstFcsTool

    widget = BurstFcsTool(parent=parent, embedded=True)
    _bind(parent, "burst_fcs", widget)
    return widget


def _burst_gs(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the photon-by-photon kinetics (Gopich-Szabo) panel."""
    from chisurf.plugins.burst.burst_gs.gui.tool import BurstGsTool

    widget = BurstGsTool(parent=parent, embedded=True)
    _bind(parent, "burst_gs", widget)
    return widget


def _burst_accurate_fret(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the accurate-FRET (correction factors) panel."""
    from chisurf.plugins.burst.accurate_fret.gui.tool import AccurateFretTool

    widget = AccurateFretTool(parent=parent, embedded=True)
    _bind(parent, "accurate_fret", widget)
    return widget


def _burst_browser(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the burst browser panel."""
    from chisurf.plugins.burst.burst_browser import BurstBrowserWidget

    widget = BurstBrowserWidget(parent=parent)
    _bind(parent, "browser", widget)
    return widget


def _burst_background(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create burst background estimation panel."""
    from chisurf.plugins.burst.burst_background import BurstBackgroundEstimator

    try:
        widget = BurstBackgroundEstimator(show_channel_definition=False)
    except TypeError as exc:
        if "show_channel_definition" not in str(exc):
            raise
        widget = BurstBackgroundEstimator()
        _remove_tab_by_name(widget, "Channel Definition")
    widget.setParent(parent)
    _bind(parent, "background", widget)
    return widget


def _burst_fusion(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the optional burst-fusion panel."""
    from chisurf.plugins.burst.burst_fusion.gui.tool import BurstFusionTool

    widget = BurstFusionTool(parent=parent)
    _bind(parent, "fusion", widget)
    return widget


def _burst_irf_bg(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """Create the IRF & background (non-burst) panel."""
    from chisurf.plugins.burst.burst_irf_bg.gui.tool import BurstIrfBackgroundTool

    widget = BurstIrfBackgroundTool(parent=parent)
    _bind(parent, "irf_bg", widget)
    return widget


def _bind(parent: QtWidgets.QWidget, role: str, widget: QtWidgets.QWidget) -> None:
    """Bind a loaded panel to the workflow coordinator when available."""
    binder = getattr(parent, "bind_workflow_panel", None)
    if callable(binder):
        binder(role, widget)


def _remove_tab_by_name(widget: QtWidgets.QWidget, tab_name: str) -> None:
    """Remove a duplicate tab from an embedded legacy widget."""
    for tab_widget in widget.findChildren(QtWidgets.QTabWidget):
        for index in range(tab_widget.count()):
            if tab_widget.tabText(index) == tab_name:
                tab_widget.removeTab(index)
                return


def _hide_dock_tab_by_name(widget: QtWidgets.QWidget, tab_name: str) -> None:
    """Hide a DockArea tab by its registered name."""
    dock_area = getattr(widget, "dock_area", None)
    if dock_area is None:
        return
    for index in range(len(getattr(dock_area, "_all_widgets", []))):
        try:
            if dock_area.tabText(index) == tab_name:
                dock_area.hideTab(index)
                return
        except Exception:
            return


BURST_PANELS = [
    {
        "name": "1. Data Selection",
        "icon": Glyphs.OPEN,
        "description": "Select raw TTTR files used by all later steps.",
        "factory": _data_selection,
        "role": "data",
    },
    {
        "name": "2. Burst Selection",
        "icon": Glyphs.SEARCH,
        "description": "Define detector channels and find/filter bursts from TTTR data.",
        "factory": _burst_selection,
        "role": "selection",
    },
    # Step 3 is optional and changes *what a burst is* rather than measuring one,
    # which is why it sits before every step that measures: a companion computed
    # on the un-fused bursts has one row per un-fused burst and cannot be carried
    # across. Walking the pipeline past it only previews; it redirects the later
    # steps only when the user writes the fused folder.
    {
        "name": "3. Burst Fusion (optional)",
        "icon": Glyphs.LINK,
        "description": (
            "Optional: merge bursts the same molecule produced (recurrence "
            "P_same) into a new burst folder the later steps then use."
        ),
        "factory": _burst_fusion,
        "role": "fusion",
        # Walking the pipeline must not fuse. The later steps analyse whatever
        # burst folder the workflow currently holds, so a step that *replaces*
        # that folder cannot be allowed to act just because someone pressed
        # Next — the bursts every downstream number is computed from would
        # change without anyone asking for it. Pressing this step's own Fuse
        # button is the only thing that hands the fused folder downstream.
        "optional": True,
    },
    # Steps 4-6 are burst-level features: one number per burst. Step 7 cuts each
    # burst into segments, and step 8 is the same MLE fit one level down — one
    # number per burst *and* state. The names carry that split so the pipeline
    # reads as "first the burst, then inside it".
    {
        "name": "4. Burst BVA",
        "icon": Glyphs.CHART,
        "description": "Burst-level feature: burst variance analysis of the selected bursts.",
        "factory": _burst_bva,
        "role": "bva",
    },
    {
        "name": "5. Burst 2CDE",
        "icon": Glyphs.CHART,
        "description": "Burst-level feature: the FRET-2CDE / ALEX-2CDE burst-dynamics filter.",
        "factory": _burst_2cde,
        "role": "two_cde",
    },
    {
        "name": "6. Burst MLE",
        "icon": Glyphs.TARGET,
        "description": "Burst-level feature: one maximum-likelihood lifetime per burst.",
        "factory": _burst_mle,
        "role": "mle",
    },
    {
        "name": "7. Burst segmentation (H2MM)",
        "icon": Glyphs.SHUFFLE,
        "description": (
            "Cut each burst into segments: photon-by-photon HMM (H2MM) assigns "
            "every photon a state."
        ),
        "factory": _burst_h2mm,
        "role": "h2mm",
    },
    {
        "name": "8. Burst segment MLE",
        "icon": Glyphs.TARGET,
        "description": (
            "Segment-level: the same MLE fit once per burst and H2MM state, "
            "written as Tau S0 / Tau S1 ... beside the burst-level lifetime."
        ),
        "factory": _burst_segment_mle,
        "role": "segment_mle",
    },
    {
        "name": "────────",
        "icon": "",
        "separator": True,
        "role": "separator",
    },
    {
        "name": "Browser",
        "icon": Glyphs.COPY,
        "description": "Inspect the current burst workflow result.",
        "factory": _burst_browser,
        "role": "browser",
    },
    {
        "name": "Accurate FRET",
        "icon": Glyphs.TARGET,
        "description": (
            "Correction factors (alpha/beta/gamma/delta) for the bursts this workflow produced."
        ),
        "factory": _burst_accurate_fret,
        "role": "accurate_fret",
    },
    {
        "name": "Burst FCS",
        "icon": Glyphs.CHART,
        "description": "Correlate the photons of the selected bursts.",
        "factory": _burst_fcs,
        "role": "burst_fcs",
    },
    {
        "name": "Kinetics (GS)",
        "icon": Glyphs.SHUFFLE,
        "description": ("Photon-by-photon kinetics (Gopich-Szabo) on the selected bursts."),
        "factory": _burst_gs,
        "role": "burst_gs",
    },
    {
        "name": "Background",
        "icon": "🌙",
        "description": "Estimate background using the selected data and channel setup.",
        "factory": _burst_background,
        "role": "background",
    },
    {
        "name": "IRF & Background",
        "icon": Glyphs.SPARKLE,
        "description": (
            "Extract a per-detector IRF and background from the non-burst photons "
            "and feed them to both MLE steps."
        ),
        "factory": _burst_irf_bg,
        "role": "irf_bg",
    },
]


class BurstAnalysisTool(NavigationPanelTool):
    """Integrated burst workflow tool: the numbered pipeline plus its side tools.

    The pipeline runs at two grains — bursts (steps 2-5) and the segments H2MM
    cuts them into (steps 6-7) — and the step names say which.

    The class is also the base for *other* burst pipelines with a different step
    order — the ALEX Suite is one. Everything below the panel list is generic:
    the context is threaded between panels by ``role``, so a subclass that swaps
    :attr:`PANELS` (and adds its own roles to :meth:`_apply_context_to_panel`)
    inherits the whole hand-off layer unchanged.
    """

    #: Step list of this pipeline. Subclasses override it; nothing else here
    #: names a step.
    PANELS: list[dict[str, Any]] = BURST_PANELS
    #: Window title of this pipeline.
    TITLE = "Burst Analysis"
    #: Left-list width. Long step labels need a wider list, so it goes with the
    #: panel list rather than being fixed here.
    NAVIGATION_WIDTH = 310
    NAVIGATION_MIN_WIDTH = 290

    def __init__(self, parent=None):
        """Create the integrated burst workflow tool."""
        self.workflow_context = BurstWorkflowContext()
        self._workflow_panels: dict[str, QtWidgets.QWidget] = {}
        # Set once the optional fusion step has written a folder: the folder it
        # fused, and the folder it produced. Burst selection re-publishes its own
        # output folder on every context refresh, which would otherwise drop the
        # workflow back onto the un-fused bursts the moment the user changed step.
        self._fusion_source: Path | None = None
        self._fused_folder: Path | None = None
        # Shared detector definition flows through the central
        # ``detector_setups.*`` RPC store (same as the Imaging Tools window).
        self._setup_client = DetectorSetupClient()
        super().__init__(
            title=self.TITLE,
            panels=self.PANELS,
            parent=parent,
            minimum_size=(950, 620),
            initial_size=(1180, 760),
            # Wide enough for the longest step label ("6. Burst segmentation
            # (H2MM)"); at 270 it was clipped mid-word and the list grew a
            # horizontal scroll bar.
            navigation_width=self.NAVIGATION_WIDTH,
            navigation_min_width=self.NAVIGATION_MIN_WIDTH,
            # Embedded panels report status via normal logging; the shared status
            # bar shows any INFO record from the burst plugin package.
            status_logger="chisurf.plugins.burst",
        )

    def bind_workflow_panel(self, role: str, widget: QtWidgets.QWidget) -> None:
        """Register a loaded panel and apply current workflow context."""
        self._workflow_panels[role] = widget
        if role == "data":
            self._sync_data_context()
        elif role == "selection":
            self._bind_selection_panel(widget)
        self._apply_context_to_panel(role, widget)

    def goto_workflow_role(self, role: str) -> bool:
        """Select the workflow step with the given ``role`` (e.g. from a panel's
        'go to IRF & Background' button).
        """
        for i, panel in enumerate(self.panels):
            if panel.get("role") == role:
                self.nav_list.setCurrentRow(i)
                return True
        return False

    def _on_nav_changed(self, index: int) -> None:
        """Refresh and apply workflow context when the user changes steps."""
        self._refresh_workflow_context()
        super()._on_nav_changed(index)
        if 0 <= index < len(self.panels):
            role = str(self.panels[index].get("role") or "")
            widget = self._panel_widget(index)
            if widget is not None:
                self._apply_context_to_panel(role, widget)

    def _panel_widget(self, index: int) -> QtWidgets.QWidget | None:
        """Return the inner widget for a loaded panel wrapper."""
        if index < 0 or index >= len(self.panels):
            return None
        wrapper = self.panels[index].get("instance")
        if wrapper is None:
            return None
        layout = wrapper.layout()
        if layout is None or layout.count() == 0:
            return None
        item = layout.itemAt(0)
        return item.widget() if item is not None else None

    def _bind_selection_panel(self, widget: QtWidgets.QWidget) -> None:
        """Wrap Burst Selection execution so downstream steps see outputs."""
        if getattr(widget, "_burst_analysis_wrapped", False):
            return
        original = getattr(widget, "analyze_files", None)
        if not callable(original):
            return

        def wrapped_analyze_files(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            # A fresh burst search supersedes any fusion of the previous one.
            self._fusion_source = None
            self._fused_folder = None
            self._sync_selection_context(widget)
            self._apply_context_to_downstream()
            return result

        widget.analyze_files = wrapped_analyze_files
        widget._burst_analysis_wrapped = True

    def _refresh_workflow_context(self) -> None:
        """Refresh shared context from loaded upstream widgets."""
        self._sync_data_context()
        self._sync_channel_context()
        selection = self._workflow_panels.get("selection")
        if selection is not None:
            self._sync_selection_context(selection)

    def _sync_data_context(self) -> None:
        """Capture raw data selection from step 1."""
        panel = self._workflow_panels.get("data")
        paths = getattr(panel, "paths", None)
        if callable(paths):
            selected = paths()
            if selected:
                self.workflow_context.raw_files = selected
        mmfdb_payload = getattr(panel, "mmfdb_payload", None)
        if callable(mmfdb_payload):
            self.workflow_context.raw_mmfdb_artifacts = mmfdb_payload()

    def _on_data_selection_changed(self) -> None:
        """Propagate changed raw data selection to loaded panels."""
        self._sync_data_context()
        self._apply_context_to_downstream()

    def _sync_channel_context(self) -> None:
        """Capture channel definitions via the shared RPC store.

        There is no standalone Channels step — the channel definition comes from
        the detector setup the Burst Selection step has chosen. It is published to
        the central ``detector_setups.*`` RPC store, then read back so the
        workflow context always reflects the canonical (RPC-held) definition.
        """
        settings = self._channel_settings_from_selection()
        if settings:
            self._setup_client.set_current(settings)
        # Pull the canonical definition back from the RPC store.
        current = self._setup_client.get_current()
        if current:
            self.workflow_context.channel_settings = current
        name = self._selected_setup_name()
        if name:
            self.workflow_context.setup_name = name

    def _selected_setup_name(self) -> str:
        """Name of the detector setup the Burst Selection step has selected."""
        panel = self._workflow_panels.get("selection")
        return str(getattr(panel, "_selected_setup_name", "") or "")

    def _channel_settings_from_selection(self) -> dict | None:
        """The detector setup the Burst Selection step has selected, if any.

        Burst Selection applies a *saved* detector setup (name → definition), so
        that saved definition is the channel setup the rest of the workflow uses
        now that the standalone Channels step is gone.
        """
        name = self._selected_setup_name()
        if not name:
            return None
        try:
            from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups import (
                load_detector_setups,
            )

            setup = load_detector_setups().get("setups", {}).get(name)
            return setup or None
        except Exception:
            return None

    def _sync_selection_context(self, widget: QtWidgets.QWidget) -> None:
        """Capture burst-selection outputs from step 2."""
        raw_files = [Path(path) for path in getattr(widget, "_file_paths", [])]
        if raw_files:
            self.workflow_context.raw_files = raw_files

        result = (
            getattr(widget, "_last_service_result", None)
            or getattr(widget, "_last_result", None)
            or {}
        )
        if isinstance(result, dict):
            artifacts = result.get("mmfdb_artifacts") or {}
            if artifacts:
                self.workflow_context.mmfdb_artifacts = dict(artifacts)

        folder = self._folder_from_selection_result(result)
        if folder is None:
            folder = self._materialize_burst_handoff(widget)
        if folder is not None:
            # Keep the fused bursts once the optional step has produced them from
            # exactly this selection output — the later steps have adopted them.
            if self._fused_folder is not None and folder == self._fusion_source:
                folder = self._fused_folder
            self.workflow_context.burst_folder = folder
            # A container *is* the burst source, so it has no `.bur` files to
            # list — and `glob` on a file returns nothing rather than raising,
            # which would have left this silently empty either way.
            self.workflow_context.bur_files = (
                sorted(folder.glob("**/*.bur")) if folder.is_dir() else []
            )

    def _folder_from_selection_result(self, result: object) -> Path | None:
        """Return an output folder from a burst-selection result payload."""
        if not isinstance(result, dict):
            return None
        candidates: list[str] = []
        for key in ("output_folder", "analysis_folder"):
            value = result.get(key)
            if isinstance(value, str):
                candidates.append(value)
        for nested_key in ("metadata", "output_paths"):
            nested = result.get(nested_key) or {}
            if isinstance(nested, dict):
                value = nested.get("output_folder")
                if isinstance(value, str):
                    candidates.append(value)
        for candidate in candidates:
            path = Path(candidate)
            if path.exists() and path.is_dir():
                return path
        return None

    def _materialize_burst_handoff(self, widget: QtWidgets.QWidget) -> Path | None:
        """Give the later steps something to read the bursts from.

        For a `.pto` source that is the container itself: it already holds the
        bursts, beside the photons they were found in, and every downstream read
        goes through ``read_burst_analysis``, which opens one. Writing a
        ``burst_analysis_handoff/`` folder of `.bur` files there put the same
        results in a second place — and the second place went stale the moment
        the selection was re-run, which is how a step came to report **8 bursts**
        from a handoff folder while the panel above it showed hundreds.

        Anything else still gets the folder: a vendor file has nowhere to keep
        the bursts, and the legacy layout is what the readers understand.
        """
        frames_by_file = getattr(widget, "_last_frames_by_file", None)
        if not frames_by_file:
            return None
        raw_files = self.workflow_context.raw_files or [
            Path(path) for path in frames_by_file.keys()
        ]
        if not raw_files:
            return None

        from chisurf.core.fio.pto import SUFFIX

        containers = [p for p in raw_files if Path(p).suffix.lower() == SUFFIX]
        if containers and len(containers) == len(raw_files):
            # One container is one measurement; the later steps take the first
            # and read the rest from their own file the same way.
            return Path(containers[0])

        output_folder = raw_files[0].parent / "burst_analysis_handoff"
        bur_folder = output_folder / "bi4_bur"
        bur_folder.mkdir(parents=True, exist_ok=True)

        from chisurf.plugins.burst.burst_selection.api.io import (
            write_bur,
            write_container,
        )

        for raw_path in raw_files:
            frame = frames_by_file.get(raw_path.resolve())
            if frame is None:
                frame = frames_by_file.get(raw_path)
            if frame is None:
                continue
            write_bur(frame, bur_folder / f"{raw_path.stem}.bur")
            # The same bursts, in the measurement's own file. The handoff
            # folder is a bridge between two steps of one session and is
            # rewritten each time; the container is where they keep living, and
            # it goes through the shared writer rather than growing a third
            # copy of the `bi4_bur` layout.
            try:
                write_container(
                    raw_path,
                    frame,
                    parameters=self.workflow_context.to_payload(),
                )
            except Exception as exc:
                chisurf.logging.warning(f"Could not write the container for {raw_path}: {exc}")

        payload = self.workflow_context.to_payload()
        payload["raw_files"] = [str(path) for path in raw_files]
        (output_folder / "burst_analysis_handoff.json").write_text(
            json.dumps(payload, indent=2, default=str)
        )
        return output_folder

    def burst_sources(self) -> list[Path]:
        """Return the burst tables this workflow has produced, however stored.

        A burst search over a `.pto` keeps its bursts **inside the measurement**
        and writes no ``.bur`` at all — the ordinary case here, since step 2
        converts every measurement into a container. So a step that reads only
        ``bur_files`` sees nothing after a perfectly successful run.

        Both shapes come back as paths: a loose ``.bur``, or a container run
        addressed like a folder (``m000.pto/sliding_window_All 0.1500#60``),
        which every burst reader in ChiSurf understands.
        """
        if self.workflow_context.bur_files:
            return list(self.workflow_context.bur_files)
        folder = self.workflow_context.burst_folder
        if folder is None:
            return []
        from chisurf.core.fio.fluorescence import burst_tree

        if not burst_tree.is_container_path(folder):
            return []
        if folder.suffix.lower() != burst_tree.SUFFIX:
            return [folder]  # the path already names one run
        try:
            runs = burst_tree.list_runs(folder)
        except Exception as exc:
            logger.warning(f"ALEX Suite: could not list the runs of {folder} — {exc}")
            return []
        if not runs:
            return []
        # Newest last -- but newest is not automatically *usable*. A container
        # accumulates runs, and a search made before the detector definitions
        # reached the step writes a table with no per-detector split at all:
        # nine columns of burst geometry and nothing that can be called I_DD.
        # Handing that to accurate FRET or the E-S step produces "the donor
        # channel is not mapped", which reads like a mapping bug and is really
        # the wrong run. So: the newest run whose columns *map*, and only if
        # none of them do, the newest run there is.
        from chisurf.core.fluorescence.burst.table import maps_fret_channels

        for run in reversed(runs):
            candidate = folder / run
            if maps_fret_channels(candidate):
                if run != runs[-1]:
                    logger.info(
                        f"burst analysis: using the run '{run}' — the newer "
                        f"'{runs[-1]}' has no per-detector columns (it was "
                        "searched without detector definitions)."
                    )
                return [candidate]
        return [folder / runs[-1]]

    def analysis_path(self) -> Path | None:
        """The burst analysis a folder-taking tool should read.

        The burst folder as it stands, except when it is a `.pto` container:
        a container holds one analysis *per run*, and the tools read a run, not
        the file. Returns the newest run in that case.
        """
        folder = self.workflow_context.burst_folder
        if folder is None:
            return None
        from chisurf.core.fio.fluorescence import burst_tree

        if folder.suffix.lower() != burst_tree.SUFFIX:
            return folder
        sources = self.burst_sources()
        return sources[0] if sources else folder

    def _apply_context_to_downstream(self) -> None:
        """Apply current workflow context to every loaded panel but the source.

        Driven by what is *loaded*, not by a hard-coded role list: a subclass
        that adds a step used to have to remember to name it here too, and a
        role missing from that list silently never received the burst folder.
        ``data`` is excluded because it is where the context comes from.
        """
        for role, widget in self._workflow_panels.items():
            if role == "data" or widget is None:
                continue
            self._apply_context_to_panel(role, widget)

    def _apply_context_to_panel(self, role: str, widget: QtWidgets.QWidget) -> None:
        """Apply current workflow context to one panel."""
        if role == "selection":
            self._apply_channels_to_burst_selection(widget)
        elif role == "fusion":
            self._apply_context_to_fusion(widget)
        elif role == "bva":
            self._apply_context_to_bva(widget)
        elif role == "two_cde":
            self._apply_context_to_2cde(widget)
        elif role in ("mle", "segment_mle"):
            self._apply_context_to_mle(widget)
        elif role == "h2mm":
            self._apply_context_to_h2mm(widget)
        elif role == "browser":
            self._apply_context_to_browser(widget)
        elif role == "burst_fcs":
            self._apply_context_to_burst_fcs(widget)
        elif role == "burst_gs":
            self._apply_context_to_burst_gs(widget)
        elif role == "accurate_fret":
            self._apply_context_to_accurate_fret(widget)
        elif role == "background":
            self._apply_context_to_background(widget)
        elif role == "irf_bg":
            self._apply_context_to_irf_bg(widget)

    def _apply_channels_to_burst_selection(self, widget: QtWidgets.QWidget) -> None:
        """Use step-1 definitions in Burst Selection."""
        raw_files = self.workflow_context.raw_files
        if raw_files and not getattr(widget, "_file_paths", []):
            try:
                widget._add_paths(raw_files)
            except Exception:
                pass
        settings = self.workflow_context.channel_settings
        if not settings:
            return
        try:
            widget._apply_custom_detector_settings(
                windows=settings.get("windows", {}),
                detectors=settings.get("detectors", {}),
                tttr_reading=settings.get("tttr_reading", {}),
            )
        except Exception:
            wizard = getattr(widget, "wizard", None)
            if wizard is not None:
                wizard.windows = settings.get("windows", {})
                wizard.detectors = settings.get("detectors", {})

    def _apply_context_to_fusion(self, widget: QtWidgets.QWidget) -> None:
        """Hand the optional fusion step the burst folder and the detectors.

        The folder is *not* re-applied once the step has written its own output
        and the workflow has adopted it: the context then holds the fused folder,
        and pushing that back into the step would point it at its own result —
        so returning to the step, or any later context refresh, would quietly
        line up a fusion of an already-fused folder.
        """
        settings = self.workflow_context.channel_settings
        if settings:
            try:
                widget.set_channel_settings(settings)
            except Exception:
                pass
        # The step announces a written folder; the workflow adopts it so every
        # later step reads the fused bursts instead of the original ones.
        model = getattr(widget, "model", None)
        if model is not None and getattr(model, "folder_written", None) is None:
            model.folder_written = self._on_fused_folder
        folder = self.workflow_context.burst_folder
        if folder is None:
            return
        written = getattr(widget, "output_folder", lambda: "")()
        if str(folder) != str(written):
            try:
                widget.set_folder(str(folder))
            except Exception:
                pass

    def _on_fused_folder(self, folder: str) -> None:
        """Adopt a fused burst folder as the folder the later steps analyse."""
        path = Path(folder)
        if not path.is_dir():
            return
        self._fusion_source = self.workflow_context.burst_folder
        self._fused_folder = path
        self.workflow_context.burst_folder = path
        self.workflow_context.bur_files = sorted(path.glob("**/*.bur"))
        self._apply_context_to_downstream()

    def _apply_context_to_bva(self, widget: QtWidgets.QWidget) -> None:
        """Use upstream burst folder and channels in BVA."""
        # Applying context touches the detector table, the donor/acceptor combos and
        # the folder -- each of which fires BVA's ``_on_param_changed``. Suspend
        # auto-recompute across the batch so switching to BVA triggers a single
        # read/compute/plot instead of several.
        suspend = getattr(widget, "suspend_recompute", None)
        ctx = suspend() if callable(suspend) else contextlib.nullcontext()
        with ctx:
            settings = self.workflow_context.channel_settings
            detector_page = getattr(widget, "detector_page", None)
            if settings and detector_page is not None:
                try:
                    detector_page.load_data_into_tables(settings)
                    widget._refresh_detector_combos()
                except Exception:
                    pass
            analysis = self.analysis_path()
            if analysis is not None:
                try:
                    widget._set_folder(str(analysis))
                except Exception:
                    pass

    def _apply_context_to_2cde(self, widget: QtWidgets.QWidget) -> None:
        """Use the upstream burst analysis folder in the 2CDE panel.

        The 2CDE tool reads a burstwise analysis folder (BUR/BST files); like BVA it
        should adopt the folder produced upstream instead of asking the user to pick
        it again. ``set_folder`` only fills the folder field (it does not auto-run),
        so this is a cheap, side-effect-free hand-off.
        """
        folder = self.analysis_path()
        set_folder = getattr(widget, "set_folder", None)
        if folder is not None and callable(set_folder):
            try:
                set_folder(str(folder))
            except Exception:
                pass

    def _apply_context_to_h2mm(self, widget: QtWidgets.QWidget) -> None:
        """Use upstream burst folder and channels in H2MM."""
        settings = self.workflow_context.channel_settings
        detector_page = getattr(widget, "detector_page", None)
        if settings and detector_page is not None:
            try:
                detector_page.load_data_into_tables(settings)
                widget._refresh_detector_combos()
            except Exception:
                pass
        analysis = self.analysis_path()
        if analysis is not None:
            try:
                widget._set_folder(str(analysis))
            except Exception:
                pass

    def _apply_context_to_mle(self, widget: QtWidgets.QWidget) -> None:
        """Use upstream burst files and channels in either MLE step."""
        # The embedded panel is the wizard's central widget (see _burst_mle); the
        # wizard that owns burst_files_list/channel_definer/etc. hangs off it.
        widget = getattr(widget, "_mle_wizard", widget)
        settings = self.workflow_context.channel_settings
        channel_definer = getattr(widget, "channel_definer", None)
        if settings and channel_definer is not None:
            try:
                channel_definer.load_data_into_tables(settings)
                widget._init_channels_from_wizard()
            except Exception:
                pass
        file_list = getattr(widget, "burst_files_list", None)
        # ``burst_files_list`` is the unified PathListWidget-backed file list (via
        # the burst-MLE ``FileListWidget`` factory), whose public API is ``paths()``
        # -- it has no QListWidget ``count()``.
        if (
            self.workflow_context.bur_files
            and file_list is not None
            and len(file_list.paths()) == 0
        ):
            for path in self.workflow_context.bur_files:
                file_list.add_file(str(path))
            # A real drop fires the list's file_added_callback (load_burst_data),
            # which reads the burst analysis AND enables the IRF/background drop
            # lists. add_file() bypasses that callback, so prepopulated burst
            # files must call it explicitly -- otherwise the IRF/BG lists stay
            # setAcceptDrops(False) and silently reject every drop.
            try:
                widget.load_burst_data()
            except Exception:
                pass
            try:
                widget.update_burst_files()
            except Exception:
                pass
        # Apply any IRF/background patterns captured from the IRF & Background step.
        if self.workflow_context.irf_background_patterns:
            self._apply_irf_bg_to_mle_widget(widget, self.workflow_context.irf_background_patterns)

    def _apply_context_to_irf_bg(self, widget: QtWidgets.QWidget) -> None:
        """Use selected raw files and channel setup in the IRF & Background tool."""
        model = getattr(widget, "model", None)
        if model is None:
            return
        settings = self.workflow_context.channel_settings
        page = getattr(model, "detector_wizard_page", None)
        if settings and page is not None:
            try:
                page.load_data_into_tables(settings)
            except Exception:
                pass
        if self.workflow_context.raw_files and not getattr(model, "files", None):
            try:
                model.add_files([str(path) for path in self.workflow_context.raw_files])
            except Exception:
                pass

    def apply_irf_background_to_mle(self, patterns: dict[str, Any]) -> int:
        """Feed non-burst IRF/background patterns to the MLE panel (workflow handoff).

        Called by the IRF & Background tool's "Send to MLE" action. The patterns
        are stored on the workflow context and applied to *both* MLE panels — the
        burst-level fit and the segment-level one are the same fit at two grains
        and must never disagree about the IRF — now (for whichever are loaded)
        and again whenever a panel is (re)bound. Returns the number of detectors
        applied.
        """
        self.workflow_context.irf_background_patterns = dict(patterns or {})
        applied = 0
        for role in ("mle", "segment_mle"):
            panel = self._workflow_panels.get(role)
            if panel is not None:
                applied = max(applied, self._apply_irf_bg_to_mle_widget(panel, patterns))
        return applied or len(patterns or {})

    @staticmethod
    def _apply_irf_bg_to_mle_widget(mle: QtWidgets.QWidget, patterns: dict[str, Any]) -> int:
        """Inject non-burst IRF/background patterns into the MLE wizard, per detector.

        The MLE wizard keeps its IRF/background per detector in a state cache,
        ``channel_settings[det]['irf'|'bg']`` — that cache is what the fit reads
        (and what ``_apply_ui_state`` restores into ``irf_np``/``bg_np`` on every
        detector switch). Writing only the transient ``irf_np``/``bg_np`` therefore
        lasted until the first channel change, then got overwritten with the
        detector's empty cached arrays — which is why "Send to MLE" appeared to do
        nothing. Write BOTH: the live arrays for the current view and the state
        cache so the patterns survive detector switches and reach the fit.
        """
        import numpy as np

        irf_np = getattr(mle, "irf_np", None)
        bg_np = getattr(mle, "bg_np", None)
        if irf_np is None or bg_np is None:
            return 0
        channel_settings = getattr(mle, "channel_settings", None)
        ensure_state = getattr(mle, "_ensure_channel_state", None)
        count = 0
        for det, pat in (patterns or {}).items():
            try:
                irf = np.asarray(pat["irf"], dtype=float)
                bg = np.asarray(pat["bg"], dtype=float)
            except Exception:
                continue
            irf_np[det] = irf
            bg_np[det] = bg
            # Persist into the per-detector state cache so a later detector
            # switch (which restores irf_np/bg_np from here) and the fit both
            # see these arrays rather than empty defaults.
            if isinstance(channel_settings, dict):
                if callable(ensure_state):
                    try:
                        ensure_state(det)
                    except Exception:
                        pass
                st = channel_settings.setdefault(det, {})
                st["irf"] = irf
                st["bg"] = bg
            count += 1
        # Rebuild the fit with the new IRF/background and refresh the display.
        try:
            mle._fit = None
        except Exception:
            pass
        for name in ("update_scatter_count_rate_ui", "update_decay_of_detector", "update_fit"):
            fn = getattr(mle, name, None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
        return count

    def _apply_context_to_browser(self, widget: QtWidgets.QWidget) -> None:
        """Load upstream burst results in Burst Browser."""
        analysis = self.analysis_path()
        if analysis is None or getattr(widget, "table", None) is not None:
            return
        try:
            widget.load_folder(analysis)
        except Exception:
            pass

    def _apply_context_to_burst_fcs(self, widget: QtWidgets.QWidget) -> None:
        """Put the burst files this workflow produced into the FCS file list.

        The correlator takes burst folders *or* BUR/BST files, and its list
        expands a folder itself — so the folder is the smaller, more faithful
        hand-off: it keeps the panel pointing at the analysis rather than at a
        snapshot of its files.
        """
        folder = self.workflow_context.burst_folder
        file_list = getattr(widget, "file_list", None)
        if folder is None or file_list is None:
            return
        try:
            if not file_list.checked_paths():
                file_list.add_paths([str(folder)])
        except Exception:
            pass

    def _apply_context_to_burst_gs(self, widget: QtWidgets.QWidget) -> None:
        """Give photon-by-photon kinetics the .bur files from upstream."""
        model = getattr(widget, "model", None)
        if model is None or not self.workflow_context.bur_files:
            return
        if getattr(model, "bur_files", None):
            return  # the user already chose files here
        try:
            model.bur_files = [str(path) for path in self.workflow_context.bur_files]
            model.notify("changed")
        except Exception:
            pass

    def _apply_context_to_accurate_fret(self, widget: QtWidgets.QWidget) -> None:
        """Give accurate-FRET the upstream detector setup and one burst table.

        The calibration reads a burst *table*, and a ``.bur`` is one — so the
        first burst file is what this step would otherwise ask the user to pick.
        The setup goes first: its named windows are what lets the panel recognise
        the table's channel columns, so it has to be in place before the table is
        read, and it is also what names the detectors for the optical prior.
        """
        model = getattr(widget, "model", None)
        if model is None:
            return
        self._apply_setup_to_accurate_fret(model)
        sources = self.burst_sources()
        if not sources:
            return
        if getattr(model, "filename", ""):
            return  # a table is already loaded here
        try:
            model.set_filename(str(sources[0]))
        except Exception:
            pass

    def _apply_setup_to_accurate_fret(self, model: Any) -> None:
        """Hand the workflow's detector setup to the accurate-FRET model.

        Uses the panel's own setup hook — the same payload its setup selector
        sends — rather than a detector table, because this panel consumes the
        window *names*, not the routing channels.

        Like the BVA and H2MM appliers, the workflow's setup wins: the panel's
        selector otherwise restores whatever setup was last used anywhere, which
        is not the one step 2 chose. Applying is idempotent, so re-propagating an
        unchanged setup does not re-map columns the user has since corrected.
        """
        settings = self.workflow_context.channel_settings
        payload = {
            "name": self.workflow_context.setup_name,
            "detectors": dict(settings.get("detectors") or {}),
        }
        if not payload["name"] and not payload["detectors"]:
            return
        current = {
            "name": str(getattr(model, "setup_name", "") or ""),
            "detectors": dict(getattr(model, "detectors", None) or {}),
        }
        if payload == current:
            return
        apply_setup = getattr(model, "apply_setup_settings", None)
        if not callable(apply_setup):
            return
        try:
            apply_setup(payload)
        except Exception:
            pass

    def _apply_context_to_background(self, widget: QtWidgets.QWidget) -> None:
        """Use selected raw files and channel setup in Background Estimation."""
        settings = self.workflow_context.channel_settings
        page = getattr(widget, "detector_wizard_page", None)
        if settings and page is not None:
            try:
                page.load_data_into_tables(settings)
            except Exception:
                pass
        if self.workflow_context.raw_files and not getattr(widget, "tttr_files", []):
            try:
                widget._add_tttr_files([str(path) for path in self.workflow_context.raw_files])
            except Exception:
                pass
        self._populate_background(widget)

    def _populate_background(self, widget: QtWidgets.QWidget) -> None:
        """Compute the inter-photon-time distribution on arrival.

        The step arrived showing an empty plot and a fit window of zero, because
        pushing the files and the detectors is not the same as reading them and
        nothing else ran: the panel waited for its own button on data it already
        had. Nothing here asks a question the data cannot answer, so it computes
        as soon as it can, like the burst-search preview does.

        The read goes through the staging cache, so arriving from the burst
        search costs no second read of the measurement. It is skipped when there
        is already a result, so returning to the step does not recompute, and
        when the panel cannot estimate yet (no files, no detectors) -- that is
        the panel's own message to show, not an error.
        """
        model = getattr(widget, "model", None)
        if model is None or getattr(model, "diagnostics", None):
            return
        if getattr(model, "can_estimate", lambda: "not ready")() is not None:
            return
        try:
            model.estimate()
        except Exception:
            logger.debug("background: could not populate on arrival", exc_info=True)
