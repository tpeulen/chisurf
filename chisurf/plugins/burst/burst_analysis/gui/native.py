"""The native Burst Analysis hub: the burst workflow's steps and side tools behind one rail, drawn with emtk.

Built on :class:`chisurf.emtk.tool_hub.ToolHubApp` (rail, search, Back / Next / fast-forward, help, tour, input
routing). Each step is the emtk app of its own plugin, made on first selection and kept: the setup and data steps
(:mod:`.setup_selection_app`, :mod:`.data_selection_app`), Burst Selection's native app, and the native apps the
child plugins name in ``entrypoints.emtk``. Burst MLE appears twice, once per burst and once per burst *and* H2MM
state (the same app with ``split_by_state``).

What one step hands the next is a :class:`..workflow_context.BurstWorkflowContext`, applied to a step each time it
is opened and to every open step when the setup, the files or the bursts change -- the hand-off of the legacy Qt
shell (``gui/tool.py``), one method per step. Nothing here imports Qt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from chisurf.emtk.tool_hub import ToolHubApp

from ..workflow_context import (
    BurstWorkflowContext,
    analysis_path,
    burst_sources,
    folder_from_result,
    materialize_handoff,
)

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent

#: The rail: step order, names and roles of the legacy ``BURST_PANELS``; ``plugin`` names the child's folder.
STEPS: list[dict[str, Any]] = [
    {"name": "Pipeline steps", "separator": True},
    {
        "name": "0. Setup Selection",
        "icon": "⚙️",
        "role": "setup",
        "help": str(HERE / "setup_selection_help.md"),
        "description": "Select detector setup, channel routing, and excitation windows.",
    },
    {
        "name": "1. Data Selection",
        "icon": "📂",
        "role": "data",
        "help": str(HERE / "data_selection_help.md"),
        "description": "Select raw TTTR files used by all later steps.",
    },
    {
        "name": "2. Burst Selection",
        "icon": "🔍",
        "role": "selection",
        "plugin": "burst/burst_selection",
        "description": "Define detector channels and find/filter bursts from TTTR data.",
    },
    {
        "name": "3. Burst Fusion (optional)",
        "icon": "🔗",
        "role": "fusion",
        "plugin": "burst/burst_fusion",
        # Walking the pipeline must not fuse: only the step's own Fuse button hands a fused folder downstream.
        "optional": True,
        "description": "Optional: merge bursts the same molecule produced (recurrence P_same) into a new burst "
        "folder the later steps then use.",
    },
    {
        "name": "4. Burst BVA",
        "icon": "📊",
        "role": "bva",
        "plugin": "burst/burst_bva",
        "description": "Burst-level feature: burst variance analysis of the selected bursts.",
    },
    {
        "name": "5. Burst 2CDE",
        "icon": "📊",
        "role": "two_cde",
        "plugin": "burst/burst_2cde",
        "description": "Burst-level feature: the FRET-2CDE / ALEX-2CDE burst-dynamics filter.",
    },
    {
        "name": "6. Burst MLE",
        "icon": "🎯",
        "role": "mle",
        "plugin": "burst/burst_mle_analysis",
        "description": "Burst-level feature: one maximum-likelihood lifetime per burst.",
    },
    {
        "name": "7. Burst segmentation (H2MM)",
        "icon": "🔀",
        "role": "h2mm",
        "plugin": "burst/burst_h2mm",
        "description": "Cut each burst into segments: photon-by-photon HMM (H2MM) assigns every photon a state.",
    },
    {
        "name": "8. Burst segment MLE",
        "icon": "🎯",
        "role": "segment_mle",
        "plugin": "burst/burst_mle_analysis",
        "description": "Segment-level: the same MLE fit once per burst and H2MM state, written as Tau S0 / "
        "Tau S1 ... beside the burst-level lifetime.",
    },
    {"name": "Side tools", "separator": True},
    {
        "name": "Browser",
        "icon": "📋",
        "role": "browser",
        "plugin": "burst/burst_browser",
        "description": "Inspect the current burst workflow result.",
    },
    {
        "name": "Accurate FRET",
        "icon": "🎯",
        "role": "accurate_fret",
        "plugin": "burst/accurate_fret",
        "description": "Correction factors (alpha/beta/gamma/delta) for the bursts this workflow produced.",
    },
    {
        "name": "Burst FCS",
        "icon": "📊",
        "role": "burst_fcs",
        "plugin": "burst/burst_fcs_correlator",
        "description": "Correlate the photons of the selected bursts.",
    },
    {
        "name": "Kinetics (GS)",
        "icon": "🔀",
        "role": "burst_gs",
        "plugin": "burst/burst_gs",
        "description": "Photon-by-photon kinetics (Gopich-Szabo) on the selected bursts.",
    },
    {
        "name": "Background",
        "icon": "🌙",
        "role": "background",
        "plugin": "burst/burst_background",
        "description": "Estimate background using the selected data and channel setup.",
    },
    {
        "name": "IRF & Background",
        "icon": "✨",
        "role": "irf_bg",
        "plugin": "burst/burst_irf_bg",
        "description": "Extract a per-detector IRF and background from the non-burst photons and feed them to "
        "both MLE steps.",
    },
]

#: The steps whose detector editor takes the workflow's setup.
MLE_ROLES = ("mle", "segment_mle")


def _signature(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


class BurstAnalysisHubApp(ToolHubApp):
    """The burst workflow on the shared native hub; the steps share one :class:`BurstWorkflowContext`."""

    def __init__(self, title: str = "Burst Analysis", steps: list[dict] | None = None) -> None:
        self.context = BurstWorkflowContext()
        self._fusion_source: Path | None = None
        self._fused_folder: Path | None = None
        #: ``{(role, what): signature}`` of what each step was last handed, so an unchanged hand-off is not
        #: re-applied (it would reset what the user has since changed in that step).
        self._handed: dict[tuple[str, str], str] = {}
        factories = {
            "setup": self._make_setup,
            "data": self._make_data,
            "selection": self._make_selection,
            "mle": lambda: self._make_mle(split_by_state=False),
            "segment_mle": lambda: self._make_mle(split_by_state=True),
            "irf_bg": self._make_irf_bg,
        }
        panels = [
            {**p, "factory": factories[p["role"]]} if p.get("role") in factories else dict(p)
            for p in (STEPS if steps is None else steps)
        ]
        super().__init__(
            title, panels, help_resource=HERE / "help.md", guide=HERE / "guide.json", initial="setup"
        )
        self._base_names = {p["role"]: p["name"] for p in self.tools}

    # -- the step apps the hub owns the wiring of ------------------------------------------------------- #
    def _make_setup(self):
        from .setup_selection_app import BurstSetupSelectionApp

        app = BurstSetupSelectionApp(
            on_changed=lambda _settings: self._setup_changed(),
            on_proceed=lambda: self.select("data"),
        )
        app.page.on_used = self._used(app.tour)
        return app

    def _make_data(self):
        from .data_selection_app import BurstDataSelectionApp, BurstDataSelectionModel

        model = BurstDataSelectionModel(on_change=self._data_changed)
        return BurstDataSelectionApp(model, on_proceed=lambda: self.select("selection"))

    def _make_selection(self):
        from chisurf.plugins.burst.burst_selection.gui.native import create_app

        return create_app(on_run_done=self._selection_done)

    def _make_mle(self, split_by_state: bool):
        from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

        app = create_app()
        app.model.split_by_state = bool(split_by_state)
        return app

    def _make_irf_bg(self):
        from chisurf.plugins.burst.burst_irf_bg.gui.app import create_app

        return create_app(mle_receiver=self.apply_irf_background_to_mle)

    def _used(self, child_tour):
        """A step's control was used: its own tour and the hub's (whose steps may wait for it) both hear of it."""

        def notify(name: str) -> None:
            child_tour.notify_used(name)
            self.tour.notify_used(name)

        return notify

    # -- context from the source steps ------------------------------------------------------------------- #
    def _setup_changed(self) -> None:
        setup = self.children.get("setup")
        if setup is None:
            return
        data = setup.selected_setup_data()
        if not data:
            return
        self.context.channel_settings = data
        self.context.setup_name = setup.selected_setup_name()
        self._apply_downstream(skip=("setup", "data"))
        self.wants_frame = True

    def _data_changed(self) -> None:
        data = self.children.get("data")
        if data is None:
            return
        self.context.raw_files = list(data.model.paths())
        self.context.raw_mmfdb_artifacts = data.model.mmfdb_payload()
        self._apply_downstream(skip=("setup", "data"))
        self.wants_frame = True

    def _selection_done(self, model) -> None:
        """Burst Selection finished a run: its output becomes the bursts every later step reads."""
        if model.files:
            self.context.raw_files = list(model.files)
        result = model.result or {}
        artifacts = result.get("mmfdb_artifacts") or {}
        if artifacts:
            self.context.mmfdb_artifacts = dict(artifacts)
        folder = folder_from_result(result) or materialize_handoff(self.context, model.frames_by_file)
        # A fresh burst search supersedes any fusion of the previous one.
        self._fusion_source = self._fused_folder = None
        if folder is not None:
            self.context.set_burst_folder(folder)
            self.status = f"Bursts for the later steps: {folder}"
        self._apply_downstream(skip=("data", "selection"))
        self.wants_frame = True

    def _on_fused_folder(self, folder: str) -> None:
        """Adopt a fused burst folder as the folder the later steps analyse."""
        path = Path(folder)
        if not path.is_dir():
            return
        self._fusion_source = self.context.burst_folder
        self._fused_folder = path
        self.context.set_burst_folder(path)
        self._apply_downstream(skip=("data", "selection", "fusion"))
        self.status = f"Fused bursts adopted by the later steps: {path}"
        self.wants_frame = True

    def apply_irf_background_to_mle(self, patterns: dict[str, Any]) -> int:
        """IRF & Background's *Send to MLE*: the patterns go to both MLE steps (now, and when they are opened)."""
        self.context.irf_background_patterns = dict(patterns or {})
        applied = 0
        for role in MLE_ROLES:
            child = self.children.get(role)
            if child is not None:
                applied = max(applied, self._patterns_to_mle(child, self.context.irf_background_patterns))
        return applied or len(patterns or {})

    # -- the hand-off ------------------------------------------------------------------------------------ #
    def _changed(self, role: str, what: str, value: Any) -> bool:
        """Whether *value* differs from what *role* was last handed as *what* (and remember it)."""
        sig = _signature(value)
        if self._handed.get((role, what)) == sig:
            return False
        self._handed[(role, what)] = sig
        return True

    def _setup_payload(self) -> dict[str, Any]:
        settings = dict(self.context.channel_settings or {})
        if self.context.setup_name:
            settings["setup_name"] = self.context.setup_name
        return settings

    def _editor_to(self, role: str, editor, settings: dict[str, Any]) -> None:
        """Show the workflow's setup in a step's own detector editor (its change callback updates the step)."""
        if settings.get("detectors") and editor is not None and self._changed(role, "setup", settings):
            editor.load_definition(settings)

    def _apply_downstream(self, skip: tuple[str, ...] = ()) -> None:
        """Hand the context to every open step but the ones it came from."""
        for role, child in list(self.children.items()):
            if role in skip:
                continue
            try:
                self.on_select(role, child)
            except Exception as exc:  # noqa: BLE001 - one step's hand-off must not stop the others'
                self.status = f"{role}: {type(exc).__name__}: {exc}"

    def on_select(self, role: str, child) -> None:
        handler = getattr(self, f"_to_{role}", None)
        if callable(handler):
            handler(child)

    def select(self, role: str, retry: bool = False, by_user: bool = True):
        child = super().select(role, retry=retry, by_user=by_user)
        if self.status == "Ready":
            self.status = self._summary_shown = self.summary()
        return child

    def _to_setup(self, child) -> None:
        name = self.context.setup_name
        if name and name != child.selected_setup_name():
            child.select_setup(name)

    def _to_selection(self, child) -> None:
        if self.context.raw_files and not child.model.files:
            child.model.add_paths(self.context.raw_files)
        settings = self._setup_payload()
        if settings.get("detectors") and self._changed("selection", "setup", settings):
            child.apply_setup(settings, self.context.setup_name)

    def _to_fusion(self, child) -> None:
        settings = self.context.channel_settings
        if settings and self._changed("fusion", "setup", settings):
            child.set_channel_settings(settings)
        if child.model.folder_written is None:
            child.model.folder_written = self._on_fused_folder
        folder = self.context.burst_folder
        if folder is not None and str(folder) != str(child.output_folder or ""):
            if self._changed("fusion", "folder", str(folder)):
                child.set_folder(str(folder))

    def _to_bva(self, child) -> None:
        settings = self.context.channel_settings
        if settings and self._changed("bva", "setup", settings):
            child.model.apply_channel_settings(settings)
        folder = analysis_path(self.context)
        if folder is not None and child.controller is not None and child.model.analysis_folder != folder:
            child.controller.set_folder(folder)

    def _to_two_cde(self, child) -> None:
        settings = self.context.channel_settings
        if settings and self._changed("two_cde", "setup", settings):
            child.model.apply_channel_settings(settings)
        folder = analysis_path(self.context)
        if folder is not None and child.model.folder != str(folder):
            child.model.set_folder(str(folder))

    def _to_mle(self, child) -> None:
        role = child_role(self, child)
        self._editor_to(role, child.editor, self._setup_payload())
        if self.context.bur_files and not child.model.session.bur_files:
            child.model.add_files(self.context.bur_files)
        patterns = self.context.irf_background_patterns
        if patterns and self._changed(role, "patterns", id(patterns)):
            self._patterns_to_mle(child, patterns)

    _to_segment_mle = _to_mle

    @staticmethod
    def _patterns_to_mle(child, patterns: dict[str, Any]) -> int:
        """Per-detector IRF / background into an MLE step's session (what its fit reads), then refit."""
        import numpy as np

        session = child.model.session
        count = 0
        for det, pattern in (patterns or {}).items():
            try:
                session.irf_np[det] = np.asarray(pattern["irf"], dtype=float)
                session.bg_np[det] = np.asarray(pattern["bg"], dtype=float)
            except (KeyError, TypeError, ValueError):
                continue
            count += 1
        if count and session.decay is not None:
            try:
                child.model.refit()
            except Exception as exc:  # noqa: BLE001 - the patterns are in place; the step shows why it cannot fit
                child.model.status_text = f"IRF / background received; refit failed: {exc}"
        child.model.notify("patterns")
        return count

    def _to_h2mm(self, child) -> None:
        folder = analysis_path(self.context)
        context = {"channel_settings": self.context.channel_settings}
        if folder is not None:
            context["burst_folder"] = str(folder)
        if self._changed("h2mm", "context", context):
            child.model.apply_workflow_context(context)
        self._editor_to("h2mm", child.editor, self._setup_payload())

    def _to_browser(self, child) -> None:
        folder = analysis_path(self.context)
        if folder is None or child.model.table is not None:
            return
        if child.controller is not None and child.controller.running:
            return
        if self._changed("browser", "folder", str(folder)):
            child.load_folder(folder)

    def _to_burst_fcs(self, child) -> None:
        folder = self.context.burst_folder
        if folder is not None and not child.controller.checked_files():
            child.controller.add_files([str(folder)])

    def _to_burst_gs(self, child) -> None:
        if self.context.bur_files and child.controller is not None and not child.model.bur_files:
            child.controller.add_files([str(p) for p in self.context.bur_files])

    def _to_accurate_fret(self, child) -> None:
        self._editor_to("accurate_fret", child.controller.channel_definition, self._setup_payload())
        sources = burst_sources(self.context)
        if not sources or getattr(child.model, "filename", "") or child.controller.running:
            return
        if Path(sources[0]).is_file() and self._changed("accurate_fret", "table", str(sources[0])):
            child.controller.load(str(sources[0]))

    def _to_background(self, child) -> None:
        controller = child.controller
        if controller is None:
            return
        self._editor_to(child_role(self, child), controller.channel_definition, self._setup_payload())
        if self.context.raw_files and not child.model.files:
            controller.add_files([str(p) for p in self.context.raw_files])
        # Compute on arrival, as the Qt step does: nothing is asked that the data cannot answer.
        if (
            not getattr(child.model, "diagnostics", None)
            and getattr(child.model, "can_estimate", lambda: "not ready")() is None
            and not controller.running
        ):
            controller.run()

    def _to_irf_bg(self, child) -> None:
        controller = child.controller
        if controller is None:
            return
        self._editor_to("irf_bg", controller.channel_definition, self._setup_payload())
        if self.context.raw_files and not child.model.files:
            controller.add_files([str(p) for p in self.context.raw_files])

    # -- the rail ------------------------------------------------------------------------------------------ #
    def badge(self, role: str) -> str:
        """What a rail row shows behind its name: done, how many files, ready to analyse (the Qt shell's badges)."""
        ctx = self.context
        if role == "setup":
            return "✓" if ctx.setup_name else ""
        if role == "data":
            return f"({len(ctx.raw_files)})" if ctx.raw_files else ""
        if role == "selection":
            if ctx.bur_files:
                return f"({len(ctx.bur_files)})"
            return "✓" if ctx.burst_folder else ""
        if role in ("bva", "two_cde", "mle", "h2mm", "segment_mle"):
            return "•" if ctx.burst_folder else ""
        return ""

    def summary(self) -> str:
        """The status line: the setup, the files and the bursts the later steps read."""
        ctx = self.context
        parts = [f"Setup: {ctx.setup_name or '(unsaved)' if ctx.channel_settings else 'none'}"]
        parts.append(f"{len(ctx.raw_files)} TTTR file(s)")
        if ctx.burst_folder is not None:
            parts.append(f"bursts: {ctx.burst_folder.name}")
        return " · ".join(parts)

    def render(self):
        if self.status == getattr(self, "_summary_shown", None) or self.status == "Ready":
            self.status = self._summary_shown = self.summary()
        for panel in self.tools:
            base = self._base_names.get(panel["role"], panel["name"])
            badge = self.badge(panel["role"])
            panel["name"] = f"{base} {badge}" if badge else base
        super().render()


def child_role(hub: BurstAnalysisHubApp, child) -> str:
    """The role a child app is open under."""
    return next((role for role, c in hub.children.items() if c is child), "")


def create_app(**kwargs) -> BurstAnalysisHubApp:
    """Factory named by ``entrypoints.emtk``."""
    from chisurf.emtk.i18n import install

    install()
    return BurstAnalysisHubApp(**kwargs)


make_app = create_app

__all__ = ["STEPS", "BurstAnalysisHubApp", "create_app", "make_app"]
