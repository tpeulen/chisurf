"""Native six-step anisotropy workflow (emtk): forms from ``anisotropy_emtk.view.json``, the IRF plot, pure linked fits."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, _clean_html_text
from chisurf.plugins.emtk_layout import LabelColumn, button_row, labelled, layout_spec

from .model import NativeAnisotropyModel

HERE = Path(__file__).parent
VV_COLOUR, VH_COLOUR = (59, 120, 255), (255, 91, 91)
#: Below this width the two spectra stack instead of sitting side by side.
SIDE_BY_SIDE = 760.0
FILE_FIELDS = (
    ("irf_vv_path", "IRF VV"),
    ("irf_vh_path", "IRF VH"),
    ("data_vv_path", "Data VV"),
    ("data_vh_path", "Data VH"),
)
STACKED_FIELDS = (("irf_vv_path", "IRF VV/VH"), ("data_vv_path", "Data VV/VH"))
#: The tour target of each step that waits for a control, and the step it lives on.
TARGET_STEP = {"data_vv_path": 1, "load_data": 2, "g_factor": 3, "lifetime.add": 4, "create_fits": 5}


class AnisotropyApp(ImApp):
    def __init__(self, model=None):
        self.model = model or NativeAnisotropyModel()
        self.steps = json.loads((HERE.parent / "anisotropy.view.json").read_text())["sections"][0]["steps"]
        for step in self.steps:
            step.pop("icon", None)          # the Qt wizard's pictograms: emtk draws text
        if model is None:
            self.model.error(self.model.restore_preferences, {})   # the stored defaults the Qt wizard starts from
        self.step_index = 0
        self.plot_info = {}
        self.item_rects = {}
        panels = json.loads((HERE / "anisotropy_emtk.view.json").read_text())["panels"]
        self.panels = {name: layout_spec(copy.deepcopy(spec)) for name, spec in panels.items()}
        self.forms = {name: FormState() for name in panels}
        self.labels = {name: LabelColumn() for name in panels}
        self.dialog = None
        self.file_window = None
        self.file_action = ""
        self.last_dir = ""
        self.help_window = EmTkHelpWindow(
            title="Time-resolved anisotropy: Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=self.target_rect,
            owner=self,
            wait_for_controls=True,
            on_step_change=self.reveal_step,
        )
        for name, form in self.forms.items():
            form.on_used = (
                (lambda n, prefix=name: self.tour.notify_used(f"{prefix}.{n}"))
                if name in ("lifetime", "rotation")
                else self.tour.notify_used
            )
        self.docks = DockManager(
            Split("h", 0.22, Region("navigation"), Region("step")), name="tr_anisotropy"
        )
        self.docks.add_window(
            "navigation", "Anisotropy workflow", self.navigation, dock="navigation", closable=False
        )
        self.docks.add_window("step", "Workflow step", self.content, dock="step", closable=False)
        super().__init__(self.render, continuous=False)

    # -- settings, tour, files ----------------------------------------------------------------- #
    def restore_settings(self, settings):
        self.model.restore_preferences(settings)
        self.last_dir = str(settings.get("last_dir", "")) if isinstance(settings, dict) else ""
        try:
            self.step_index = max(0, min(int(settings.get("step_index", 0)), len(self.steps) - 1))
        except (TypeError, ValueError):
            self.step_index = 0

    def export_settings(self):
        return {**self.model.export_preferences(), "step_index": self.step_index, "last_dir": self.last_dir}

    def target_rect(self, key):
        return self.item_rects.get(key) or next(
            (f.rects[key] for f in self.forms.values() if key in f.rects), None
        )

    def reveal_step(self, index, step):
        key = EmTkGuidedTour._target_key(step.get("target"))
        self.step_index = TARGET_STEP.get(key, 0 if index == 0 else self.step_index)

    def select_step(self, index):
        self.step_index = max(0, min(int(index), len(self.steps) - 1))

    def choose(self, action):
        """Open the in-app file dialog for *action* (a path attribute, or one of the spectra / export actions)."""
        self.file_action = action
        saving = action in ("save_spectra", "export_irfs")
        title = {
            "save_spectra": "Save spectra",
            "load_spectra": "Load spectra",
            "export_irfs": "Export corrected IRFs",
        }.get(action, "Select polarized decay")
        filename = {"save_spectra": "anisotropy.spk.json", "export_irfs": "corrected_irfs.dat"}.get(action, "")
        filters = (
            "Spectra (*.spk.json *.json);;All files (*)"
            if "spectra" in action
            else "TCSPC data (*.dat *.txt *.csv *.npy *.thd *.pqres);;All files (*)"
        )
        self.dialog = FileDialog(
            title, mode="save" if saving else "open", filename=filename, filters=filters,
            directory=self.last_dir or None,
        )
        self.file_window = DialogWindow(title, size=(760, 540))

    def files_dropped(self, paths):
        """Host drop: a ``.json`` loads the spectra, other files fill the next empty path (IRF VV, IRF VH, Data VV, Data VH)."""
        paths = [str(p) for p in paths]
        if not paths:
            return False
        for path in paths:
            self.last_dir = str(Path(path).parent)
            if path.lower().endswith(".json"):
                self.model.error(self.model.load_spectra, path)
                self.select_step(4)
                continue
            fields = STACKED_FIELDS if self.model.stacked_files else FILE_FIELDS
            empty = [attr for attr, _ in fields if not getattr(self.model, attr)]
            attr = empty[0] if empty else fields[0][0]
            setattr(self.model, attr, path)
            self.select_step(1)
        if self.model.files_ready():
            self.tour.notify_used("data_vv_path")
        return True

    on_files_dropped = files_dropped

    def _file_chosen(self, result):
        action = self.file_action
        self.last_dir = str(Path(result[0]).parent)
        if action == "load_spectra":
            self.model.error(self.model.load_spectra, result[0])
        elif action == "save_spectra":
            self.model.error(self.model.save_spectra, result[0])
        elif action == "export_irfs":
            if self.model.error(self.model.export_irfs, result[0]) is not None:
                self.model.status = f"Exported the corrected IRFs to {result[0]}."
        else:
            setattr(self.model, action, str(result[0]))
            if self.model.files_ready():
                self.tour.notify_used("data_vv_path")

    # -- navigation ---------------------------------------------------------------------------- #
    def navigation(self, box):
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Explain polarized decays, background correction and parameter linking.")
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Follow a guided tour through the real wizard controls.")
        im.separator()
        for index, step in enumerate(self.steps):
            mark = "[x]" if self.model.step_complete(index) else "[ ]"
            if im.selectable(f"{mark} {step['title']}##anisotropy{index}", selected=self.step_index == index):
                self.select_step(index)
            im.set_item_tooltip(step.get("subtitle", step["title"]))
            self.item_rects[step["title"]] = im.get_item_rect()

    # -- one step -------------------------------------------------------------------------------- #
    def form(self, name, model=None):
        """Draw the panel *name*; its captions share one column."""
        spec, column = self.panels[name], self.labels[name]
        if not column.ready:
            column.measure([f["label"] for f in labelled(spec["sections"])])
        column.pad(spec["sections"])
        draw_form(spec, model or self.model, self.forms[name])

    def data_step(self):
        m = self.model
        fields = STACKED_FIELDS if m.stacked_files else FILE_FIELDS
        label_w = max(im.calc_text_size(label)[0] for _, label in fields) + 12.0
        browse_w = im.calc_text_size("Browse")[0] + 2 * im.get_style().frame_padding[0]
        spacing = im.get_style().item_spacing[0]
        field_w = max(160.0, min(520.0, im.get_content_region_avail()[0] - label_w - browse_w - 80.0 - 3 * spacing))
        im.text_disabled("Files")
        for attr, label in fields:
            im.text(label)
            im.same_line(label_w)
            im.set_next_item_width(field_w)
            changed, value = im.input_text(f"##{attr}", getattr(m, attr), elide_start=True)
            im.set_item_tooltip(f"Path to the {label} curve: type or paste it, press Enter, or use Browse.")
            self.item_rects[attr] = im.get_item_rect()
            if changed:
                setattr(m, attr, value)
                if m.files_ready():
                    self.tour.notify_used("data_vv_path")
            im.same_line()
            if im.button(f"Browse##browse_{attr}"):
                self.choose(attr)
            im.set_item_tooltip(f"Choose the {label} file from disk.")
            im.same_line()
            ok = bool(getattr(m, attr)) and Path(getattr(m, attr)).is_file()
            im.text("found" if ok else "missing")
            im.set_item_tooltip("Whether the file exists." if ok else "No file at this path yet.")
        im.spacing()
        self.form("reader")
        im.text_wrapped(
            "All required files are ready: continue to Normalize IRF."
            if m.files_ready()
            else "Select each required file before loading the data. Dropping files on the window fills the next empty path."
        )

    def normalization_step(self):
        m = self.model
        pressed = button_row(
            [
                {"label": "Load / reload data", "key": "load_data", "enabled": m.enabled("load_data"),
                 "tip": "Read all selected IRF and decay files, then initialize a background region."},
                {"label": "Export corrected IRFs", "key": "export_irfs", "enabled": m.enabled("export_irfs"),
                 "tip": "Save the two background-subtracted, intensity-matched IRFs with their time-bin width."},
            ],
            remember=lambda name: self.item_rects.__setitem__(name, im.get_item_rect()),
        )
        if pressed == "load_data":
            m.error(m.load_data)
            self.tour.notify_used("load_data")
        elif pressed == "export_irfs":
            self.choose("export_irfs")
        self.form("background")
        series = m.plot_series()
        if not series:
            im.text_wrapped("Load the data to see the IRFs.")
            return
        if implot.begin_plot("IRF normalization", size=(-1.0, -1.0)):
            implot.setup_axes("Channel", "IRF counts")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            for curve in series:
                y = np.asarray(curve["y"])
                base = VV_COLOUR if "VV" in curve["name"] else VH_COLOUR
                corrected = "corrected" in curve["name"]
                implot.set_next_line_style((*base, 255 if corrected else 110), 2.0 if corrected else 1.0)
                implot.plot_line(curve["name"], np.asarray(curve["x"]), np.where(y > 0, y, np.nan))
            positive = np.concatenate([np.asarray(c["y"])[np.asarray(c["y"]) > 0] for c in series])
            low = max(float(positive.min()) * 0.5, 1e-12) if positive.size else 1e-12
            high = max(float(positive.max()), low) * 1.1 if positive.size else 1.0
            region = implot.drag_rect(
                1, float(m.region_lb), low, float(m.region_ub), high,
                col=(70, 200, 90, 180), flags=implot.DRAG_TOOL_FLAGS_NO_FIT,
            )
            if region.modified:
                m.error(m.apply_region, int(round(region.x_min)), int(round(region.x_max)))
            mid = (low * high) ** 0.5
            self.plot_info = {          # where the plot and the box edges are on screen (tour, tests)
                "pos": implot.get_plot_pos(), "size": implot.get_plot_size(),
                "lb": implot.plot_to_pixels(float(m.region_lb), mid), "ub": implot.plot_to_pixels(float(m.region_ub), mid),
            }
            implot.end_plot()

    def corrections_step(self):
        self.form("corrections")
        im.text_wrapped(
            "g scales every anisotropy: a 10 % error in g is about 10 % in r(t). l1 and l2 compensate the "
            "polarization mixing of a high-aperture objective (zero on a low-NA setup)."
        )

    def components_step(self):
        m = self.model
        pressed = button_row(
            [
                {"label": "Save spectra", "key": "save_spectra", "tip": "Save the lifetime and rotation components as amplitude/value pairs in JSON."},
                {"label": "Load spectra", "key": "load_spectra", "tip": "Replace both component lists from a saved spectrum file."},
            ],
            remember=lambda name: self.item_rects.__setitem__(name, im.get_item_rect()),
        )
        if pressed == "save_spectra":
            if m.spk_path:
                m.error(m.save_spectra)
            else:
                self.choose("save_spectra")
        elif pressed == "load_spectra":
            self.choose("load_spectra")
        avail_w, avail_h = im.get_content_region_avail()
        side = avail_w >= SIDE_BY_SIDE
        width = (avail_w - im.get_style().item_spacing[0]) / 2 if side else avail_w
        height = max(200.0, avail_h if side else (avail_h - im.get_style().item_spacing[1]) / 2)
        for index, (name, table) in enumerate((("lifetime", m.lifetime), ("rotation", m.rotation))):
            if side and index:
                im.same_line()
            if im.begin_child(f"{name}_spectrum", (width, height)):
                im.push_id(name)                    # both tables name their buttons "add" and "delete"
                self.form(name, table)
                im.pop_id()
                self.item_rects[f"{name}.add"] = self.forms[name].rects.get("add")
            im.end_child()

    def finish_step(self):
        m = self.model
        im.text_wrapped(_clean_html_text(m.finish_html().split("<p style")[0]))
        if im.button("Create fits", ) and m.enabled("create_fits"):
            m.error(m.create_fits)
            self.tour.notify_used("create_fits")
        im.set_item_tooltip(
            "Create the VV, VH and global fits with configured spectra, corrected IRFs and linked parameters."
            if m.enabled("create_fits")
            else "Load the data and define both spectra first."
        )
        self.item_rects["create_fits"] = im.get_item_rect()
        if m.fit_groups:
            im.text("Created: " + ", ".join(str(getattr(g, "name", g)) for g in m.fit_groups))

    def content(self, box):
        m = self.model
        step = self.steps[self.step_index]
        im.text(step["title"])
        im.text_wrapped(step.get("subtitle", ""))
        im.separator()
        avail_w, avail_h = im.get_content_region_avail()
        bar = 34.0
        if im.begin_child("step_body", (avail_w, max(60.0, avail_h - bar))):
            if self.step_index == 0:
                im.text_wrapped(_clean_html_text(m.welcome_html()))
            elif self.step_index == 1:
                self.data_step()
            elif self.step_index == 2:
                self.normalization_step()
            elif self.step_index == 3:
                self.corrections_step()
            elif self.step_index == 4:
                self.components_step()
            else:
                self.finish_step()
        im.end_child()
        # bottom bar: the status line, then Back / Next at the right (as the Qt wizard)
        im.separator()
        back_w = im.calc_text_size("Back")[0] + 2 * im.get_style().frame_padding[0]
        status_w = max(100.0, avail_w - 2 * (back_w + 24.0) - 30.0)
        im.begin_child("status", (status_w, 22.0), scrollable=False)
        im.text_disabled(m.status[:200])
        im.end_child()
        spacing = im.get_style().item_spacing[0]
        next_w = im.calc_text_size("Next")[0] + 2 * im.get_style().frame_padding[0]
        im.same_line(max(0.0, avail_w - back_w - next_w - 2 * spacing))
        im.begin_disabled(self.step_index == 0)
        if im.button("Back"):
            self.select_step(self.step_index - 1)
        im.end_disabled()
        im.set_item_tooltip("Return to the previous workflow step.")
        im.same_line()
        im.begin_disabled(self.step_index == len(self.steps) - 1)
        if im.button("Next"):
            self.select_step(self.step_index + 1)
        im.end_disabled()
        im.set_item_tooltip("Continue to the next workflow step.")

    # -- one frame ------------------------------------------------------------------------------- #
    def render(self):
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.item_rects.clear()
        for form in self.forms.values():
            form.rects.clear()
        im.begin_disabled(self.dialog is not None)
        self.docks.draw(box)
        im.end_disabled()
        if self.dialog is not None:
            pressed = self.file_window.begin(box)
            result = self.dialog.draw()
            if result:
                self.dialog = None
                self._file_chosen(result)
            elif result is False or pressed == "close":
                self.dialog = None
            self.file_window.end()
        self.help_window.draw(box)
        self.tour.draw(*vp.size)


def make_app():
    return AnisotropyApp()
