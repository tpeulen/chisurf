"""`ray` must leave the object panel on screen.

Reported as "after ray the menu disappears -- it should never disappear, only
shouldn't be on screenshot", and that is exactly the distinction the old
implementation lost. The traced image was shown in a ``QLabel`` laid over the
viewport, and PyMOL's object panel is drawn *in* the viewport rather than beside
it -- so the label covered the A/S/H/L/C menus, the mouse-mode block and the
sequence strip along with the scene. The panel is the only way to switch a
representation back on, so it went away exactly when it was next needed, and the
click that dismissed the overlay was swallowed instead of reaching the button it
landed on.

The image belongs *behind* the chrome: absent from the saved file, never from
the window. These tests read back the frame the renderer draws on the offscreen
canvas -- the traced image composited into the scene column, the chrome over
it -- which is the frame every host shows.
"""

from __future__ import annotations

import pathlib

import pytest

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test"
    / "data"
    / "atomic_coordinates"
    / "pdb_files"
    / "148l.pdb"
)

#: A colour nothing else in the viewport uses, so a pixel test cannot pass on
#: the scene or the chrome happening to be near it.
RAY_RGB = (220, 30, 30)


@pytest.fixture(scope="module")
def viewport():
    """Build a laid-out viewport with a structure in it, and its renderer."""
    from native_window import NativeWindow

    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")

    window = NativeWindow(size=(1200, 900))
    window.load_structure_from_path(PDB, name="148l")
    # This host shows the system info on load, unpinned, so the next click in
    # the scene would put *it* away first; the clicks below are about the image.
    window.viewer.set_system_info_visible(False)
    window.pump(3)

    widget = window.viewer.renderer
    if widget.height() < 200 or widget.scene_width() < 200:
        pytest.skip(f"viewport is {widget.scene_width()}x{widget.height()}; never laid out")
    yield window, widget, window
    window.close()


def _ray_image():
    import numpy as np

    return np.tile(np.array(RAY_RGB, dtype=np.uint8), (500, 700, 1))


def _compose(window):
    """Draw a frame and read it back, ``(H, W, 4)``."""
    window.pump()
    return window.grab()


def _rgb(canvas, x, y):
    return tuple(int(v) for v in canvas[int(y), int(x), :3])


def test_the_traced_image_is_shown_in_the_scene_column(viewport):
    """It replaces the scene, and it is really painted."""
    window, widget, _ = viewport

    assert widget.show_ray_image(_ray_image())
    canvas = _compose(window)

    scene = _rgb(canvas, widget.scene_width() // 2, widget.height() // 2)
    assert scene == RAY_RGB, f"the traced image is not in the scene column (found {scene})"
    widget.clear_ray_image()


def test_the_image_stays_out_of_the_chrome(viewport):
    """The whole report, as geometry.

    Asserted on the rect rather than on pixels: the panel's background is
    semi-transparent, so an image painted across its column comes back
    *darkened* rather than replaced, and a colour comparison would pass on the
    broken case.
    """
    _window, widget, _ = viewport
    gui = widget._internal_gui
    if not (gui.visible and gui.docked):
        pytest.skip("the object panel is not docked in the viewport")

    rect = widget.ray_image_rect()
    assert rect.right() < widget.width() - 1, (
        f"the image area {rect.getRect()} runs under the panel's column, which "
        f"starts at {widget.scene_width()} of {widget.width()}"
    )
    assert rect.width() == widget.scene_width()
    assert rect.top() >= int(gui.sequence_height()), (
        "the image area covers the sequence strip's band"
    )


def test_the_panel_still_takes_a_click_while_the_image_shows(viewport):
    """ "Still on screen" is not enough; it has to still work.

    The old overlay swallowed the press that dismissed it, so the first click
    after `ray` never reached the button under the cursor. What is asserted is
    that the panel *took* the press -- not that the image survived it, which it
    should not when the click is one that changes what is drawn.
    """
    from emtk.events import LEFT_BUTTON, NO_MODIFIER

    _window, widget, _ = viewport
    gui = widget._internal_gui
    gui.layout(widget.width(), widget.height())

    hit = None
    for y in range(4, min(int(widget.height()), 400), 4):
        for x in range(int(widget.width()) - 4, int(widget.scene_width()), -8):
            if gui.wants(float(x), float(y)):
                hit = (x, y)
                break
        if hit:
            break
    if hit is None:
        pytest.skip("no panel hot-spot found to click")

    assert widget.show_ray_image(_ray_image())
    widget._gui_grab = False
    consumed = widget.on_pointer_press(float(hit[0]), float(hit[1]), LEFT_BUTTON, NO_MODIFIER)

    assert widget._gui_grab, (
        f"the press at {hit} was over the object panel and the panel did not "
        "get it -- it was consumed dismissing the traced image, which is what "
        "made the first click after `ray` do nothing"
    )
    assert consumed
    widget.on_pointer_release(float(hit[0]), float(hit[1]), LEFT_BUTTON, NO_MODIFIER)
    widget.clear_ray_image()


def test_a_click_on_the_scene_goes_back_to_the_live_view(viewport):
    """The camera is about to move, so a still frame of where it was must go."""
    from emtk.events import LEFT_BUTTON, NO_MODIFIER

    _window, widget, _ = viewport
    assert widget.show_ray_image(_ray_image())

    x, y = widget.scene_width() / 2.0, widget.height() / 2.0
    widget.on_pointer_press(x, y, LEFT_BUTTON, NO_MODIFIER)
    widget.on_pointer_release(x, y, LEFT_BUTTON, NO_MODIFIER)
    assert widget._ray_image is None


def test_nothing_is_laid_over_the_viewport(viewport):
    """The mechanism, guarded directly: the panel is still drawn over the image.

    Anything laid over the 3-D column hides the panel drawn inside it, whatever
    it is, so what is checked is the frame: with a traced image showing, the
    panel's column carries the chrome and not the image's colour.
    """
    window, widget, _ = viewport
    gui = widget._internal_gui
    if not (gui.visible and gui.docked):
        pytest.skip("the object panel is not docked in the viewport")

    assert window.viewer.show_ray_overlay(_ray_image())
    try:
        canvas = _compose(window)
        column = canvas[: int(widget.height()), int(widget.scene_width()) + 2 :, :3]
        ray = (column == list(RAY_RGB)).all(axis=2)
        assert not ray.any(), (
            f"{int(ray.sum())} pixels of the traced image landed in the panel's "
            "column; the object panel is drawn there and is now hidden"
        )
        scene = _rgb(canvas, widget.scene_width() // 2, widget.height() // 2)
        assert scene == RAY_RGB, f"the traced image is not drawn at all (found {scene})"
    finally:
        window.viewer.hide_ray_overlay()


def test_changing_what_is_drawn_drops_the_image(viewport):
    """A traced image is a picture of the scene that was."""
    from chimol.commands.command import Cmd

    window, widget, _ = viewport
    assert widget.show_ray_image(_ray_image())

    cmd = Cmd(window.host)
    cmd.set_message_callback(lambda _m: None)
    cmd.set_error_callback(lambda _m: None)
    cmd.do("hide everything")
    window.pump()

    assert widget._ray_image is None, (
        "the viewport still shows a picture of a scene that has changed"
    )
    cmd.do("show cartoon")
    window.pump()
