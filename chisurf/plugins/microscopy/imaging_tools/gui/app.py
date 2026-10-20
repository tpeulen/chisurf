"""Native imaging pipeline: the steps that share one imaging context, in one window.

The list holds the tools that consume the shared state -- the detector setup, the photon source the
Browser picks, the imaging HDF5 the Intensity step creates and the IRF & BG calibration -- in pipeline
order; the chosen step is built on first use (with that context applied) and drawn on the right. Child
factories are resolved from their manifests.

Tools that read their own input and take none of that context (Drift Correction, Particle Tracking, PSF
Determination, CLSM Generator) are not listed here: each is its own Spectroscopy › Imaging ribbon entry.
"""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

from emtk import im, keys
from emtk.app import ImApp
from emtk.i18n import tr

from chisurf.emtk.background_build import BackgroundBuild, draw_opening
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.plugin_icons import entry_icon
from chisurf.plugins.core.setup_channel_definition.gui.model import default_settings
from chisurf.plugins.emtk_layout import window_size

from .client import DetectorSetupClient

#: The pipeline: every tool that consumes the shared setup, source, HDF5 or calibration, in order.
PANELS = (
    (
        "setup",
        "core/setup_channel_definition",
        "Setup",
        "Define detector channels and PIE time windows once for all imaging tools.",
    ),
    (
        "browser",
        "tttr/tttr_image_browser",
        "Browser",
        "Browse TTTR image files and explore intensity maps.",
    ),
    (
        "frc",
        "microscopy/img_frc",
        "Resolution",
        "How fine a detail this acquisition actually resolves, by Fourier ring correlation between two independent halves of it, on the Browser's source and the Setup's detector windows. Drift blurs the image and so lowers the measured resolution: measure it on frames that are already aligned (Drift Correction).",
    ),
    (
        "flow",
        "microscopy/img_flow",
        "Flow",
        "Map the velocity field of the Browser's source: one arrow per tile, over the image. It measures motion rather than building a per-pixel map, and a drifting stage is indistinguishable from a sample flowing the other way, so correct drift first (Drift Correction). Particle Tracking follows individual particles; this reads a velocity from the correlations of everything at once, so it works where the labels are too dense to resolve as spots.",
    ),
    (
        "coloc",
        "microscopy/img_coloc",
        "Colocalization",
        "Two-channel colocalization (Pearson, Manders, Costes, Li ICQ) of the Setup's detector windows, with an interactive intensity scatter gate. Outside the numbered steps because it compares two channels rather than building a per-pixel map; a channel registration error reads as anti-correlation, so align first.",
    ),
    (
        "pixel_intensity",
        "microscopy/img_pixel_intensity",
        "1. Intensity",
        "Per-pixel intensity map; creates the standard imaging HDF5 (with source back-reference).",
    ),
    (
        "pixel_nb",
        "microscopy/img_pixel_nb",
        "2. Number & Brightness",
        "Per-pixel Number (N) and Brightness (B); adds fields to the imaging HDF5.",
    ),
    (
        "pixel_micro_time",
        "microscopy/img_pixel_micro_time",
        "3. Mean Micro-Time",
        "Per-pixel mean micro-time (arrival time, ns) per detector window; adds fields to the imaging HDF5.",
    ),
    (
        "calibration",
        "microscopy/img_calibration",
        "4. IRF & BG",
        "Optional: per-detector IRF file + background (kHz); transferred to Phasor and MLE. Skippable.",
    ),
    (
        "pixel_phasor",
        "microscopy/img_pixel_phasor",
        "5. Phasor-FLIM",
        "Per-pixel phasor (g, s) maps and phasor plot; adds fields to the imaging HDF5.",
    ),
    (
        "pixel_mle",
        "microscopy/img_pixel_mle",
        "6. Pixel-wise MLE",
        "Pixel-wise MLE lifetime analysis; adds fields to the imaging HDF5.",
    ),
    (
        "clsm_draw",
        "microscopy/clsm",
        "CLSM Draw",
        "Interactive CLSM pixel selection, ROI drawing and decay extraction; opens imaging HDF5 (via source back-reference).",
    ),
    (
        "spot_finder",
        "microscopy/spot_finder",
        "Spot Finder",
        "Find the regions — molecules, beads, objects — and write them, with their pixels, into each measurement's container.",
    ),
    (
        "molecule_mle",
        "microscopy/region_mle",
        "Region MLE",
        "Lifetime MLE per region, on the regions the Spot Finder found.",
    ),
)
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
LIST_MAX_W = 300.0
#: The role the list draws a separator above (the Qt list's rule before the tools outside the numbered pipeline).
SEPARATOR_BEFORE = "clsm_draw"


def label(text):
    return tr(text, context="ImagingToolsTool")


class ImagingToolsApp(ImApp):
    """The imaging pipeline list on the left, the chosen step (built on first use) on the right, one shared context."""

    #: The steps a tool's own Next / Previous walk, in pipeline order (the Qt tool's order, less the tools that left).
    PIPELINE_ORDER = (
        "browser",
        "frc",
        "pixel_intensity",
        "pixel_nb",
        "pixel_micro_time",
        "calibration",
        "pixel_phasor",
        "pixel_mle",
    )
    ANALYSIS_ROLES = ("pixel_intensity", "pixel_nb", "pixel_micro_time", "pixel_phasor")

    def __init__(self, client=None, factories=None, mmfdb_db=None, mmfdb_session=None):
        self.window_size = window_size(
            json.loads((HERE / "app.view.json").read_text(encoding="utf-8")), (1100, 720)
        )
        self.entries = [
            SimpleNamespace(id=r, label=name, icon=entry_icon({}, p), description=tip, alias=r)
            for r, p, name, tip in PANELS
        ]
        self.children = {}
        self.error = ""
        self.child_box = (220.0, 80.0, 700.0, 550.0)
        self.item_rects: dict[str, tuple] = {}
        self._painter = None
        self._builder = BackgroundBuild(wake=self.request_frame)
        self.client = client or DetectorSetupClient()
        self.factories = factories
        self.selected = "browser"
        self.search = ""
        self.status = "Ready"
        # Without a live or last-used definition the tools use what Setup shows a new user (its defaults), not a
        # ch-0 fallback window that Setup never displays.
        self.setup = copy.deepcopy(self.client.get_current()) or default_settings()
        self._pipeline = {"source": "", "hdf5": ""}
        self._calibration = {}
        self._saved_children = {}
        self._mmfdb_db = mmfdb_db
        self._mmfdb_session = mmfdb_session
        self._mmfdb_source_artifact_id = ""
        self._ff_queue = []
        self._precompute_queue = []
        self._precomputing = False
        #: Apps made by the background build of the first frame, waiting for :meth:`_build_child` to wire them.
        self._prebuilt = {}
        self.help = self.help_window = EmTkHelpWindow(
            title="Imaging Tools - Help",
            resource=HERE / "help.md",
            owner=self,
            on_start_guide=self.start_guide,
            size=(700.0, 480.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key),
        )
        super().__init__(self.render, continuous=False)

    # -- the hosted step ------------------------------------------------------------------------- #
    @property
    def child(self):
        """The app of the selected step (``None`` before it is built)."""
        return self.children.get(self.selected)

    @property
    def building(self):
        """Whether the shown step's app is being made in the background."""
        return self._builder.busy

    @property
    def native_layouts(self):
        """The dock layouts of the built steps, keyed ``role`` / ``role/name``, for the shell to persist."""
        layouts = {}
        for role, child in self.children.items():
            for name, manager in getattr(child, "native_layouts", {}).items():
                layouts[role + "/" + name] = manager
            if hasattr(child, "docks"):
                layouts[role] = child.docks
        return layouts

    def start_guide(self):
        """Start the guided tour of the pipeline window."""
        self.tour.start()

    def show_help(self):
        """Open the pipeline window's help."""
        self.help_window.show()

    def draw_opening(self):
        """The "Opening" placeholder in the tool area, while the shown step is made."""
        if self.building and self.child is None:
            entry = next((e for e in self.entries if e.id == self.selected), None)
            draw_opening(entry.label if entry else str(self.selected), self.child_box, "Hub opening")

    def next_frame_in(self):
        """The sooner of this window's and the shown step's next due frame."""
        own = super().next_frame_in()
        child = self.child.next_frame_in() if self.child is not None else None
        due = [t for t in (own, child) if t is not None]
        return min(due) if due else None

    # -- the tools ------------------------------------------------------------------------------- #
    def factory(self, role):
        if self.factories is not None:
            return self.factories.get(role)
        row = next((p for p in PANELS if p[0] == role), None)
        if row is None:
            return None
        manifest = ROOT / row[1] / "manifest.json"
        return json.loads(manifest.read_text()).get("entrypoints", {}).get("emtk")

    def goto_role(self, role):
        """Select a tool, building its native app on first use with the shared context applied."""
        if role not in {row[0] for row in PANELS}:
            return False
        self.selected = role
        self.error = ""
        self.tour.notify_used("entry:" + role)
        if role in self.children:
            return True
        try:
            child = self._build_child(role)
            if child is None:
                self.error = label("Native migration pending for this tool.")
                return False
            if role == "setup":
                self.set_setup(child.get_settings())
            else:
                self._apply_context(child)
            self.autorun_role(role)
            entry = next(e for e in self.entries if e.id == role)
            self.status = f"{entry.label}: ready."
            return True
        except Exception as exc:
            self.error = str(exc)
            self.status = self.error
            return False

    def _construct_child(self, role):
        """Import and construct the native app of *role* (``None`` without one); may run on the build thread."""
        factory = self.factory(role)
        if factory is None:
            return None
        if isinstance(factory, str):
            module, name = factory.split(":")
            factory = getattr(importlib.import_module(module), name)
        kwargs = (
            {"settings": self.setup or None, "on_changed": self.set_setup}
            if role == "setup"
            else {"coordinator": self}
        )
        return factory(**kwargs)

    def _build_child(self, role):
        """Build the native app of *role* (once), wired to the hub; ``None`` when it has no native app."""
        if role in self.children:
            return self.children[role]
        if role in self._prebuilt:
            child, exc = self._prebuilt.pop(role)
            if exc is not None:
                raise exc
        else:
            child = self._construct_child(role)
        if child is None:
            return None
        child.set_frame_request_callback(self.request_frame)
        child._coordinator = self
        child._pipeline_role = role
        model = getattr(child, "model", None)
        if model is not None:
            model.pipeline_sink = self.set_pipeline
            if hasattr(model, "publish"):
                model.publish = self.set_calibration
        self.children[role] = child
        if role in self._saved_children:
            restore = getattr(child, "restore_settings", None)
            if restore:
                restore(copy.deepcopy(self._saved_children[role]))
        if role != "setup":
            # The shared detector setup and calibration reach every tool as it is built, also one the background
            # precompute builds before it is ever opened; otherwise it computes on the ch-0 fallback window and
            # keeps that result when opened later (opening an existing tool applies no context).
            for method, payload in (
                ("apply_setup_settings", self.setup),
                ("apply_calibration", self._calibration),
            ):
                apply = getattr(child, method, None)
                if callable(apply) and payload:
                    apply(copy.deepcopy(payload))
        return child

    select = goto_role  # the hub base's name for it

    def _apply_context(self, child):
        for method, payload in (
            ("apply_setup_settings", self.setup),
            ("apply_pipeline_context", self._pipeline),
            ("apply_calibration", self._calibration),
        ):
            apply = getattr(child, method, None)
            if callable(apply) and payload:
                apply(copy.deepcopy(payload))
        self._bind_model_to_mmfdb(getattr(child, "model", None))

    def _bind_model_to_mmfdb(self, model):
        bind = getattr(model, "bind_mmfdb", None)
        if bind and self._mmfdb_source_artifact_id and self._mmfdb_session:
            from mmfdb.security.auth import AuthenticatedPrincipal

            bind(
                self._mmfdb_db,
                source_artifact_id=self._mmfdb_source_artifact_id,
                principal=AuthenticatedPrincipal(
                    self._mmfdb_session.user_id, self._mmfdb_session.is_admin
                ),
            )

    def set_setup(self, settings=None):
        if not isinstance(settings, dict):
            page = self.children.get("setup")
            if page is None:
                return
            settings = page.get_settings()
        self.setup = copy.deepcopy(settings)
        self.client.set_current(self.setup)
        for role, child in self.children.items():
            if role != "setup":
                self._apply_context(child)
        self.precompute()
        self.request_frame()

    def set_pipeline(self, source=None, hdf5=None):
        new_source = bool(source) and str(source) != self._pipeline["source"]
        if source:
            if new_source:
                self._mmfdb_source_artifact_id = ""
                if self._mmfdb_db is not None and self._mmfdb_session is not None:
                    from mmfdb.provenance.result_registry import register_raw_measurement

                    from chisurf.core.transform.mmfdb import require_authenticated_session

                    require_authenticated_session(self._mmfdb_db, self._mmfdb_session)
                    self._mmfdb_source_artifact_id = register_raw_measurement(
                        str(source),
                        metadata={"source_path": str(source), "integration": "imaging_tools"},
                        db=self._mmfdb_db,
                        session=self._mmfdb_session,
                    )
            self._pipeline["source"] = str(source)
        if hdf5:
            self._pipeline["hdf5"] = str(hdf5)
        for role, child in self.children.items():
            if role != "setup":
                self._apply_pipeline_quietly(role, child)
                self._bind_model_to_mmfdb(getattr(child, "model", None))
        if new_source:
            self.precompute()
        self.request_frame()

    def _apply_pipeline_quietly(self, role, child):
        """Hand a child the source and HDF5; the analysis steps are *selected*, the precompute queue runs them one by one."""
        model = getattr(child, "model", None)
        idle = not (
            getattr(getattr(child, "job", None), "busy", False) or getattr(model, "busy", False)
        )
        if (
            idle
            and role in self.ANALYSIS_ROLES
            and hasattr(model, "apply_pipeline_context")
            and hasattr(child, "start")
        ):
            model.apply_pipeline_context(copy.deepcopy(self._pipeline))
            return
        apply = getattr(child, "apply_pipeline_context", None)
        if apply:
            apply(copy.deepcopy(self._pipeline))

    # -- background precompute (the Qt hub's _start_background_compute) -------------------------------------------------- #
    def precompute(self):
        """Queue intensity, N&B, micro-time and phasor to compute in the background, one after the other.

        Called when a new source arrives and when the detector setup changes (the windows changed, so the maps
        are stale); a step whose inputs did not change is skipped when its turn comes. The steps share one
        imaging HDF5, so they run in series, each started from the frame after the previous finished.
        """
        if not self._pipeline["source"]:
            return
        self._precompute_queue = list(self.ANALYSIS_ROLES)
        self._precomputing = True
        self.status = label("Computing imaging steps in background ...")

    def precompute_pending(self):
        """The steps still waiting for (or in) their background compute."""
        return list(self._precompute_queue)

    def _any_child_busy(self):
        for child in self.children.values():
            job = getattr(child, "job", None)
            model = getattr(child, "model", None)
            if getattr(job, "busy", False) or getattr(model, "busy", False):
                return True
        return False

    def _poll_children(self):
        """Deliver the results of background jobs; a tool that is not on screen never draws, so nobody else would."""
        for child in self.children.values():
            job = getattr(child, "job", None)
            if job is None:
                continue
            if job.busy and callable(getattr(job, "poll", None)):
                job.poll()
            # Mirror the job into ``model.busy`` in both directions. Setting it only while the job ran left it True for
            # good when the open tool's own frame delivered the result (the Spot Finder's Load example / Detect): every
            # later precompute then waited on a tool that was idle, and Run all stalled.
            model = getattr(child, "model", None)
            if model is not None and (job.busy or getattr(model, "busy", False)):
                model.busy = job.busy

    def animating(self):
        return bool(
            super().animating()
            or self.building
            or (self.child is not None and self.child.animating())
            or self._precompute_queue
            or self._precomputing
        )

    def _precompute_tick(self):
        """Start the next queued step when no tool is computing."""
        self._poll_children()
        if not self._precompute_queue:
            if self._precomputing and not self._any_child_busy():
                self._precomputing = False
                if not self.status.endswith("failed"):
                    self.status = label("Imaging steps ready.")
            return
        if self._any_child_busy():
            return
        role = self._precompute_queue.pop(0)
        try:
            child = self._build_child(role)
            model = getattr(child, "model", None)
            if child is None or model is None or not hasattr(child, "start"):
                return
            flush = getattr(child, "_flush_pending", None)
            if flush:
                flush()
            self._apply_pipeline_quietly(role, child)
            if model.filename and model.needs_recompute():
                self.status = f"{role}: computing in the background ..."
                self._precomputing = True
                child.start("compute_job")
        except Exception as exc:
            self.status = f"Background compute of {role} failed: {exc}"
        self.request_frame()

    def set_calibration(self, calibration):
        self._calibration = copy.deepcopy(calibration or {})
        for child in self.children.values():
            apply = getattr(child, "apply_calibration", None)
            if apply:
                apply(copy.deepcopy(self._calibration))
        self.request_frame()

    def advance_from(self, role):
        self._step(role, 1)

    def previous_from(self, role):
        self._step(role, -1)

    # -- the Back / Next / fast-forward stepper (the Qt shell's: the list order, up to the rule) ---------------------------- #
    def list_roles(self):
        """The list's tools in order (the entries the stepper walks)."""
        return [e.id for e in self.entries]

    def step_list(self, direction):
        """Move one tool down (+1) or up (-1) the list; the numbered steps compute on arrival when a source is known."""
        roles = self.list_roles()
        at = roles.index(self.selected) if self.selected in roles else 0
        target = at + direction
        if 0 <= target < len(roles):
            self.goto_role(roles[target])
            return True
        return False

    def fast_forward_queue(self):
        """The tools from the open one to the end of the numbered pipeline (the Qt queue stops at the separator)."""
        roles = self.list_roles()
        at = roles.index(self.selected) if self.selected in roles else 0
        end = roles.index(SEPARATOR_BEFORE)
        return roles[at:end]

    def toggle_fast_forward(self):
        """Start walking the rest of the pipeline one step at a time, each when the previous has finished; again to stop."""
        if self._ff_queue:
            self._ff_queue = []
            self.status = "Fast-forward stopped: finishing this step"
            return
        queue = self.fast_forward_queue()
        self._ff_queue = queue[1:] if len(queue) > 1 else []
        self.status = (
            f"Fast-forward: {len(self._ff_queue)} step(s) to go"
            if self._ff_queue
            else "Nothing to fast-forward"
        )
        self.request_frame()

    def _child_busy(self):
        child = self.child
        job = getattr(child, "job", None)
        model = getattr(child, "model", None)
        return bool(getattr(job, "busy", False) or getattr(model, "busy", False))

    def _fast_forward_tick(self):
        if self._ff_queue and not self._child_busy():
            self.goto_role(self._ff_queue.pop(0))
            self.status = (
                f"Fast-forward: {len(self._ff_queue)} step(s) to go"
                if self._ff_queue
                else "Fast-forward finished"
            )
            self.request_frame()

    def _step(self, role, direction):
        if role in self.PIPELINE_ORDER:
            index = self.PIPELINE_ORDER.index(role) + direction
            if 0 <= index < len(self.PIPELINE_ORDER):
                self.goto_role(self.PIPELINE_ORDER[index])

    def autorun_role(self, role):
        child = self.children.get(role)
        model = getattr(child, "model", None)
        job = getattr(child, "job", None)
        if (
            role in self.ANALYSIS_ROLES
            and self._pipeline["source"]
            and model is not None
            and not getattr(model, "_columns", None)
            and not getattr(job, "busy", False)
        ):
            start = getattr(child, "start", None)
            if start:
                start("compute_job")

    def export_settings(self):
        states = copy.deepcopy(self._saved_children)
        for role, child in self.children.items():
            export = getattr(child, "export_settings", None)
            if export:
                states[role] = export()
        return {
            "selected": self.selected,
            "search": self.search,
            "setup": copy.deepcopy(self.setup),
            "pipeline": dict(self._pipeline),
            "calibration": copy.deepcopy(self._calibration),
            "children": states,
        }

    def restore_settings(self, data):
        self._saved_children = copy.deepcopy(data.get("children", {}))
        self.search = str(data.get("search", ""))
        self.set_setup(data.get("setup", self.setup))
        self.set_pipeline(**data.get("pipeline", {}))
        self.set_calibration(data.get("calibration", {}))
        self.goto_role(data.get("selected", "browser"))

    def close(self):
        self._prebuilt.update(self._builder.collect(wait=True) or {})
        for child, _exc in self._prebuilt.values():  # made for the first frame, never shown
            if callable(getattr(child, "close", None)):
                child.close()
        self._prebuilt.clear()
        for child in self.children.values():
            model = getattr(child, "model", None)
            flush = getattr(model, "flush_to_hdf5", None)
            try:
                if flush:
                    flush()
            except Exception as exc:
                self.error = str(exc)
            close = getattr(child, "close", None)
            if close:
                close()
        self.help.close()

    # -- frames -------------------------------------------------------------------------------------- #
    def _prebuild(self):
        """Make the tools the first frame opens (the setup when none is stored, and the selected tool) on a worker
        thread; whether they are all ready to be wired in."""
        built = self._builder.collect()
        if built is not None:
            self._prebuilt.update(built)
        if self._builder.busy:
            return False
        roles = (["setup"] if not self.setup and "setup" not in self.children else []) + [
            self.selected
        ]
        missing = [
            r for r in dict.fromkeys(roles) if r not in self.children and r not in self._prebuilt
        ]
        return not self._builder.start(
            {r: (lambda r=r: self._construct_child(r)) for r in missing},
            name="chisurf-imaging-tools",
        )

    def draw(self, painter, x, y, w, h):
        self._painter = painter
        if self.child is None and not self.error and self._prebuild():
            if not self.setup and "setup" not in self.children:
                selected = self.selected
                self.goto_role("setup")
                self.selected = selected
                self.error = ""
            self.goto_role(self.selected)
        super().draw(painter, x, y, w, h)
        self._painter = None

    def visible_entries(self):
        needle = self.search.casefold()
        return [e for e in self.entries if needle in (e.label + " " + e.description).casefold()]

    def render(self):
        vp = im.get_main_viewport()
        width, height = vp.size
        left = min(LIST_MAX_W, max(215.0, width * 0.24))
        self.item_rects.clear()
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((left, height), im.Cond.ALWAYS)
        if im.begin(label("Imaging Tools"), flags=im.WindowFlags.NO_RESIZE):
            # The steps scroll under the search field; Back/Next below keep their measured room.
            _, self.search = im.begin_filtered_list(
                "imaging_steps",
                self.search,
                label("Search..."),
                stretch=True,
                tooltip=label("Filter imaging tools by name or description."),
            )
            self.item_rects["search"] = im.get_item_rect()
            first = last = None
            shown = self.visible_entries()
            for entry in shown:
                if entry.id == SEPARATOR_BEFORE and first is not None:
                    im.separator()
                available = bool(self.factory(entry.id))
                title = label(entry.label) + ("" if available else " - " + label("pending"))
                if im.selectable(title, self.selected == entry.id, icon=entry.icon):
                    self.goto_role(entry.id)
                im.set_item_tooltip(
                    label(entry.description)
                    + ("" if available else " " + label("Native migration pending for this tool."))
                )
                rect = im.get_item_rect()
                self.item_rects["entry:" + entry.id] = rect
                first, last = first or rect, rect
            if first is not None:
                self.item_rects["navigation"] = (
                    first[0],
                    first[1],
                    first[2],
                    last[1] + last[3] - first[1],
                )
            if not shown:
                im.text_wrapped(label("No tool matches the search."))
            im.end_filtered_list()
            im.separator()
            roles = self.list_roles()
            at = roles.index(self.selected) if self.selected in roles else 0
            im.begin_disabled(at <= 0)
            if im.button(label("Back")):
                self.step_list(-1)
            im.end_disabled()
            im.set_item_tooltip(label("Go to the previous tool in the list."))
            self.item_rects["previous"] = im.get_item_rect()
            im.same_line()
            im.begin_disabled(at >= len(roles) - 1)
            if im.button(label("Next")):
                self.step_list(1)
                self.tour.notify_used("next")
            im.end_disabled()
            im.set_item_tooltip(
                label(
                    "Go to the next tool in the list; the numbered steps compute on arrival when a source is known."
                )
            )
            self.item_rects["next"] = im.get_item_rect()
            im.same_line()
            numbered = roles[: roles.index(SEPARATOR_BEFORE)]
            im.begin_disabled(
                not (
                    self.selected in numbered
                    and (len(self.fast_forward_queue()) > 1 or self._ff_queue)
                )
            )
            if im.button(label("Stop") if self._ff_queue else label("Run all")):
                self.toggle_fast_forward()
            im.end_disabled()
            im.set_item_tooltip(
                label(
                    "Walk the rest of the numbered pipeline, each step when the previous has finished; press again to stop."
                )
            )
            self.item_rects["fast_forward"] = im.get_item_rect()
            if im.button(label("Help")):
                self.help.show()
            im.set_item_tooltip(
                label("Read how detector setup, calibration and shared HDF5 are propagated.")
            )
            self.item_rects["help"] = im.get_item_rect()
            im.same_line()
            if im.button(label("Guide")):
                self.tour.start()
            im.set_item_tooltip(label("Walk through the imaging workflow."))
            self.item_rects["guide"] = im.get_item_rect()
            im.separator()
            im.text_wrapped(self.status)
        im.end()
        entry = next((e for e in self.entries if e.id == self.selected), None)
        wrap = max(width - left - 16.0, 50.0)
        source = label("Source") + ": " + (Path(self._pipeline["source"]).name or "-")
        hdf5 = "HDF5: " + (Path(self._pipeline["hdf5"]).name or "-")
        texts = [
            entry.label if entry else "",
            entry.description if entry else label("Select a tool on the left."),
            source + "    " + hdf5,
            self.error,
        ]
        header_h = max(
            80.0, 12.0 + sum(im.calc_text_size(t, wrap_width=wrap)[1] + 4.0 for t in texts if t)
        )
        im.set_next_window_pos((left, 0), im.Cond.ALWAYS)
        im.set_next_window_size((width - left, header_h), im.Cond.ALWAYS)
        if im.begin(
            "Imaging tool description", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
        ):
            if entry:
                im.text_unformatted(label(entry.label))
                im.text_wrapped(label(entry.description))
            im.text_unformatted(source)
            im.set_item_tooltip(
                self._pipeline["source"] or label("Choose a photon image in Browser.")
            )
            self.item_rects["source"] = im.get_item_rect()
            im.same_line()
            im.text_unformatted("    " + hdf5)
            im.set_item_tooltip(
                self._pipeline["hdf5"] or label("Intensity creates the shared imaging HDF5.")
            )
            if self.error:
                im.text_wrapped(self.error)
            self.item_rects["description"] = im.get_item_rect()
        im.end()
        self.child_box = (left, header_h, max(1.0, width - left), max(1.0, height - header_h))
        if self.child:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        self.draw_opening()
        self.help.draw((0, 0, width, height))
        self.tour.draw(width, height)
        self._fast_forward_tick()
        self._precompute_tick()


    # -- events: the shown step gets the pointer inside its box, every key, the wheel and file drops ------------- #
    def _inside(self, x, y):
        bx, by, bw, bh = self.child_box
        return bx <= x < bx + bw and by <= y < by + bh

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        super().pointer_press(x, y, button, modifiers, clicks)
        if self.child and self._inside(x, y):
            self.child.pointer_press(
                x - self.child_box[0], y - self.child_box[1], button, modifiers, clicks
            )

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        if self.child:
            self.child.pointer_release(x - self.child_box[0], y - self.child_box[1], button, modifiers)

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if self.child:
            self.child.pointer_move(x - self.child_box[0], y - self.child_box[1], buttons, modifiers)

    def wheel(self, x, y, steps, modifiers=0):
        super().wheel(x, y, steps, modifiers)
        if self.child and self._inside(x, y):
            self.child.wheel(x - self.child_box[0], y - self.child_box[1], steps, modifiers)

    def key(self, key, text="", modifiers=0):
        own = super().key(key, text, modifiers)  # the window's own help and tour read Escape from its io
        taken = self.child.key(key, text, modifiers) if self.child else own
        if not taken and key in (keys.KEY_UP, keys.KEY_DOWN):
            # Up and Down step the list while no field of the shown step wants them
            if self.step_list(-1 if key == keys.KEY_UP else 1):
                self.request_frame()
                return True
        return taken

    def files_dropped(self, paths):
        """Hand a dropped file to the shown step."""
        for name in ("files_dropped", "on_files_dropped", "on_paths_dropped"):
            handler = getattr(self.child, name, None) if self.child is not None else None
            if callable(handler):
                result = handler(list(paths))
                return True if result is None else bool(result)
        return False

    on_files_dropped = files_dropped
    on_paths_dropped = files_dropped


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return ImagingToolsApp(**kwargs)
