"""The standalone metadata editor window: edit a JSON metadata file, any schema.

Hosts embed :class:`~chisurf.plugins.core.metadata_editor.gui.widget.MetadataEditorWidget`
into their own windows; this app is the same editor on its own -- open it from
the hub (``?app=metadata-editor``), open a JSON file, edit, save. A schema
picks the typed fields: *free-form* (no typed fields), *flrCIF* (the analysis
metadata of a burst export), or *Zenodo* (a deposit).
"""

from __future__ import annotations

import json
import pathlib

from emtk import im, style
from chisurf.plugins.emtk_layout import action_button
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.file_dialog import FileDialog
from emtk.i18n import tr

from ..core import flrcif_schema, freeform_schema, zenodo_schema
from .widget import MetadataEditorWidget

_FILTERS = [("Metadata (JSON)", ["*.json"]), ("All files", ["*"])]

#: name -> factory; the combo's order is this tuple's.
_SCHEMAS = (
    ("free-form", freeform_schema),
    ("flrCIF", flrcif_schema),
    ("Zenodo", zenodo_schema),
)


class MetadataEditorApp(ImApp):
    """A JSON metadata file in the shared editor."""

    def __init__(self) -> None:
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.path: pathlib.Path | None = None
        self.schema_name = "free-form"
        self.editor = MetadataEditorWidget(on_apply=self._applied)
        self.file_window = DialogWindow(title=tr("Metadata file"), size=(700.0, 440.0))
        self.dialog: FileDialog | None = None
        self._dialog_save = False
        self._error = ""
        self.editor.open(freeform_schema(), {})
        from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

        here = pathlib.Path(__file__).resolve().parent
        self.help_window = EmTkHelpWindow(
            title="Metadata editor — Help", resource=here / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=here / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key),
        )
        super().__init__(gui=self._render)

    # -- schema ----------------------------------------------------------------------- #
    def _schema(self):
        for name, factory in _SCHEMAS:
            if name == self.schema_name:
                return factory()
        return freeform_schema()

    def pick_schema(self, name: str) -> None:
        """Switch the schema, keeping what has been typed."""
        if name not in dict(_SCHEMAS):
            return
        entries = self.editor.editor.entries() if self.editor.editor else {}
        self.schema_name = name
        self.editor.open(self._schema(), entries)

    # -- files ------------------------------------------------------------------------ #
    def choose_open(self) -> None:
        self.dialog = FileDialog(
            tr("Open metadata"), mode="open", multiselect=False, filters=_FILTERS
        )
        self._dialog_save = False
        self.dialog.open()
        self.file_window.show()

    def choose_save(self) -> None:
        self.dialog = FileDialog(
            tr("Save metadata as"), mode="save", filters=_FILTERS, filename="metadata.json"
        )
        self._dialog_save = True
        self.dialog.open()
        self.file_window.show()

    def _read(self, path: pathlib.Path) -> dict:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("the file is not a JSON object")
        return payload

    def _applied(self, entries: dict[str, str]) -> None:
        """Apply hands the entries back; with a file open they are written to it."""
        if self.path is None:
            self._error = tr("Open a .json file first -- or keep editing and Save as…")
            self.editor.open(self._schema(), entries)
            return
        self._error = ""
        self.path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")

    def save_as(self, path: str | pathlib.Path) -> None:
        """Write the current entries to *path* and make it the open file."""
        entries = self.editor.editor.entries() if self.editor.editor else {}
        self.path = pathlib.Path(path)
        self.path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
        self._error = ""

    # -- frame ------------------------------------------------------------------------ #
    def _render(self) -> None:
        names = [n for n, _ in _SCHEMAS]
        im.text(tr("Schema:"))
        im.same_line()
        im.set_next_item_width(220.0)
        changed, index = im.combo("##schema", names.index(self.schema_name), names)
        im.set_item_tooltip(tr("Which metadata schema to edit."))
        if changed:
            self.pick_schema(names[index])
        self.remember("schema")
        if action_button("open", tooltip=tr("Open a metadata record.")):
            self.choose_open()
        self.remember("open")
        im.same_line()
        if im.button(tr("Save as…"), tooltip=tr("Write the metadata record to a file.")):
            self.choose_save()
        self.remember("save_as")
        name = self.path.name if self.path else tr("no file")
        im.text(tr("File: {}").format(name))
        if self._error:
            im.text_colored(style.TEXT_DANGER, tr(self._error))
        im.separator()

        if self.dialog is not None:
            # The chooser is modal: the editor behind it is idle while a file is
            # picked, and nothing of it can sit under the chooser's buttons.
            close = self.file_window.begin((0, 58, 640, 460))
            selected = self.dialog.draw()
            self.file_window.end()
            if close or selected is False:
                self.dialog = None
            elif selected:
                saving, self.dialog = self._dialog_save, None
                target = pathlib.Path(str(selected[0]))
                if saving:
                    self.save_as(target)
                else:
                    try:
                        payload = self._read(target)
                    except (OSError, ValueError) as exc:
                        self._error = f"{target.name}: {exc}"
                    else:
                        self._error = ""
                        self.path = target
                        self.editor.open(self._schema(), payload)
            return  # the chooser's frame

        self.editor.draw()
        self.item_rects.update(self.editor.item_rects)
        vp = im.get_main_viewport()
        self.help_window.draw((*vp.pos, *vp.size))
        self.tour.draw(*vp.size)


def make_app() -> "MetadataEditorApp":
    """The plugin registry's EMTK entrypoint."""
    return MetadataEditorApp()


__all__ = ["MetadataEditorApp", "make_app"]
