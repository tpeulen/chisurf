"""Qt-free native preferences and dock-layout persistence.

Factories stay deterministic. The native launcher binds persistence after
construction; callers can disable it when loading isolated test controls.
"""
from __future__ import annotations

import re
import sys

from emtk.docking import DockManager, LayoutStore, load_states, save_states


def _path(plugin_id: str, kind: str):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", plugin_id):
        raise ValueError(f"Invalid native plugin state id: {plugin_id!r}")
    from chisurf.core.settings.path_utils import get_path

    return get_path("settings") / "emtk" / f"{plugin_id}.{kind}.json"


def load_settings(plugin_id: str) -> dict:
    return load_states(_path(plugin_id, "settings"))


def save_settings(plugin_id: str, settings: dict) -> bool:
    """Write only the plugin's declared JSON preferences, not live results."""
    return save_states(settings, _path(plugin_id, "settings"))


def bind_layout(plugin_id: str, docks: DockManager) -> DockManager:
    """Restore a layout and automatically save subsequent dock changes."""
    path = None if sys.platform == "emscripten" else _path(plugin_id, "layout")
    docks.store = LayoutStore(f"chisurf.{plugin_id}", path=path)
    docks.load()
    return docks


def attach_native_state(plugin_id: str, app):
    """Bind dock managers and window-size lifecycle to a newly loaded app."""
    if getattr(app, "_native_state_bound", False):
        return app
    app._native_state_bound = True
    app._native_state_id = plugin_id
    layouts = dict(getattr(app, "native_layouts", {}))
    # Native apps conventionally own their GUI object. Inspect only that one
    # level, not scientific models, containers or arbitrary object graphs.
    for name, value in vars(app).items():
        docks = value if isinstance(value, DockManager) else getattr(value, "docks", None)
        if isinstance(docks, DockManager):
            layouts.setdefault(name, docks)
    seen = set()
    for name, docks in layouts.items():
        if id(docks) not in seen:
            bind_layout(f"{plugin_id}.{name}", docks)
            seen.add(id(docks))
    restore = getattr(app, "restore_settings", None)
    if callable(restore):
        restore(load_settings(plugin_id))
    window = load_states(_path(plugin_id, "window"))
    size = window.get("size")
    if isinstance(size, list) and len(size) == 2 and all(
        isinstance(value, (int, float)) and 120 <= value <= 8192 for value in size
    ):
        app.window_size = tuple(int(value) for value in size)
    elif getattr(app, "window_size", None) is None:
        app.window_size = (1200, 800)
    prior_resize = getattr(app, "window_resized", None)
    prior_close = getattr(app, "close", None)
    closed = False

    def resized(width, height):
        app.window_size = (int(width), int(height))
        if callable(prior_resize):
            prior_resize(width, height)

    def close():
        nonlocal closed
        if closed:
            return
        closed = True
        try:
            export = getattr(app, "export_settings", None)
            if callable(export):
                save_settings(plugin_id, export())
        finally:
            try:
                if callable(prior_close):
                    prior_close()
            finally:
                save_states({"size": list(app.window_size)}, _path(plugin_id, "window"))
                for docks in layouts.values():
                    docks.save()

    app.window_resized = resized
    app.close = close
    return app
