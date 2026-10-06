"""How an MMFDB record's values are shown in an entity form and written back (Qt-free).

One definition for both renderers of the dictionary-driven entity form: the Qt
:class:`~.autoform_entity_form.EntityForm` and the native emtk admin. A field's
``widget`` (from :class:`~.entity_schema.FieldSpec`) decides the typed empty value,
how a stored value is coerced for editing, and how an edited value goes back into
the record (``1``/``0`` for a check box, ``None`` for an empty text, JSON for the
two fields the database stores as JSON).
"""

from __future__ import annotations

import json
from typing import Any

#: Fields stored as JSON in the database but edited as text.
JSON_LIST_FIELDS = frozenset({"laser_wavelengths"})
JSON_DICT_FIELDS = frozenset({"detector_channels"})


def default_for(fs: Any) -> Any:
    """Typed empty value of a field, so an editor builds without a coercion error."""
    widget = getattr(fs, "widget", "str")
    if widget == "int":
        return 0
    if widget == "float":
        return 0.0
    if widget == "bool":
        return False
    return ""


def coerce_in(fs: Any, val: Any) -> Any:
    """A stored value as the form edits it."""
    widget = getattr(fs, "widget", "str")
    if isinstance(val, (list, dict)):
        return json.dumps(val)
    if widget == "int":
        try:
            return int(val) if val not in (None, "") else 0
        except (TypeError, ValueError):
            return 0
    if widget == "float":
        try:
            return float(val) if val not in (None, "") else 0.0
        except (TypeError, ValueError):
            return 0.0
    if widget == "bool":
        return bool(val)
    return "" if val is None else str(val)


def coerce_out(fs: Any, raw: Any) -> Any:
    """An edited value as the record stores it."""
    name = getattr(fs, "name", "")
    widget = getattr(fs, "widget", "str")
    if widget == "bool":
        val: Any = 1 if raw else 0
    elif widget == "int":
        try:
            val = int(raw)
        except (TypeError, ValueError):
            val = 0
    elif widget == "float":
        try:
            val = float(raw)
        except (TypeError, ValueError):
            val = 0.0
    else:
        val = (str(raw).strip() or None) if raw is not None else None
    if name in JSON_LIST_FIELDS:
        try:
            return json.loads(val) if val else []
        except Exception:
            return []
    if name in JSON_DICT_FIELDS:
        try:
            return json.loads(val) if val else {}
        except Exception:
            return {}
    return val


def view_section(fs: Any, fk_source: str = "", read_only: bool = False) -> dict:
    """The ``view.json`` section of one entity field (the dialect AutoForm and emtk read).

    *fk_source* names the model's options method of a foreign key (a choice of
    ``(value, label)`` pairs); *read_only* forces a read-only field (an entity the
    server does not let you write).
    """
    name = getattr(fs, "name", "")
    label = getattr(fs, "label", "") or name
    widget = getattr(fs, "widget", "str")
    tip = getattr(fs, "tooltip", "") or label
    locked = bool(read_only or getattr(fs, "readonly", False))
    base = {"attr": name, "label": label, "description": tip}
    if fk_source and not locked:
        return {"type": "choice", "options_source": fk_source, "filter": True, **base}
    if widget == "choice" and not locked and getattr(fs, "choices", None):
        return {"type": "choice", "options_source": f"choices__{name}", **base}
    # A dictionary ``code`` item without an enumeration is free text, not an empty choice.
    if widget == "bool":
        if locked:
            return {"type": "value", "kind": "str", "read_only": True, **base}
        return {"type": "toggle", **base}
    kind = widget if widget in ("int", "float", "text") else "str"
    section = {"type": "value", "kind": kind, "read_only": locked, **base}
    if kind == "text":
        section["lines"] = 3
    placeholder = getattr(fs, "placeholder", "")
    if placeholder:
        section["placeholder"] = placeholder
    return section
