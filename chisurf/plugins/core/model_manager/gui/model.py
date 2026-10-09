"""Qt-free model of the native model manager.

:class:`ModelManagerModel` is the shared :class:`~.view_model.ModelManagerViewModel`
(registry rows, the disabled list, save and revert) plus what only the painted
window needs: a record list for the table that keeps its identity between
frames, the two confirmations the Qt tool asked through message boxes, a
background rescan, and the table's CSV text for Copy and Export.
"""

from __future__ import annotations

import csv
import io
import pathlib
from typing import Any, Callable

from chisurf.plugins.core.model_manager.gui.view_model import ModelManagerViewModel

#: The columns the table shows, in order: ``(record key, header)``.
TABLE_COLUMNS = (
    ("name", "Model"),
    ("experiment", "Experiment"),
    ("status", "Status"),
    ("spec", "Spec"),
    ("ui", "Parameter UI"),
    ("shared", "Shared"),
)


class _Records(list):
    """A list of table records that says when its content changed.

    The painted table re-reads its source when the list object, its length or
    its ``revision`` changes; a status that flips from enabled to disabled
    changes none of the first two, so the revision carries it.
    """

    revision = 0


class ModelManagerModel(ModelManagerViewModel):
    """State and actions behind the emtk model manager."""

    def __init__(self, settings_block: dict[str, Any] | None = None) -> None:
        #: ``runner(method_name)`` runs a model method off the draw loop (the
        #: app's :class:`~chisurf.emtk.jobs.SnapshotJob`); ``None`` runs it here.
        self.runner: Callable[[str], bool] | None = None
        self.busy = False
        #: ``"revert"`` / ``"drop_stale"`` while the app asks the user to confirm.
        self.confirm = ""
        #: ``"export"`` / ``"copy"`` while the app should act on the table.
        self.request = ""
        #: Returns the records the table shows (filtered, sorted) and its columns.
        self.displayed_provider: Callable[[], tuple[list[dict], list[tuple[str, str]]]] | None = (
            None
        )
        self._records = _Records()
        self._signature: tuple = ()
        super().__init__(settings_block)

    # -- table source ----------------------------------------------------

    def model_rows(self) -> list[dict[str, Any]]:
        """The table source: one record per visible model, stable between edits."""
        records = [row.as_record() for row in self.visible_rows()]
        signature = tuple(tuple(r.items()) for r in records)
        if signature != self._signature:
            self._signature = signature
            fresh = _Records(records)
            fresh.revision = self._records.revision + 1
            self._records = fresh
        return self._records

    @property
    def selected_key(self) -> str:
        """``module.qualname`` of the selected model, ``""`` for none."""
        return self._selected_key

    def select_key(self, key: str) -> None:
        """Select the model with *key* (a no-op when there is none)."""
        if any(r.key == key for r in self._rows):
            self._selected_key = key
            self.notify("selected")

    # -- what the controls may do ----------------------------------------

    def enabled(self, name: str) -> bool:
        """Whether the control *name* is usable now."""
        if name == "selected_disabled":
            return self.selected is not None and not self.busy
        if name in ("save", "ask_revert", "rescan", "ask_drop_stale"):
            return not self.busy and not self.confirm
        return True

    # -- confirmations ---------------------------------------------------

    def ask_revert(self) -> None:
        """Revert, after the user confirms; nothing to ask when nothing changed."""
        if not self.dirty:
            self.set_status("Nothing to revert.")
            return
        self.confirm = "revert"

    def ask_drop_stale(self) -> None:
        """Drop stale entries, after the user confirms."""
        if not self.stale_entries():
            self.set_status("No stale entries: every disabled name matches a model.")
            return
        self.confirm = "drop_stale"

    @property
    def confirm_title(self) -> str:
        """Title of the confirmation dialog."""
        return {"revert": "Discard changes", "drop_stale": "Drop stale entries"}.get(
            self.confirm, ""
        )

    @property
    def confirm_text(self) -> str:
        """The question the confirmation dialog asks."""
        if self.confirm == "revert":
            return "Discard every model setting changed since the last save?"
        if self.confirm == "drop_stale":
            return (
                "These disabled entries match no registered model and do nothing:\n  "
                + "\n  ".join(self.stale_entries())
                + "\n\nRemove them?"
            )
        return ""

    def confirm_yes(self) -> None:
        """The user agreed: do what was asked."""
        action, self.confirm = self.confirm, ""
        if action == "revert":
            self.revert()
        elif action == "drop_stale":
            self.drop_stale()

    def confirm_no(self) -> None:
        """The user declined: nothing changes."""
        self.confirm = ""

    # -- rescan ----------------------------------------------------------

    def rescan(self) -> None:
        """Read the experiment registry again, in the background when a runner is set."""
        if self.runner is not None and self.runner("scan"):
            self.busy = True
            return
        self.scan()

    def scan(self) -> None:
        """The work of :meth:`rescan`: re-read the registry and say so."""
        self.reload()
        self.set_status("Model registry re-read.")

    # -- copy and export -------------------------------------------------

    def request_copy(self) -> None:
        """Ask the app to copy the shown rows to the clipboard."""
        self.request = "copy"

    def request_export(self) -> None:
        """Ask the app to choose a CSV file for the shown rows."""
        self.request = "export"

    def displayed(self) -> tuple[list[dict], list[tuple[str, str]]]:
        """The rows and columns the table shows: after its filter, sort and column choice."""
        if self.displayed_provider is not None:
            records, columns = self.displayed_provider()
            return list(records), list(columns)
        return list(self.model_rows()), list(TABLE_COLUMNS)

    def table_text(self, delimiter: str = "\t", header: bool = True) -> str:
        """The shown rows as delimited text."""
        records, columns = self.displayed()
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
        if header:
            writer.writerow([title for _key, title in columns])
        for record in records:
            writer.writerow([record.get(key, "") for key, _title in columns])
        return buffer.getvalue()

    def export_csv(self, path: str) -> bool:
        """Write the shown rows to *path* as CSV; returns whether it worked."""
        try:
            target = pathlib.Path(path)
            if target.suffix == "":
                target = target.with_suffix(".csv")
            target.write_text(self.table_text(",", True), encoding="utf-8", newline="")
        except OSError as exc:
            self.set_status(f"Could not write {path}: {exc}")
            return False
        self.set_status(f"Exported {len(self.displayed()[0])} rows to {target}.")
        return True
