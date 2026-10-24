"""The shared metadata editor: one core plugin, embedded by every host.

- ``core``: the Qt-free state (schema of typed fields + free-form extras).
- ``gui.widget.MetadataEditorWidget``: the EMTK body hosts embed.
- ``gui.app.MetadataEditorApp``: the standalone window (``?app=metadata-editor``).
"""

from .core import EditorModel, Field, Schema, flrcif_schema, freeform_schema, zenodo_schema

__all__ = [
    "EditorModel",
    "Field",
    "Schema",
    "flrcif_schema",
    "freeform_schema",
    "zenodo_schema",
]
