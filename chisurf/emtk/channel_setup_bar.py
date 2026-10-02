"""Qt-free state of the Setup row of the shared channel-definition editor.

What the Qt page puts on one row above its sections -- the Setup choice, Save, Rename, Delete, Public and
Calibration -- is a small state machine of its own: Save and Rename ask for a name, Delete asks for
confirmation, Rename onto an existing name asks before it overwrites, Public is only available for a saved
setup the user owns. That state lives here so it can be tested without drawing, against the same temporary
setups file or MMFDB the Qt page would use. :class:`~chisurf.emtk.channel_definition.ChannelDefinitionWidget`
draws it and owns the instance as ``widget.toolbar``.
"""

from __future__ import annotations

import copy
from typing import Any

from chisurf.core.fio import setup_store
from chisurf.core.setup_channel_definition import ChannelDefinition

#: The label of the "no saved setup" entry of the Setup choice.
UNSAVED = "Unsaved"
#: The calibration entry that means "leave the factors as they are".
LATEST = "Latest"
#: Dialog kinds of :attr:`SetupToolbar.dialog`.
SAVE, RENAME, DELETE, OVERWRITE = "save", "rename", "delete", "overwrite"


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
    def reload(self, open_last: bool = False) -> None:
        """Read the saved setups again from the setups file or the MMFDB.

        With *open_last* the setup the store names as last used is opened, as the Qt page does when it
        starts; a store without one (or without that setup any more) leaves the working definition alone.
        """
        try:
            self.definition.refresh_setups()
            self._say(f"{len(self.definition.setups)} setups available.")
            if open_last:
                name = self.definition.last_used
                if name and name in self.definition.setups:
                    self.select(name, remember=False)
        except Exception as exc:  # the store is unreachable: keep working on the definition
            self._say(f"Error: {exc}")

    def select(self, name: str, remember: bool = True) -> None:
        """Choose a saved setup, or ``""`` for none, as the Qt Setup combo does.

        A saved setup becomes the *last used* one (the Qt page writes that on every choice), so the next start
        opens it; *remember* false skips that (opening the last used one at start).
        """
        if not name:
            self.definition.current_name = ""
            self.page.setup_name = ""
            self.page.public = False
            self.page.calibrations = []
            self.page.calibration = LATEST
            return
        self.page._call(self.page.select_setup, name)
        if remember:
            try:
                self.definition.remember_last_used(name)
            except Exception as exc:
                self._say(f"Error: {exc}")

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


__all__ = ["DELETE", "LATEST", "OVERWRITE", "RENAME", "SAVE", "SetupToolbar", "UNSAVED"]
