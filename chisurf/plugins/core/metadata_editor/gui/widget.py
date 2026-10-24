"""The EMTK body of the shared metadata editor.

:class:`MetadataEditorWidget` draws an :class:`~chisurf.plugins.core.metadata_editor.core.EditorModel`:
the schema's typed fields, the free-form extras with their add row and delete
button, the validation verdict, and Apply / Cancel. It draws *only* the body --
the host puts it where metadata belongs (a panel of its window, a dialog, a tab),
so every plugin that has metadata gets the same editor without owning any of it.
"""

from __future__ import annotations

from typing import Any, Callable

from emtk import im
from emtk.i18n import tr
from emtk.view_form import FormState, draw_sections

from ..core import EditorModel, Schema

__all__ = ["MetadataEditorWidget"]


class _Values:
    """The schema's values as attributes (what ``draw_sections`` binds to)."""

    def __init__(self, values: dict[str, str]) -> None:
        object.__setattr__(self, "_values", values)

    def __getattr__(self, key: str) -> str:
        values = object.__getattribute__(self, "_values")
        return values.get(key, "")

    def __setattr__(self, key: str, value: Any) -> None:
        object.__getattribute__(self, "_values")[key] = str(value)


class _SafeEditor:
    """The :class:`EditorModel` behind a guard: a bad add shows as a message, not a crash.

    ``draw_sections`` invokes ``add_extra`` bare, so the widget intercepts the
    one error a user can provoke (an entry without a key) and shows it inline.
    """

    def __init__(self, editor: EditorModel, message: list[str]) -> None:
        object.__setattr__(self, "_editor", editor)
        object.__setattr__(self, "_message", message)

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_editor"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(object.__getattribute__(self, "_editor"), name, value)

    def add_extra(self, *_args: Any) -> None:
        editor = object.__getattribute__(self, "_editor")
        message = object.__getattribute__(self, "_message")
        try:
            editor.add_extra()
        except ValueError as exc:
            message[0] = str(exc)

    def remove_extra(self, record: dict) -> None:
        object.__getattribute__(self, "_editor").remove_extra(record)


def _field_sections(schema: Schema) -> list[dict]:
    """The schema's fields as view-form sections (typed inputs)."""
    sections: list[dict] = []
    for field in schema:
        section: dict[str, Any] = {
            "type": "value",
            "attr": field.key,
            "label": f"{field.display_label} *" if field.required else field.display_label,
            "kind": field.kind,
        }
        if field.kind == "choice":
            section["options"] = list(field.options)
        if field.placeholder:
            section["placeholder"] = field.placeholder
        if field.help:
            section["description"] = field.help
        sections.append(section)
    return sections


_ADD_SECTIONS: list[dict] = [
    {"type": "value", "attr": "extra_key", "label": "Add key", "kind": "str",
     "description": "A new (or existing) key for an entry beyond the schema."},
    {"type": "value", "attr": "extra_value", "label": "Add value", "kind": "str",
     "description": "Its value. Add entry adds (or replaces) the entry."},
    {"type": "button_row", "buttons": [
        {"label": "Add entry", "action": "add_extra",
         "description": "Add or replace the entry for this key."},
    ]},
]

_EXTRAS_SECTION: dict = {
    "type": "custom",
    "key": "data_table",
    "title": "",
    "description": "Every entry. Select a row and press Delete to remove it.",
    "options": {
        "source": "rows",
        "row_key": "key",
        "delete_call": "remove_extra",
        "editable": False,
        "height": 150,
        "columns": [
            {"key": "key", "title": "Key", "width": 160, "tooltip": "Metadata key."},
            {"key": "value", "title": "Value", "width": 240, "tooltip": "Metadata value."},
        ],
    },
}


class MetadataEditorWidget:
    """The one metadata editor body: typed fields, free-form extras, Apply."""

    def __init__(
        self,
        on_apply: Callable[[dict[str, str]], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        self.on_apply = on_apply
        self.on_cancel = on_cancel
        self.editor: EditorModel | None = None
        self.form = FormState(on_used=lambda name: None)
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self._values: _Values | None = None
        self._sections: list[dict] = []
        #: the inline message of the guarded add (index 0 is replaced as it happens)
        self._message: list[str] = [""]

    # -- open / close ---------------------------------------------------------------- #
    def open(self, schema: Schema, initial: dict[str, Any] | None = None) -> None:
        """Fill the editor from *initial* (schema fields and extras alike)."""
        self.editor = EditorModel(schema, initial)
        self._values = _Values(self.editor.values)
        self._sections = _field_sections(schema)
        self._message[0] = ""

    def close(self) -> None:
        self.editor = None
        self._message[0] = ""

    @property
    def visible(self) -> bool:
        return self.editor is not None

    # -- drawing --------------------------------------------------------------------- #
    def draw(self) -> None:
        """Draw the editor body (the host frames it)."""
        editor = self.editor
        if editor is None:
            im.text_wrapped(tr("Nothing to edit: open the editor with metadata."))
            return
        safe = _SafeEditor(editor, self._message)
        if editor.schema:
            draw_sections(self._sections, self._values, self.form)
            im.spacing()
        im.text_colored((1.0, 0.8, 0.4, 1.0), tr("Further entries"))
        im.text_wrapped(tr("Anything beyond the typed fields: add it as key/value."))
        draw_sections(_ADD_SECTIONS, safe, self.form)
        self.item_rects.update(self.form.rects)
        problems = editor.errors()
        if self._message[0]:
            im.text_colored((1.0, 0.5, 0.5, 1.0), tr(self._message[0]))
        for text in problems.values():
            im.text_colored((1.0, 0.5, 0.5, 1.0), tr(text))
        im.spacing()
        im.begin_disabled(bool(problems))
        pressed_apply = im.button(tr("Apply"), role="primary")
        im.end_disabled()
        im.set_item_tooltip(
            tr("Store every entry (nothing is written until the host applies it).")
        )
        self.remember("apply")
        im.same_line()
        pressed_cancel = im.button(tr("Cancel"))
        im.set_item_tooltip(tr("Leave the metadata as it was."))
        self.remember("cancel")
        if pressed_apply:
            entries = editor.entries()
            self.close()
            if callable(self.on_apply):
                self.on_apply(entries)
        elif pressed_cancel:
            self.close()
            if callable(self.on_cancel):
                self.on_cancel()
        # The entries table last: a table region takes the pointer over its area,
        # so the buttons stay above it, where their clicks land.
        draw_sections([_EXTRAS_SECTION], safe, self.form)
        self.item_rects.update(self.form.rects)

    def remember(self, name: str) -> None:
        """Record the last item's rect for tours and tests."""
        rect = im.get_item_rect()
        if rect is not None:
            self.item_rects[name] = tuple(rect)  # type: ignore[assignment]
