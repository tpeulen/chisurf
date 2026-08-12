"""Every display setting, editable in the 3-D view.

The viewport had two panels and neither of them edited the display
configuration: settings could be changed from the command line (``set …``) or
from a Qt table, and the Qt table is exactly the thing the viewport-UI
migration exists to remove. So this is the panel that closes it —
**everything** in ``chimol_display.json`` is a row here, not the subset
somebody wrote a control for.

That is the reason the rows are *derived*. The model is built by walking the
live configuration, so a section added to the JSON tomorrow shows up with no
code written here; a registered :class:`~chimol.settings.SettingSpec` supplies
the PyMOL name and the one-line documentation where one exists, and the rest
come through under their dotted path. What the code does own is the part that
cannot be derived: :data:`RANGES` gives sliders a meaningful track, matched by
key *suffix* so one rule covers the ninety-odd radii rather than one entry
each.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator, Optional

from .. import config
from .. import settings as settings_api
from ..config import _DISPLAY_CONFIG
from .internal_gui import GuiWindow
from .ui.settings_editor import (
    ACTION,
    BOOL,
    CHOICE,
    COLOUR,
    FLOAT,
    INT,
    TEXT,
    Setting,
    SettingsEditor,
    SettingsModel,
)

__all__ = ["RANGES", "CHOICES", "PROMPT_KEY", "build_model", "SettingsWindow"]

#: The one row that is a *preference* rather than a display setting: whether
#: start-up compares this version's defaults with yours. It lives in the user's
#: configuration file under a leading underscore, which is how the walk knows
#: to skip it, so it is added by hand.
PROMPT_KEY = "ask_about_package_defaults"

#: Slider tracks by key suffix, longest match first. A guessed range (zero to
#: twice the current value) is honest but useless for dragging -- the thumb
#: never reaches a value the setting has not already had. These are the ranges
#: the settings actually mean.
RANGES: dict[str, tuple[float, float]] = {
    "alpha": (0.0, 1.0),
    "transparency": (0.0, 1.0),
    "strength": (0.0, 2.0),
    "intensity": (0.0, 2.0),
    "opacity": (0.0, 1.0),
    "radius": (0.0, 5.0),
    "width": (0.0, 10.0),
    "scale": (0.0, 5.0),
    "factor": (0.0, 10.0),
    "tension": (-2.0, 2.0),
    "shininess": (0.0, 128.0),
    "power": (0.0, 16.0),
    "gamma": (0.1, 4.0),
    "fov": (5.0, 120.0),
    "quality": (0.0, 4.0),
    "samples": (1.0, 64.0),
    "iso_value": (0.0, 1.0),
    "ui_scale": (0.5, 2.0),
    "sigma_factor": (0.5, 8.0),
    "spacing": (0.05, 5.0),
    "distance": (0.0, 50.0),
    "size": (0.0, 64.0),
}

#: Settings whose value is one of a short list. Given here rather than inferred
#: because a string field cannot say what it will accept.
CHOICES: dict[str, tuple[str, ...]] = {
    "renderer.backend": ("wgpu", "opengl", "raytracer"),
    "defaults.color_mode": ("chain", "element", "spectrum", "b_factor", "ss"),
}


def _leaves(node: Any, prefix: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Every leaf of a nested mapping, with its path."""
    if isinstance(node, dict):
        for name, value in node.items():
            yield from _leaves(value, prefix + (str(name),))
    else:
        yield prefix, node


def _range_for(path: tuple[str, ...], value: float) -> tuple[float, float]:
    """The track a numeric setting gets, by key suffix."""
    leaf = path[-1]
    for suffix, bounds in sorted(RANGES.items(), key=lambda kv: -len(kv[0])):
        if leaf.endswith(suffix):
            low, high = bounds
            # A value outside its own declared range would sit pinned at an
            # end and could never be dragged back: widen rather than clamp.
            return (min(low, float(value)), max(high, float(value)))
    number = float(value)
    return (0.0 if number >= 0.0 else number * 2.0,
            1.0 if 0.0 <= number <= 1.0 else max(abs(number) * 2.0, 1.0))


def _kind_for(spec_kind: str, value: Any) -> str:
    """Map a chimol setting kind and its value onto an editor kind."""
    if spec_kind == "bool":
        return BOOL
    if spec_kind == "int":
        return INT
    if spec_kind == "float":
        return FLOAT
    if spec_kind in ("color", "color_or_default", "vector"):
        # A colour is a triple *or* a name ("k", "grey70"); only the triple has
        # a swatch to drag.
        if isinstance(value, (list, tuple)) and len(value) in (3, 4):
            return COLOUR
        return TEXT
    return TEXT


def build_model(on_change: Optional[Callable[[str, Any], None]] = None) -> SettingsModel:
    """A model over the whole live display configuration.

    Parameters
    ----------
    on_change : callable, optional
        ``on_change(key, value)`` after a successful write -- where the viewer
        gets told to redraw.

    Returns
    -------
    SettingsModel
        One row per configuration leaf, grouped by section, with registered
        settings carrying their PyMOL name and documentation.
    """
    by_path = {spec.path: spec for spec in settings_api.iter_settings()}
    rows: list[Setting] = []

    for path, value in _leaves(_DISPLAY_CONFIG):
        if path[-1].startswith("_"):
            continue                      # schema bookkeeping, not a setting
        spec = by_path.get(path)
        dotted = ".".join(path)
        # Registered settings are addressed by *name* so their stored/shown
        # transforms run: `transparency` must edit as transparency, not as the
        # alpha it is kept as.
        key = spec.name if spec is not None else dotted
        kind = _kind_for(spec.kind if spec is not None else settings_api._kind_of(value), value)
        options = CHOICES.get(dotted)
        if options:
            kind = CHOICE
            # A value the list does not mention is still the value: dropping it
            # would make the control read as the first option and the next
            # click would silently replace a setting nobody meant to touch.
            options = tuple(dict.fromkeys([*options, str(value)]))
        low = high = None
        if kind in (FLOAT, INT):
            shown = spec.from_config(value) if spec is not None else value
            try:
                low, high = _range_for(path, shown)
            except (TypeError, ValueError):
                kind = TEXT
        rows.append(Setting(
            key=key,
            kind=kind,
            label=spec.name if spec is not None else path[-1].replace("_", " "),
            v_min=low,
            v_max=high,
            options=options,
            fmt="%.3f" if kind == FLOAT else "",
            # No invented documentation for an unregistered key: the footer
            # already prints the path and the value, and "display-config
            # entry" said nothing while pushing the useful half off the line.
            description=(spec.doc if spec is not None else ""),
            group=path[0] if len(path) > 1 else "general",
            source=dotted,
        ))

    # Preferences that are not display config but are edited in the same
    # place. The start-up prompt used to be a tick box in the JSON dialog, and
    # the dialog is gone; a preference with no way to turn it back on is a
    # preference that only turns off.
    rows.append(Setting(
        key=PROMPT_KEY, kind=BOOL, label="ask about package defaults",
        default=True, group="general", source="_ask_about_package_defaults",
        description="Ask at start-up when this version ships display defaults "
                    "different from yours.",
    ))

    def read(key: str) -> Any:
        if key == PROMPT_KEY:
            return config.get_update_prompt_enabled()
        return settings_api.get_setting(key)

    def write(key: str, value: Any) -> None:
        if key == PROMPT_KEY:
            config.set_update_prompt_enabled(bool(value))
        else:
            settings_api.set_setting(key, value)
        if on_change is not None:
            on_change(key, value)

    return SettingsModel(rows, read, write)


class SettingsWindow:
    """The settings editor, wired as a viewport window.

    Parameters
    ----------
    viewer : object, optional
        The viewer to refresh after a change. Anything with ``_update_view``
        will do, which is what makes this testable without a GPU.
    on_change : callable, optional
        Called after a change instead of the viewer refresh, when the host
        wants to do more than redraw.
    """

    #: What the window is called, and the key panels are looked up by.
    KEY = "settings"

    def __init__(self, viewer=None, on_change=None) -> None:
        self.viewer = viewer
        self.on_change = on_change
        self.model = build_model(self._changed)
        self.editor = SettingsEditor(self.model, visible_rows=10)
        self._gui = None

    # ------------------------------------------------------------------ #
    def _changed(self, key: str, value: Any) -> None:
        """Tell whoever is listening that a setting moved."""
        if self.on_change is not None:
            self.on_change(key, value)
            return
        update = getattr(self.viewer, "_update_view", None)
        if callable(update):
            update()

    def refresh(self) -> None:
        """Rebuild the rows, after the configuration was reloaded."""
        self.model = build_model(self._changed)
        self.editor.model = self.model

    def attach(self, gui) -> None:
        """Remember the chrome, so the filter box can take the keyboard."""
        self._gui = gui

    # ------------------------------------------------------------------ #
    def window(self, **kwargs) -> GuiWindow:
        """A :class:`GuiWindow` wired to this panel."""
        options = dict(key=self.KEY, title="Settings", x=24.0, y=90.0,
                       w=420.0, h=300.0)
        options.update(kwargs)
        return GuiWindow(body=self.draw, on_press=self.press,
                         on_drag=self.drag, on_release=self.release, **options)

    # ------------------------------------------------------------------ #
    def draw(self, p, rect) -> None:
        """Paint the editor into the window's body."""
        # Rows follow the panel's height rather than a fixed count: a window
        # dragged twice as tall that still shows ten rows has learned nothing
        # from being resized.
        line = p.line_height()
        self.editor.visible_rows = max(3, int((rect.h - line * 3.0) / (line * 1.5)))
        self.editor.draw(p, rect.x + 4.0, rect.y + 4.0, rect.w - 8.0, rect.h - 8.0)

    def press(self, x: float, y: float, rect) -> bool:
        """Route a press into the editor, and take the keyboard for the filter."""
        was_filter = self.editor._inside(self.editor._filter_box, x, y)
        self.editor.press(x, y)
        if was_filter and self._gui is not None:
            focus = getattr(self._gui, "focus_field", None)
            if callable(focus):
                focus(self.editor.filter.field)
        return True

    def drag(self, x: float, y: float, rect) -> bool:
        """Continue a scrollbar drag."""
        return self.editor.drag(x, y)

    def release(self) -> None:
        """End a drag."""
        self.editor.release()
