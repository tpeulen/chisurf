"""The editor core: schemas, validation, entries -- no drawing."""

from .widget import MetadataEditorWidget
from .app import MetadataEditorApp, make_app

__all__ = ["MetadataEditorWidget", "MetadataEditorApp", "make_app"]
