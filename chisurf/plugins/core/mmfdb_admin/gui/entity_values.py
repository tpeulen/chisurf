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
