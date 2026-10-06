"""The native ALEX Suite: the old ALEX-Suite program's workflow as one linear pipeline, walked with Next.

Seven numbered steps (setup, files, µs-ALEX alternation, burst search, background, accurate FRET, E–S histogram)
and four side tools (burst properties, titration, BVA, the ALEX-Suite CSV export) behind one rail, drawn with emtk.
The hub is :class:`~chisurf.plugins.burst.burst_analysis.gui.native.BurstAnalysisHubApp` with ALEX's own steps:
the hand-off of the setup, the files and the bursts from step to step (``BurstWorkflowContext``, ``_to_<role>``,
``_apply_downstream``) is Burst Analysis's, so an analysis started here is the same analysis, written to the same
``.pto`` container and companions. What this module adds is what only ALEX has:

* the files step offers a simulated µs-ALEX measurement (:mod:`..demo`) to walk the pipeline on;
* the alternation step converts µs-ALEX data on arrival and hands the converted container and the detected setup
  ("ALEX Suite (auto)") to every later step (:meth:`AlexHubApp.adopt_alex_conversion`);
* Next on Accurate FRET calibrates (α, β, γ, δ from the bursts), and the E–S step opens the bursts in ndX with the
  constants the measurement now stores;
* the titration and the CSV export are seeded with the workflow's bursts and corrections.

So a user gets from files to an E–S histogram with Next presses only. Nothing here imports Qt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chisurf.plugins.burst.burst_analysis.gui.native import BurstAnalysisHubApp
from chisurf.plugins.burst.burst_analysis.workflow_context import burst_sources

HERE = Path(__file__).resolve().parent
BURST_GUI = HERE.parents[1] / "burst_analysis" / "gui"

#: The rail: the legacy ``ALEX_PANELS`` order, names and roles (``alternation`` keeps its ``optional`` flag: Next
#: does not run it, it converts by itself on arrival). ``plugin`` names a child's folder under ``chisurf/plugins``.
STEPS: list[dict[str, Any]] = [
    {"name": "Pipeline steps", "separator": True},
    {
        "name": "1. Setup",
        "icon": "⚙️",
        "role": "setup",
        "help": str(BURST_GUI / "setup_selection_help.md"),
        "description": "The detector setup: which routing channels are the donor and the acceptor, and which "
        "micro-time window is which excitation. µs-ALEX data can leave it: step 3 measures it.",
    },
    {
        "name": "2. Files",
        "icon": "📂",
        "role": "data",
        "help": str(BURST_GUI / "data_selection_help.md"),
        "description": "The measurements: any format tttrlib reads, including the .sm files of the old "
        "ALEX-Suite. No measurement at hand: Load demo data.",
    },
    {
        "name": "3. Alternation (optional)",
        "icon": "🚦",
        "role": "alternation",
        "optional": True,
        "help": str(HERE / "help.md"),
        "description": "µs-ALEX only: finds the laser alternation and folds it into the micro-time on arrival, "
        "which turns the measurement into ordinary PIE data and writes the setup. PIE / ns-ALEX: nothing to do.",
    },
    {
        "name": "4. Burst search",
        "icon": "🔍",
        "role": "selection",
        "plugin": "burst/burst_selection",
        "description": "Find the bursts. All-photon (APBS) or dual-channel (DCBS): the old program's two search "
        "modes are the search settings here. Next runs the search.",
    },
    {
        "name": "5. Background",
        "icon": "🌙",
        "role": "background",
        "plugin": "burst/burst_background",
        "description": "Per-channel background rate from the inter-photon times, estimated on arrival: the numbers "
        "the old Accurate FRET panel asked you to type in.",
    },
    {
        "name": "6. Accurate FRET",
        "icon": "🎯",
        "role": "accurate_fret",
        "plugin": "burst/accurate_fret",
        "description": "α, δ, γ and β from the donor-only, acceptor-only and FRET populations of your own bursts. "
        "Next calibrates.",
    },
    {
        "name": "7. E–S histogram",
        "icon": "📊",
        "role": "es",
        "plugin": "ndxplorer",
        "description": "The E vs S map, its projections, and any burst property against any other (ndX): the old "
        "E vs S and Dataset Viewer windows in one.",
    },
    {"name": "Side tools", "separator": True},
    {
        "name": "Burst properties",
        "icon": "📋",
        "role": "browser",
        "plugin": "burst/burst_browser",
        "description": "The burst table: sizes, durations, per-channel counts.",
    },
    {
        "name": "Titration",
        "icon": "🧪",
        "role": "titration",
        "optional": True,
        "help": str(HERE / "help.md"),
        "description": "A concentration series fitted together with shared population positions, and the binding "
        "isotherm in it.",
    },
    {
        "name": "BVA",
        "icon": "📊",
        "role": "bva",
        "plugin": "burst/burst_bva",
        "description": "Burst variance analysis: is a population one state, or fast exchange between two?",
    },
    {
        "name": "Export (ALEX-Suite CSV)",
        "icon": "💾",
        "role": "legacy_export",
        "optional": True,
        "help": str(HERE / "help.md"),
        "description": "The five CSV files the old program wrote, for scripts built on that layout. The analysis "
        "itself is in the .pto container.",
    },
]

#: The E–S step's axes, in order of preference (ndX's equations name them; the first one a table has wins).
ES_X = ("FRET efficiency (accurate)", "FRET efficiency(ALEX)", "FRET efficiency(PIE)", "FRET efficiency",
        "Proximity ratio(PIE)", "Proximity ratio")
ES_Y = ("Stoichiometry (accurate)", "Stoichiometry (ALEX)", "Stoichiometry (PIE)", "Sapp(PIE,S)", "Stoichiometry")

#: What the status line asks for on each step (before anything else it says).
NEEDS = {
    "setup": "Pick your setup (PIE), or press Next (µs-ALEX: step 3 writes one).",
    "data": "Drop measurement files, or Load demo data; then Next.",
    "alternation": "µs-ALEX is converted on arrival; then Next.",
    "selection": "Next runs the burst search.",
    "background": "Background is estimated on arrival; Next.",
    "accurate_fret": "Next calibrates α, β, γ, δ and opens the E–S map.",
    "es": "The E–S histogram of your bursts.",
}


class AlexHubApp(BurstAnalysisHubApp):
    """The ALEX Suite workflow on the Burst Analysis hub."""

    def __init__(self, title: str = "ALEX Suite", steps: list[dict] | None = None) -> None:
        #: Burst sources already opened in the E–S step (a revisit does not reload them over the user's gates).
        self._es_loaded: list[str] = []
        self._es_axes_pending = False
        #: The measurements the files step holds (the alternation step converts these, not the container it wrote).
        self._source_files: list[Path] = []
        #: Next on Accurate FRET while its table is still loading: calibrate once the load is done.
        self._pending_calibration = False
        super().__init__(title=title, steps=STEPS if steps is None else steps)
        from chisurf.emtk.help_guide import EmTkHelpWindow

        self.help = EmTkHelpWindow(title=f"{title} — Help", resource=HERE / "help.md", owner=self)
        self._load_guide(HERE / "guide.json")
        # The base class supplies the setup, data (``_make_data`` below), selection and plugin steps.
        extra = {
            "alternation": self._make_alternation,
            "titration": self._make_titration,
            "legacy_export": self._make_export,
        }
        for panel in self.tools:
            if panel["role"] in extra:
                panel["factory"] = extra[panel["role"]]

    def _load_guide(self, path: Path) -> None:
        """Point the hub's tour at the ALEX guide (the base class built it from Burst Analysis's)."""
        from chisurf.emtk.help_guide import EmTkGuidedTour

        self.tour = EmTkGuidedTour(
            path,
            owner=self,
            on_step_change=self._tour_step,
            get_target_rect=self._target_rect,
            wait_for_controls=True,
        )

    # -- the steps only ALEX has ------------------------------------------------------------------------------ #
    def _make_setup(self, app_class=None):
        from .step_apps import AlexSetupSelectionApp

        return super()._make_setup(app_class or AlexSetupSelectionApp)

    def _make_data(self):
        from chisurf.plugins.burst.burst_analysis.gui.data_selection_app import BurstDataSelectionModel

        from .step_apps import AlexDataSelectionApp

        model = BurstDataSelectionModel(on_change=self._data_changed)
        app = AlexDataSelectionApp(model, on_proceed=lambda: self.select("alternation"))
        own = app.track

        def track(name: str) -> None:  # the step's controls (Load demo data) also advance the hub's tour
            own(name)
            self.tour.notify_used(name)

        app.track = track
        return app

    def _make_alternation(self):
        from .alternation_model import AlexAlternationModel
        from .step_apps import AlternationStepApp

        return AlternationStepApp(AlexAlternationModel(on_converted=self.adopt_alex_conversion))

    def _make_titration(self):
        from .step_apps import TitrationStepApp

        return TitrationStepApp()

    def _make_export(self):
        from .step_apps import ExportStepApp

        return ExportStepApp()

    # -- the conversion becomes the workflow's data and setup -------------------------------------------------- #
    def adopt_alex_conversion(self, setup: dict, converted) -> None:
        """Take the alternation step's output as the workflow's files and detector setup.

        Both change at once: the files every later step analyses become the converted container (the originals
        still have the alternation in the macro time, where every micro-time window is meaningless), and the setup
        becomes the one whose windows are the detected laser gates. The setup is saved to the setups store the
        detector editors read, so the setup step and every step's own editor list it.
        """
        converted = [Path(p) for p in converted or () if Path(p).exists()]
        if converted:
            self.context.raw_files = converted
            selection = self.children.get("selection")
            if selection is not None and list(selection.model.files) != converted:
                selection.model.clear()
                selection.model.add_paths(converted)
            for role in ("background", "irf_bg"):
                child = self.children.get(role)
                if child is not None and getattr(child, "model", None) is not None:
                    try:
                        child.model.files = []
                    except Exception:  # noqa: BLE001 - a step without a file list
                        pass
        if setup:
            name = str(setup.get("setup_name") or "")
            try:
                from chisurf.plugins.burst.burst_selection.gui.model import save_setup

                save_setup(name, setup)
            except Exception as exc:  # noqa: BLE001 - the context still carries it
                self.status = f"The ALEX setup could not be saved: {exc}"
            self.context.channel_settings = dict(setup)
            self.context.setup_name = name
        self._apply_downstream(skip=("data", "alternation"))
        self.wants_frame = True

    # -- the hand-off to ALEX's steps ------------------------------------------------------------------------- #
    def _to_setup(self, child) -> None:
        name = self.context.setup_name
        if name and name != child.selected_setup_name():
            child.refresh_setups()
            child.select_setup(name)

    def _data_changed(self) -> None:
        super()._data_changed()
        self._source_files = list(self.context.raw_files)

    def _to_alternation(self, child) -> None:
        files = self._source_files or list(self.context.raw_files)
        if files:
            child.model.set_files(files)

    def _to_selection(self, child) -> None:
        files = [Path(p) for p in self.context.raw_files]
        if files and [Path(p) for p in child.model.files] != [p.resolve() for p in files]:
            child.model.clear()
            child.model.add_paths(files)
        settings = self._setup_payload()
        if settings.get("detectors") and self._changed("selection", "setup", settings):
            child.apply_setup(settings, self.context.setup_name)

    def _to_accurate_fret(self, child) -> None:
        self._editor_to("accurate_fret", child.controller.channel_definition, self._setup_payload())
        sources = burst_sources(self.context)
        if not sources or child.controller.running:
            return
        if self._changed("accurate_fret", "table", str(sources[0])):
            child.controller.load(str(sources[0]))

    def _to_es(self, child) -> None:
        """Open the workflow's bursts in ndX, once per set of them; a revisit refreshes the stored constants."""
        features = {getattr(f, "name", ""): f for f in getattr(child, "features", [])}
        fret = features.get("accurate_fret")
        if fret is not None and self._es_loaded:
            try:
                fret.restore_stored()
            except Exception:  # noqa: BLE001 - nothing stored yet
                pass
        files, kind = self.ndx_sources()
        if not files or files == self._es_loaded or "io" not in features:
            return
        features["io"].load(files, kind)
        self._es_loaded = files
        self._es_axes_pending = True

    def _es_axes(self, child) -> tuple[str, str]:
        """Show E against S once the bursts are in (ndX would open on its last-used pair of columns)."""
        options = set(child.model.parameter_options())
        x = next((name for name in ES_X if name in options), "")
        y = next((name for name in ES_Y if name in options), "")
        for axis, name in (("x", x), ("y", y)):
            if name:
                child.model.set_parameter(axis, name)
                # E and S live in [0, 1]; an auto range would stretch to the odd burst with no donor photons.
                state = child.model.axis(axis)
                state.lo, state.hi, state.auto_scale = -0.1, 1.1, False
        child.model.invalidate()
        return x, y

    def ndx_sources(self) -> tuple[list[str], str | None]:
        """The burst sources in the form ndX opens: the ``.pto`` itself for container runs, else the tables."""
        from chisurf.core.fio.fluorescence import burst_tree

        sources = burst_sources(self.context)
        if not sources:
            return [], None
        containers: list[str] = []
        for path in sources:
            node = Path(path)
            while node.suffix.lower() != burst_tree.SUFFIX and node.parent != node:
                node = node.parent
            if node.suffix.lower() == burst_tree.SUFFIX:
                containers.append(str(node))
        if containers and len(containers) == len(sources):
            return list(dict.fromkeys(containers)), "pto"
        return [str(p) for p in sources], None

    def _calibration(self) -> dict[str, float]:
        """γ and β of the Accurate FRET step's result, if it has one."""
        child = self.children.get("accurate_fret")
        result = getattr(getattr(child, "model", None), "result", None)
        calibration = getattr(getattr(result, "calibration", None), "calibration", None)
        values = {}
        for key in ("gamma", "beta"):
            value = getattr(calibration, key, None)
            if value is None and isinstance(calibration, dict):
                value = calibration.get(key)
            if value is not None:
                values[key] = float(value)
        return values

    def _to_titration(self, child) -> None:
        sources = burst_sources(self.context)
        if sources:
            child.step.set_burst_files(sources)
        calibration = self._calibration()
        if calibration and self._changed("titration", "corrections", calibration):
            child.step.set_corrections(**calibration)

    def _to_legacy_export(self, child) -> None:
        sources = burst_sources(self.context)
        if sources and self._changed("legacy_export", "files", [str(p) for p in sources]):
            child.set_burst_files(sources)

    # -- Next ------------------------------------------------------------------------------------------------ #
    def next_step(self) -> None:
        """Next (the tour's steps wait for this button)."""
        self.tour.notify_used("next")
        super().next_step()

    def fast_forward(self) -> None:
        """>> (the tour's steps may wait for this button)."""
        self.tour.notify_used("fast_forward")
        super().fast_forward()

    def _busy(self) -> bool:
        child = self.child
        if child is None:
            return False
        if self._pending_calibration and self.selected == "accurate_fret" and not child.controller.running:
            self._pending_calibration = False
            if child.model.result is None and child.model.can_run() is None:
                child.controller.run()
        for obj in (child, getattr(child, "controller", None), getattr(child, "model", None)):
            if obj is not None and getattr(obj, "running", False) is True:
                return True
        return False

    def _run_current(self) -> bool:
        """Next on Accurate FRET calibrates (when its table is loaded and nothing ran yet); else the base rule."""
        child = self.child
        if self.selected == "accurate_fret" and child is not None:
            # The table may still be loading (it is read on arrival): calibrate as soon as it is in.
            self._pending_calibration = child.model.result is None
            return self._pending_calibration
        return super()._run_current()

    # -- the rail and the status line ------------------------------------------------------------------------- #
    def badge(self, role: str) -> str:
        ctx = self.context
        if role == "es":
            return "•" if self._es_loaded else ""
        if role in ("background", "accurate_fret"):
            return "•" if ctx.burst_folder else ""
        return super().badge(role)

    def need(self, role: str) -> str:
        """What the open step needs now (the step's state moves it on: done steps say so)."""
        ctx, child = self.context, self.children.get(role)
        if role == "setup" and ctx.setup_name:
            return "Setup chosen; Next."
        if role == "data" and ctx.raw_files:
            return "Files chosen; Next opens 3. Alternation."
        if role == "alternation" and child is not None:
            if child.model.running:
                return "Converting the µs-ALEX alternation..."
            if child.model.converted:
                return "Converted; Next opens the burst search."
            if child.model.decision == "pie":
                return "Nothing to convert (PIE); Next."
        if role == "selection" and ctx.burst_folder is not None:
            return "Bursts found; Next (Restart searches again)."
        if role == "accurate_fret" and getattr(getattr(child, "model", None), "result", None) is not None:
            return "Calibrated; Next opens the E–S map."
        return NEEDS.get(role, "")

    def summary(self, width: float = 1200.0) -> str:
        """What the open step needs; on a wide window also the setup, the files and the bursts."""
        need = self.need(self.selected or "")
        if width < 1000:
            return _fit(need or super().summary(width), width)
        context = super().summary(width)
        return _fit(f"{need} · {context}" if need else context, width)

    def render(self):
        # A status line wider than the space left of Back / >> / Next is one hovered item that covers the buttons
        # (they stop taking clicks), so every status is cut to that space; the summary already is.
        from emtk import im

        width = float(im.get_main_viewport().size[0])
        if self.status not in ("Ready", getattr(self, "_summary_shown", None)):
            self.status = _fit(self.status, width)
        es = self.children.get("es")
        if es is not None and self._es_axes_pending and getattr(es.model, "has_data", False):
            self._es_axes_pending = False
            self._es_axes(es)
        super().render()


def _fit(text: str, width: float) -> str:
    """*text* cut (with an ellipsis) to the status bar's room left of the Back / >> / Next buttons."""
    room = max(80.0, width - min(230.0, width * 0.26) - 250.0)
    try:
        from emtk.im_widgets import calc_text_size

        measure = lambda t: float(calc_text_size(t)[0])  # noqa: E731
        measure("x")
    except Exception:  # noqa: BLE001 - no frame: estimate
        measure = lambda t: 7.0 * len(t)  # noqa: E731
    if measure(text) <= room:
        return text
    while text and measure(text + "…") > room:
        text = text[:-1]
    return text.rstrip(" ·") + "…"


def create_app(**kwargs) -> AlexHubApp:
    """Factory named by ``entrypoints.emtk``."""
    from chisurf.emtk.i18n import install

    install()
    return AlexHubApp(**kwargs)


make_app = create_app

__all__ = ["NEEDS", "STEPS", "AlexHubApp", "create_app", "make_app"]
