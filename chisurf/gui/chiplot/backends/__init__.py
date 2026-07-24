"""Backend selection for chiplot.

The active backend is chosen once, lazily, from the ``CHISURF_PLOT_BACKEND``
environment variable (default ``"pyqtgraph"``). A future OpenGL backend
registers here and becomes selectable without any call-site change.
"""

from __future__ import annotations

import os

from chisurf.gui.chiplot.backends import base

_REGISTRY: dict[str, str] = {
    # name -> "module:ClassName"
    "pyqtgraph": "chisurf.gui.chiplot.backends.pyqtgraph_backend:PyQtGraphBackend",
}

_active: base.Backend | None = None


def register_backend(name: str, dotted_path: str) -> None:
    """Register a backend implementation under a name.

    Parameters
    ----------
    name : str
        Selection key (matched against ``CHISURF_PLOT_BACKEND``).
    dotted_path : str
        ``"package.module:ClassName"`` of a :class:`base.Backend` subclass.
    """
    _REGISTRY[name] = dotted_path


def get_backend() -> base.Backend:
    """Return the process-wide active backend, instantiating it on first use.

    Returns
    -------
    base.Backend

    Raises
    ------
    KeyError
        If ``CHISURF_PLOT_BACKEND`` names an unregistered backend.
    """
    global _active
    if _active is None:
        name = os.environ.get("CHISURF_PLOT_BACKEND", "pyqtgraph")
        if name not in _REGISTRY:
            raise KeyError(f"unknown chiplot backend {name!r}; registered: {sorted(_REGISTRY)}")
        module_path, cls_name = _REGISTRY[name].split(":")
        import importlib

        cls = getattr(importlib.import_module(module_path), cls_name)
        _active = cls()
    return _active


def set_backend(name: str) -> None:
    """Force the active backend by name (resets any cached instance).

    Parameters
    ----------
    name : str
        A registered backend name.
    """
    global _active
    if name not in _REGISTRY:
        raise KeyError(f"unknown chiplot backend {name!r}; registered: {sorted(_REGISTRY)}")
    os.environ["CHISURF_PLOT_BACKEND"] = name
    _active = None
