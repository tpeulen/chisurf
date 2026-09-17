"""Qt-free view model behind the model manager."""

from __future__ import annotations

import pathlib
from typing import Any

from chisurf.plugins.core.model_manager.api.records import ModelRow, collect_model_rows

_VIEW_JSON = pathlib.Path(__file__).parent / "models.view.json"

#: The settings key the model combo filters on (``chisurf/gui/main.py``).
DISABLED_KEY = "disabled_models"


class ModelManagerViewModel:
    """State and behaviour of the model manager panel."""

    def __init__(self, settings_block: dict[str, Any] | None = None) -> None:
        self._view_json = _VIEW_JSON
        self._observers: list[Any] = []

        if settings_block is None:
            try:
                import chisurf as cs

                settings_block = cs.core.settings.cs_settings.setdefault("plugins", {})
            except Exception:
                settings_block = {}
        self._settings_block = settings_block

        # A private copy. The old manager held the *same list object* as the
        # live settings and mutated it in place, so ticking a checkbox took
        # effect immediately and closing without saving did not undo it.
        self._disabled: list[str] = [str(x) for x in (settings_block.get(DISABLED_KEY) or [])]
        self._saved = list(self._disabled)

        self._rows: list[ModelRow] = []
        self._selected_key = ""
        self._status = ""
        self.show_disabled = True
        self.reload()

    # -- plumbing --------------------------------------------------------

    def add_observer(self, callback) -> None:
        """Register a callback invoked after every change."""
        self._observers.append(callback)

    def notify(self, event: str = "changed") -> None:
        """Tell observers something changed."""
        for callback in list(self._observers):
            try:
                callback(event)
            except Exception:  # pragma: no cover
                pass

    def view_spec(self):
        """The parsed view specification for this panel."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(self._view_json)

    def reload(self) -> None:
        """Re-read the model registry."""
        self._rows = collect_model_rows(disabled=self._disabled)
        if self._selected_key and not any(r.key == self._selected_key for r in self._rows):
            self._selected_key = ""
        self.notify("reloaded")

    # -- table -----------------------------------------------------------

    @property
    def rows(self) -> list[ModelRow]:
        """Every registered model."""
        return list(self._rows)

    def visible_rows(self) -> list[ModelRow]:
        """Rows after the show/hide-disabled filter."""
        if self.show_disabled:
            return list(self._rows)
        return [r for r in self._rows if not r.disabled]

    def model_rows(self) -> list[dict[str, Any]]:
        """The table source."""
        return [row.as_record() for row in self.visible_rows()]

    def select_row(self, record: Any) -> None:
        """Called by the table when the selection moves."""
        if isinstance(record, dict):
            wanted = (record.get("module"), record.get("name"))
            self._selected_key = next(
                (r.key for r in self.visible_rows() if (r.module, r.name) == wanted),
                "",
            )
        elif isinstance(record, int) and 0 <= record < len(self.visible_rows()):
            self._selected_key = self.visible_rows()[record].key
        else:
            self._selected_key = ""
        self.notify("selected")

    @property
    def selected(self) -> ModelRow | None:
        """The selected model."""
        return next((r for r in self._rows if r.key == self._selected_key), None)

    # -- details ---------------------------------------------------------

    def details_text(self) -> str:
        """A markdown summary of the selected model."""
        row = self.selected
        if row is None:
            return (
                "### No model selected\n\n"
                "Pick a row to see what the model is, which experiment offers "
                "it, and how its parameter panel is described."
            )
        lines = [f"### {row.name}", ""]
        if row.doc:
            lines += [row.doc, ""]
        lines += [
            f"- **Experiment:** {row.experiment_label} (`{row.experiment}`)",
            f"- **Class:** `{row.module}.{row.qualname}`",
            f"- **Status:** {'disabled' if row.disabled else 'enabled'}",
            f"- **Parameter UI:** {'a Qt class' if row.qt_bound else 'a view spec'}",
        ]
        if row.view_spec:
            state = "resolves" if row.view_spec_ok else "**declared but not found**"
            lines.append(f"- **View spec:** `{row.view_spec}` — {state}")
        else:
            lines.append("- **View spec:** none declared")

        if row.shares_name_with:
            lines += [
                "",
                "> **Shared name.** Other experiments offer a model called "
                f"`{row.name}` too ({', '.join(row.shares_name_with)}). The "
                "disabled-model setting matches on the name, so switching this "
                "one off switches off all of them.",
            ]
        return "\n".join(lines)

    def status_text(self) -> str:
        """The status line under the table."""
        if self._status:
            return self._status
        total = len(self._rows)
        off = sum(1 for r in self._rows if r.disabled)
        parts = [f"{total} models", f"{off} disabled"]
        stale = [n for n in self._disabled if not any(r.name == n for r in self._rows)]
        if stale:
            parts.append(f"{len(stale)} disabled name(s) match no model")
        if self.dirty:
            parts.append("unsaved changes")
        return " · ".join(parts)

    def set_status(self, text: str) -> None:
        """Show *text* until the next reload."""
        self._status = text
        self.notify("status")

    def stale_entries(self) -> list[str]:
        """Disabled names that match no registered model.

        The shipped defaults carry two (``Et-Model free``, ``Dye-diffusion``)
        that no longer exist, and nothing ever reported them.
        """
        return sorted(n for n in self._disabled if not any(r.name == n for r in self._rows))

    # -- edits -----------------------------------------------------------

    @property
    def selected_disabled(self) -> bool:
        """Whether the selected model is switched off."""
        row = self.selected
        return bool(row and row.disabled)

    @selected_disabled.setter
    def selected_disabled(self, value: bool) -> None:
        row = self.selected
        if row is None:
            return
        if value and row.name not in self._disabled:
            self._disabled.append(row.name)
        elif not value:
            self._disabled = [n for n in self._disabled if n != row.name]
        self.reload()

    def drop_stale(self) -> int:
        """Remove disabled names that match no model. Returns how many went."""
        stale = set(self.stale_entries())
        if not stale:
            return 0
        self._disabled = [n for n in self._disabled if n not in stale]
        self.reload()
        self.set_status(f"Dropped {len(stale)} stale entr{'y' if len(stale) == 1 else 'ies'}.")
        return len(stale)

    # -- persistence -----------------------------------------------------

    @property
    def dirty(self) -> bool:
        """Whether there are unsaved changes."""
        return self._disabled != self._saved

    def save(self) -> bool:
        """Write ``plugins.disabled_models`` to the user's settings file.

        The old Save resolved its target through ``cs_settings.get(
        'use_source_folder', True)`` -- which is not a settings key at all, only
        a parameter name -- so the default always won and it wrote
        ``settings_chisurf.yaml`` *inside the installed package*. Settings load
        as packaged-defaults-merged-with-the-user-file, user wins, so the write
        was discarded on the next start (or raised PermissionError on a
        read-only install) while the dialog reported success.
        """
        from chisurf.core.settings.settings_utils import update_settings_section

        self._settings_block[DISABLED_KEY] = list(self._disabled)
        written = update_settings_section("plugins", {DISABLED_KEY: list(self._disabled)})
        if written:
            self._saved = list(self._disabled)
            self.set_status("Saved. The model list updates on the next dataset selection.")
        else:
            self.set_status("Could not write the settings file -- see the log for why.")
        return written

    def revert(self) -> None:
        """Discard unsaved changes."""
        self._disabled = list(self._saved)
        self.reload()
        self.set_status("Unsaved changes discarded.")
