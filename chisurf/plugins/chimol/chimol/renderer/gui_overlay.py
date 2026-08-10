"""The in-viewport chrome, painted to an image any backend can composite.

``InternalGui`` -- the object panel down the right and the sequence strip across
the top -- paints with a ``QPainter`` and always did; only its *host* was
OpenGL-specific. ``qtgl`` opens a painter on its own ``QOpenGLWidget`` after the
GL pass, which works there and nowhere else: a WebGPU surface is presented by
the compositor, not painted by Qt, and a translucent child stacked over it does
not blend with it -- it covers it.

So the chrome is painted into a premultiplied RGBA image here and composited by
whoever is drawing, which for the WebGPU backend is a textured quad at the end
of its own render pass. That is the only form a browser could use either, and
it is what ``kind == "text"`` labels will want -- so the shape that looks like a
detour is the one that generalises.

It also gives the WebGPU path something the GL one has wanted for a long time:
``win.grab()`` captures the chrome *and* the molecule, where the GL screenshot
helper pastes the framebuffer over the widget area and hides overlay children,
which once produced a whole-window grab with no panel in it while the panel was
plainly visible on screen.
"""
from __future__ import annotations

from qtpy import QtCore, QtGui

__all__ = ["paint_chrome", "refresh_gui_state"]


def refresh_gui_state(gui, controller) -> None:
    """Pull the movie position and sequence colours into the panel.

    Pulled every frame rather than pushed on change, because there is no one
    place a frame changes: playback advances it on a timer, ``frame`` and the
    transport set it directly, and a trajectory reload resets it. A slider wired
    to one of those and not the others sits still while the molecule moves,
    which is worse than having no slider.

    A drag in progress wins: the position under the cursor is what the user is
    asking for, and overwriting it from the viewer each frame would drag the
    thumb out of their hand.

    Parameters
    ----------
    gui : InternalGui
        The panel to update in place.
    controller : object or None
        The :class:`~.view.MolView` to read from.
    """
    if controller is None or gui is None or gui.is_dragging():
        return

    # Re-read the sequence colours as well. Colouring is a *command* --
    # `spectrum`, `color`, `ss` -- and there is no signal for it, so a strip
    # coloured once at load keeps showing the old scheme while the molecule in
    # front of it shows the new one. Reading them back is a cached array copy,
    # which costs nothing beside drawing the molecule itself.
    for row in gui.sequences:
        if not row.object_id:
            continue
        try:
            colours = controller.get_residue_colors(row.object_id)
        except Exception:
            continue
        if colours is None:
            continue
        row.colors = [tuple(float(c) for c in rgba[:3]) for rgba in colours]

    try:
        current = int(controller.get_current_frame()) + 1
        total = max(int(controller.get_total_frames()), 1)
    except Exception:
        return
    if (current, total) != gui.state:
        gui.state = (current, total)


def paint_chrome(gui, controller, width: int, height: int, ratio: float = 1.0):
    """Paint the chrome into a transparent image, ready to composite.

    Returns premultiplied RGBA, which is what Qt paints into natively and what
    the compositing blend expects: converting to straight alpha here and back in
    the shader would darken every antialiased glyph edge twice.

    Two ways of getting the chrome onto a WebGPU surface were tried and rejected
    before this one, and both failed in ways that looked like renderer bugs:

    * a translucent child ``QWidget`` stacked over the surface, whose backing
      store Qt does not clear -- the uncleared memory composited over the frame
      and turned a rainbow cartoon salmon-and-blue, which reads exactly like a
      channel-order bug;
    * the same, with the backing store cleared -- the molecule disappeared
      entirely, because a presented surface and a Qt child do not blend, the
      child simply covers it.

    A ``QPainter`` opened directly on the 3-D widget, which is what ``qtgl``
    does, is not available either: a WebGPU surface is presented by the
    compositor, not painted by Qt.

    Parameters
    ----------
    gui : InternalGui
        The chrome to paint.
    controller : object or None
        The viewer, for :func:`refresh_gui_state`.
    width, height : int
        Target size in **device** pixels.
    ratio : float, optional
        Device pixels per logical pixel. The chrome lays itself out in logical
        pixels because that is what a painter on a widget uses, so on a
        high-DPI screen the painter is scaled rather than the layout.

    Returns
    -------
    numpy.ndarray
        ``(height, width, 4)`` uint8, premultiplied RGBA.
    """
    import numpy as np

    width, height = max(int(width), 1), max(int(height), 1)
    image = QtGui.QImage(width, height, QtGui.QImage.Format_RGBA8888_Premultiplied)
    image.fill(QtCore.Qt.transparent)
    if gui is None:
        return np.zeros((height, width, 4), dtype=np.uint8)

    painter = QtGui.QPainter(image)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        if ratio != 1.0:
            painter.scale(ratio, ratio)
        refresh_gui_state(gui, controller)
        gui.layout(int(width / ratio), int(height / ratio))
        gui.paint(painter)
    finally:
        painter.end()

    buffer = image.constBits()
    try:
        buffer.setsize(image.sizeInBytes())
    except AttributeError:  # PyQt6/PySide return a memoryview already sized
        pass
    # bytesPerLine, not width*4: Qt pads scanlines to a 4-byte boundary and a
    # reshape that assumes otherwise skews the image into a diagonal smear.
    stride = image.bytesPerLine()
    arr = np.frombuffer(bytes(buffer), dtype=np.uint8).reshape(height, stride // 4, 4)
    return np.ascontiguousarray(arr[:, :width, :])
