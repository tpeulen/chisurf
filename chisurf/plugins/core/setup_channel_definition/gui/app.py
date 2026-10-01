"""Native emtk Setup:Channel Definition tool.

One window: the toolbar of the Qt tool (Setup, Save, Rename, Delete, Public, Calibration, Help,
Guide) in a single row, and below it the shared editor
:class:`chisurf.emtk.channel_definition.ChannelDefinitionWidget` in six tabs (Setups, TTTR
reading, Detectors, PIE windows, TAC corrections, Optical setup). The editor is another
stream's shared widget; this app only hosts it and adds what the Qt tool had around it. The
state of the toolbar (name prompts, confirmations, ownership of Public) is in
:class:`~.model.SetupToolbar`; the definition and its stores are
:class:`chisurf.core.setup_channel_definition.ChannelDefinition`. Nothing here imports Qt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region

from chisurf.core.setup_channel_definition import ChannelDefinition
from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from .model import (
    DELETE,
    LATEST,
    OVERWRITE,
    RENAME,
    SAVE,
    UNSAVED,
    SetupToolbar,
    default_settings,
)

HERE = Path(__file__).parent
#: The window title: the plugin's display name.
TITLE = "Setup: Channel Definition"
#: The editor's tabs, in drawing order (the Qt page is one scroll of sections).
TAB_NAMES = ("Setups", "TTTR reading", "Detectors", "PIE windows", "TAC corrections", "Optical setup")


class SetupChannelDefinitionApp(ImApp):
    """Detector channels, PIE windows, reading routine, LUTs and optical setup of an instrument."""

    def __init__(
        self,
        settings: dict | None = None,
        model: ChannelDefinition | None = None,
        on_changed: Any = None,
        file_path: str | None = None,
        db: Any = None,
        autoload: bool = True,
    ) -> None:
        if model is None:
            model = ChannelDefinition(
                default_settings() if settings is None else settings, file_path=file_path, db=db
            )
        self._on_changed = on_changed
        self.page = ChannelDefinitionWidget(
            model=model, on_changed=self._model_changed
        )
        self.model = self.page.model
        self.toolbar = SetupToolbar(self.page)
        self.item_rects: dict[str, tuple] = {}
        self.dialog_window = DialogWindow("Setup", size=(460.0, 130.0), key="channel_setup", fit_height=True)
        self.help_window = EmTkHelpWindow(title="Setup: Channel Definition - Help", resource=HERE / "help.md", owner=self)
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key),
        )
        self.docks = DockManager(Region("setup"), name="setup_channel_definition")
        self.docks.add_window("setup", TITLE, self._draw_window, dock="setup", closable=False)
        #: The Qt tool lists the saved setups when it opens; so does this one, on its first frame.
        self.autoload = autoload
        super().__init__(gui=self._render, continuous=True)

    # ------------------------------------------------------------------ model
    def _model_changed(self, settings: dict) -> None:
        self.toolbar.model_changed(settings)
        if callable(self._on_changed):
            self._on_changed(settings)

    # ------------------------------------------------------------------ frame
    def _render(self) -> None:
        if self.autoload:
            self.autoload = False
            self.toolbar.reload()
        vp = im.get_main_viewport()
        box = (float(vp.pos[0]), float(vp.pos[1]), float(vp.size[0]), float(vp.size[1]))
        self.docks.draw(box)
        self.page.draw_dialogs(box)
        self._draw_prompt(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _draw_window(self, box: Any = None) -> None:
        self._draw_toolbar()
        im.separator()
        self.page.draw()

    # ---------------------------------------------------------------- toolbar
    def _item(self, name: str, tooltip: str) -> None:
        """Tooltip and tour rectangle for the control just drawn."""
        im.set_item_tooltip(tooltip)
        self.item_rects[name] = im.get_item_rect()

    @staticmethod
    def _width(label: str) -> float:
        return im.calc_text_size(label)[0] + 18.0

    def _draw_toolbar(self) -> None:
        """Setup choice, Save / Rename / Delete, Public, Calibration, Help / Guide in one row.

        The row wraps to a second line when the window is too narrow for it.
        """
        bar = self.toolbar
        total = im.get_content_region_avail()[0]
        spacing = 8.0
        used = [0.0]

        def place(width: float) -> None:
            if used[0] > 0.0 and used[0] + spacing + width > total:
                used[0] = 0.0
            elif used[0] > 0.0:
                im.same_line()
            used[0] += width + (spacing if used[0] > 0.0 else 0.0)

        im.begin_disabled(self.page._future is not None or bool(bar.dialog))
        names = [UNSAVED] + bar.names
        index = names.index(bar.selected) if bar.selected in names else 0
        place(self._width("Setup:") + 230.0)
        im.text("Setup:")
        im.same_line()
        im.set_next_item_width(220.0)
        changed, picked = im.combo("##setup_choice", index, names)
        self._item(
            "setup_choice",
            "Choose a saved detector setup; its detectors, PIE windows, reading routine, LUTs and "
            "optical setup replace the working definition.",
        )
        if changed:
            bar.select("" if picked == 0 else names[picked])
            self.tour.notify_used("setup_choice")
        for name, label, tip, action in (
            ("save", "Save", "Ask for a name and store the working definition as a saved setup.", bar.request_save),
            ("rename", "Rename", "Give the selected saved setup another name.", bar.request_rename),
            ("delete", "Delete", "Delete the selected saved setup after asking.", bar.request_delete),
        ):
            place(self._width(label))
            if im.button(label):
                action()
                self.tour.notify_used(name)
            self._item(name, tip)
        place(self._width("Public") + 24.0)
        im.begin_disabled(not bar.can_public())
        changed, value = im.checkbox("Public", bool(self.page.public))
        im.set_item_tooltip(
            "When checked, the setup is visible to all users in the MMFDB; it takes effect with Save. "
            "Only the owner of a saved setup can change this."
        )
        self.item_rects["public"] = im.get_item_rect()
        im.end_disabled()
        if changed:
            bar.select_public(value)
        items = bar.calibration_items()
        picked_index = items.index(self.page.calibration) if self.page.calibration in items else 0
        place(self._width("Calibration:") + 200.0)
        im.text("Calibration:")
        im.same_line()
        im.set_next_item_width(190.0)
        changed, picked = im.combo("##calibration_choice", picked_index, items)
        self._item(
            "calibration",
            "Pick a stored calibration snapshot of the selected setup: its G factor, l1 and l2 are "
            "applied to the detectors. Latest leaves the factors as they are.",
        )
        if changed:
            bar.select_calibration(items[picked])
            self.tour.notify_used("calibration")
        im.end_disabled()
        place(self._width("Help"))
        if im.button("Help"):
            self.help_window.show()
        self._item("help", "Explain the setups, the six tabs, units of micro-time ranges and LUTs.")
        place(self._width("Guide"))
        if im.button("Guide"):
            self.tour.start()
        self._item("guide", "Walk through choosing, editing and saving a setup.")

    # ----------------------------------------------------------------- prompts
    def _draw_prompt(self, box: tuple) -> None:
        """The in-app name prompt (Save, Rename) and the confirmations (Delete, overwrite)."""
        bar = self.toolbar
        if bar.dialog and not self.dialog_window.open:
            self.dialog_window.show()
        if not bar.dialog and self.dialog_window.open:
            self.dialog_window.hide()
        if not self.dialog_window.open:
            return
        titles = {SAVE: "Save setup", RENAME: "Rename setup", DELETE: "Confirm deletion", OVERWRITE: "Setup exists"}
        self.dialog_window.title = titles.get(bar.dialog, "Setup")
        pressed = self.dialog_window.begin(box)
        kind = bar.dialog
        if kind in (SAVE, RENAME):
            im.text("Enter a name for this setup:" if kind == SAVE else "Enter a new name for this setup:")
            im.set_next_item_width(-1.0)
            changed, value = im.input_text("##setup_name_prompt", bar.name_text)
            im.set_item_tooltip("The name the setup is stored under.")
            self.item_rects["name_prompt"] = im.get_item_rect()
            if changed:
                bar.name_text = value
            ok = "Save" if kind == SAVE else "Rename"
            ok_tip = "Store the setup under this name." if kind == SAVE else "Rename the selected setup."
            keep = "Cancel"
        elif kind == DELETE:
            im.text_wrapped(f"Are you sure you want to delete the setup '{bar.selected}'?")
            ok, ok_tip, keep = "Delete", "Delete this saved setup from its store.", "Keep setup"
        else:
            im.text_wrapped(f"A setup named '{bar._pending_name}' already exists. Do you want to overwrite it?")
            ok, ok_tip, keep = "Overwrite", "Replace the existing setup by the renamed one.", "Cancel"
        if im.button(ok):
            bar.confirm()
            self.tour.notify_used("confirm")
        im.set_item_tooltip(ok_tip)
        self.item_rects["confirm"] = im.get_item_rect()
        im.same_line()
        if im.button(keep):
            bar.cancel()
        im.set_item_tooltip("Close this prompt; nothing changes.")
        self.dialog_window.end()
        if pressed == "close":
            bar.cancel()

    # ------------------------------------------------------------ the old API
    def get_settings(self) -> dict:
        """The complete working definition (windows, detectors, reading, LUTs, optical setup)."""
        return self.model.get_settings()

    def load_data_into_tables(self, data: dict) -> None:
        """Replace the working definition by *data*, keeping the stores and the change callback."""
        callback = self.model.on_changed
        loaded = ChannelDefinition(data, file_path=self.model.file_path, db=self.model.db)
        setups = self.model.setups
        self.model.__dict__.update(loaded.__dict__)
        self.model.setups = setups
        self.model.on_changed = callback
        self.page.setup_name = self.model.current_name
        self.page.public = bool(self.model.data.get("_is_public"))
        self.page.optical = None
        self.page.detector_names, self.page.window_names = {}, {}
        self.toolbar.sync_luts()
        self.model.changed()

    # ------------------------------------------------------------ persistence
    def export_settings(self) -> dict:
        """What is remembered: the working definition, the setups file and the tab."""
        return {
            "channel_definition": self.get_settings(),
            "section": self.page.section,
            "setups_file": str(self.model.file_path) if self.model.file_path else None,
        }

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        self.model.file_path = settings.get("setups_file") or None
        if isinstance(settings.get("channel_definition"), dict):
            self.load_data_into_tables(settings["channel_definition"])
        try:
            self.page.section = max(0, min(len(TAB_NAMES) - 1, int(settings.get("section", 0))))
        except (TypeError, ValueError):
            self.page.section = 0
        self.toolbar.reload()

    def close(self) -> None:
        """Stop a running read."""
        self.page.close()


def make_app(**kwargs: Any) -> SetupChannelDefinitionApp:
    """Build the tool (the manifest's ``entrypoints.emtk``)."""
    from chisurf.emtk.i18n import install

    install()
    return SetupChannelDefinitionApp(**kwargs)


#: The factory's earlier name, kept for callers that still use it.
create_app = make_app

__all__ = ["SetupChannelDefinitionApp", "TAB_NAMES", "LATEST", "make_app", "create_app"]
