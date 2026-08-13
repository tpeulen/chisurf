"""The field of view answers to its own name, and the bar is seven menus.

fov
---
The lens worked; its **name** did not. ``set field_of_view, 60`` was the only
spelling that did anything: ``fov 60`` answered "not implemented" and
``set fov, 60`` answered "unknown setting". Between them those read as a missing
feature rather than a missing alias, which is what was reported.

Two reasons it could not be found. :func:`~chimol.settings.resolve` accepts any
unambiguous **prefix**, and ``fov`` is not a prefix of ``field_of_view`` -- it
is a different word, the one the other two viewers use. And there was no ``fov``
command, so the spelling a user reaches for first hit the command layer before
it ever reached a setting.

Both are pinned here, along with the property underneath: changing the angle has
to change the **picture**. A setting that stores a number nothing reads is the
same failure one layer down, and would pass every test above.

The bar
-------
Build and Wizard were top-level menus of two and four entries. A bar of ten
costs every menu on it -- the wider it is, the further any one of them is from
"what can this do" -- so both are submenus of Tools, which is where a tool
belongs. Preset went under Display for a plainer reason: a preset *is* a
display choice, so on the bar it was a second place to look for what Display
already answers. The tours moved from Demo to Help: a demo runs itself and
shows a finished result, and a tour points at real controls and waits for you
to press them, which is what someone opens the command list for.

Nothing was dropped in either move, and that is what the tests check. A menu is
a way to *find* a command, never the only way to reach one.
"""
from __future__ import annotations

import pytest

from toolkit_free import probe


@pytest.fixture(scope="module")
def measured():
    """Every spelling of the field of view, driven through the command layer."""
    return probe('''
        app = open_app(size=(420, 340))
        errors = []
        app.cmd.set_error_callback(errors.append)
        messages = []
        app.cmd.set_message_callback(messages.append)

        app.cmd.do("fetch 148L")
        app.cmd.do("hide everything")
        app.cmd.do("show spheres")
        app.cmd.do("orient")
        app.cmd.do("zoom all")

        def run(label, command):
            errors.clear()
            messages.clear()
            app.cmd.do(command)
            emit(label, "; ".join(errors) or "ok")
            emit(label + ":said", messages[-1] if messages else "")
            emit(label + ":fov", f"{float(app.renderer._fov):g}")

        run("command", "fov 60")
        run("setting", "set fov, 35")
        run("full", "set field_of_view, 22")
        run("read", "fov")
        run("too_wide", "fov 500")
        run("not_a_number", "fov abc")

        # The picture, which is the only thing that makes any of it a feature.
        def shot():
            app.renderer.draw_frame()
            image = np.asarray(app.renderer.grab_image(chrome=False))
            return image[..., :3].astype(float)

        app.cmd.do("fov 15")
        narrow = shot()
        app.cmd.do("fov 90")
        wide = shot()
        emit("picture_changed", f"{float(np.abs(wide - narrow).mean()):.3f}")
    ''')


@pytest.mark.parametrize(
    "label, spelling",
    [
        ("command", "fov 60"),
        ("setting", "set fov, 35"),
        ("full", "set field_of_view, 22"),
        ("read", "fov"),
    ],
)
def test_every_spelling_of_the_field_of_view_works(measured, label, spelling):
    """All four, because a user reaches for whichever one they know."""
    assert measured[label] == "ok", f"{spelling}: {measured[label]}"


def test_the_command_actually_sets_it(measured):
    """Not merely accepted -- applied."""
    assert float(measured["command:fov"]) == pytest.approx(60.0)
    assert float(measured["setting:fov"]) == pytest.approx(35.0)
    assert float(measured["full:fov"]) == pytest.approx(22.0)


def test_reading_it_reports_the_value(measured):
    """`fov` with no argument answers rather than silently doing nothing."""
    assert "field_of_view" in measured["read:said"]


def test_a_lens_that_shows_nothing_is_refused(measured):
    """500 degrees and 'abc' are mistakes, not settings."""
    assert measured["too_wide"] != "ok"
    assert measured["not_a_number"] != "ok"


def test_changing_the_angle_changes_the_picture(measured):
    """The property underneath: a stored number nothing reads is not a lens."""
    assert float(measured["picture_changed"]) > 1.0, (
        "15 and 90 degrees rendered the same image; the projection is not "
        "reading the field of view"
    )


# ------------------------------------------------------------------- menus


def test_the_bar_is_seven_menus():
    """Build and Wizard folded into Tools, Preset nested under Display.

    Every one of the three is still complete and one level down, which is what
    `FOLDED_MENUS` and `NESTED_MENUS` declare and what the tests below check.
    """
    from chisurf.plugins.chimol.chimol.app.menu_bar import MENU_BAR

    titles = [title for title, _entries in MENU_BAR]
    for gone in ("Build", "Wizard", "Preset"):
        assert gone not in titles, f"{gone} is back on the bar"
    assert titles == [
        "File", "Edit", "Display", "Setting", "Demo", "Tools", "Help"
    ], titles


def test_the_presets_are_the_first_thing_under_display():
    """A preset is a display choice, so Display is where it is looked for."""
    from chisurf.plugins.chimol.chimol.app.menu_bar import DISPLAY_MENU
    from chisurf.plugins.chimol.chimol.cmd.presets import load_reference_presets

    first = DISPLAY_MENU[0]
    assert str(getattr(first, "label", "")) == "Preset"
    children = {
        str(getattr(child, "command", "") or "")
        for child in (getattr(first, "children", None) or ())
    }
    for key in load_reference_presets():
        assert f"preset_cx {key}" in children, f"{key} is not under Display"


def test_nothing_was_lost_in_the_fold():
    """Every command that was on Build or Wizard is still reachable from Tools.

    The check that makes the move safe: a menu is a way to find a command, and
    folding one into another must not quietly drop half of it.
    """
    from chisurf.plugins.chimol.chimol.app.menu_bar import (
        BUILD_MENU,
        TOOLS_MENU,
        WIZARD_MENU,
    )

    def commands(entries):
        found = set()
        for entry in entries or ():
            command = getattr(entry, "command", None)
            if command:
                found.add(str(command))
            found |= commands(getattr(entry, "children", None))
        return found

    tools = commands(TOOLS_MENU)
    for name, menu in (("Build", BUILD_MENU), ("Wizard", WIZARD_MENU)):
        missing = commands(menu) - tools
        assert not missing, f"{name} lost {sorted(missing)} in the fold"


def test_the_tours_are_under_help_and_not_under_demo():
    """A tour is help, not a demonstration."""
    from chisurf.plugins.chimol.chimol.app.menu_bar import DEMO_MENU, HELP_MENU
    from chisurf.plugins.chimol.chimol.tour import available_tours

    def commands(entries):
        found = set()
        for entry in entries or ():
            command = getattr(entry, "command", None)
            if command:
                found.add(str(command))
            found |= commands(getattr(entry, "children", None))
        return found

    help_commands = commands(HELP_MENU)
    demo_commands = commands(DEMO_MENU)
    for key, _title in available_tours():
        assert f"tour {key}" in help_commands, f"{key} is not under Help"
        assert f"tour {key}" not in demo_commands, f"{key} is still under Demo"
