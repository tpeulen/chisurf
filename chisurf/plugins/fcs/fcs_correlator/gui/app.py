"""The native FCS correlator: the workflow (channel definitions → files → filter → correlator → merger) behind a
rail, as the Qt ``FcsCorrelatorTool``; the FCS hub (``fcs_toolbox``) is this with the FCS tools below it.

Built on :class:`chisurf.emtk.tool_hub.ToolHubApp`. The steps are emtk apps (:mod:`.steps`, the channel-preset and
merger apps of their plugins); what one step hands the next is :class:`..workflow.FcsWorkflow`'s, applied each time a
step is opened.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.emtk.tool_hub import ToolHubApp

from ..correlator_model import CorrelatorSettingsModel
from ..filter_model import FilterSettingsModel
from ..workflow import FcsWorkflow
from .steps import CorrelatorStepApp, FilesStepApp, FilterStepApp

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
PLUGINS = PLUGIN.parents[1]

STEP_ROLES = ("channel_def", "files", "filter", "correlator", "merger")

class FcsHubApp(ToolHubApp):
    """The correlator workflow (+ *tools* below it); the steps share one :class:`FcsWorkflow`."""

    def __init__(self, title: str = "FCS Correlator", tools: list | None = None, *,
                 help_resource: Path | None = None, guide: Path | None = None) -> None:
        self.workflow = FcsWorkflow()
        self.filter_model = FilterSettingsModel()
        self.correlator_model = CorrelatorSettingsModel()
        self._setup_seen: str | None = None
        steps = [
            {"name": "Correlator", "separator": True},
            {"name": "1. Channel Definitions", "icon": "🎚️", "role": "channel_def", "plugin": "fcs/fcs_channel_preset",
             "description": "Choose the detector setup and its correlation channel pairs (ACF/CCF presets)."},
            {"name": "2. Files & Steps", "icon": "📂", "role": "files", "factory": self._make_files,
             "help": str(PLUGIN / "README.md"),
             "description": "Add TTTR files and choose the optional steps (photon filter, FCS merger)."},
            {"name": "3. Photon / Burst Filter", "icon": "🔍", "role": "filter", "factory": self._make_filter,
             "description": "Filter photons by count rate or burst selection before correlating."},
            {"name": "4. Correlator", "icon": "📊", "role": "correlator", "factory": self._make_correlator,
             "description": "Configure channels / micro-time windows and compute the correlation."},
            {"name": "5. FCS Merger", "icon": "🔗", "role": "merger", "plugin": "fcs/fcs_merger",
             "description": "Screen and merge the computed correlation curves."},
        ]
        panels = steps + ([{"name": "Tools", "separator": True}, *tools] if tools else [])
        super().__init__(title, panels, help_resource=help_resource or PLUGIN / "help.md",
                         guide=guide or PLUGIN / "guide.json", initial="files")

    # step factories (the steps the workflow owns the models of)
    def _make_files(self):
        return FilesStepApp(on_change=self._files_changed, on_used=self.tour.notify_used)

    def _make_filter(self):
        return FilterStepApp(self.filter_model, on_used=self.tour.notify_used)

    def _make_correlator(self):
        return CorrelatorStepApp(self.correlator_model, open_tool=self._open_tool, on_used=self.tour.notify_used)

    def _open_tool(self, role: str) -> None:
        if any(p["role"] == role for p in self.tools):
            self.select(role)

    # the workflow
    @property
    def files_step(self) -> FilesStepApp:
        return self.ensure_child("files")

    def _files_changed(self) -> None:
        files = self.children.get("files")
        if files is not None:
            self.workflow.set_files(files.checked_files, files.use_filter, files.use_merger)
        self.wants_frame = True

    def refresh_setup(self) -> None:
        """The channel step's selected setup into the workflow; a new setup drops the filter's photons (they were read
        with the old setup's channels and LUTs), as in Qt."""
        preset = self.ensure_child("channel_def")
        if preset is None:
            return
        name = preset.model.current_setup
        self.workflow.set_setup(name, preset.model._detector_setups)
        if self._setup_seen is not None and name != self._setup_seen:
            self.filter_model.set_tttr_objects({}, [])
        self._setup_seen = name

    def panel_enabled(self, role: str) -> bool:
        files = self.children.get("files")
        if role == "filter":
            return bool(files and files.use_filter and files.filter_allowed)
        if role == "merger":
            return bool(files is None or files.use_merger)
        return True

    def on_select(self, role: str, child) -> None:
        if role == "filter_calc":
            self._hand_to_filter_calc(child)
        if role not in STEP_ROLES:
            return
        self.refresh_setup()
        self._files_changed()
        if role == "filter":
            self.workflow.load_files_into_filter(self.filter_model)
        elif role == "correlator":
            self.workflow.apply_to_correlator(self.correlator_model, self.filter_model)
            if self.correlator_model._tttr is not None:
                child.status = f"{len(self.correlator_model._tttr):,} photons loaded."
        elif role == "merger":
            correlations, folder = self.workflow.merger_input(self.correlator_model)
            if correlations:
                child.set_correlations(correlations, folder)
            elif folder is not None and Path(folder).is_dir():
                child.model.folder = str(folder)
                child.load_folder(folder)


    def _hand_to_filter_calc(self, child) -> None:
        """The Filter Calculator reads the correlator's files as its mixed decay (with the correlator's micro-time
        binning), as the Qt hub does each time it is shown: once, while it has no mixed decay of its own."""
        self._files_changed()
        self.workflow.context.expanded_files = self.workflow.expanded_files()
        self.workflow.context.microtime_binning = int(self.correlator_model.microtime_binning or 1)
        child.workflow_context = lambda: self.workflow.context
        self._calc_pending = bool(self.workflow.context.expanded_files)
        self._hand_pending()

    def _hand_pending(self) -> None:
        """Send the pending hand-over once the calculator is idle (its own first computation runs when it opens, and a
        busy calculator refuses new work)."""
        child = self.children.get("filter_calc")
        if not getattr(self, "_calc_pending", False) or child is None:
            return
        if getattr(getattr(child, "job", None), "running", False):
            self.wants_frame = True
            return
        self._calc_pending = False
        if not getattr(getattr(child, "model", None), "_total_paths", None):
            child.from_correlator()

    def render(self):
        super().render()
        self._hand_pending()


def make_app(**_kwargs) -> FcsHubApp:
    """The correlator workflow alone (the ``FCS Correlator`` entry)."""
    from chisurf.emtk.i18n import install

    install()
    return FcsHubApp()


__all__ = ["FcsHubApp", "make_app"]
