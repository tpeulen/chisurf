"""Every cell of the mouse-mode block does what the block says it does.

The report
----------
"Shift + middle mouse move, i.e. moving of objects, does not work. Check all
mouse commands and combinations with keys again."

It did not, and neither did most of the table. The press resolved the action
from the mode table and then **threw it away**: it recorded only where the
pointer was, and the move handler guessed from the button --- pan if it had
been told to pan, dolly for the right button, and **orbit for everything
else**. So every cell that was not `move` rotated the camera whatever the panel
promised: `movo` (move object) rotated the view, and so did `roto`, `mova`,
`torf`, `pkat` and `orig`.

Right-drag was worse: the right *press* opened the object context menu and
grabbed the pointer, so `MovZ` --- which the same row of the block promises ---
never ran at all. The menu belongs on the release, where a click can be told
from a drag.

What this pins
--------------
Each cell is driven for real --- press, five moves, release --- and the scene
is measured before and after. The assertion is on the **kind** of change, since
that is what the block's label promises:

* a camera cell moves the camera and **not** the object;
* an object cell moves the object and **not** the camera. That distinction is
  the whole bug: rotating the view looks like something happened, which is why
  this went unnoticed;
* a pick or click cell does **nothing on a drag**. Doing nothing is right ---
  silently orbiting instead is what made them look implemented.
"""
from __future__ import annotations

import pytest

from toolkit_free import probe

#: ``(mode, button, modifiers, action, expectation)``. The expectation names
#: what must change, and the table is the one the panel draws -- if a binding
#: moves in `ui/input/mouse_modes.py`, this fails and one of the two is wrong.
CELLS = [
    ("three_button_viewing", "l", "", "rota", "camera"),
    ("three_button_viewing", "l", "ctrl", "move", "camera"),
    ("three_button_viewing", "m", "", "move", "camera"),
    ("three_button_viewing", "r", "", "movz", "camera"),
    ("three_button_viewing", "r", "shft", "clip", "slab"),
    ("three_button_viewing", "l", "shft", "+box", "selection"),
    ("three_button_viewing", "l", "ctsh", "sele", "selection"),
    ("three_button_viewing", "m", "ctrl", "pkat", "nothing"),
    ("three_button_viewing", "m", "ctsh", "orig", "nothing"),
    ("three_button_editing", "l", "", "rota", "camera"),
    ("three_button_editing", "l", "shft", "roto", "object"),
    ("three_button_editing", "l", "ctsh", "mova", "object"),
    ("three_button_editing", "m", "", "move", "camera"),
    ("three_button_editing", "m", "shft", "movo", "object"),
    ("three_button_editing", "r", "", "movz", "camera"),
    ("three_button_editing", "r", "shft", "mvoz", "object"),
    ("three_button_editing", "m", "ctrl", "+/-", "nothing"),
]


@pytest.fixture(scope="module")
def measured():
    """Drive every cell in its own viewer and report what moved."""
    cells = [(m, b, k) for m, b, k, _a, _e in CELLS]
    return probe(f'''
        from emtk.events import (
            LEFT_BUTTON, MIDDLE_BUTTON, RIGHT_BUTTON,
            NO_MODIFIER, CONTROL_MODIFIER, SHIFT_MODIFIER,
        )

        BUTTONS = {{"l": LEFT_BUTTON, "m": MIDDLE_BUTTON, "r": RIGHT_BUTTON}}
        MODS = {{
            "": NO_MODIFIER,
            "shft": SHIFT_MODIFIER,
            "ctrl": CONTROL_MODIFIER,
            "ctsh": CONTROL_MODIFIER | SHIFT_MODIFIER,
        }}

        def state(app):
            r, v = app.renderer, app.viewer
            entry = v.objects.get(next(iter(v.objects), None))
            coords = None
            if entry is not None and getattr(entry.state, "coords", None) is not None:
                coords = np.asarray(entry.state.coords, dtype=float).mean(axis=0)
            return {{
                "camera": (
                    tuple(np.asarray(r._rotation, dtype=float).ravel().round(6)),
                    round(float(r._distance), 6),
                    tuple(np.asarray(r._target, dtype=float).ravel().round(6)),
                ),
                "object": None if coords is None else tuple(coords.round(6)),
                "slab": float(getattr(r, "_slab_moved", 0.0) or 0.0),
                "selection": len(getattr(entry.state, "selected_residues", ()) or ())
                if entry is not None else 0,
            }}

        for mode, bname, mname in {cells!r}:
            app = open_app(size=(900, 650))
            app.cmd.do("fetch 148L")
            # The info panel is shown unpinned after a load, and the first
            # press anywhere is eaten putting it away -- which would measure
            # the dismissal instead of the binding.
            app.cmd.do("info_panel off")
            app.renderer._internal_gui.mouse_mode = mode
            app.cmd.do("orient")
            app.cmd.do("zoom all")
            app.renderer.draw_frame()

            button, mods = BUTTONS[bname], MODS[mname]
            before = state(app)
            app.renderer.on_pointer_press(450.0, 330.0, button, mods)
            for step in range(1, 6):
                app.renderer.on_pointer_move(
                    450.0 + step * 14, 330.0 + step * 9, button, mods
                )
            app.renderer.on_pointer_release(520.0, 375.0, button, mods)
            app.renderer.draw_frame()
            after = state(app)

            moved = [k for k in before if before[k] != after[k]]
            emit(f"{{mode}}:{{bname}}:{{mname}}", ",".join(moved) or "nothing")
    ''')


@pytest.mark.parametrize(
    "mode, button, mods, action, expectation",
    CELLS,
    ids=[f"{m.split('_')[-1]}-{b}{'+' + k if k else ''}-{a}" for m, b, k, a, _e in CELLS],
)
def test_a_cell_does_what_the_block_says(measured, mode, button, mods, action, expectation):
    """The label on the block is a promise; this is the promise being kept."""
    moved = measured[f"{mode}:{button}:{mods}"].split(",")
    moved = [m for m in moved if m and m != "nothing"]

    if expectation == "nothing":
        assert not moved, (
            f"{action} is a pick, not a drag, and dragging it changed {moved} -- "
            "silently orbiting is what made these look implemented"
        )
        return

    assert expectation in moved, (
        f"{action} promises to move the {expectation} and moved {moved or 'nothing'}"
    )
    if expectation == "object":
        assert "camera" not in moved, (
            f"{action} moved the camera as well as the object; the press's "
            "action is being ignored again"
        )
    if expectation == "camera":
        assert "object" not in moved, f"{action} moved the object"


#: ``(mode, button, modifiers, action)`` for the cells that act on a *click*.
#: The drag table above pins that these do nothing when dragged; this pins that
#: they are not simply dead.
CLICK_CELLS = [
    ("three_button_viewing", "m", "ctrl", "pkat"),
    ("three_button_viewing", "m", "ctsh", "orig"),
    ("three_button_viewing", "l", "ctsh", "sele"),
    ("three_button_editing", "m", "ctrl", "+/-"),
    ("three_button_viewing", "r", "ctrl", "pk1"),
]


@pytest.fixture(scope="module")
def clicked():
    """Click each pick cell and report whether the viewer was asked to act."""
    cells = [(m, b, k) for m, b, k, _a in CLICK_CELLS]
    return probe(f'''
        from emtk.events import (
            LEFT_BUTTON, MIDDLE_BUTTON, RIGHT_BUTTON,
            NO_MODIFIER, CONTROL_MODIFIER, SHIFT_MODIFIER,
        )

        BUTTONS = {{"l": LEFT_BUTTON, "m": MIDDLE_BUTTON, "r": RIGHT_BUTTON}}
        MODS = {{
            "": NO_MODIFIER,
            "shft": SHIFT_MODIFIER,
            "ctrl": CONTROL_MODIFIER,
            "ctsh": CONTROL_MODIFIER | SHIFT_MODIFIER,
        }}

        for mode, bname, mname in {cells!r}:
            app = open_app(size=(900, 650))
            app.cmd.do("fetch 148L")
            app.cmd.do("info_panel off")
            app.renderer._internal_gui.mouse_mode = mode
            app.cmd.do("orient")
            app.cmd.do("zoom all")
            app.renderer.draw_frame()

            # What the click reaches, recorded at the viewer's own door.
            seen = []
            viewer = app.renderer._controller
            inner = viewer.handle_mouse_click
            viewer.handle_mouse_click = (
                lambda ev, action=None, _i=inner, _s=seen: (
                    _s.append(str(action)), _i(ev, action)
                )[1]
            )

            button, mods = BUTTONS[bname], MODS[mname]
            app.renderer.on_pointer_press(450.0, 330.0, button, mods)
            app.renderer.on_pointer_release(450.0, 330.0, button, mods)
            emit(f"{{mode}}:{{bname}}:{{mname}}", ",".join(seen) or "nothing")
            emit(
                f"{{mode}}:{{bname}}:{{mname}}:menu",
                "yes" if app.renderer._internal_gui.has_menu() else "no",
            )
    ''')


@pytest.mark.parametrize(
    "mode, button, mods, action",
    CLICK_CELLS,
    ids=[f"{m.split('_')[-1]}-{b}{'+' + k if k else ''}-{a}" for m, b, k, a in CLICK_CELLS],
)
def test_a_pick_cell_fires_on_a_click(clicked, mode, button, mods, action):
    """These do nothing on a drag by design; doing nothing at all is the bug."""
    key = f"{mode}:{button}:{mods}"
    assert clicked[key] == action, (
        f"clicking {action} reached the viewer as {clicked[key]!r}"
    )
    assert clicked[key + ":menu"] == "no", (
        f"{action} ended in the context menu; the menu is pending on every "
        "right press again, which swallows the cells that name a click"
    )


def test_bond_editing_cells_say_they_are_not_implemented():
    """`PkTB` and `TorF` need bond editing, which chimol has not.

    They are on the block, so they cannot be silent: an unimplemented cell
    indistinguishable from a broken one costs the same afternoon twice.
    """
    measured = probe('''
        from emtk.events import (
            LEFT_BUTTON, RIGHT_BUTTON, CONTROL_MODIFIER,
        )

        for label, button in (("torf", LEFT_BUTTON), ("pktb", RIGHT_BUTTON)):
            app = open_app(size=(900, 650))
            app.cmd.do("fetch 148L")
            app.cmd.do("info_panel off")
            app.renderer._internal_gui.mouse_mode = "three_button_editing"
            app.renderer.draw_frame()
            app.renderer._internal_gui.status_text = ""

            app.renderer.on_pointer_press(450.0, 330.0, button, CONTROL_MODIFIER)
            for step in range(1, 4):
                app.renderer.on_pointer_move(
                    450.0 + step * 12, 330.0, button, CONTROL_MODIFIER
                )
            app.renderer.on_pointer_release(486.0, 330.0, button, CONTROL_MODIFIER)
            emit(label, app.renderer._internal_gui.status_text)
    ''')

    for action in ("torf", "pktb"):
        assert "bond editing" in measured[action].lower(), (
            f"{action} was silent: {measured[action]!r}"
        )


def test_a_right_click_still_opens_the_menu():
    """The menu moved to the release; a right *click* must still open it.

    Both cells of that row are promised -- `SnglClk R Menu` and `R MovZ` -- and
    opening the menu on the press delivered one and silently ate the other.
    """
    measured = probe('''
        from emtk.events import (
            RIGHT_BUTTON, NO_MODIFIER,
        )

        app = open_app(size=(900, 650))
        app.cmd.do("fetch 148L")
        app.cmd.do("info_panel off")
        app.renderer.draw_frame()
        gui = app.renderer._internal_gui

        # A click: press and release at the same point.
        app.renderer.on_pointer_press(450.0, 330.0, RIGHT_BUTTON, NO_MODIFIER)
        app.renderer.on_pointer_release(450.0, 330.0, RIGHT_BUTTON, NO_MODIFIER)
        emit("menu_after_click", "yes" if gui.has_menu() else "no")

        # Put the menu away for the second half. `close_menus`, not a click
        # somewhere else: an open menu holds the pointer grab, so a stray press
        # would be spent closing it and the drag below would never start.
        gui.close_menus()
        app.renderer._gui_grab = False
        distance = float(app.renderer._distance)

        # A drag: the same button, moved. No menu, and the camera dollies.
        app.renderer.on_pointer_press(450.0, 330.0, RIGHT_BUTTON, NO_MODIFIER)
        for step in range(1, 6):
            app.renderer.on_pointer_move(450.0, 330.0 + step * 12, RIGHT_BUTTON, NO_MODIFIER)
        app.renderer.on_pointer_release(450.0, 390.0, RIGHT_BUTTON, NO_MODIFIER)
        emit("menu_after_drag", "yes" if gui.has_menu() else "no")
        emit("dollied", "yes" if abs(float(app.renderer._distance) - distance) > 1e-6 else "no")
    ''')

    assert measured["menu_after_click"] == "yes", "a right click no longer opens the menu"
    assert measured["menu_after_drag"] == "no", (
        "a right *drag* ended in a menu; it was a motion, not a click"
    )
    assert measured["dollied"] == "yes", "right-drag did not move the camera in z"
