"""The ``set`` / ``get`` / ``unset`` / ``toggle`` commands.

These resolve names through :mod:`chimol.settings`, which owns the mapping from
PyMOL's flat setting namespace onto chimol's nested display config. The commands
themselves only parse, apply, and push the change to the live viewer.
"""

from __future__ import annotations

from typing import Any

from .. import settings as _settings
from ..settings import SettingSpec, SettingValueError, UnknownSettingError
from .base import BaseCmd
from .registry import command

# Setting paths whose section tells us which part of the viewer has to be
# poked after a change. Anything not listed here is picked up by the generic
# scene rebuild.
_CAMERA_SECTION = "camera"


class SettingsMixin(BaseCmd):
    """PyMOL-compatible access to the display settings."""

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #
    @command("set")
    def set(self, name: str = "", value: str = "") -> None:
        """Set a display setting (PyMOL ``set <name>, <value>``).

        Accepts any registered PyMOL setting name, an unambiguous prefix of one,
        or a dotted path into the display config such as ``metaball.alpha``.
        Boolean settings take ``on``/``off``.
        """
        name = str(name).strip().rstrip(",")
        value = str(value).strip()
        if not name:
            self._emit_error("Usage: set <name>, <value>")
            return

        # Representation toggles are commands in PyMOL (`show cartoon`), but
        # chimol has long accepted `set cartoon, on` and scripts rely on it.
        if self._apply_representation_toggle(name, value):
            return

        if not value:
            self._emit_error("Usage: set <name>, <value>")
            return

        try:
            spec, coerced = _settings.set_setting(name, value)
        except (UnknownSettingError, SettingValueError) as exc:
            self._emit_error(str(exc))
            return

        self._apply_setting(spec, coerced)
        self._emit_message(f"{spec.name} set to {_format(coerced)}")

    @command("get")
    def get(self, name: str = "") -> None:
        """Print the value of a display setting (PyMOL ``get <name>``)."""
        name = str(name).strip().rstrip(",")
        if not name:
            self._emit_error("Usage: get <name>")
            return
        try:
            spec = _settings.resolve(name)
            value = _settings.get_setting(name)
        except UnknownSettingError as exc:
            self._emit_error(str(exc))
            return
        self._emit_message(f"{spec.name} = {_format(value)}")

    @command("unset")
    def unset(self, name: str = "") -> None:
        """Restore a display setting to its default (PyMOL ``unset <name>``)."""
        name = str(name).strip().rstrip(",")
        if not name:
            self._emit_error("Usage: unset <name>")
            return
        try:
            spec, value = _settings.unset_setting(name)
        except UnknownSettingError as exc:
            self._emit_error(str(exc))
            return
        self._apply_setting(spec, value)
        self._emit_message(f"{spec.name} reset to {_format(value)}")

    @command("toggle")
    def toggle(self, name: str = "") -> None:
        """Flip a boolean display setting (PyMOL ``toggle <name>``)."""
        name = str(name).strip().rstrip(",")
        if not name:
            self._emit_error("Usage: toggle <name>")
            return
        try:
            spec, value = _settings.toggle_setting(name)
        except (UnknownSettingError, SettingValueError) as exc:
            self._emit_error(str(exc))
            return
        self._apply_setting(spec, value)
        self._emit_message(f"{spec.name} set to {_format(value)}")

    @command("help_setting")
    def help_setting(self, name: str = "") -> str:
        """Describe a setting, or list every setting when given no name."""
        name = str(name).strip().rstrip(",")
        if not name:
            return "Available settings: " + ", ".join(_settings.setting_names())
        try:
            spec = _settings.resolve(name)
        except UnknownSettingError as exc:
            return str(exc)
        path = ".".join(spec.path)
        return (
            f"{spec.name} ({spec.kind}, default {_format(spec.default)})\n"
            f"  {spec.doc}\n"
            f"  stored at {path}"
        )

    # ------------------------------------------------------------------ #
    # Applying a change to the live viewer
    # ------------------------------------------------------------------ #
    def _apply_setting(self, spec: SettingSpec, value: Any) -> None:
        """Push a changed setting to the attached viewer, if there is one."""
        viewer = getattr(self.window, "viewer", None)
        if viewer is None:
            return

        if spec.path == ("background",):
            _call(viewer, "set_background_color", value)
        elif spec.path[0] == _CAMERA_SECTION:
            if spec.path[-1] == "field_of_view":
                _call(viewer, "set_field_of_view", value)
            elif spec.path[-1] == "mouse_mode":
                _call(viewer, "set_mouse_mode", value)

        # Everything else is read out of the display config during the rebuild.
        _call(viewer, "_update_view")

    def _apply_representation_toggle(self, name: str, value: str) -> bool:
        """Handle the legacy ``set <representation>, on|off`` spelling.

        Returns ``True`` when ``name`` was a representation and the toggle was
        applied (or rejected), so the caller stops.
        """
        key = name.lower()
        if key in ("bg_color", "bg_colour"):
            self.bg_color(value)
            return True
        if key in ("color_mode",):
            self.color(value)
            return True
        if key not in (
            "cartoon", "trace", "ca_trace", "atoms",
            "sticks", "surface", "dots", "plane", "grid",
        ):
            return False

        try:
            visible = _settings.coerce(value, "bool")
        except SettingValueError:
            self._emit_error(f"Value for set {key} must be one of: on, off, true, false, 1, 0")
            return True
        (self.show if visible else self.hide)(key)
        return True


def _call(target: object, method: str, *args: Any) -> None:
    """Best-effort call of an optional viewer method."""
    fn = getattr(target, method, None)
    if not callable(fn):
        return
    try:
        fn(*args)
    except Exception:
        pass


def _format(value: Any) -> str:
    """Render a setting value the way PyMOL echoes it."""
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_format(v) for v in value) + "]"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


__all__ = ["SettingsMixin"]
