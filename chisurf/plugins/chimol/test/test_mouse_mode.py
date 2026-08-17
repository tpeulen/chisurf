"""The chimol drag style is gone; chimol's mouse is PyMOL's.

This file used to test a second drag style -- ``camera.mouse_mode``, a toolbar
toggle reading *PyMOL* / *Chimol*, and a pair of sign helpers -- under which the
camera followed the cursor instead of the object. It was removed on 2026-08-11
at the user's request, and it was already inert when it went: neither
``rotation_delta_multiplier`` nor ``pan_delta_multiplier`` had a single caller
in the tree, so the toggle wrote a string that nothing read. Its middle-drag
half had been recorded as never having worked (``docs/development/chimol_todo.md``).

What is left here is a guard, because an inert switch is exactly the kind of
thing that grows back: the tests below fail if the setting, the sign helpers or
the viewer accessors reappear. The mouse-mode *matrix* -- PyMOL's own
three-button viewing/editing table in ``ui/input/mouse_modes.py`` -- is a different thing
with the same word in its name and is deliberately untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

from chimol.core.settings import config
from chimol.ui.input import mouse_modes


def test_no_drag_style_setting():
    """`camera.mouse_mode` is not a setting any more.

    Asserted against the *shipped* defaults, not the merged live config: the
    live one carries whatever is in the user's `~/.chisurf/chimol_display.json`,
    which is not this test's business.
    """
    shipped = json.loads(
        (Path(config.__file__).with_name("chimol_display.json")).read_text()
    )
    assert "mouse_mode" not in shipped["camera"]


def test_migration_drops_a_users_stale_drag_style():
    """An existing user config loses the key rather than keeping a dead choice."""
    cfg = {"camera": {"mouse_mode": "chimol", "field_of_view": 20.0}}
    changed = config.apply_display_config_migrations(cfg, from_version=15)
    assert "mouse_mode" not in cfg["camera"]
    assert "camera.mouse_mode (removed)" in changed
    # The rest of the section is untouched.
    assert cfg["camera"]["field_of_view"] == 20.0


def test_no_drag_style_helpers():
    """The sign helpers are gone and must not come back."""
    for name in (
        "normalize_mouse_mode",
        "rotation_delta_multiplier",
        "pan_delta_multiplier",
    ):
        assert not hasattr(mouse_modes, name), (
            f"{name} is back: chimol has one drag style, PyMOL's"
        )


def test_mouse_mode_matrix_survives():
    """The PyMOL mode matrix shares the word and is a different feature."""
    assert mouse_modes.MODE_NAMES
    assert mouse_modes.rows_for("three_button_viewing")
