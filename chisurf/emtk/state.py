"""Qt-free native preferences and dock-layout persistence.

Factories stay deterministic. The native launcher binds persistence after
construction; callers can disable it when loading isolated test controls.
"""

from __future__ import annotations

import math
from pathlib import Path
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


def _window_position(pos, screen=None):
    """Validate saved coordinates, using the host's primary screen when known."""
    if not (
        isinstance(pos, (list, tuple))
        and len(pos) == 2
        and all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            for value in pos
        )
    ):
        return None
    x, y = (int(value) for value in pos)
    if screen is not None:
        left, top, width, height = screen
        if not (left <= x < left + width and top <= y < top + height):
            return None
    return x, y


#: Data a tool works on (measurements, burst containers, decays, images, structures): what a
#: reopened tool must not come back with. Settings files (yaml, json, css, db) are not data.
DATA_SUFFIXES = (
    ".ptu", ".pto", ".spc", ".set", ".ht3", ".ht2", ".pt3", ".pt2", ".t3r", ".t2r", ".phu", ".sptw",
    ".sm", ".hdf", ".h5", ".hdf5", ".bur", ".bv4", ".br4", ".bg4", ".by4", ".dat", ".csv", ".txt",
    ".cor", ".fcs", ".npy", ".npz", ".tif", ".tiff", ".pdb", ".cif", ".mmcif", ".xyz", ".mrc",
    ".bin", ".asc", ".sdt", ".lsm", ".czi",
)


def is_data_reference(value) -> bool:
    """Whether *value* names a data file: a path (or ``kind:path`` address, ``mmfdb://`` link)
    ending in a data format."""
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str):
        return False
    text = value.strip()
    if text.startswith("mmfdb://"):
        return True
    if "/" not in text and "\\" not in text:
        return False  # ".pto" as an output-format choice is a setting, not a file
    return text.rstrip("/\\").lower().endswith(DATA_SUFFIXES)


def strip_data_files(state):
    """*state* without its data files: settings stay, every reference to a measurement goes.

    A data path as a value is dropped (its key removed), from a list it is filtered out, and a list
    entry that is a record naming one (``{"path": ".../x.ptu", ...}``) goes with it.
    """
    if isinstance(state, dict):
        out = {}
        for key, value in state.items():
            if is_data_reference(value):
                continue
            out[key] = strip_data_files(value)
        return out
    if isinstance(state, list):
        kept = []
        for item in state:
            if is_data_reference(item):
                continue
            if isinstance(item, dict) and any(is_data_reference(v) for v in item.values()):
                continue
            kept.append(strip_data_files(item))
        return kept
    return state


def attach_native_state(plugin_id: str, app, *, restore_files: bool = True):
    """Bind preferences, dock layouts and window geometry to a newly loaded app.

    With *restore_files* ``False`` (a tool opened inside the ChiSurf window) its settings come back
    but not its data: closed and opened again, a tool has no files, runs or results of the last
    opening (:func:`strip_data_files`).
    """
    if getattr(app, "_native_state_bound", False):
        return app
    app._native_state_bound = True
    app._native_state_id = plugin_id
    window = load_states(_path(plugin_id, "window"))
    saved_docks = window.get("docks", {})
    layouts = dict(getattr(app, "native_layouts", {}))
    # Native apps conventionally own their GUI object. Inspect only that one
    # level, not scientific models, containers or arbitrary object graphs.
    if not hasattr(app, "native_layouts"):
        for name, value in vars(app).items():
            docks = value if isinstance(value, DockManager) else getattr(value, "docks", None)
            if isinstance(docks, DockManager):
                layouts.setdefault(name, docks)
    seen = set()
    for name, docks in layouts.items():
        if id(docks) not in seen:
            bind_layout(f"{plugin_id}.{name}", docks)
            state = saved_docks.get(name) if isinstance(saved_docks, dict) else None
            if isinstance(state, dict):
                docks.restore(state)
            seen.add(id(docks))
    restore = getattr(app, "restore_settings", None)
    if callable(restore):
        settings = load_settings(plugin_id)
        if settings and not restore_files:
            settings = strip_data_files(settings)
        if settings:
            restore(settings)
    size = window.get("size")
    if (
        isinstance(size, list)
        and len(size) == 2
        and all(isinstance(value, (int, float)) and 120 <= value <= 8192 for value in size)
    ):
        app.window_size = tuple(int(value) for value in size)
    elif getattr(app, "window_size", None) is None:
        app.window_size = (1200, 800)
    app.window_pos = _window_position(window.get("pos"), getattr(app, "window_screen", None))
    prior_resize = getattr(app, "window_resized", None)
    prior_move = getattr(app, "window_moved", None)
    prior_screen = getattr(app, "window_screen_changed", None)
    prior_close = getattr(app, "close", None)
    closed = False

    def resized(width, height):
        """Remember a host resize and preserve the app's existing callback."""
        app.window_size = (int(width), int(height))
        if callable(prior_resize):
            prior_resize(width, height)

    def moved(x, y):
        """Remember logical window coordinates as the user moves the host."""
        app.window_pos = _window_position((x, y))
        if callable(prior_move):
            prior_move(x, y)

    def screen_changed(screen):
        """Reject a saved position outside the primary screen supplied by a host."""
        app.window_screen = tuple(screen)
        app.window_pos = _window_position(app.window_pos, screen)
        if callable(prior_screen):
            prior_screen(screen)

    def close():
        """Save one coherent geometry/layout snapshot and close the app once."""
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
                pos = _window_position(app.window_pos, getattr(app, "window_screen", None))
                save_states(
                    {
                        "size": list(app.window_size),
                        "pos": list(pos) if pos is not None else None,
                        "docks": {name: docks.state() for name, docks in layouts.items()},
                    },
                    _path(plugin_id, "window"),
                )
                for docks in layouts.values():
                    docks.save()

    app.window_resized = resized
    app.window_moved = moved
    app.window_screen_changed = screen_changed
    app.close = close
    return app
