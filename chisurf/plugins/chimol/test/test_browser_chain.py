"""The density panel through the chain the **browser** drives -- no Qt.

Why a subprocess and no Qt
--------------------------
The alpha-slider drag was "verified" through the Qt window while the user
hit it in the browser, and the two are not the same host: Qt translates
events in ``wgpu_view``, the page in ``boot.js`` → ``web.page.Page`` →
``button_from_dom`` → ``canvas_base.on_pointer_*``. The shared part -- the
part that must be right -- is ``on_pointer_press/move/release`` and
everything behind them, and *that* is what this file drives, in a process
where importing Qt is impossible (``CHIMOL_TOOLKIT=none``).

What runs where: the browser's own 20-line shim (DOM numbers → engine
buttons, ``dblclick`` → ``double=True``) is covered by the
``button_from_dom`` assertions; everything past it is covered by the
subprocess drives below. If the slider works here it works on the page.

The gestures
------------
* **alpha slider**: press consumes and arms the body drag; the slide is
  *free* (the model's alpha is untouched mid-drag); the release applies
  once. This is the exact gesture that failed.
* **level picker**: a single press on empty plot adds nothing; a double
  press adds one level; a double on a marker grabs it.
* **per-row controls**: the eye toggles only its row's object; the
  per-row alpha touches only its own density.
"""

from __future__ import annotations

import pytest

pytest.importorskip("rendercanvas", reason="the offscreen canvas host")

from toolkit_free import probe  # noqa: E402


def test_dom_button_translation_names_the_engine_buttons():
    """The browser's DOM numbers reach the engine as the right buttons.

    The left button is what a drag carries; if the translation moved it,
    every slider and marker in the panel would take a press and ignore the
    moves -- exactly the reported failure, one layer out.
    """
    from emtk.events import (
        LEFT_BUTTON,
        MIDDLE_BUTTON,
        RIGHT_BUTTON,
        button_from_dom,
    )

    assert button_from_dom(0) == LEFT_BUTTON
    assert button_from_dom(1) == MIDDLE_BUTTON
    assert button_from_dom(2) == RIGHT_BUTTON


_DRIVE = '''
    app = open_app(size=(1000, 800))
    errors = []
    app.cmd.set_message_callback(lambda _m: None)
    app.cmd.set_error_callback(errors.append)

    app.cmd.do("load 148l.pdb")
    app.cmd.do("add_dye resi 119 and name CB, Cy5")
    app.cmd.do("add_dye resi 44 and name CB, ATTO550")
    app.cmd.do("density_panel on")

    viewer = app.viewer
    renderer = app.renderer
    gui = renderer._internal_gui
    panel = viewer.gui.panels.get("density")
    emit("panel", "yes" if panel is not None else "no")
    if panel is None:
        raise SystemExit(1)

    # Lay the panel out through the real frame path, as a page does.
    renderer._chrome_quads()

    rows = panel._row_boxes
    emit("rows", str(len(rows)))
    oid1, oid2 = rows[0][1], rows[1][1]
    other_alpha = panel.model.alpha_for(oid1)

    box, slider = panel._row_alpha[oid2]
    x0 = box.x + box.w * 0.3
    y0 = box.y + box.h / 2

    # --- the alpha drag, exactly as the browser delivers it -------------
    from emtk.events import LEFT_BUTTON

    consumed = renderer.on_pointer_press(x0, y0, LEFT_BUTTON, 0, double=False)
    emit("press", f"{consumed}|{renderer._gui_grab}|{slider._held}|{gui._window_body_drag}")
    # A frame between the press and the first move, as every host that
    # draws per event delivers it (the page, the Qt window). The panel
    # rebuilt its sliders on each draw and the held one forgot it was held
    # -- the slider took the press and ignored the drag; only a double
    # click ever moved it. A probe that never drew mid-gesture passed.
    renderer._chrome_quads()
    emit("held_after_frame", str(slider._held))
    for index, fraction in enumerate((0.35, 0.4, 0.45, 0.5)):
        renderer.on_pointer_move(box.x + box.w * fraction, y0, LEFT_BUTTON, 0)
        renderer._chrome_quads()
        emit(f"freemid{index}", f"{panel.model.alpha_for(oid2):.3f}")
    renderer.on_pointer_release(x0, y0, LEFT_BUTTON, 0)
    emit("applied", f"{panel.model.alpha_for(oid2):.3f}")
    emit("other", f"{panel.model.alpha_for(oid1):.3f}")

    # --- the level picker: single inert, double adds --------------------
    hist = next(h for h, o in panel._plot_boxes if o == oid2)
    before = len(panel.model.levels_for(oid2))
    renderer.on_pointer_press(hist.x + 0.35 * hist.w, hist.y + hist.h / 2,
                              LEFT_BUTTON, 0, double=False)
    renderer.on_pointer_release(hist.x + 0.35 * hist.w, hist.y + hist.h / 2,
                                LEFT_BUTTON, 0)
    emit("single", str(len(panel.model.levels_for(oid2)) - before))
    renderer.on_pointer_press(hist.x + 0.35 * hist.w, hist.y + hist.h / 2,
                              LEFT_BUTTON, 0, double=True)
    renderer.on_pointer_release(hist.x + 0.35 * hist.w, hist.y + hist.h / 2,
                                LEFT_BUTTON, 0)
    emit("double", str(len(panel.model.levels_for(oid2)) - before))

    # --- the per-row eye -------------------------------------------------
    eye = next(b for b, o in panel._row_eyes if o == oid2)
    was = viewer.objects[oid2].visible
    renderer.on_pointer_press(eye.x + 2, eye.y + 2, LEFT_BUTTON, 0, double=False)
    emit("eye", str(viewer.objects[oid2].visible != was))

    emit("errors", "; ".join(errors[:2]) or "none")
'''


def test_the_alpha_slider_drag_works_on_the_browser_chain():
    """The gesture that failed, through the chain the page drives."""
    m = probe(_DRIVE)
    assert m["panel"] == "yes"
    assert m["rows"] == "2", "the two dyes did not stack"
    press = m["press"].split("|")
    assert press[0] == "True", "the press was not consumed"
    assert press[1] == "True", "the gui grab was not taken"
    assert press[2] == "True", "the slider did not receive the press"
    assert press[3] == "density", "no body drag was armed"
    assert m["held_after_frame"] == "True", "a drawn frame dropped the slider's grab"
    # Free slide: mid-drag the alpha never moved.
    mids = [m[f"freemid{i}"] for i in range(4)]
    assert all(v == mids[0] for v in mids), "a drag tick wrote the alpha"
    assert abs(float(m["applied"]) - 0.5) < 0.02, "the release did not apply"
    assert abs(float(m["other"]) - 0.35) < 0.02, "the drag leaked to another row"
    assert m["errors"] == "none", m["errors"]


def test_the_level_picker_on_the_browser_chain():
    """Single press adds nothing; the double adds one level."""
    m = probe(_DRIVE)
    assert m["single"] == "0", "a single click added a level"
    assert m["double"] == "1", "the double press did not add exactly one"
    assert m["eye"] == "True", "the per-row eye did not toggle its object"
    assert m["errors"] == "none", m["errors"]



#: The DOM's delivery order for a double click -- ``press, release, press,
#: release, dblclick`` where the ``dblclick`` is one more press with **no
#: release after it** -- on the object list, and then a plain click on the
#: scene. This is BUGS/001 + BUGS/002: the unpaired press left ``_gui_grab``
#: held, and ``on_pointer_release`` returned on the held grab before the
#: click could reach ``_handle_click`` -- the first click after any double
#: click on the panel picked nothing.
_UNPAIRED_DOUBLE_THEN_CLICK = '''
    app = open_app(size=(1000, 800))
    errors = []
    app.cmd.set_message_callback(lambda _m: None)
    app.cmd.set_error_callback(errors.append)
    app.cmd.do("load 148l.pdb")

    viewer = app.viewer
    renderer = app.renderer
    gui = renderer._internal_gui
    renderer._chrome_quads()          # lay the panel out, as a frame does
    # This host opens with the info panel up, and a click on the scene
    # dismisses an overlay *instead of* picking -- by design. Put it away so
    # the click below is a click.
    gui.hide_info()

    from emtk.events import LEFT_BUTTON

    viewer.set_selected_residues([0, 1, 2])
    emit("selected_before", str(len(viewer._selected_residues)))

    row = gui._row_rects[1]           # the molecule's row in the object list
    rx, ry = row.x + row.w * 0.4, row.y + row.h / 2
    renderer.on_pointer_press(rx, ry, LEFT_BUTTON, 0, double=False)
    renderer.on_pointer_release(rx, ry, LEFT_BUTTON, 0)
    renderer.on_pointer_press(rx, ry, LEFT_BUTTON, 0, double=False)
    renderer.on_pointer_release(rx, ry, LEFT_BUTTON, 0)
    renderer.on_pointer_press(rx, ry, LEFT_BUTTON, 0, double=True)
    # -- and no release: the DOM does not send one for `dblclick`.
    emit("grab_after_dbl", str(renderer._gui_grab))

    # A click on the scene, well away from the panel: on empty space it
    # clears the selection, on the molecule it toggles a residue -- either
    # way the selection is no longer the three residues, unless the click
    # was swallowed.
    x, y = 40.0, 400.0
    emit("scene_point_is_gui", str(gui.wants(x, y)))
    renderer.on_pointer_press(x, y, LEFT_BUTTON, 0, double=False)
    emit("grab_after_scene_press", str(renderer._gui_grab))
    renderer.on_pointer_release(x, y, LEFT_BUTTON, 0)
    emit("selected_after", str(len(viewer._selected_residues)))
    emit("errors", "; ".join(errors[:2]) or "none")
'''


def test_a_lost_release_does_not_swallow_the_next_click():
    """BUGS/001 + BUGS/002: after an unpaired double press, a click still picks.

    The engine drops a grab that is still held when a *new* press arrives --
    a release was lost, and no host delivers press-after-press -- so the
    click's release reaches the picker instead of returning on the grab.
    """
    m = probe(_UNPAIRED_DOUBLE_THEN_CLICK)
    assert m["selected_before"] == "3"
    assert m["grab_after_dbl"] == "True", "the double press was not consumed"
    assert m["scene_point_is_gui"] == "False", "the scene point hit the panel"
    assert m["grab_after_scene_press"] == "False", (
        "a press arriving on a held grab did not drop the stale grab"
    )
    assert m["selected_after"] != "3", (
        "the click after the double click was swallowed (BUGS/001, BUGS/002)"
    )
    assert m["errors"] == "none", m["errors"]
