"""Backend selection for chiplot.

The active backend is chosen once, lazily. The resolution order is:

1. ``CHISURF_PLOT_BACKEND`` environment variable.
2. ``gui.plot.backend`` from the ChiSurf settings (``settings_chisurf.yaml``).
3. ``"emtk"`` (the default).

A new backend registers here via :func:`register_backend` and becomes
selectable with no call-site change.
"""

from __future__ import annotations

import os

from chisurf.gui.chiplot.backends import base

_REGISTRY: dict[str, str] = {
    # name -> "module:ClassName"
    # emtk, the native renderer and the default: chimol's own toolkit, drawn
    # through its painter. What it does not draw yet raises a
    # NotImplementedError naming the family and PRD-104; pyqtgraph stays
    # selectable for those (CHISURF_PLOT_BACKEND=pyqtgraph).
    "emtk": "chisurf.gui.chiplot.backends.emtk_backend:EmtkBackend",
    "pyqtgraph": "chisurf.gui.chiplot.backends.pyqtgraph_backend:PyQtGraphBackend",
}

_active: base.Backend | None = None


def _resolve_backend_name() -> str:
    """Return the backend name following the documented resolution order."""
    env_name = os.environ.get("CHISURF_PLOT_BACKEND")
    if env_name:
        return env_name
    try:
        from chisurf.core import settings as _cs
        name = _cs.cs_settings.get("gui", {}).get("plot", {}).get("backend")
        if name:
            return name
    except Exception:
        pass
    return "emtk"


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


def available_backends() -> list[str]:
    """Return the sorted names of all registered backends."""
    return sorted(_REGISTRY)


def get_backend() -> base.Backend:
    """Return the process-wide active backend, instantiating it on first use.

    Returns
    -------
    base.Backend

    Raises
    ------
    KeyError
        If the resolved backend name is not registered.
    """
    global _active
    if _active is None:
        name = _resolve_backend_name()
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
