"""Qt-free state of the Setup toolbar around the shared channel-definition editor.

The six editor tabs (setups, TTTR reading, detectors, PIE windows, TAC corrections, optical
setup) are the shared :class:`chisurf.emtk.channel_definition.ChannelDefinitionWidget`. What the
Qt tool puts on one row above its sections -- the Setup choice, Save, Rename, Delete, Public,
Calibration and Help -- is a small state machine of its own: Save and Rename ask for a name,
Delete asks for confirmation, Rename onto an existing name asks before it overwrites, Public is
only available for a saved setup the user owns. That state lives here so it can be tested
without drawing, against the same temporary setups file or MMFDB the Qt tool would use.
"""

from __future__ import annotations

import copy
from typing import Any

from chisurf.core.fio import setup_store
from chisurf.core.setup_channel_definition import ChannelDefinition

#: What a fresh tool shows, as in the Qt tool: three detectors, two PIE windows, SPC-130 timing.
DEFAULT_SETTINGS: dict[str, Any] = {
    "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
    "detectors": {
        "green": {"chs": [8, 0, 3], "micro_time_ranges": [[0, 4095]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        "red": {"chs": [9, 1, 2], "micro_time_ranges": [[0, 2048]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        "yellow": {"chs": [9, 1, 2], "micro_time_ranges": [[2048, 4095]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
    },
    "tttr_reading": {
        "file_type": "SPC-130",
        "macro_time_resolution": 50.0,
        "micro_time_resolution": 50.0,
        "micro_time_binning": 1,
    },
}

#: The label of the "no saved setup" entry of the Setup choice.
UNSAVED = "Unsaved"
#: The calibration entry that means "leave the factors as they are".
LATEST = "Latest"
#: Dialog kinds of :attr:`SetupToolbar.dialog`.
SAVE, RENAME, DELETE, OVERWRITE = "save", "rename", "delete", "overwrite"


def default_settings() -> dict[str, Any]:
    """Return a fresh copy of the settings a new tool starts with."""
    return copy.deepcopy(DEFAULT_SETTINGS)


class SetupToolbar:
    """Save / Rename / Delete / Public / Calibration of the named detector setups.

    Parameters
    ----------
    page : ChannelDefinitionWidget
        The shared editor; its ``model`` holds the working definition and the named setups, its
        ``setup_name``, ``public``, ``calibrations`` and ``status`` are the state the editor's
        own Setups tab shows, so both stay in step.
    """

    def __init__(self, page: Any) -> None:
        self.page = page
        #: Which prompt is open: ``""``, ``"save"``, ``"rename"``, ``"delete"`` or ``"overwrite"``.
        self.dialog = ""
        #: The name typed into the Save / Rename prompt.
        self.name_text = ""
        #: A rename waiting for the overwrite confirmation.
        self._pending_name = ""
        self._lut_channels: set[int] = set()
        self._loading = False

    # ------------------------------------------------------------------ state
    @property
    def definition(self) -> ChannelDefinition:
        """The working definition and its named setups."""
        return self.page.model

    @property
    def names(self) -> list[str]:
        """The saved setups, sorted, as the Setup choice lists them."""
        return sorted(self.definition.setups)

    @property
    def selected(self) -> str:
        """The selected saved setup, or ``""`` when the working definition is unsaved."""
        name = self.definition.current_name
        return name if name in self.definition.setups else ""

    @property
    def status(self) -> str:
        """The status line shared with the editor."""
        return self.page.status

    def _say(self, text: str) -> None:
        self.page.status = text

    def is_owner(self) -> bool:
        """Whether the active user may change the visibility of the selected setup."""
        if not self.selected:
            return False
        owner = self.definition.setups[self.selected].get("_owner")
        return owner is None or owner == setup_store.resolve_active_user_id()

    def can_public(self) -> bool:
        """Public is available for a saved setup its owner is looking at (as in the Qt tool)."""
        return bool(self.selected) and self.is_owner()

    def calibration_items(self) -> list[str]:
        """The calibration choice: ``Latest`` and the stored snapshot dates."""
        return [LATEST] + [str(date) for date in self.page.calibrations]

    # ------------------------------------------------------------- setup choice
    def reload(self) -> None:
        """Read the saved setups again from the setups file or the MMFDB."""
        try:
            self.definition.refresh_setups()
            self._say(f"{len(self.definition.setups)} setups available.")
        except Exception as exc:  # the store is unreachable: keep working on the definition
            self._say(f"Error: {exc}")

    def select(self, name: str) -> None:
        """Choose a saved setup, or ``""`` for none, as the Qt Setup combo does."""
        if not name:
            self.definition.current_name = ""
            self.page.setup_name = ""
            self.page.public = False
            self.page.calibrations = []
            self.page.calibration = LATEST
            return
        self._loading = True
        try:
            self.page._call(self.page.select_setup, name)
        finally:
            self._loading = False
            self.sync_luts()

    def select_public(self, value: bool) -> None:
        """Mark the working definition public; it is stored by the next Save."""
        if self.can_public():
            self.page.public = bool(value)

    def select_calibration(self, label: str) -> None:
        """Apply a stored calibration snapshot to the detectors' G, l1 and l2.

        ``Latest`` leaves the working factors untouched, as in the Qt tool.
        """
        self.page.calibration = label
        if label == LATEST or not self.selected:
            return
        try:
            count = self.definition.apply_calibration(label)
        except Exception as exc:
            self._say(f"Error: {exc}")
            return
        self._say(f"Applied the calibration of {label} to {count} detector(s).")

    # -------------------------------------------------------------- the prompts
    def request_save(self) -> None:
        """Open the Save prompt, pre-filled with the selected name."""
        self.name_text = self.selected or self.definition.current_name or ""
        self.dialog = SAVE

    def request_rename(self) -> None:
        """Open the Rename prompt, or say that no setup is selected."""
        if not self.selected:
            self._say("No setup selected.")
            return
        self.name_text = self.selected
        self.dialog = RENAME

    def request_delete(self) -> None:
        """Open the delete confirmation, or say that no setup is selected."""
        if not self.selected:
            self._say("No setup selected.")
            return
        self.dialog = DELETE

    def cancel(self) -> None:
        """Close the open prompt; nothing changes."""
        self.dialog = ""
        self._pending_name = ""

    def confirm(self) -> None:
        """Carry out the open prompt (its OK button)."""
        kind, self.dialog = self.dialog, ""
        if kind == SAVE:
            self.save(self.name_text)
        elif kind == RENAME:
            self.rename(self.name_text)  # may open the overwrite prompt, which keeps the name
        elif kind == OVERWRITE:
            pending, self._pending_name = self._pending_name, ""
            self.rename(pending, overwrite=True)
        elif kind == DELETE:
            self.delete()

    # ------------------------------------------------------------------ actions
    def save(self, name: str) -> bool:
        """Store the working definition under *name*; an empty name does nothing."""
        name = str(name).strip()
        if not name:
            return False
        try:
            self.definition.save_setup(name, public=bool(self.page.public and self.can_public()))
        except Exception as exc:
            self._say(f"Failed to save setup '{name}': {exc}")
            return False
        self.page.setup_name = name
        self._refresh_after_store()
        self._say(f"Setup '{name}' saved successfully.")
        return True

    def rename(self, name: str, overwrite: bool = False) -> bool:
        """Rename the selected setup; a name already in use asks before overwriting."""
        name = str(name).strip()
        old = self.selected
        if not old:
            self._say("No setup selected.")
            return False
        if not name or name == old:
            return False
        setups = self.definition.setups
        if name in setups and not overwrite:
            self._pending_name = name
            self.dialog = OVERWRITE
            return False
        backup = copy.deepcopy(setups)
        if name in setups:
            del setups[name]
        try:
            self.definition.rename_setup(name)
        except Exception as exc:
            self.definition.setups = backup
            self.definition.current_name = old
            self._say(f"Failed to rename setup from '{old}' to '{name}': {exc}")
            return False
        self.page.setup_name = name
        self._refresh_after_store()
        self._say(f"Setup renamed from '{old}' to '{name}' successfully.")
        return True

    def delete(self) -> bool:
        """Delete the selected saved setup from its store."""
        name = self.selected
        if not name:
            self._say("No setup selected.")
            return False
        try:
            self.definition.delete_setup()
        except Exception as exc:
            self._say(f"Failed to delete setup '{name}': {exc}")
            return False
        self.page.setup_name = ""
        self.page.public = False
        self.page.calibrations = []
        self.page.calibration = LATEST
        self._say(f"Setup '{name}' deleted successfully.")
        return True

    def _refresh_after_store(self) -> None:
        """Re-read the store (the Qt tool reloads its combo) and the calibration history."""
        try:
            self.definition.refresh_setups()
            self.page.calibrations = self.definition.calibration_dates()
        except Exception:
            self.page.calibrations = []
        data = self.definition.setups.get(self.definition.current_name, {})
        self.page.public = bool(data.get("_is_public", self.page.public))

    # --------------------------------------------------------------------- LUTs
    def sync_luts(self) -> None:
        """Remember which channels carry a LUT now (after a setup was loaded)."""
        self._lut_channels = {int(ch) for ch, v in self.definition.data.get("channel_luts", {}).items() if v}

    def model_changed(self, settings: dict[str, Any]) -> None:
        """Turn the LUT gate on when a LUT has been added, as the Qt tool does.

        The Qt tool states the rule "a LUT is stored => it is applied on every read": adding a
        LUT ticks *Apply TAC linearization* automatically, otherwise the LUT would be stored and
        silently never used. The shared editor only stores the table, so the app applies the rule
        when the model reports the change.
        """
        if self._loading:
            return
        channels = {int(ch) for ch, values in (settings.get("channel_luts") or {}).items() if values}
        added = channels - self._lut_channels
        self._lut_channels = channels
        if added and not self.definition.data.get("apply_lut"):
            self.definition.data["apply_lut"] = True
            self.definition.changed()
