"""The screenshot helper itself, since a broken one fails silently as a black image.

Every other GUI check in this plugin depends on it: if `grabFramebuffer` quietly
returns nothing, the saved PNG is a black rectangle, and a black rectangle reads
as "the renderer is broken" rather than "the camera was". So the helper asserts
its own preconditions and these tests hold it to them.

These need a window server -- the whole point of the helper is that Qt's
offscreen platform cannot make an OpenGL context -- so they skip where there is
none rather than pretending to pass.
"""
from __future__ import annotations

import os

import pytest
from qtpy import QtCore, QtWidgets

from chisurf.plugins.chimol.test import screenshot as shot

pytestmark = pytest.mark.skipif(
    os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen"
    or not (os.environ.get("DISPLAY") or os.uname().sysname == "Darwin"),
    reason="needs a window server; the offscreen platform has no GL context",
)


@pytest.fixture(scope="module")
def app():
    return shot.ensure_app()


def test_the_offscreen_platform_is_refused(monkeypatch):
    """Refusing beats returning a black image.

    Under `QT_QPA_PLATFORM=offscreen` the 3-D view cannot render at all, and a
    screenshot taken there is worse than none: it looks exactly like a broken
    renderer.
    """
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    with pytest.raises(RuntimeError, match="offscreen"):
        shot.ensure_app()


def test_a_gl_widget_can_be_grabbed_without_a_window(app):
    """The point of the exercise: real GL output, nothing on the display."""
    widget = QtWidgets.QOpenGLWidget()
    try:
        image = shot.grab_gl(widget, size=(160, 120))
        assert not image.isNull()
        assert (image.width(), image.height()) == (160, 120)
        # Never mapped onto the display.
        assert widget.testAttribute(QtCore.Qt.WA_DontShowOnScreen)
    finally:
        widget.deleteLater()


def test_grabbing_something_with_no_gl_says_so(app):
    """A plain widget is not a 3-D view, and pretending otherwise hides a mistake."""
    widget = QtWidgets.QLabel("no gl here")
    try:
        with pytest.raises(RuntimeError, match="no QOpenGLWidget"):
            shot.grab_gl(widget)
    finally:
        widget.deleteLater()


def test_the_window_grab_composites_the_gl_view_in(app):
    """`QWidget.grab` leaves a hole where a child GL surface is; this fills it.

    The GL child is painted a solid colour, so a whole-window grab that failed
    to composite would show the parent's background there instead.
    """
    class _Solid(QtWidgets.QOpenGLWidget):
        def paintGL(self):  # noqa: N802 - Qt API
            from OpenGL import GL

            GL.glClearColor(0.0, 1.0, 0.0, 1.0)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT)

    parent = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(parent)
    layout.setContentsMargins(0, 0, 0, 0)
    gl = _Solid(parent)
    layout.addWidget(gl)
    try:
        image = shot.grab_window(parent, size=(200, 160))
        assert not image.isNull()
        centre = image.pixelColor(image.width() // 2, image.height() // 2)
        assert centre.green() > 150 and centre.red() < 100, (
            "the GL surface did not make it into the window grab"
        )
    finally:
        parent.deleteLater()


def test_shoot_writes_both_images(app, tmp_path):
    widget = QtWidgets.QOpenGLWidget()
    try:
        written = shot.shoot(widget, "probe", directory=tmp_path, size=(120, 90))
        assert set(written) == {"window", "view"}
        for path in written.values():
            assert path.is_file() and path.stat().st_size > 0
    finally:
        widget.deleteLater()
