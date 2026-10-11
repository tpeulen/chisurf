"""
Code editor module providing syntax highlighting and editing capabilities.

This module provides a text editor with syntax highlighting for Python, JSON, and YAML.
It uses QSyntaxHighlighter and QPlainTextEdit instead of QScintilla2.
"""

from pathlib import Path

from chisurf.core.plugin import load_manifest
from chisurf.core.plugin.registry import apply_manifest_statefulness
from chisurf.plugins.core.code_editor.document_store import DocumentSnapshot, DocumentStore
from chisurf.plugins.core.code_editor.symbols import CodeSymbol, extract_python_symbols


def __getattr__(attribute):
    """Load legacy Qt exports only when a Qt caller explicitly requests them."""
    if attribute == "SimpleCodeEditor":
        from chisurf.gui.autoform.sections.code_editor_section import SimpleCodeEditor

        globals()[attribute] = SimpleCodeEditor
        return SimpleCodeEditor

    import importlib

    modules = {
        "CodeEditor": "editor",
        "CodeEditorWindow": "window",
        "NotebookEditor": "notebook_editor",
        "shipped_notebooks": "notebook_editor",
        "JSONHighlighter": "text_editor",
        "PythonHighlighter": "text_editor",
        "SyntaxHighlighter": "text_editor",
        "TextEditor": "text_editor",
        "YAMLHighlighter": "text_editor",
    }
    module = modules.get(attribute)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")
    value = getattr(importlib.import_module(f"{__name__}.{module}"), attribute)
    globals()[attribute] = value
    return value


_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Tools:System:Code Editor"
icon = "📝"  # Memo/notepad emoji for editor


def load():
    """Return the plugin's full editor window."""
    from .text_editor import CodeEditorWindow

    return CodeEditorWindow()


def load_emtk():
    """Return the plugin's EMTK editor window."""
    from chisurf.plugins.core.code_editor.gui.tool import CodeEditorEmtkTool

    return CodeEditorEmtkTool()


__all__ = [
    "name",
    "load",
    "icon",
    "CodeEditor",
    "CodeEditorWindow",
    "DocumentSnapshot",
    "DocumentStore",
    "CodeSymbol",
    "NotebookEditor",
    "shipped_notebooks",
    "JSONHighlighter",
    "PythonHighlighter",
    "TextEditor",
    "SimpleCodeEditor",
    "SyntaxHighlighter",
    "YAMLHighlighter",
    "extract_python_symbols",
]

if __name__ == "plugin":
    from chisurf.plugins.core.code_editor.gui.tool import CodeEditorEmtkTool

    window = CodeEditorEmtkTool()
    if _manifest is not None:
        apply_manifest_statefulness(window, _manifest)
    window.show()
