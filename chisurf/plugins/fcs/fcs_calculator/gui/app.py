"""Native FCS confocal calculator: the Qt ConfocalCalcWidget's form, Guide and ? over a Qt-free model.

The form is ``fcs_calculator_emtk.view.json`` drawn by :func:`emtk.view_form.draw_form` over
:class:`.model.ConfocalModel`; this app adds the Guide / Help row, the settings-file dialogs and a
scroll region, so a narrow window keeps every panel reachable.
"""

from __future__ import annotations

import json
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.file_dialog import FileDialog
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import action_button, action_caption, window_size

from .model import ConfocalModel

HERE = Path(__file__).parent
PLUGIN = HERE.parent
ERROR = (230, 90, 90, 255)
JSON_FILTERS = "JSON Files (*.json);;All Files (*)"
#: guide.json names panels by title; those are the spec's fold headers here.
TOUR_KEYS = {
    "Constraint (choose one)": "Constraint (choose one).fold",
    "Reference dye (D @ 25 °C, water)": "Reference dye (D @ 25 °C, water).fold",
    "Molecular shape": "Molecular shape.fold",
}


class ConfocalApp(ImApp):
    def __init__(self, model=None):
        self.model = model or ConfocalModel()
        self.spec = json.loads((HERE / "fcs_calculator_emtk.view.json").read_text(encoding="utf-8"))
        self.window_size = window_size(self.spec, (640, 480))
        self.item_rects = {}
        self.dialog = None
        self.dialog_window = None
        self.form = FormState()
        self.form.custom["confocal_json"] = self.draw_json
        self.help_window = EmTkHelpWindow(
            title=tr("FCS confocal calculator — help"),
            resource=PLUGIN / "help.md",
            owner=self,
            on_start_guide=self.start_guide,
        )
        self.tour = EmTkGuidedTour(
            steps=PLUGIN / "guide.json",
            get_target_rect=self.target_rect,
            owner=self,
            wait_for_controls=True,
        )
        self.form.on_used = self.tour.notify_used
        super().__init__(self.render, continuous=False)

    # -- compatibility with the stream's API (and the capture script) --------------------
    @property
    def dye(self):
        return self.model.dye

    @dye.setter
    def dye(self, value):
        self.model.dye = value

    @property
    def shape(self):
        return ("Sphere", "Ellipsoid", "Cylinder").index(self.model.shape_type)

    @shape.setter
    def shape(self, index):
        self.model.shape_type = ("Sphere", "Ellipsoid", "Cylinder")[int(index)]

    def edited(self, attr):
        {
            "conc_nM": self.model.conc_edited,
            "num_mols": self.model.N_edited,
            "invN": self.model.invN_edited,
        }.get(attr, self.model.recompute)()

    def apply_dye(self):
        return self.model.apply_dye()

    def settings(self):
        return self.model.settings()

    # -- actions -----------------------------------------------------------------------
    def target_rect(self, key):
        return self.item_rects.get(TOUR_KEYS.get(key, key))

    def start_guide(self):
        self.tour.start()

    def choose_file(self, save):
        title = tr("Save FCS Calculator Settings") if save else tr("Load FCS Calculator Settings")
        self.dialog = FileDialog(
            title,
            mode="save" if save else "open",
            filename="fcs_calculator.json" if save else "",
            filters=tr(JSON_FILTERS),
        )
        self.dialog_window = DialogWindow(title, size=(720, 520))

    def file_chosen(self, path):
        """Write or read the settings file the dialog returned; a failure is the red error line."""
        save = self.dialog is not None and self.dialog.mode == "save"
        self.dialog = None
        try:
            (self.model.export_json if save else self.model.import_json)(path)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            self.model.error = tr("{action} {name} failed: {error}").format(
                action=tr("Saving") if save else tr("Loading"), name=Path(path).name, error=exc
            )

    def files_dropped(self, paths):
        """A dropped .json file is imported, as Import JSON does."""
        path = next((str(p) for p in paths or () if str(p).lower().endswith(".json")), None)
        if path is None:
            return False
        try:
            self.model.import_json(path)
        except Exception as exc:  # noqa: BLE001
            self.model.error = tr("Loading {name} failed: {error}").format(
                name=Path(path).name, error=exc
            )
        return True

    def close(self):
        self.dialog = None
        self.help_window.open = False
        self.tour.active = False

    # -- drawing -----------------------------------------------------------------------
    def draw_json(self, section, model, state, width):
        for index, (label, save, tip) in enumerate(
            (
                (
                    "Export JSON",
                    True,
                    "Save every value, the constraint, the reference and the shape to a JSON file.",
                ),
                (
                    "Import JSON",
                    False,
                    "Load calculator settings from a JSON file (unknown entries are ignored).",
                ),
            )
        ):
            if index:
                im.same_line()
            # One id per button: two labels sharing "##confocal_json" are one ImGui id, and the
            # second button never fires.
            if im.button(f"{tr(label)}##confocal_json_{'export' if save else 'import'}"):
                self.choose_file(save)
            im.set_item_tooltip(tr(tip))
            state.rects["export_json" if save else "import_json"] = tuple(im.get_item_rect())

    def toolbar(self, width):
        actions = (("guide", self.start_guide), ("help", self.help_window.show))
        widths = [
            im.calc_text_size(action_caption(key))[0] + 2 * im.get_style().frame_padding[0]
            for key, _ in actions
        ]
        spacing = im.get_style().item_spacing[0]
        im.dummy(
            max(1.0, width - sum(widths) - 2 * spacing), 1.0
        )  # right-aligned, as the Qt toolbar
        for key, action in actions:
            im.same_line()
            if action_button(key):
                action()
            self.item_rects[key] = tuple(im.get_item_rect())

    def render(self):
        viewport = im.get_main_viewport()
        box = (*viewport.pos, *viewport.size)
        im.set_next_window_pos(viewport.pos, im.Cond.ALWAYS)
        im.set_next_window_size(viewport.size, im.Cond.ALWAYS)
        im.begin_disabled(self.dialog is not None)
        if im.begin(
            tr("FCS confocal calculator") + "##confocal",
            flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE | im.WindowFlags.NO_MOVE,
        ):
            self.toolbar(im.get_content_region_avail()[0])
            if im.begin_child("confocal_form", (0.0, 0.0)):
                self.form.rects.clear()
                draw_form(self.spec, self.model, self.form)
                self.item_rects.update(self.form.rects)
                if self.model.error:
                    im.text_colored(ERROR, self.model.error)
                elif self.model.status:
                    im.text_disabled(self.model.status)
            im.end_child()
        im.end()
        im.end_disabled()
        if self.dialog is not None:
            pressed = self.dialog_window.begin(box)
            result = self.dialog.draw()
            if result:
                self.file_chosen(str(result[0]))
            elif result is False or pressed == "close":
                self.dialog = None
            self.dialog_window.end()
        self.help_window.draw(box)
        self.tour.draw(*viewport.size)


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return ConfocalApp(**kwargs)
