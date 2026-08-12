"""Every tunable the game has, in one place, with nothing hard-coded past it.

Why this exists
---------------
The pause menu used to be three parallel lists: one that wrote the row's text,
one that decided which control drew it, and one that acted on a key press --
each keyed by a *row number*. Inserting a setting meant editing three
``elif`` ladders that agreed about ``row == 4`` and nothing else, and the value
itself lived as a plain attribute on the game with its range written into the
branch that stepped it.

So the settings are data. Each one declares its type, its bounds, its choices
and its default here; the menu renders whatever is declared, in order, with the
control the type implies; and stepping a setting is the *model* moving a value
inside its own declared range. Adding a setting is adding one entry.

The declaration is Chimol's (:mod:`chimol.renderer.ui.settings_editor`), which
is also what draws the settings panel inside the 3-D view -- the game and the
molecular viewer describe their settings the same way and are edited by the
same controls. That is the whole reason Lumis Quest depends on Chimol.

Applying a change is separate from storing it: :class:`GameSettings` keeps the
values, and a *hook* per key does whatever the change implies -- rebinding the
controller, telling the mixer, regenerating the wilderness.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

from chisurf.plugins.chimol.chimol.renderer.ui.settings_editor import (
    ACTION,
    BOOL,
    CHOICE,
    FLOAT,
    Setting,
    SettingsModel,
)

__all__ = [
    "ACCENT_TONES",
    "CAMERA_MODES",
    "SCHEME_NAMES",
    "SOUNDTRACKS",
    "SETTINGS",
    "GameSettings",
    "row_text",
]

#: Control schemes, by the name the key bindings are registered under. Kept
#: here rather than read from the binding table so that this module stays
#: Qt-free and importable without the GUI; a test pins the two together.
SCHEME_NAMES: tuple[str, ...] = ("arrows", "wasd", "left-handed")

#: How the camera follows.
CAMERA_MODES: tuple[str, ...] = ("scrolling", "screen by screen")

#: The music the game can play.
SOUNDTRACKS: tuple[str, ...] = (
    "Ninja Adventure (CC0)", "Classic Chiptune", "Synthesiser",
)

#: Accent tones, matching :data:`..gui.imgui_controls.ACCENT_COLORS`.
ACCENT_TONES: tuple[str, ...] = ("Gold", "Cyan", "Emerald", "Ruby", "Violet")


def _setting(key, kind, label, default, **kwargs) -> Setting:
    """One entry, with the group taken from the key's first component."""
    return Setting(key=key, kind=kind, label=label, default=default, **kwargs)


#: Every setting, in the order the menu shows it. The group is the tab.
SETTINGS: tuple[Setting, ...] = (
    # ---------------------------------------------------------------- OPTIONS
    _setting("options.scheme", CHOICE, "controls", "arrows",
             options=SCHEME_NAMES,
             description="Which keys walk, confirm and cancel."),
    _setting("options.camera", CHOICE, "camera", CAMERA_MODES[0],
             options=CAMERA_MODES,
             description="Follow Iris, or hold the screen she is standing in."),
    _setting("options.walk_speed", FLOAT, "walk speed", 190.0,
             v_min=120.0, v_max=260.0, step=20.0, fmt="%.0f",
             description="World units a second, before the sprint multiplier."),
    _setting("options.view_height", FLOAT, "default zoom", 330.0,
             v_min=300.0, v_max=600.0, step=45.0, fmt="%.0f",
             description="How much of the world the view is tall."),
    _setting("options.music_volume", FLOAT, "music volume", 0.1,
             v_min=0.0, v_max=1.0, step=0.1, fmt="%.0%",
             description="The soundtrack, under the dialogue."),
    _setting("options.sfx_volume", FLOAT, "sound volume", 0.5,
             v_min=0.0, v_max=1.0, step=0.1, fmt="%.0%",
             description="Everything that is not music."),
    _setting("options.llm", ACTION, "llm provider", False,
             description="Which model answers the keepers, and whether it is wired."),
    _setting("options.regenerate", ACTION, "regenerate the wilderness", False,
             description="New scenery. The lands and the pages stay where they are."),
    _setting("options.prologue", ACTION, "watch the opening again", False,
             description="Replay the opening cards."),

    # ------------------------------------------------------------- GAMELOGIC
    _setting("gamelogic.soundtrack", CHOICE, "soundtrack", SOUNDTRACKS[0],
             options=SOUNDTRACKS, description="Which music set plays."),
    _setting("gamelogic.enemy_aggro_radius", FLOAT, "enemy aggro", 4.5,
             v_min=2.0, v_max=8.0, step=0.5, fmt="%.1f tiles",
             description="How close Iris gets before a beast comes for her."),
    _setting("gamelogic.action_combat", BOOL, "action combat", True,
             description="Real-time swings in the overworld, rather than only turns."),
    _setting("gamelogic.particles", BOOL, "particle effects", True,
             description="Bursts, sparks and dust."),
    _setting("gamelogic.crt_filter", BOOL, "crt retro shader", False,
             description="Scanlines and a curved tube over the whole picture."),
    _setting("gamelogic.accent_tone", CHOICE, "ui accent tone", ACCENT_TONES[0],
             options=ACCENT_TONES, description="The colour the menus highlight with."),
    _setting("gamelogic.quick_save", ACTION, "quick save run", False,
             description="Write the run to its file now."),
    _setting("gamelogic.quick_load", ACTION, "quick load run", False,
             description="Read the run back from its file."),
    _setting("gamelogic.test_sfx", ACTION, "test audio sfx", False,
             description="Play one sound, at the current volume."),
)


def row_text(setting: Setting, value: Any) -> str:
    """The menu line for one setting.

    Parameters
    ----------
    setting : Setting
        The declaration.
    value : object
        Its current value.

    Returns
    -------
    str
        ``"walk speed: 190"``, ``"action combat: [✓] enabled"``, or just the
        label for an action -- the shapes the menu had before the rows became
        data, kept because they are what the screen reads like.
    """
    if setting.kind == ACTION:
        return setting.label
    if setting.kind == BOOL:
        return f"{setting.label}: {'[✓] enabled' if value else '[ ] disabled'}"
    if setting.kind == FLOAT:
        from chisurf.plugins.chimol.chimol.renderer.ui.widgets import _format

        return f"{setting.label}: {_format(setting.fmt or '%.2f', float(value))}"
    return f"{setting.label}: {value}"


class GameSettings:
    """The values, and what each change implies.

    Parameters
    ----------
    overrides : mapping, optional
        Values to start from, for a run being loaded back.

    Notes
    -----
    Hooks are how a setting *does* something. ``set`` stores first and calls the
    hook second, so a hook that reads the value back sees the new one -- and a
    hook that fails leaves the value stored rather than half-applied, which is
    what keeps the menu honest about what it is showing.
    """

    def __init__(self, overrides: Optional[dict[str, Any]] = None) -> None:
        self.values: dict[str, Any] = {one.key: one.default for one in SETTINGS}
        self.hooks: dict[str, Callable[[Any], None]] = {}
        if overrides:
            self.update(overrides)

    # ------------------------------------------------------------------ #
    def __contains__(self, key: str) -> bool:
        return key in self.values

    def get(self, key: str) -> Any:
        """The current value."""
        return self.values[key]

    def set(self, key: str, value: Any) -> Any:
        """Store a value and run its hook."""
        self.values[key] = value
        hook = self.hooks.get(key)
        if hook is not None:
            hook(value)
        return value

    def on(self, key: str, hook: Callable[[Any], None]) -> None:
        """Register what a change to ``key`` does."""
        self.hooks[key] = hook

    def update(self, values: dict[str, Any]) -> None:
        """Take a saved run's values, ignoring keys that no longer exist."""
        for key, value in values.items():
            if key in self.values:
                self.values[key] = value

    def reset(self) -> None:
        """Put every setting back to its default, running the hooks."""
        for one in SETTINGS:
            self.set(one.key, one.default)

    def as_dict(self) -> dict[str, Any]:
        """The values, for saving. Actions are not state and are left out."""
        actions = {one.key for one in SETTINGS if one.kind == ACTION}
        return {k: v for k, v in self.values.items() if k not in actions}

    # ------------------------------------------------------------------ #
    def rows(self, group: str) -> list[Setting]:
        """The settings of one group, in declaration order."""
        return [one for one in SETTINGS if one.group == group]

    def model(self, settings: Optional[Iterable[Setting]] = None) -> SettingsModel:
        """A :class:`SettingsModel` over these values.

        The same model the settings panel in the 3-D view is built from, which
        is what lets one editor draw both.
        """
        return SettingsModel(SETTINGS if settings is None else settings,
                             self.get, self.set)
