"""Node editor widgets, imported on demand.

The GUI classes are not imported at module level so that the headless
submodules (model, graph, registry) stay importable without Qt. They are
resolved lazily instead of merely being named in ``__all__``: a name promised
there but never bound raises ``AttributeError`` on the attribute access that
``__all__`` invites, which is what ``node_editor.NodeEditorWidget`` did.
"""
import importlib

#: exported name -> submodule that defines it
_LAZY = {
    "apply_node_ui_theme": "theme_widgets",
    "StyledComboBox": "theme_widgets",
    "InlineLabeledSlider": "inline_slider",
    "Vector1DWidget": "vector_widget",
    "NodeEditorWidget": "editor",
    "NodeViewerWidget": "node_viewer",
}

__all__ = list(_LAZY)


def __getattr__(name):
    """Import the submodule that defines *name* on first access (PEP 562)."""
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value          # subsequent lookups skip this hook
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY))
