"""Native imaging coordinator; child factories are resolved from their manifests."""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.i18n import tr

from chisurf.emtk.help_guide import EmTkHelpWindow

from .client import DetectorSetupClient

# Keep every Qt route, including tools whose native migration is still pending.
PANELS = (
    (
        "setup",
        "core/setup_channel_definition",
        "Setup",
        "Define shared detector channels and PIE windows.",
    ),
    (
        "browser",
        "tttr/tttr_image_browser",
        "Browser",
        "Select photon images and hand the source to the imaging pipeline.",
    ),
    ("drift", "microscopy/img_drift", "Drift", "Align frames before calculating per-pixel maps."),
    ("frc", "microscopy/img_frc", "Resolution", "Measure resolution by Fourier ring correlation."),
    ("flow", "microscopy/img_flow", "Flow", "Map sample velocity by image correlation."),
    (
        "tracking",
        "microscopy/img_tracking",
        "Tracking",
        "Follow particles and estimate their diffusion.",
    ),
    (
        "pixel_intensity",
        "microscopy/img_pixel_intensity",
        "1. Intensity",
        "Create intensity maps and the shared imaging HDF5.",
    ),
    (
        "pixel_nb",
        "microscopy/img_pixel_nb",
        "2. Number & Brightness",
        "Add molecular number and brightness to the shared image.",
    ),
    (
        "pixel_micro_time",
        "microscopy/img_pixel_micro_time",
        "3. Mean Micro-Time",
        "Add mean photon arrival times per detector window.",
    ),
    (
        "calibration",
        "microscopy/img_calibration",
        "4. IRF & BG",
        "Optional per-detector IRF and background calibration.",
    ),
    (
        "pixel_phasor",
        "microscopy/img_pixel_phasor",
        "5. Phasor-FLIM",
        "Add calibrated lifetime phasor maps.",
    ),
    (
        "pixel_mle",
        "microscopy/img_pixel_mle",
        "6. Pixel-wise MLE",
        "Fit lifetime by maximum likelihood per pixel.",
    ),
    (
        "clsm_draw",
        "microscopy/clsm",
        "CLSM Draw",
        "Draw regions and extract decays from photon images.",
    ),
    (
        "spot_finder",
        "microscopy/spot_finder",
        "Spot Finder",
        "Find regions and persist their pixels in measurement containers.",
    ),
    (
        "molecule_mle",
        "microscopy/region_mle",
        "Region MLE",
        "Fit lifetimes in the regions found by Spot Finder.",
    ),
    (
        "psf",
        "microscopy/psf_determination",
        "PSF Determination",
        "Detect beads and fit the three-dimensional point spread function.",
    ),
)
ROOT = Path(__file__).resolve().parents[3]
ICONS = {
    "setup": "🧭",
    "browser": "📂",
    "drift": "🎯",
    "frc": "◎",
    "flow": "🌊",
    "tracking": "🐜",
    "pixel_intensity": "☀",
    "pixel_nb": "✨",
    "pixel_micro_time": "◷",
    "calibration": "▦",
    "pixel_phasor": "◐",
    "pixel_mle": "🗺",
    "clsm_draw": "✎",
    "spot_finder": "🎯",
    "molecule_mle": "💠",
    "psf": "🔭",
}


def label(text):
    return tr(text, context="ImagingToolsTool")


class ImagingToolsApp(ImApp):
    PIPELINE_ORDER = tuple(row[0] for row in PANELS[1:12])
    ANALYSIS_ROLES = ("pixel_intensity", "pixel_nb", "pixel_micro_time", "pixel_phasor")

    def __init__(self, client=None, factories=None, mmfdb_db=None, mmfdb_session=None):
        self.client = client or DetectorSetupClient()
        self.factories = factories
        self.children = {}
        self.selected = "browser"
        self.search = ""
        self.error = ""
        self.setup = copy.deepcopy(self.client.get_current())
        self._pipeline = {"source": "", "hdf5": ""}
        self._calibration = {}
        self._saved_children = {}
        self._mmfdb_db = mmfdb_db
        self._mmfdb_session = mmfdb_session
        self._mmfdb_source_artifact_id = ""
        self._painter = None
        self.child_box = (250.0, 100.0, 950.0, 650.0)
        self.help = EmTkHelpWindow(
            title="Imaging Tools — Help", resource=Path(__file__).with_name("help.md"), owner=self
        )
        super().__init__(self.render, continuous=False)

    def factory(self, role):
        if self.factories is not None:
            return self.factories.get(role)
        row = next((p for p in PANELS if p[0] == role), None)
        if row is None:
            return None
        manifest = ROOT / row[1] / "manifest.json"
        return json.loads(manifest.read_text()).get("entrypoints", {}).get("emtk")

    @property
    def child(self):
        return self.children.get(self.selected)

    def goto_role(self, role):
        if role not in {row[0] for row in PANELS}:
            return False
        self.selected = role
        self.error = ""
        if role in self.children:
            return True
        factory = self.factory(role)
        if factory is None:
            self.error = label("Native migration pending for this tool.")
            return False
        try:
            if isinstance(factory, str):
                module, name = factory.split(":")
                factory = getattr(importlib.import_module(module), name)
            kwargs = (
                {"settings": self.setup or None, "on_changed": self.set_setup}
                if role == "setup"
                else {"coordinator": self}
            )
            child = factory(**kwargs)
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
            if role == "setup":
                self.set_setup(child.get_settings())
            else:
                self._apply_context(child)
            self.autorun_role(role)
            return True
        except Exception as exc:
            self.error = str(exc)
            return False

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
        self.request_frame()

    def set_pipeline(self, source=None, hdf5=None):
        if source:
            if str(source) != self._pipeline["source"]:
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
                apply = getattr(child, "apply_pipeline_context", None)
                if apply:
                    apply(copy.deepcopy(self._pipeline))
                self._bind_model_to_mmfdb(getattr(child, "model", None))
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

    @property
    def native_layouts(self):
        layouts = {}
        for role, child in self.children.items():
            if hasattr(child, "docks"):
                layouts[role] = child.docks
            for name, manager in getattr(child, "native_layouts", {}).items():
                layouts[role + "/" + name] = manager
        return layouts

    def draw(self, painter, x, y, w, h):
        self._painter = painter
        if self.child is None and not self.error:
            if not self.setup and "setup" not in self.children:
                selected = self.selected
                self.goto_role("setup")
                self.selected = selected
                self.error = ""
            self.goto_role(self.selected)
        super().draw(painter, x, y, w, h)
        self._painter = None

    def render(self):
        w, h = im.get_main_viewport().size
        left = min(260.0, w * 0.28)
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((left, h), im.Cond.ALWAYS)
        if im.begin(label("Imaging Tools"), flags=im.WindowFlags.NO_RESIZE):
            im.text_unformatted(label("Imaging workflow"))
            im.separator()
            im.set_next_item_width(-1)
            _, self.search = im.input_text(label("Search"), self.search)
            im.set_item_tooltip(label("Filter imaging tools by name or description."))
            for role, path, name, tip in PANELS:
                if self.search.casefold() not in (name + " " + tip).casefold():
                    continue
                if role == "clsm_draw":
                    im.separator()
                available = bool(self.factory(role))
                title = (
                    ICONS[role]
                    + " "
                    + label(name)
                    + (" · " + label("pending") if not available else "")
                )
                if im.selectable(title, self.selected == role, size=(0, 32)):
                    self.goto_role(role)
                im.set_item_tooltip(
                    label(tip)
                    + (
                        " " + label("Native migration pending for this tool.")
                        if not available
                        else ""
                    )
                )
        im.end()
        im.set_next_window_pos((left, 0), im.Cond.ALWAYS)
        im.set_next_window_size((w - left, 72), im.Cond.ALWAYS)
        if im.begin(
            "Imaging workflow", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
        ):
            for text, tip, action in (
                (
                    "Previous",
                    "Go to the previous imaging step.",
                    lambda: self.previous_from(self.selected),
                ),
                (
                    "Next",
                    "Go to the next imaging step and reuse the current source.",
                    lambda: self.advance_from(self.selected),
                ),
                (
                    "Help",
                    "Read how detector setup, calibration and shared HDF5 are propagated.",
                    self.help.show,
                ),
            ):
                if im.button(label(text)):
                    action()
                im.set_item_tooltip(label(tip))
                im.same_line()
            im.new_line()
            im.text_unformatted(
                label("Source") + ": " + (Path(self._pipeline["source"]).name or "—")
            )
            im.set_item_tooltip(
                self._pipeline["source"] or label("Choose a photon image in Browser.")
            )
            im.text_unformatted("HDF5: " + (Path(self._pipeline["hdf5"]).name or "—"))
            im.set_item_tooltip(
                self._pipeline["hdf5"] or label("Intensity creates the shared imaging HDF5.")
            )
            if self.error:
                im.text_wrapped(self.error)
        im.end()
        self.child_box = (left, 72.0, max(1.0, w - left), max(1.0, h - 72.0))
        if self.child:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        self.help.draw((0, 0, w, h))

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
            self.child.pointer_release(
                x - self.child_box[0], y - self.child_box[1], button, modifiers
            )

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if self.child:
            self.child.pointer_move(
                x - self.child_box[0], y - self.child_box[1], buttons, modifiers
            )

    def wheel(self, x, y, steps, modifiers=0):
        super().wheel(x, y, steps, modifiers)
        if self.child and self._inside(x, y):
            self.child.wheel(x - self.child_box[0], y - self.child_box[1], steps, modifiers)

    def key(self, key, text="", modifiers=0):
        return (
            self.child.key(key, text, modifiers)
            if self.child
            else super().key(key, text, modifiers)
        )

    def animating(self):
        return super().animating() or any(child.animating() for child in self.children.values())

    def next_frame_in(self):
        values = [super().next_frame_in()] + [
            child.next_frame_in() for child in self.children.values()
        ]
        return min((v for v in values if v is not None), default=None)

    def on_files_dropped(self, paths):
        handler = getattr(self.child, "on_files_dropped", None)
        return bool(handler and handler(paths))


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return ImagingToolsApp(**kwargs)
