"""ChiSurf Code Editor: a multi-document editor, notebooks and an AI assistant, drawn by emtk.

The window is the emtk app (``gui/editor_app.py``, ``gui/notebook_app.py``, ``gui/chat_app.py``);
the toolkit-free parts are the document store, symbols, Ruff runner, ``.ipynb`` I/O, the shipped
notebooks, assistant file writes and modes.
"""

from pathlib import Path

from chisurf.core.plugin import load_manifest
from chisurf.plugins.core.code_editor.document_store import DocumentSnapshot, DocumentStore
from chisurf.plugins.core.code_editor.shipped_notebooks import shipped_notebooks
from chisurf.plugins.core.code_editor.symbols import CodeSymbol, extract_python_symbols

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Tools:System:Code Editor"
icon = "📝"  # Memo/notepad emoji for editor


def load():
    """Return the plugin's editor window (the emtk app)."""
    from chisurf.plugins.core.code_editor.gui.editor_app import make_editor_app

    return make_editor_app()


load_emtk = load

__all__ = [
    "name",
    "load",
    "load_emtk",
    "icon",
    "DocumentSnapshot",
    "DocumentStore",
    "CodeSymbol",
    "shipped_notebooks",
    "extract_python_symbols",
]
