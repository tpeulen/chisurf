"""Pushing a display-config value to the live viewer.

Most of the display config is read out of :data:`chimol.config._DISPLAY_CONFIG`
during the scene rebuild, so changing it and asking for a rebuild is enough. A
few values are **held** by the renderer instead -- the background is the clear
colour, the field of view is the projection -- and those have to be pushed.

That push used to live inside the ``set`` command, which made it reachable from
exactly one caller. Everything else that changes the same values (``bg_color``,
`reinitialize`, a preset, a restored session) either wrote the renderer
directly and left the config saying something else, or wrote the config and
left the screen unchanged. Both directions were live at once: `bg_color red`
turned the screen red while `get bg_rgb` still answered ``k``, and
`reinitialize` put ``k`` back in the config while the screen stayed red.

So the push is here, and there is one of it. A caller changes the config and
calls :func:`apply_config_path`; nothing writes renderer state that the config
also names.
"""
from __future__ import annotations

from typing import Any

__all__ = ["apply_config_path", "PUSHED_PATHS"]

#: Config paths the renderer *holds* rather than re-reads. Everything else is
#: picked up by the scene rebuild, so this list is deliberately short -- a path
#: here is a value with two homes, which is the thing to avoid.
#:
#: ``camera.orthoscopic`` is deliberately **not** here: nothing in the renderer
#: reads it, so there is no projection to push it into. See the known issues --
#: adding it to this list would make a setting that does nothing look wired up,
#: which is the failure mode this module exists to end.
PUSHED_PATHS: tuple[tuple[str, ...], ...] = (
    ("background",),
    ("camera", "field_of_view"),
    ("selection", "mouse_selection_mode"),
    ("renderer", "max_fps"),
)


def _call(target: Any, name: str, *args) -> bool:
    """Call ``target.name(*args)`` when it exists. Returns whether it ran."""
    method = getattr(target, name, None)
    if not callable(method):
        return False
    try:
        method(*args)
    except Exception:  # noqa: BLE001 - one unhappy setting must not stop a reset
        return False
    return True


def apply_config_path(viewer, path, value, *, rebuild: bool = True) -> None:
    """Push one display-config value at *path* into *viewer*.

    Parameters
    ----------
    viewer : object
        The ``MolView`` (or anything with the same methods). ``None`` is
        accepted and does nothing, so callers need no guard.
    path : tuple of str or str
        The config path, as a tuple or a dotted string.
    value : object
        The value now in the config, in config units.
    rebuild : bool, optional
        Whether to ask for a scene rebuild afterwards. Pass ``False`` when
        applying many paths at once and rebuilding once at the end.
    """
    if viewer is None:
        return
    if isinstance(path, str):
        path = tuple(p for p in path.split(".") if p)
    else:
        path = tuple(str(p) for p in path)

    if path == ("background",):
        _call(viewer, "set_background_color", value)
    elif path == ("camera", "field_of_view"):
        _call(viewer, "set_field_of_view", value)
    elif path == ("selection", "mouse_selection_mode"):
        _call(viewer, "set_selection_level", value)
        # The level is drawn in the viewport's mouse block, which reads it back
        # from the viewer -- so the block has to be re-synced or the row keeps
        # showing the level that was replaced.
        window = getattr(viewer, "window", None) or getattr(viewer, "_window", None)
        _call(window, "sync_internal_gui")
    elif path == ("renderer", "max_fps"):
        _call(viewer, "set_max_fps", value)
    elif path[:1] == ("info_overlay",):
        # Chrome re-reads its palette every frame; all this needs is a repaint.
        _call(viewer, "_request_chrome_redraw")

    if rebuild:
        _call(viewer, "_update_view")
