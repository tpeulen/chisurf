"""Toolkit-neutral contracts for AutoForm rows that are not fitted ports.

A parameter table normally displays a canonical scientific port and therefore
must retain exact UID/object identity against the restored model.  Some forms
also show document configuration (a described-model scalar) or a value computed
from the model.  Those rows must not masquerade as ports: their binding is plain
JSON-compatible data naming the real owner, kind and path.

The contract deliberately carries no Qt object, callback, model instance or
serialized widget state.  Renderers resolve ``owner`` against their live model;
the canonical session codec continues to persist the named scientific state.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: The binding categories supported by the shared parameter-table renderer.
MODEL_SCALAR = "model_scalar"
COMPUTED_OUTPUT = "computed_output"
DATA_METADATA = "data_metadata"

#: The only owner/kind/editability combinations that table-only rows may claim.
_BINDING_RULES = {
    ("model", MODEL_SCALAR): True,
    ("model", COMPUTED_OUTPUT): False,
    ("fit.data", DATA_METADATA): False,
}


def validate_display_binding(binding: Mapping[str, Any]) -> dict[str, Any]:
    """Return a validated, JSON-compatible copy of one display-row binding.

    ``owner`` is intentionally a stable symbolic path rather than a Python
    object.  ``path`` is interpreted only by the renderer/probe for the given
    kind: an explicit description scalar, a computed model attribute, or a
    data-metadata projection.  This keeps the scientific state and its UI
    projection separable without preserving a callback or a widget.
    """
    if not isinstance(binding, Mapping):
        raise TypeError("display binding must be a mapping")
    if set(binding) != {"owner", "kind", "path", "editable"}:
        raise ValueError("display binding must contain owner, kind, path and editable")
    owner = binding["owner"]
    kind = binding["kind"]
    path = binding["path"]
    editable = binding["editable"]
    if not isinstance(owner, str) or not owner:
        raise ValueError("display binding owner must be a nonempty string")
    if not isinstance(kind, str) or not kind:
        raise ValueError("display binding kind must be a nonempty string")
    if not isinstance(path, str) or not path or path.startswith(".") or path.endswith("."):
        raise ValueError("display binding path must be a nonempty dotted string")
    if type(editable) is not bool:
        raise ValueError("display binding editable must be a bool")
    expected_editable = _BINDING_RULES.get((owner, kind))
    if expected_editable is None:
        raise ValueError(f"unsupported display binding owner/kind: {owner!r}/{kind!r}")
    if editable is not expected_editable:
        raise ValueError("display binding editability conflicts with its kind")
    return {"owner": owner, "kind": kind, "path": path, "editable": editable}


def model_scalar_binding(path: str) -> dict[str, Any]:
    """Declare one editable description scalar projected into a table row."""
    return validate_display_binding(
        {"owner": "model", "kind": MODEL_SCALAR, "path": path, "editable": True}
    )


def computed_output_binding(path: str) -> dict[str, Any]:
    """Declare one read-only value calculated by a model/group property."""
    return validate_display_binding(
        {"owner": "model", "kind": COMPUTED_OUTPUT, "path": path, "editable": False}
    )


def data_metadata_binding(path: str) -> dict[str, Any]:
    """Declare one read-only display projection of the fit data's metadata."""
    return validate_display_binding(
        {"owner": "fit.data", "kind": DATA_METADATA, "path": path, "editable": False}
    )


__all__ = [
    "COMPUTED_OUTPUT",
    "DATA_METADATA",
    "MODEL_SCALAR",
    "computed_output_binding",
    "data_metadata_binding",
    "model_scalar_binding",
    "validate_display_binding",
]
