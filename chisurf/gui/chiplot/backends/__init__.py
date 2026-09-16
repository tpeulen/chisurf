"""Backend selection for chiplot.

The active backend is chosen once, lazily. The resolution order is:

1. ``CHISURF_PLOT_BACKEND`` environment variable.
2. ``gui.plot.backend`` from the ChiSurf settings (``settings_chisurf.yaml``).
3. ``"pyqtgraph"`` (the default).

A new backend registers here via :func:`register_backend` and becomes
selectable with no call-site change.
"""

from __future__ import annotations

import os

from chisurf.gui.chiplot.backends import base

_REGISTRY: dict[str, str] = {
    # name -> "module:ClassName"
    # The two supported options: pyqtgraph (the engine) and
    # emtk (chimol's ImPlot-style toolkit), the designated native
    # renderer / primary plotting widget. Target state of _REGISTRY.
    "pyqtgraph": "chisurf.gui.chiplot.backends.pyqtgraph_backend:PyQtGraphBackend",
    # TODO(emtk-backend): register chimol's emtk here as the native backend once
    # a chiplot backend for it exists. Until
    # then wgpu/opengl stay registered so the backend seam is exercisable.
    # Both are superseded experiment backends and retire when emtk lands.
    #   "emtk": "chisurf.gui.chiplot.backends.emtk_backend:EmtkBackend",
    "wgpu": "chisurf.gui.chiplot.backends.wgpu:WgpuBackend",
    # Superseded by the emtk direction; kept until the emtk backend has been
    # through the plot families, then removed.
    "opengl": "chisurf.gui.chiplot.backends.opengl:OpenGLBackend",
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
    return "pyqtgraph"


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
