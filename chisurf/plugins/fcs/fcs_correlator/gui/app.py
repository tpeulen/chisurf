"""The native FCS workflow: channel definitions → files → filter → correlator → merger behind a rail.

The ribbon's **FCS** entry. The other FCS tools are ribbon entries of their own (in emtk every tool is its own dock);
the one this workflow reaches is the fFCS Filter Calculator, which **Filter Calc...** opens with the workflow's files
(the ``fcs_correlator_files`` hand-off its manifest declares).

Built on :class:`chisurf.emtk.tool_hub.ToolHubApp`. The steps are emtk apps (:mod:`.steps`, the channel-preset and
merger apps of their plugins); what one step hands the next is :class:`..workflow.FcsWorkflow`'s, applied each time a
step is opened.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from emtk.i18n import tr

from chisurf.emtk.tool_hub import ToolHubApp

from ..correlator_model import CorrelatorSettingsModel
from ..filter_model import FilterSettingsModel
from ..workflow import FcsWorkflow
from . import handoffs
from .handoffs import FILES_HANDOFF, FILTER_CALCULATOR
from .steps import CorrelatorStepApp, FilesStepApp, FilterStepApp

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
PLUGINS = PLUGIN.parents[1]

STEP_ROLES = ("channel_def", "files", "filter", "correlator", "merger")


class FcsHubApp(ToolHubApp):
    """The FCS correlator workflow; the steps share one :class:`FcsWorkflow`."""

    def __init__(
        self,
        title: str = "FCS",
        *,
        help_resource: Path | None = None,
        guide: Path | None = None,
    ) -> None:
        self.workflow = FcsWorkflow()
        self.filter_model = FilterSettingsModel()
        self.correlator_model = CorrelatorSettingsModel()
        self._setup_seen: str | None = None
        steps: list[dict[str, Any]] = [
            {"name": "Correlator", "separator": True},
            {
                "name": "1. Channel Definitions",
                "icon": "🎚️",
                "role": "channel_def",
                "plugin": "fcs/fcs_channel_preset",
                "description": "Choose the detector setup and its correlation channel pairs (ACF/CCF presets).",
            },
            {
                "name": "2. Files & Steps",
                "icon": "📂",
                "role": "files",
                "factory": self._make_files,
                "help": str(PLUGIN / "README.md"),
                "description": "Add TTTR files and choose the optional steps (photon filter, FCS merger).",
            },
            {
                "name": "3. Photon / Burst Filter",
                "icon": "🔍",
                "role": "filter",
                "factory": self._make_filter,
                "description": "Filter photons by count rate or burst selection before correlating.",
            },
            {
                "name": "4. Correlator",
                "icon": "📊",
                "role": "correlator",
                "factory": self._make_correlator,
                "description": "Configure channels / micro-time windows and compute the correlation.",
            },
            {
                "name": "5. FCS Merger",
                "icon": "🔗",
                "role": "merger",
                "plugin": "fcs/fcs_merger",
                "description": "Screen and merge the computed correlation curves.",
            },
        ]
        super().__init__(
            title,
            steps,
            help_resource=help_resource or PLUGIN / "help.md",
            guide=guide or PLUGIN / "guide.json",
            initial="files",
            steps=True,
        )

    # step factories (the steps the workflow owns the models of)
    def _make_files(self):
        from chisurf.plugins.tttr.workspace_io import NamedWorkspaceInput

        files = FilesStepApp(
            on_change=self._files_changed,
            on_used=self.tour.notify_used,
            regions=self.workflow.regions,
            reader=self.workflow.read_for_trace,
        )
        files.workspace_input = NamedWorkspaceInput("fcs_correlator", "files", self, height=60)
        files.workspace_input.workspace_input_on_used = lambda _key: self.tour.notify_used(
            "workspace_input_rows"
        )
        return files

    def _make_filter(self):
        return FilterStepApp(self.filter_model, on_used=self.tour.notify_used)

    def _make_correlator(self):
        from chisurf.plugins.tttr.workspace_io import NamedWorkspaceInput

        correlator = CorrelatorStepApp(
            self.correlator_model,
            open_tool=self._open_tool,
            on_used=self.tour.notify_used,
            tool_available=handoffs.available,
        )
        #: Lifetime filters come from the Datasets workspace (a setup row).
        correlator.filter_input = NamedWorkspaceInput("fcs_correlator", "filters", self, height=72)
        correlator.filter_input.workspace_input_on_used = lambda _key: self.tour.notify_used(
            "load_filters"
        )
        return correlator

    def files_payload(self) -> dict[str, Any]:
        """What the Filter Calculator gets: the checked files (folders expanded) and the micro-time binning, so its
        filters use the micro-time axis of the correlation."""
        self._files_changed()
        return {
            "files": [str(p) for p in self.workflow.expanded_files()],
            "microtime_binning": int(self.correlator_model.microtime_binning or 1),
        }

    def _open_tool(self, plugin_id: str) -> None:
        """Open *plugin_id* (the Filter Calculator) as its own dock, handing it the workflow's files."""
        try:
            handoffs.open_with_files(self.files_payload(), plugin_id)
        except (handoffs.HandoffError, OSError) as exc:
            child = self.children.get("correlator")
            if child is not None:
                child.filter_status = tr("Filter Calc could not open: {error}").format(error=exc)
        self.wants_frame = True

    # the workflow
    @property
    def files_step(self) -> FilesStepApp:
        return self.ensure_child("files")

    def _files_changed(self) -> None:
        files = self.children.get("files")
        if files is not None:
            self.workflow.set_files(
                files.checked_files, files.use_filter, files.use_merger, per_file=files.per_file
            )
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

    def requires(self, role: str) -> tuple[str, ...]:
        # Opening a step reads the channel step's setup (refresh_setup): build both off the first frame.
        return ("channel_def", role) if role in STEP_ROLES and role != "channel_def" else (role,)

    def panel_enabled(self, role: str) -> bool:
        files = self.children.get("files")
        if role == "filter":
            return bool(files and files.use_filter and files.filter_allowed)
        if role == "merger":
            return bool(files is None or files.use_merger)
        return True

    def disabled_reason(self, role: str) -> str:
        return tr("(switched off in Files & Steps)")

    def on_select(self, role: str, child) -> None:
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
                child.set_correlations(
                    correlations,
                    folder,
                    labels=self.workflow.merger_labels(correlations),
                    provenance=self.workflow.merger_provenance(self.correlator_model),
                )
            elif folder is not None and Path(folder).is_dir():
                child.model.folder = str(folder)
                child.load_folder(folder)


def receive_files(app: FcsHubApp, payload: dict[str, Any]) -> bool:
    """The workspace's photon streams (``accepts[].from_workspace``): added to the Files step and
    ticked, read through their container when they are one's members."""
    from chisurf.core.plugin.workspace_input import read_address

    files = app.ensure_child("files")
    if files is None:
        return False
    added = files.add_paths([read_address(str(a)) for a in payload.get("files") or []])
    datasets = [str(d) for d in payload.get("datasets") or [] if d]
    if datasets:
        files.source_datasets = datasets
    app.goto_role("files") if hasattr(app, "goto_role") else None
    return added > 0


def receive_filters(app: FcsHubApp, payload: dict[str, Any]) -> bool:
    """Lifetime filters picked in the workspace (a setup row): loaded into the Correlator step,
    which switches to species-resolved correlation."""
    from chisurf.core.plugin.workspace_input import read_address

    address = payload.get("filters")
    correlator = app.ensure_child("correlator")
    if not address or correlator is None:
        return False
    correlator.load_filters(read_address(str(address)))
    return correlator.model.filter_mode


def make_app(**_kwargs) -> FcsHubApp:
    """The FCS workflow (the ribbon's ``FCS`` entry)."""
    from chisurf.emtk.i18n import install

    install()
    return FcsHubApp()


__all__ = ["FILES_HANDOFF", "FILTER_CALCULATOR", "FcsHubApp", "make_app"]
