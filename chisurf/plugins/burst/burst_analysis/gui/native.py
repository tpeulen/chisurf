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
import logging
import threading
from pathlib import Path
from typing import Any

from emtk.i18n import tr

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

#: Steps that read the bursts: they open once Burst Selection has found them.
NEEDS_BURSTS = frozenset({"fusion", "bva", "two_cde", "mle", "h2mm", "browser", "accurate_fret",
                          "burst_fcs", "burst_gs"})
#: Steps that read the measurements: they open once Data Selection has files.
NEEDS_FILES = frozenset({"selection", "background", "irf_bg"})

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
        "name": "2.1 Burst Fusion (optional)",
        "icon": "🔗",
        "role": "fusion",
        "plugin": "burst/burst_fusion",
        "advanced": True,
        # Walking the pipeline must not fuse: only the step's own Fuse button hands a fused folder downstream.
        "optional": True,
        "description": "Optional: merge bursts the same molecule produced (recurrence P_same) into a new burst "
        "folder the later steps then use.",
    },
    {
        "name": "2.2 Burst BVA",
        "icon": "📊",
        "role": "bva",
        "plugin": "burst/burst_bva",
        # Simple: not shown, run with its defaults once the bursts are there
        "background": True,
        "description": "Burst-level feature: burst variance analysis of the selected bursts.",
    },
    {
        "name": "2.3 Burst 2CDE",
        "icon": "📊",
        "role": "two_cde",
        "plugin": "burst/burst_2cde",
        "background": True,
        "description": "Burst-level feature: the FRET-2CDE / ALEX-2CDE burst-dynamics filter.",
    },
    {
        "name": "3. Burst MLE",
        "icon": "🎯",
        "role": "mle",
        "plugin": "burst/burst_mle_analysis",
        "description": "Burst-level feature: one maximum-likelihood lifetime per burst (Advanced: also "
        "per H2MM state of each burst, after step 3.1, H2MM).",
    },
    {
        "name": "3.1 Burst segmentation (H2MM)",
        "icon": "🔀",
        "role": "h2mm",
        "plugin": "burst/burst_h2mm",
        "advanced": True,
        "description": "Cut each burst into segments: photon-by-photon HMM (H2MM) assigns every photon a state.",
    },
    # The side tools are Advanced: Simple is the pipeline, pressed through with Next.
    {"name": "Side tools", "separator": True, "advanced": True},
    {
        "name": "Browser",
        "icon": "📋",
        "role": "browser",
        "advanced": True,
        "plugin": "burst/burst_browser",
        "description": "Inspect the current burst workflow result.",
    },
    {
        "name": "Accurate FRET",
        "icon": "🎯",
        "role": "accurate_fret",
        "advanced": True,
        "plugin": "burst/accurate_fret",
        "description": "Correction factors (alpha/beta/gamma/delta) for the bursts this workflow produced.",
    },
    {
        "name": "Burst FCS",
        "icon": "📊",
        "role": "burst_fcs",
        "advanced": True,
        "plugin": "burst/burst_fcs_correlator",
        "description": "Correlate the photons of the selected bursts.",
    },
    {
        "name": "Kinetics (GS)",
        "icon": "🔀",
        "role": "burst_gs",
        "advanced": True,
        "plugin": "burst/burst_gs",
        "description": "Photon-by-photon kinetics (Gopich-Szabo) on the selected bursts.",
    },
    {
        "name": "Background",
        "icon": "🌙",
        "role": "background",
        "advanced": True,
        "plugin": "burst/burst_background",
        "description": "Estimate background using the selected data and channel setup.",
    },
    {
        "name": "IRF & Background",
        "icon": "✨",
        "role": "irf_bg",
        "advanced": True,
        "plugin": "burst/burst_irf_bg",
        "description": "Extract a per-detector IRF and background from the non-burst photons and feed them to "
        "both MLE steps.",
    },
]

#: The steps whose detector editor takes the workflow's setup.
MLE_ROLES = ("mle", "segment_mle")


#: Seconds the second stage of the warm-up waits: its imports hold the interpreter in long stretches,
#: and the window's first frames need it for themselves.
WARM_LATER_S = 1.0


def _warm_steps() -> None:
    """Import and read once what the pipeline's steps need when they open, in two stages: what the
    first frames draw at once (icons, the plugin catalogue, the session API), the steps' own modules
    and the task processes after :data:`WARM_LATER_S` -- before the user can have dropped a file."""
    import time

    first = (
        lambda: getattr(__import__("emtk.icons", fromlist=["preload"]), "preload", lambda: None)(),
        lambda: __import__("chisurf.emtk.plugins", fromlist=["manifests"]).manifests(),
        lambda: __import__("chisurf.core.api"),  # the workspace tables' session API
    )
    later = (
        lambda: __import__("chisurf.core.registry.catalog", fromlist=["registry"]).registry(),
        lambda: tr("Burst Selection"),
        lambda: __import__("chisurf.plugins.burst.burst_selection.gui.native"),
        lambda: __import__("chisurf.plugins.burst.burst_mle_analysis.gui.native"),
        # BVA's and 2CDE's task processes, started now rather than when the bursts arrive
        lambda: __import__(
            "chisurf.plugins.burst.burst_analysis.gui.background_tasks", fromlist=["warm"]
        ).warm(),
    )
    for index, warm in enumerate((*first, *later)):
        if index == len(first):
            time.sleep(WARM_LATER_S)
        try:
            warm()
        except Exception:  # noqa: BLE001 - the step loads it itself when it opens
            pass


def _signature(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


class BurstAnalysisHubApp(ToolHubApp):
    """The burst workflow on the shared native hub; the steps share one :class:`BurstWorkflowContext`."""

    def __init__(self, title: str = "Burst Analysis", steps: list[dict] | None = None) -> None:
        self.context = BurstWorkflowContext()
        #: MLE steps whose hand-over was still running when the context changed again
        self._resync: set[str] = set()
        # What the steps load on first open (the search registry imports IMP.bff, the translations,
        # the MLE step's modules): loaded now, in the background, not as the step opens.
        threading.Thread(target=_warm_steps, name="burst-warm", daemon=True).start()
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
            "irf_bg": self._make_irf_bg,
        }
        panels = [
            {**p, "factory": factories[p["role"]]} if p.get("role") in factories else dict(p)
            for p in (STEPS if steps is None else steps)
        ]
        for panel in panels:
            if panel.get("role") in {
                "selection",
                "bva",
                "mle",
                "segment_mle",
                "background",
                "irf_bg",
                "h2mm",
                "accurate_fret",
                "burst_fcs",
            }:
                panel["uses_setup"] = True
        super().__init__(
            title,
            panels,
            help_resource=HERE / "help.md",
            guide=HERE / "guide.json",
            initial="setup",
            # A pipeline: Next runs a step, and >> (documented in its help and in guides 27 and 66) walks the rest.
            steps=True,
        )
        self._base_names = {p["role"]: p["name"] for p in self.tools}

    # -- the step apps the hub owns the wiring of ------------------------------------------------------- #
    def _make_setup(self, app_class=None):
        from .setup_selection_app import BurstSetupSelectionApp

        app = (app_class or BurstSetupSelectionApp)(
            model=self.setup_model,
            on_changed=self._hub_setup_changed,
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

        return create_app(on_run_done=self._selection_done, pipeline=True)

    def _make_mle(self, split_by_state: bool):
        from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

        app = create_app()
        app.pipeline = True  # the bursts come from Burst Selection: no Input of its own
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
    def _hub_setup_changed(self, settings: dict) -> None:
        """Fan out shared acquisition settings and retain the workflow's context handoff."""
        self._shared_setup_changed(settings)
        self._setup_changed()

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
        if self.context.raw_files:
            # Every step reads these photons: read them now, in the background, while the user
            # is still on this step (the search, its check and its preview then find them read).
            from chisurf.core.fio.staging import prefetch_tttr

            prefetch_tttr(self.context.raw_files)
            self._prepare_containers(data)
        self._propose_setup_from_first_file()
        self.context.raw_mmfdb_artifacts = data.model.mmfdb_payload()
        self._apply_downstream(skip=("setup", "data"))
        self.wants_frame = True

    def _prepare_containers(self, data) -> None:
        """Make each file's analysis container in the project now, in the background: linking the
        photons hashes the whole file (1.5 s for 300 MB), which the first search waited for."""
        sources = getattr(getattr(data, "model", None), "sources", None) or {}
        files = [str(p) for p in self.context.raw_files]

        def work() -> None:
            from chisurf.core.fio.fluorescence.burst_container import ensure_container
            from chisurf.core.project.analysis import container_dir

            for path in files:
                try:
                    ensure_container(path, container_dir(sources.get(path, "")), raw_data="sidecar")
                except Exception:  # noqa: BLE001 - the search makes it, and says why it cannot
                    pass

        threading.Thread(target=work, name="burst-containers", daemon=True).start()

    def _propose_setup_from_first_file(self) -> None:
        """No setup chosen or defined yet: open the setup the library says was used last; only a
        library without one gets detectors and excitation windows proposed from the first file
        (editable in step 0, saveable to the Settings library), so a PTU can be analysed at once.

        Photons handed in from the Datasets workspace ("Open in…") open the Data step before step 0
        ever drew, so step 0 had not opened the last used setup yet -- the proposal used to win."""
        model = self.setup_model
        files = self.context.raw_files
        if model.data.get("detectors") or not files:
            return
        try:
            model.refresh_setups()
            name = model.open_last_used()
        except Exception:  # noqa: BLE001 - the library is unreachable: propose from the file
            name = ""
        if name:
            model.changed()
            # step 0 may not exist yet: the workflow's context takes the setup from the shared model
            self.context.channel_settings = model.get_settings()
            self.context.setup_name = model.current_name
            setup = self.children.get("setup")
            if setup is not None:
                setup.open_last_used = False  # opened already: step 0 lists the library, keeps this
            self.status = f"Setup {name} (last used) for {Path(files[0]).name}."
            return
        try:
            tttr = model.open_tttr(files[0], raw=True, auto=True)
            names = model.propose_from_tttr(tttr)
            header = tttr.get_header()
            reading = model.data["tttr_reading"]
            reading["macro_time_resolution"] = float(header.macro_time_resolution) * 1e9
            reading["micro_time_resolution"] = float(header.micro_time_resolution) * 1e12
        except Exception as exc:  # noqa: BLE001 - the user still can define the setup by hand
            self.status = f"No setup could be proposed from {Path(files[0]).name}: {exc}"
            return
        model.changed()
        self.status = (
            f"Setup proposed from {Path(files[0]).name}: detectors {', '.join(names)}; "
            "review it in step 0 and save it to the library."
        )

    def _selection_done(self, model) -> None:
        """Burst Selection finished a run: its output becomes the bursts every later step reads."""
        if model.files:
            self.context.raw_files = list(model.files)
        result = model.result or {}
        artifacts = result.get("mmfdb_artifacts") or {}
        if artifacts:
            self.context.mmfdb_artifacts = dict(artifacts)
        legacy_folder = folder_from_result(result)
        # The run the search wrote (into the project's analysis container) is what the later
        # steps read -- by its address, ``<container>/<run>``, so a new search is a new input
        # for them. Only a search that wrote no container gets one written here.
        sources = searched_runs(result, model.files) or materialize_handoff(
            self.context,
            model.frames_by_file,
            run_name=legacy_folder.name if legacy_folder is not None else _search_run(model),
        )
        # A fresh burst search supersedes any fusion of the previous one.
        self._fusion_source = self._fused_folder = None
        folder = None
        if sources:
            # One measurement, one container: the first is what the status line names,
            # and every step reads the rest the same way. The legacy tree (when the
            # search wrote one) keeps the still folder-reading steps fed.
            self.context.set_burst_folder(sources[0])
            self.context.bur_files = sources
            self.context.legacy_burst_folder = legacy_folder
            folder = sources[0]
        elif legacy_folder is not None:
            self.context.set_burst_folder(legacy_folder)
            self.context.legacy_burst_folder = legacy_folder
            folder = legacy_folder
        if folder is not None:
            self.status = f"Bursts for the later steps: {folder}"
        self._apply_downstream(skip=("data", "selection"))
        if folder is not None:
            # at once, each in a process of its own (background_tasks): while the user sets up Burst
            # MLE, without taking the interpreter from it or from the window
            self._run_in_background()
        self.wants_frame = True

    def _on_fused_folder(self, folder: str) -> None:
        """Adopt the fused bursts -- a run of the analysis container (``m000.pto/<run>``), or a
        legacy folder -- as what the later steps analyse."""
        from chisurf.core.fio.analysis_path import is_container_path

        path = Path(folder)
        run = is_container_path(path)
        if not (run or path.is_dir()):
            return
        self._fusion_source = self.context.burst_folder
        self._fused_folder = path
        self.context.set_burst_folder(path)
        # A legacy folder is what the folder-reading steps read; a run is read as a run.
        self.context.legacy_burst_folder = None if run else path
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
                applied = max(
                    applied, self._patterns_to_mle(child, self.context.irf_background_patterns)
                )
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

    def _apply_downstream(self, skip: tuple[str, ...] = ()) -> None:
        """Hand the context to every open step but the ones it came from."""
        for role, child in list(self.children.items()):
            if role in skip:
                continue
            try:
                self.on_select(role, child)
            except Exception as exc:  # noqa: BLE001 - one step's hand-off must not stop the others'
                self.status = f"{role}: {type(exc).__name__}: {exc}"

    def _adopt(self, role, child, route, error):
        super()._adopt(role, child, route, error)
        # every step of the pipeline takes its input from the step before: no Input of its own
        made = self.children.get(role)
        for target in (made, *(getattr(made, a, None) for a in ("bva_gui", "two_cde_gui", "gui"))):
            if target is not None:
                try:
                    target.pipeline = True
                except Exception:  # noqa: BLE001 - a tool without attributes stays as it is
                    pass

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
        """All files of 1. Data Selection, kept identical to it (added, removed, reordered)."""
        data = self.children.get("data")
        sources = getattr(getattr(data, "model", None), "sources", None) or {}
        paths = [str(p) for p in self.context.raw_files]
        uids = [sources.get(p, "") for p in paths]
        use = getattr(child, "use_files", None)
        if callable(use):
            use(paths, uids)  # each file's runs go into its workspace dataset's analysis container
        elif paths and not child.model.files:
            child.model.add_paths(self.context.raw_files)

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
        if (
            folder is not None
            and child.controller is not None
            and child.model.analysis_folder != folder
        ):
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
        bursts = [str(p) for p in self.context.bur_files or ()]
        settings = self.context.channel_settings
        patterns = self.context.irf_background_patterns
        take = getattr(child, "take_bursts", None)
        if bursts and callable(take) and (
            not child.model.session.bur_files or self._changed(role, "bursts", bursts)
        ):
            # A new search is a new analysis: the step drops the previous bursts and their
            # lifetimes and takes the new run (``m.pto/<run> (2)``) -- never fits stale bursts.
            # In the step's background job, setup and IRF / background preparation included.
            self._handed[(role, "bursts")] = _signature(bursts)
            if settings:
                self._handed[(role, "setup")] = _signature(settings)
            prepare_from = ()
            if not patterns and self.context.raw_files:
                self._handed[(role, "prepared")] = _signature(str(self.context.burst_folder))
                prepare_from = self.context.raw_files  # measured buffer / scatter, else estimated
            take(self.context.bur_files, settings, prepare_from)
            if patterns:
                self._resync.add(role)  # the patterns go in once the bursts are there
            return
        if getattr(child, "pending", False):
            self._resync.add(role)  # the hand-over is running: what changed meanwhile follows it
            return
        # The workflow's setup is the authority: a container may carry the setup of
        # the search that wrote it, so this goes to the session AFTER the files.
        if settings and self._changed(role, "setup", settings):
            child.model.set_setup(settings)
        if patterns and self._changed(role, "patterns", id(patterns)):
            self._patterns_to_mle(child, patterns)
        elif (
            child.model.session.bur_files
            and self.context.raw_files
            and self._changed(role, "prepared", str(self.context.burst_folder))
        ):
            prepare = getattr(child, "prepare", None)
            if callable(prepare):
                prepare(self.context.raw_files)  # measured buffer / scatter, else estimated

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
        context = {}
        if folder is not None:
            context["burst_folder"] = str(folder)
        if self._changed("h2mm", "context", context):
            child.model.apply_workflow_context(context)

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
        settings = self.context.channel_settings
        if settings and self._changed("burst_gs", "setup", settings):
            child.model.apply_channel_settings(settings)
        # The run the later steps read (a fused run after Fusion), as the workspace hands it.
        run = analysis_path(self.context)
        if run is not None and child.controller is not None and not child.model.bur_files:
            child.controller.set_run(str(run))

    def _to_accurate_fret(self, child) -> None:
        from chisurf.core.fio.fluorescence import burst_tree

        sources = burst_sources(self.context)
        if not sources or getattr(child.model, "filename", None) or child.controller.running:
            return
        first = Path(sources[0])
        readable = first.is_file() or burst_tree.is_container_path(first)
        if readable and self._changed("accurate_fret", "table", str(first)):
            child.controller.load(str(first))

    def _to_background(self, child) -> None:
        controller = child.controller
        if controller is None:
            return
        if self.context.raw_files and not child.model.files:
            controller.add_files([str(p) for p in self.context.raw_files])
        # Compute on arrival, as the Qt step does: nothing is asked that the data cannot answer.
        reason = getattr(child.model, "can_estimate", lambda: None)()
        if (
            not getattr(child.model, "diagnostics", None)
            and reason is None
            and not controller.running
        ):
            controller.run()
        elif reason is not None:
            # A refusal is a state the user has to be able to act on: dropping it
            # here left the step opened with a permanently blank plot and no
            # reason anywhere (the ALEX-on-pre-converted-data bug).
            child.model.status = reason
            controller.status = reason
            self.status = reason

    def _to_irf_bg(self, child) -> None:
        controller = child.controller
        if controller is None:
            return
        if self.context.raw_files and not child.model.files:
            controller.add_files([str(p) for p in self.context.raw_files])

    # -- the rail ------------------------------------------------------------------------------------------ #
    def panel_enabled(self, role: str) -> bool:
        """The steps open in order: Burst Selection once there are files, everything that reads
        bursts (MLE, BVA, 2CDE, Fusion, H2MM and the burst side tools) once the bursts are there."""
        if role in NEEDS_BURSTS:
            return self.step_done("selection")
        if role in NEEDS_FILES:
            return bool(self.context.raw_files)
        return True

    def disabled_reason(self, role: str) -> str:
        if role in NEEDS_BURSTS:
            return tr("Run 2. Burst Selection first: this step reads its bursts.")
        if role in NEEDS_FILES:
            return tr("Add the measurements in 1. Data Selection first.")
        return super().disabled_reason(role)

    def step_done(self, role: str) -> bool:
        """Whether a step has done its work (its rail row gets a check)."""
        ctx = self.context
        child = self.children.get(role)
        model = getattr(child, "model", None)
        if role == "setup":
            return bool(ctx.setup_name or (ctx.channel_settings or {}).get("detectors"))
        if role == "data":
            return bool(ctx.raw_files)
        if role == "selection":
            return ctx.burst_folder is not None or bool(ctx.bur_files)
        if role == "fusion":
            return self._fused_folder is not None
        if role in ("bva", "two_cde"):
            return getattr(model, "df", None) is not None
        if role == "mle":
            return bool(getattr(model, "burst_results", None))
        if role == "h2mm":
            return getattr(model, "result", None) is not None
        return False

    def badge(self, role: str) -> str:
        """What a rail row shows behind its name: a check once the step is done (the number of files of
        the data step), a dot where a step could run now."""
        ctx = self.context
        if role == "data" and ctx.raw_files:
            return f"✓ ({len(ctx.raw_files)})"
        if self.step_done(role):
            return "✓"
        if role in ("bva", "two_cde", "mle", "h2mm") and ctx.burst_folder:
            return "•"
        return ""

    def finish_ready(self) -> bool:
        """The last required step (Burst MLE) has its lifetimes."""
        return self.step_done("mle")

    def finish_message(self) -> str:
        return (
            "Close Burst Analysis? The bursts and every result are kept in the measurements' "
            "containers of the project."
        )

    def _run_in_background(self) -> None:
        """Simple mode: the steps not shown (BVA, 2CDE) run with their defaults once the bursts are
        there, so their results exist for the browser and the export."""
        if self.advanced:
            return
        for role in ("bva", "two_cde"):
            if self.step_done(role):
                continue
            try:
                child = self.ensure_child(role)
                if child is None:
                    continue
                self.on_select(role, child)
                controller = getattr(child, "controller", None)
                if controller is None or getattr(controller, "running", False):
                    continue
                from . import background_tasks

                start = background_tasks.start_bva if role == "bva" else background_tasks.start_two_cde
                try:
                    started = start(controller)
                except Exception:  # noqa: BLE001 - computed by the step itself instead
                    logging.getLogger(__name__).exception("%s: no background task", role)
                    started = False
                if not started:
                    controller.run(force=True, explicit=False)
            except Exception as exc:  # noqa: BLE001 - a background check must not stop the pipeline
                self.status = f"{role}: {type(exc).__name__}: {exc}"

    def summary(self, width: float = 1200.0) -> str:
        """The status line: the setup, the files and the bursts the later steps read (shorter when narrow, so it
        stays clear of Back / Next)."""
        ctx = self.context
        parts = [f"Setup: {ctx.setup_name or '(unsaved)' if ctx.channel_settings else 'none'}"]
        parts.append(f"{len(ctx.raw_files)} TTTR file(s)")
        if ctx.burst_folder is not None:
            folder = Path(ctx.burst_folder)
            # a run of a container reads "m000.pto/<run>": which measurement, which analysis
            shown = f"{folder.parent.name}/{folder.name}" if folder.parent.suffix == ".pto" else folder.name
            parts.append(f"bursts: {shown}" if width >= 1000 else "bursts ready")
        return " · ".join(parts)

    def export_settings(self):
        """Keep workflow sources, provenance and measured patterns beside child UI state."""
        state = super().export_settings()
        payload = self.context.to_payload()
        payload["irf_background_patterns"] = self.context.irf_background_patterns
        state["workflow"] = json.loads(json.dumps(payload, default=lambda value: value.tolist()))
        state["fusion_source"] = str(self._fusion_source) if self._fusion_source else None
        state["fused_folder"] = str(self._fused_folder) if self._fused_folder else None
        return state

    def restore_settings(self, state):
        """Restore workflow authority before reconnecting saved child views."""
        from dataclasses import fields

        state = state or {}
        payload = dict(state.get("workflow") or {})
        if payload:
            for key in ("raw_files", "bur_files"):
                payload[key] = [Path(path) for path in payload.get(key, [])]
            if payload.get("burst_folder") is not None:
                payload["burst_folder"] = Path(payload["burst_folder"])
            names = {field.name for field in fields(BurstWorkflowContext)}
            self.context = BurstWorkflowContext(
                **{key: value for key, value in payload.items() if key in names}
            )
        self._fusion_source = Path(state["fusion_source"]) if state.get("fusion_source") else None
        self._fused_folder = Path(state["fused_folder"]) if state.get("fused_folder") else None
        super().restore_settings(state)
        self.context.channel_settings = self.setup_model.get_settings()
        self.context.setup_name = self.setup_model.current_name
        if not self.context.raw_files and not self.context.bur_files and self.selected != "setup":
            # restored without its data (the shell's reopen): the workflow starts at its first step
            self.select("setup", by_user=False)

    def render(self):
        if self.status == getattr(self, "_summary_shown", None) or self.status == "Ready":
            from emtk import im

            self.status = self._summary_shown = self.summary(float(im.get_main_viewport().size[0]))
        # A step that runs without being shown (BVA, 2CDE in Simple) is never drawn, so its own
        # frame never collects its result: the hub polls it until it is done.
        for role, child in list(self.children.items()):
            if role == self.selected:
                continue
            controller = getattr(child, "controller", None)
            if controller is not None and getattr(controller, "running", False):
                poll = getattr(controller, "poll", None)
                if callable(poll):
                    try:
                        poll()
                    except Exception as exc:  # noqa: BLE001 - shown in the status line
                        self.status = f"{role}: {type(exc).__name__}: {exc}"
                self.wants_frame = True
            # MLE prepares the new bursts (references, IRF / background) as soon as they come,
            # also while another step is on screen; its job's poll is all its frame does with it.
            job = getattr(child, "job", None) if role in MLE_ROLES else None
            if job is not None and (getattr(child, "pending", False) or role in self._resync):
                try:
                    job.poll()
                    waiting = getattr(child, "_fit_if_waiting", None)
                    if callable(waiting):
                        waiting()  # the next queued job, or the fit Next asked for
                    if role in self._resync and not getattr(child, "pending", False):
                        self._resync.discard(role)
                        self._to_mle(child)
                except Exception as exc:  # noqa: BLE001 - shown in the status line
                    self.status = f"{role}: {type(exc).__name__}: {exc}"
                self.wants_frame = True
        for panel in self.tools:
            base = self._base_names.get(panel["role"], panel["name"])
            badge = self.badge(panel["role"])
            panel["name"] = f"{base} {badge}" if badge else base
        super().render()


def searched_runs(result: Any, files) -> list[Path]:
    """The container runs (``m.pto/<run>``) a burst search wrote, in the order of *files*."""
    from chisurf.core.fio.analysis_path import is_container_path

    by_file = (result or {}).get("output_paths_by_file") or {} if isinstance(result, dict) else {}
    runs = []
    for path in [str(f) for f in files] or list(by_file):
        folder = (by_file.get(path) or by_file.get(str(Path(path).resolve())) or {}).get("output_folder")
        if folder and is_container_path(Path(folder)) and Path(folder).parent.exists():
            runs.append(Path(folder))
    return runs


def _search_run(model) -> str | None:
    """The run a burst search's results are named by -- what the search names its own run, and
    its legacy folder was called (``sliding_window_All 0.1500#60``). Without a name the bursts
    would land at a container's top level, where a run is listed under another name than the one
    it is read by, and every later step finds no burst table."""
    from chisurf.plugins.burst.burst_selection.api.selection import legacy_output_folder_name

    try:
        return legacy_output_folder_name(model.analysis_settings())
    except Exception:  # noqa: BLE001 - a model without settings hands an unnamed run on
        return None


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


def receive_photons(app, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``photons``): the photon streams
    ``payload["files"]`` of the Datasets workspace become the workflow's data (its Data step).

    *app* is the hub (*Open in…*) or its Data step (the step's own Input section)."""
    from chisurf.core.plugin.workspace_input import read_address

    files = payload.get("files") or []
    files = files if isinstance(files, list) else [files]
    paths = [read_address(str(f)) for f in files]
    data = app
    if hasattr(app, "children") and hasattr(app, "select"):
        app.select("data")
        data = app.children.get("data")
    if data is None:
        raise RuntimeError("the burst analysis has no Data step to take photon streams")
    if not data.take_photons(paths, list(payload.get("datasets") or [])):
        if not {str(p) for p in paths} & {str(p) for p in data._paths()}:
            raise ValueError("nothing new to add (already listed, or not a photon stream)")


def receive_setup(app, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``setup``): the detector setup
    ``payload["setup_file"]`` of the Datasets workspace is loaded into the Setup step.

    *app* is the hub (*Open in…*) or its Setup step (the step's own Input section)."""
    from chisurf.core.plugin.workspace_input import read_address

    path = read_address(str(payload["setup_file"]))
    step = app
    if hasattr(app, "children") and hasattr(app, "select"):
        app.select("setup")
        step = app.children.get("setup")
    if step is None or not step.take_setup(path):
        raise ValueError(f"{path} is not a detector setup the editor reads")
