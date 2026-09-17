"""The node editor: a emtk-backed graph editor, imported on demand.

The editor itself is Qt-free: the graph is a plain
:class:`~.document.GraphDocument` and the editing behaviour lives in
:class:`~.emtk_control.GraphControl`, which draws through `emtk` and is
hosted — in a Qt window by :class:`~.widget.NodeGraphWidget`, in a browser
or a headless test by the same control. The Qt wrapper adds only the
signals the consumers connect to.

Nothing here is imported at module level so the headless submodules stay
importable without Qt; names resolve lazily (PEP 562).
"""

import importlib

#: exported name -> submodule that defines it
_LAZY = {
    "NodeGraphWidget": "widget",
}

__all__ = list(_LAZY)


def __getattr__(name):
    """Import the submodule that defines *name* on first access (PEP 562)."""
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value  # subsequent lookups skip this hook
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY))
