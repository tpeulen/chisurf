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

import hashlib

import numpy as np
from qtpy import QtCore, QtGui

__all__ = [
    "image_from_rgb",
    "paint_chrome",
    "paint_chrome_into",
    "paint_labels",
    "paint_ray_image",
    "paint_select_rect",
    "refresh_gui_state",
]


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
        # Converting the array to a list of tuples is 234k tuples and 700k
        # `float()` calls on an integrative model -- 395 ms, on every repaint,
        # to produce the same list as last time. The colours only change when a
        # command replaces the array, so its address is the signal: same buffer,
        # same list. Content is deliberately not hashed; that would cost more
        # than the conversion it avoids.
        # Content, not address. The colour arrays are re-derived by the colour
        # commands rather than replaced, so identity survives a change it must
        # not survive -- keyed on the address, a scene came back in the previous
        # one's colours. The hash is paid once per chrome repaint, which is ten
        # times a second, not sixty.
        signature = hashlib.blake2b(
            np.ascontiguousarray(colours).view(np.uint8), digest_size=16
        ).digest()
        if getattr(row, "_colors_from", None) == signature:
            continue
        row.colors = [tuple(float(c) for c in rgba[:3]) for rgba in colours]
        row._colors_from = signature

    try:
        current = int(controller.get_current_frame()) + 1
        total = max(int(controller.get_total_frames()), 1)
    except Exception:
        return
    if (current, total) != gui.state:
        gui.state = (current, total)


def paint_labels(painter, labels, project) -> int:
    """Draw 3-D labels at their projected positions.

    Parameters
    ----------
    painter : QtGui.QPainter
        Already scaled to logical pixels by the caller.
    labels : sequence
        Objects with ``pos`` (3 floats), ``text`` and ``color`` (an RGBA tuple
        in 0..1, or a ``QColor``).
    project : callable
        ``points -> (x, y, visible)`` in **logical** widget pixels, which must
        be the projection the frame was drawn with. A label placed by a
        second, independently-derived projection lands where the atom is not,
        and the error only shows once the panel or the sequence strip takes a
        share of the widget -- which is exactly when nobody is looking at label
        placement.

    Returns
    -------
    int
        How many labels were drawn.
    """
    import numpy as np

    if not labels:
        return 0
    positions = np.asarray([label.pos for label in labels], dtype=float)
    xs, ys, visible = project(positions)
    if len(xs) != len(labels):
        return 0

    painter.save()
    font = painter.font()
    font.setPointSize(10)
    font.setBold(True)
    painter.setFont(font)
    drawn = 0
    for i, label in enumerate(labels):
        if not visible[i]:
            continue
        x, y = int(xs[i]), int(ys[i])
        colour = label.color
        if not isinstance(colour, QtGui.QColor):
            r, g, b, a = (list(colour) + [1.0, 1.0, 1.0, 1.0])[:4]
            colour = QtGui.QColor(int(r * 255), int(g * 255), int(b * 255), int(a * 255))
        # A one-pixel black shadow first: white text on a white surface and
        # black text on a black background are both invisible, and a molecule
        # is whatever colour the user made it.
        painter.setPen(QtGui.QColor(0, 0, 0, 150))
        painter.drawText(x + 1, y + 1, label.text)
        painter.setPen(colour)
        painter.drawText(x, y, label.text)
        drawn += 1
    painter.restore()
    return drawn


def image_from_rgb(array) -> "QtGui.QImage":
    """Wrap an ``(h, w, 3|4)`` uint8 array as a QImage, copied.

    Copied deliberately: a QImage over a numpy buffer is a view, and the array
    is routinely a temporary -- the image then renders whatever replaced it.
    """
    import numpy as np

    data = np.ascontiguousarray(array)
    if data.dtype != np.uint8:
        data = np.clip(data, 0.0, 1.0)
        data = (data * 255.0).astype(np.uint8)
    if data.ndim != 3 or data.shape[2] not in (3, 4):
        raise ValueError(f"expected (h, w, 3) or (h, w, 4), got {data.shape}")
    height, width, channels = data.shape
    fmt = (
        QtGui.QImage.Format_RGB888 if channels == 3 else QtGui.QImage.Format_RGBA8888
    )
    return QtGui.QImage(
        data.tobytes(), width, height, width * channels, fmt
    ).copy()


def paint_ray_image(painter, image, rect) -> bool:
    """Blit a traced frame into the scene column, aspect preserved.

    Into the *column*, not across the widget: a traced image stretched over the
    whole viewport puts the picture where the chrome goes, and the panel is what
    tells you which object you are looking at.
    """
    if image is None or rect is None:
        return False
    if hasattr(image, "isNull") and image.isNull():
        return False
    size = image.size()
    if size.width() <= 0 or size.height() <= 0 or rect.width() <= 0:
        return False
    scaled = size.scaled(rect.size(), QtCore.Qt.KeepAspectRatio)
    target = QtCore.QRect(QtCore.QPoint(0, 0), scaled)
    target.moveCenter(rect.center())
    painter.drawImage(target, image, QtCore.QRect(QtCore.QPoint(0, 0), size))
    return True


def paint_select_rect(painter, rect) -> bool:
    """Draw the rubber-band selection box."""
    if rect is None or rect.isNull():
        return False
    painter.save()
    pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 220))
    pen.setStyle(QtCore.Qt.DashLine)
    pen.setWidth(1)
    painter.setPen(pen)
    painter.setBrush(QtGui.QColor(255, 255, 255, 30))
    painter.drawRect(rect)
    painter.restore()
    return True


def paint_chrome_into(painter, gui, controller, width: int, height: int, *,
                      labels=None, project=None, ray_image=None, ray_rect=None,
                      select_rect=None) -> None:
    """Draw every screen-space element into ``painter``, in order.

    The order *is* the contract: the traced frame first, so everything below is
    chrome drawn over it exactly as it is drawn over the live scene; then the
    labels; then the panel and strip, which are a column and a band beside the
    molecule and must not be overprinted by a label; then the selection box,
    which is transient and belongs on top of all of it.

    Sizes are in **logical** pixels -- the painter is already scaled if the
    caller is drawing at device resolution.
    """
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
    painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
    paint_ray_image(painter, ray_image, ray_rect)
    if labels and project is not None:
        paint_labels(painter, labels, project)
    if gui is not None:
        from .ui.qt_painter import QtPainter

        refresh_gui_state(gui, controller)
        gui.layout(int(width), int(height))
        # The panel no longer knows what a ``QPainter`` is: it draws through
        # the six operations in :mod:`chimol.renderer.ui.painter`, of which
        # this is the Qt implementation and the reference. Constructed here,
        # per paint, because it owns the font it sets on the painter.
        gui.paint(QtPainter(painter, font_pt=gui.FONT_PT))
    paint_select_rect(painter, select_rect)


def paint_chrome(gui, controller, width: int, height: int, ratio: float = 1.0,
                 labels=None, project=None, ray_image=None, ray_rect=None,
                 select_rect=None):
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
    labels : sequence, optional
        3-D labels, drawn *under* the panel: the panel is a column beside the
        molecule and a label that overprinted it would be unreadable on both.
    project : callable, optional
        The projection for ``labels``; see :func:`paint_labels`.

    Returns
    -------
    numpy.ndarray
        ``(height, width, 4)`` uint8, premultiplied RGBA.
    """
    import numpy as np

    width, height = max(int(width), 1), max(int(height), 1)
    image = QtGui.QImage(width, height, QtGui.QImage.Format_RGBA8888_Premultiplied)
    image.fill(QtCore.Qt.transparent)
    if gui is None and not labels and ray_image is None and select_rect is None:
        return np.zeros((height, width, 4), dtype=np.uint8)

    painter = QtGui.QPainter(image)
    try:
        if ratio != 1.0:
            painter.scale(ratio, ratio)
        paint_chrome_into(
            painter, gui, controller,
            int(width / ratio), int(height / ratio),
            labels=labels, project=project,
            ray_image=ray_image, ray_rect=ray_rect, select_rect=select_rect,
        )
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
