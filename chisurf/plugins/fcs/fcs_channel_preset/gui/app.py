"""Native editor for detector-scoped correlation pair presets."""

from __future__ import annotations

import copy
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.core.support.i18n import tr
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.i18n import install

from .view_model import FCSChannelViewModel


class PresetApp(ImApp):
    def __init__(self, model=None, apply_callback=None):
        install()
        self.model = model or FCSChannelViewModel()
        self.apply_callback = apply_callback
        self.selected = -1
        self.channel_a = self.channel_b = self.pair_name = ""
        self.message = ""
        self.closed = False
        self.dialog = None
        self.dialog_action = ""
        self.drafts = {}
        self.item_rects = {}
        root = Path(__file__).parents[1]
        self.help = EmTkHelpWindow(title="FCS channel definitions", resource=root / "help.md")
        self.tour = EmTkGuidedTour(steps=root / "guide.json", get_target_rect=self.item_rects.get)
        self.docks = DockManager(Split("h", 0.34, Region("setup"), Region("pairs")))
        self.docks.add_window("setup", tr("Detector setup"), self.draw_setup, dock="setup")
        self.docks.add_window("pairs", tr("Channel pairs"), self.draw_pairs, dock="pairs")
        super().__init__(gui=self.render, continuous=False)

    def run_action(self, callback):
        try:
            result = callback()
            if result is False:
                raise ValueError("The action did not save its result.")
            return result
        except Exception as error:
            self.message = str(error)
            return False

    def select_setup(self, name):
        if self.model.current_setup:
            self.drafts[self.model.current_setup] = {
                "pairs": copy.deepcopy(self.model.pairs),
                "public": self.model.is_public,
            }
        self.model.current_setup = name
        draft = self.drafts.get(name)
        if draft:
            self.model._pairs = copy.deepcopy(draft["pairs"])
            if self.model.can_edit_public:
                self.model._is_public = draft["public"]
        self.selected = -1

    def add_pair(self):
        if (
            self.channel_a not in self.model.channel_names
            or self.channel_b not in self.model.channel_names
        ):
            raise ValueError("Select two available logical channels.")
        self.model.add_pair(self.channel_a, self.channel_b, self.pair_name)
        self.selected = len(self.model.pairs) - 1
        self.pair_name = ""

    def save(self):
        if not self.model.save():
            raise OSError("Select a detector setup and save its valid pairs.")
        self.drafts.pop(self.model.current_setup, None)
        self.message = "Channel preset saved."
        return True

    def apply(self):
        self.save()
        data = self.model._collect_setup_data()
        if self.apply_callback:
            self.apply_callback(self.model.current_setup, copy.deepcopy(data))
            self.message = "Channel preset saved and applied to the connected correlator."
        else:
            self.message = "Saved as the active preset; correlation tools read it on reload."
        return data

    def delete(self):
        self.model.delete_preset()
        self.drafts.pop(self.model.current_setup, None)
        self.selected = -1
        self.message = "FCS preset deleted; detector setup retained."

    def reload(self):
        self.model.reload_setups()
        self.drafts.clear()
        self.selected = -1
        self.message = "Saved detector setups and FCS presets reloaded."

    def browse(self, action):
        self.dialog_action = action
        self.dialog = FileDialog(
            tr("Channel pairs"),
            mode="save" if action == "export" else "open",
            filename="fcs_channel_setups.json" if action == "export" else "",
            filters=[("JSON", ["*.json"])],
        )

    def button(self, label, tip, callback):
        if im.button(tr(label)):
            self.run_action(callback)
        im.set_item_tooltip(tr(tip))
        self.item_rects[label] = im.get_item_rect()

    def choice(self, label, value, options, tip):
        im.text(tr(label))
        options = options or [""]
        if value and value not in options:
            options = [*options, value]
        changed, index = im.combo(
            "##" + label, options.index(value) if value in options else 0, options
        )
        im.set_item_tooltip(tr(tip))
        self.item_rects[label] = im.get_item_rect()
        return changed, options[index]

    def draw_setup(self, box):
        changed, name = self.choice(
            "Detector setup",
            self.model.current_setup,
            self.model.setup_names(),
            "Choose the detector setup whose logical channels are paired.",
        )
        if changed:
            self.select_setup(name)
        im.begin_disabled(not self.model.can_edit_public)
        changed, public = im.checkbox(tr("Public"), self.model.is_public)
        if changed:
            self.run_action(lambda: setattr(self.model, "is_public", public))
        im.set_item_tooltip(tr("Only the owner may change sharing with other MMFDB users."))
        im.end_disabled()
        self.button(
            "Reload",
            "Reload saved detector setups and presets; discard editing drafts.",
            self.reload,
        )
        im.separator()
        channels = self.model.channel_names
        if not channels:
            im.text_wrapped(
                tr("No logical channels. Define detector and excitation windows first.")
            )
        im.begin_disabled(not channels)
        _, self.channel_a = self.choice(
            "A", self.channel_a, channels, "First logical detector/excitation channel."
        )
        _, self.channel_b = self.choice(
            "B",
            self.channel_b,
            channels,
            "Second channel; identical channels make an autocorrelation.",
        )
        im.text(tr("Name"))
        _, self.pair_name = im.input_text(
            "##new_name", self.pair_name, hint=tr("Pair label (optional)")
        )
        im.set_item_tooltip(
            tr("Optional unique pair name; otherwise an ACF or cross-channel label is generated.")
        )
        self.button(
            "Add", "Add a channel pair with the configured correlator defaults.", self.add_pair
        )
        im.end_disabled()
        im.separator()
        self.button("Save", "Validate and persist pairs for this detector setup.", self.save)
        self.button(
            "Apply",
            "Save as the active preset and notify a connected correlator when provided.",
            self.apply,
        )
        self.button(
            "Delete preset",
            "Delete only the FCS preset; retain its detector definition.",
            self.delete,
        )
        self.button(
            "Import JSON",
            "Import and persist a channel preset library from JSON.",
            lambda: self.browse("import"),
        )
        self.button(
            "Export JSON",
            "Export the full library including this current editing draft.",
            lambda: self.browse("export"),
        )
        self.button(
            "Help",
            "Explain logical channels, correlation pairs and per-pair settings.",
            self.help.show,
        )
        self.button(
            "Guide", "Walk through selecting a setup, creating pairs and saving.", self.tour.start
        )
        self.button(
            "Close",
            "Close this native editor; exported host state preserves drafts.",
            self.request_close,
        )
        if self.message:
            im.text_wrapped(tr(self.message))

    def draw_pairs(self, box):
        if im.begin_table("pairs", 7, im.TableFlags.BORDERS | im.TableFlags.ROW_BG):
            for title in ("Name", "Channel A", "Channel B", "Kind", "Bins", "Cascades", "Fine"):
                im.table_setup_column(tr(title))
            im.table_headers_row()
            for index, pair in enumerate(self.model.pairs):
                im.table_next_row()
                im.table_set_column_index(0)
                if im.selectable(
                    f"{pair['name'] or '(automatic)'}##{index}", self.selected == index
                ):
                    self.selected = index
                im.set_item_tooltip(
                    tr("Select this pair to edit its channels and correlator overrides.")
                )
                for column, value in enumerate(
                    (
                        pair["channel_a"],
                        pair["channel_b"],
                        "ACF" if pair["channel_a"] == pair["channel_b"] else "CCF",
                        str(pair.get("n_bins")) if pair.get("n_bins") is not None else "Default",
                        str(pair.get("n_casc")) if pair.get("n_casc") is not None else "Default",
                        "Default"
                        if pair.get("make_fine") is None
                        else "On"
                        if pair["make_fine"]
                        else "Off",
                    ),
                    1,
                ):
                    im.table_set_column_index(column)
                    im.text(value)
            im.end_table()
        if not 0 <= self.selected < len(self.model.pairs):
            im.text_wrapped(tr("Add or select a pair to edit it."))
            return
        pair = self.model.pairs[self.selected]
        im.separator()
        im.text(tr("Name"))
        changed, value = im.input_text("##pair_name", pair["name"])
        im.set_item_tooltip(tr("Unique name used by the correlation tools and database."))
        if changed:
            self.model.update_pair(self.selected, "name", value)
        for key, label in (("channel_a", "Channel A"), ("channel_b", "Channel B")):
            changed, value = self.choice(
                label,
                pair[key],
                self.model.channel_names,
                "Choose an available logical channel from the detector setup.",
            )
            if changed:
                self.model.update_pair(self.selected, key, value)
        for key, label in (("n_bins", "Bins"), ("n_casc", "Cascades")):
            im.text(tr(label))
            changed, value = im.input_text(
                "##" + key, str(pair[key]) if pair[key] is not None else "", hint=tr("Default")
            )
            im.set_item_tooltip(
                tr("Positive whole-number override; leave blank to inherit global settings.")
            )
            if changed:
                self.model.update_pair(self.selected, key, value if value.strip() else None)
        fine = pair.get("make_fine")
        changed, choice = self.choice(
            "Fine",
            "Default" if fine is None else "On" if fine else "Off",
            ["Default", "Off", "On"],
            "Override the fine correlation grid or inherit its default.",
        )
        if changed:
            self.model.update_pair(
                self.selected, "make_fine", None if choice == "Default" else choice == "On"
            )
        self.button(
            "Remove this pair",
            "Remove the selected pair from this editing draft.",
            lambda: self.model.remove_pair(self.selected),
        )

    def export_state(self):
        return {
            "setup": self.model.current_setup,
            "pairs": copy.deepcopy(self.model.pairs),
            "public": self.model.is_public,
            "selected": self.selected,
            "drafts": copy.deepcopy(self.drafts),
            "docks": self.docks.state(),
        }

    def restore_state(self, state):
        if not isinstance(state, dict):
            return
        if state.get("setup") in self.model.setup_names():
            self.model.current_setup = state["setup"]
            pairs = state.get("pairs", self.model.pairs)
            if isinstance(pairs, list) and all(isinstance(pair, dict) for pair in pairs):
                self.model._pairs = [self.model._normalize_pair(pair) for pair in pairs]
            if self.model.can_edit_public:
                self.model._is_public = bool(state.get("public", self.model.is_public))
        try:
            self.selected = int(state.get("selected", -1))
        except (TypeError, ValueError):
            self.selected = -1
        drafts = state.get("drafts", {})
        self.drafts = {}
        if isinstance(drafts, dict):
            for name, draft in drafts.items():
                if not isinstance(draft, dict):
                    continue
                pairs = draft.get("pairs")
                if isinstance(pairs, list) and all(isinstance(pair, dict) for pair in pairs):
                    self.drafts[name] = {
                        "pairs": [self.model._normalize_pair(pair) for pair in pairs],
                        "public": bool(draft.get("public", False)),
                    }
        self.docks.restore(state.get("docks"))

    export_settings = export_state
    restore_settings = restore_state

    def close(self):
        self.closed = True

    def render(self):
        vp = im.get_main_viewport()
        self.docks.draw((0, 0, *vp.size))
        if self.dialog:
            if im.begin(tr("Channel preset file")):
                result = self.dialog.draw()
                if result:
                    if self.dialog_action == "import":
                        self.run_action(lambda: self.model.import_presets(result[0]))
                    else:
                        self.run_action(lambda: self.model.export_presets(result[0]))
                    self.dialog = None
                elif result is False:
                    self.dialog = None
            im.end()
        if self.help.open:
            self.help.draw((0, 0, *vp.size))
        if self.tour.active:
            self.tour.draw(*vp.size)


def create_app(*, db_path=None, detector_file=None, preset_file=None, apply_callback=None):
    return PresetApp(
        FCSChannelViewModel(db_path, detector_file=detector_file, preset_file=preset_file),
        apply_callback,
    )
