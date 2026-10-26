"""The editor core: schemas, validation, entries -- no drawing."""

from .app import MetadataEditorApp, make_app
from .widget import MetadataEditorWidget

__all__ = ["MetadataEditorWidget", "MetadataEditorApp", "make_app"]
