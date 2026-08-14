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
the window. These tests paint the widget's screen-space pass onto a plain
``QImage`` -- the same code the widget runs, with a painter that can be read
back, since an offscreen GL framebuffer cannot be.
"""
from __future__ import annotations

import pathlib

import pytest

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)

#: A colour nothing else in the viewport uses, so a pixel test cannot pass on
#: the scene or the chrome happening to be near it.
RAY_RGB = (220, 30, 30)


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def viewport(qapp):
    """Build a laid-out viewport with a structure in it, and its GL widget."""
    from chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )

    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")

    window = MolViewPluginWindow()
    # A viewport that was never laid out is not a viewport: offscreen the
    # window collapses the 3-D column to a few dozen pixels, and every
    # measurement below would be taken on a widget with no room in it.
    window.viewer.setMinimumWidth(760)
    window.viewer.setMinimumHeight(560)
    window.resize(1200, 900)
    window.show()
    for _ in range(30):
        qapp.processEvents()

    window._load_structure_from_path(PDB, name="148l")
    for _ in range(20):
        qapp.processEvents()

    widget = window.viewer._renderer.widget()
    if widget.height() < 200 or widget.scene_width() < 200:
        pytest.skip(
            f"viewport is {widget.scene_width()}x{widget.height()}; never laid out"
        )
    yield window, widget, qapp
    window.close()


def _ray_image():
    from qtpy import QtGui

    image = QtGui.QImage(700, 500, QtGui.QImage.Format_RGB32)
    image.fill(QtGui.QColor(*RAY_RGB))
    return image


def _compose(widget):
    """Run the widget's screen-space pass onto a readable canvas."""
    from qtpy import QtGui

    canvas = QtGui.QImage(widget.width(), widget.height(), QtGui.QImage.Format_RGB32)
    canvas.fill(QtGui.QColor(0, 0, 255))
    painter = QtGui.QPainter(canvas)
    try:
        widget.paint_screen_space(painter)
    finally:
        painter.end()
    return canvas


def _rgb(canvas, x, y):
    colour = canvas.pixelColor(int(x), int(y))
    return (colour.red(), colour.green(), colour.blue())


def test_the_traced_image_is_shown_in_the_scene_column(viewport):
    """It replaces the scene, and it is really painted."""
    _window, widget, _qapp = viewport

    assert widget.show_ray_image(_ray_image())
    canvas = _compose(widget)

    scene = _rgb(canvas, widget.scene_width() // 2, widget.height() // 2)
    assert scene == RAY_RGB, (
        f"the traced image is not in the scene column (found {scene})"
    )
    widget.clear_ray_image()


def test_the_image_stays_out_of_the_chrome(viewport):
    """The whole report, as geometry.

    Asserted on the rect rather than on pixels: the panel's background is
    semi-transparent, so an image painted across its column comes back
    *darkened* rather than replaced, and a colour comparison would pass on the
    broken case.
    """
    _window, widget, _qapp = viewport
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
    """"Still on screen" is not enough; it has to still work.

    The old overlay swallowed the press that dismissed it, so the first click
    after `ray` never reached the button under the cursor. What is asserted is
    that the panel *took* the press -- not that the image survived it, which it
    should not when the click is one that changes what is drawn.
    """
    from qtpy import QtCore, QtGui

    _window, widget, _qapp = viewport
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
    event = QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonPress,
        QtCore.QPointF(*hit),
        QtCore.Qt.LeftButton,
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
    )
    widget._gui_grab = False
    widget.mousePressEvent(event)

    assert widget._gui_grab, (
        f"the press at {hit} was over the object panel and the panel did not "
        "get it -- it was consumed dismissing the traced image, which is what "
        "made the first click after `ray` do nothing"
    )
    assert event.isAccepted()
    widget.clear_ray_image()


def test_a_click_on_the_scene_goes_back_to_the_live_view(viewport):
    """The camera is about to move, so a still frame of where it was must go."""
    from qtpy import QtCore, QtGui

    _window, widget, _qapp = viewport
    assert widget.show_ray_image(_ray_image())

    event = QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonPress,
        QtCore.QPointF(widget.scene_width() / 2.0, widget.height() / 2.0),
        QtCore.Qt.LeftButton,
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
    )
    widget.mousePressEvent(event)
    assert widget._ray_image is None


def test_nothing_is_laid_over_the_viewport(viewport):
    """The mechanism, guarded directly.

    Any widget shown over the 3-D column hides the panel drawn inside it,
    whatever it is called, so what is checked is that showing a traced image
    adds no visible child covering the container -- not that one particular
    ``QLabel`` is gone.
    """
    from qtpy import QtCore

    window, widget, qapp = viewport
    container = getattr(window.viewer, "_container", None)
    if container is None:
        pytest.skip("the viewer has no container widget")

    def covering() -> list:
        area = QtCore.QRect(QtCore.QPoint(0, 0), container.size())
        return [
            child.__class__.__name__
            for child in container.findChildren(QtCore.QObject)
            if hasattr(child, "isVisible")
            and child is not widget
            and child.isVisible()
            and child.geometry().contains(area)
        ]

    before = covering()
    assert window.viewer.show_ray_overlay(_ray_image())
    for _ in range(5):
        qapp.processEvents()
    after = covering()

    assert after == before, (
        f"showing a traced image put {sorted(set(after) - set(before))} over "
        "the viewport; the object panel is drawn inside it and is now hidden"
    )
    window.viewer.hide_ray_overlay()


def test_changing_what_is_drawn_drops_the_image(viewport):
    """A traced image is a picture of the scene that was."""
    from chimol.cmd.command import Cmd

    window, widget, qapp = viewport
    assert widget.show_ray_image(_ray_image())

    cmd = Cmd(window)
    cmd.set_message_callback(lambda _m: None)
    cmd.set_error_callback(lambda _m: None)
    cmd.do("hide everything")
    for _ in range(10):
        qapp.processEvents()

    assert widget._ray_image is None, (
        "the viewport still shows a picture of a scene that has changed"
    )
    cmd.do("show cartoon")
    for _ in range(10):
        qapp.processEvents()
