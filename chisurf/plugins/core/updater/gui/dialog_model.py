"""The in-app confirm / notice / text-entry dialog the Qt tool asked with message boxes.

A model that mixes :class:`DialogMixin` in shows its dialog through the ``dialog`` panel of its view spec: the
text, an optional entry field and one or two buttons (``dialog_ok`` / ``dialog_cancel``). The dialog is modal:
the model's ``enabled`` greys everything else while :attr:`dialog` is set (:meth:`dialog_blocks`).
"""

from __future__ import annotations

from typing import Any


class DialogMixin:
    """State and buttons of one in-app dialog; a model implements :meth:`on_dialog`."""

    #: The kind of dialog open now (``""`` when none), what it asks, and the text typed into its entry field.
    dialog: str = ""
    dialog_title: str = ""
    dialog_text: str = ""
    dialog_input: str = ""
    dialog_context: Any = None
    _dialog_entry: bool = False
    _dialog_cancel: bool = True
    _dialog_labels: tuple = ("OK", "Cancel")

    def ask(
        self,
        kind: str,
        title: str,
        text: str,
        *,
        yes_no: bool = True,
        entry: bool = False,
        value: str = "",
        context: Any = None,
    ) -> None:
        """Open a dialog: a question (``yes_no``: Yes / No, else OK / Cancel), optionally with an entry field."""
        self.dialog, self.dialog_title, self.dialog_text = kind, title, text
        self.dialog_input, self.dialog_context = value, context
        self._dialog_entry, self._dialog_cancel = entry, True
        self._dialog_labels = ("Yes", "No") if yes_no else ("OK", "Cancel")

    def notice(self, title: str, text: str) -> None:
        """Open a message with one OK button."""
        self.dialog, self.dialog_title, self.dialog_text = "notice", title, text
        self.dialog_input, self.dialog_context = "", None
        self._dialog_entry, self._dialog_cancel = False, False
        self._dialog_labels = ("OK", "")

    @property
    def dialog_blocks(self) -> bool:
        """Whether a dialog is open (the rest of the window is greyed)."""
        return bool(self.dialog)

    @property
    def dialog_input_hidden(self) -> str:
        """``"no"`` while the entry field is shown (the spec hides it otherwise)."""
        return "no" if self._dialog_entry else "yes"

    @property
    def dialog_cancel_hidden(self) -> str:
        """``"no"`` while the dialog has a second button."""
        return "no" if self._dialog_cancel else "yes"

    def dialog_ok_label(self) -> str:
        """Caption of the first button."""
        return self._dialog_labels[0]

    def dialog_cancel_label(self) -> str:
        """Caption of the second button."""
        return self._dialog_labels[1] or "Cancel"

    def dialog_ok(self) -> None:
        """The first button: do what the dialog asked."""
        kind, context, value = self.dialog, self.dialog_context, self.dialog_input
        self.dialog, self.dialog_context = "", None
        self.on_dialog(kind, True, value, context)

    def dialog_cancel(self) -> None:
        """The second button, or the window's close button: leave everything as it is."""
        kind, context, value = self.dialog, self.dialog_context, self.dialog_input
        self.dialog, self.dialog_context = "", None
        self.on_dialog(kind, False, value, context)

    def on_dialog(self, kind: str, accepted: bool, value: str, context: Any) -> None:
        """What a closed dialog means; the model overrides it."""
