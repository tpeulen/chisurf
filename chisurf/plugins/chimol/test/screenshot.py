"""Take real screenshots of the viewer, including the 3-D view, without a window.

Why this exists
---------------
The project rule is that a GUI change is unfinished until the widget has been
rendered and the image *looked at*. For most widgets ``widget.grab()`` under
``QT_QPA_PLATFORM=offscreen`` is enough. The 3-D view is not most widgets: its
pixels do not live in the widget's backing store, so a plain grab comes back a
uniform rectangle of the right size and no error.

**Ask the renderer, not the toolkit.** ``CanvasRenderer.grab_image`` re-renders
the frame into an offscreen texture through the same code the window draws
with, and composites the chrome. It needs no window server, no GL context and
no platform plugin, so it works under ``QT_QPA_PLATFORM=offscreen`` and it is
the route this module takes first.

That is not how it started, and the previous arrangement is worth stating
because it cost a rule its teeth. This module was written for a
``QOpenGLWidget`` and captured with ``grabFramebuffer()``, arguing at length
about the offscreen plugin's inability to create a GL context. chimol's
renderer became a plain ``QWidget`` presenting a WebGPU surface during the WGSL
port -- so the search found nothing, ``grab_window`` fell through to
``widget.grab()``, and **every chimol screenshot since was a blank**. Silently.
The fallback still exists for a genuine ``QOpenGLWidget``, and now it is a
fallback rather than the only path.

Consequences worth knowing:

* the WebGPU route runs anywhere, including CI. The ``QOpenGLWidget`` fallback
  still needs a window server and refuses the offscreen platform rather than
  producing a black image;
* a 3-D view is grabbed separately from the rest of the window and pasted in.
  ``QWidget.grab()`` captures neither a child GL surface nor a presented WebGPU
  one, which is what makes a whole-window grab of a 3-D app come out with a
  hole in it.

Use
---
    from chisurf.plugins.chimol.test.screenshot import shoot

    paths = shoot(window, "npc_demo", area="all")
"""

from __future__ import annotations

import os
import pathlib

from qtpy import QtCore, QtGui, QtWidgets

__all__ = [
    "ensure_app",
    "grab_window",
    "grab_gl",
    "grab_view",
    "shoot",
    "OFFSCREEN_REFUSED",
]

#: Raised as a message, not an exception type, so a caller can decide.
OFFSCREEN_REFUSED = (
    "the offscreen Qt platform cannot create an OpenGL context, so the 3-D view "
    "would come out black -- unset QT_QPA_PLATFORM and run on a logged-in session"
)


def ensure_app() -> QtWidgets.QApplication:
    """Return the application, creating one if there is none.

    Returns
    -------
    QtWidgets.QApplication
    """
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _refuse_offscreen() -> None:
    """Raise if the offscreen platform cannot serve the route about to be taken.

    Only the ``QOpenGLWidget`` fallback needs this. The renderer's own capture
    does not touch a platform GL context, so refusing it there would rule out
    the one route that works.

    Raises
    ------
    RuntimeError
    """
    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        raise RuntimeError(OFFSCREEN_REFUSED)


def _renderers(widget: QtWidgets.QWidget) -> list[QtWidgets.QWidget]:
    """Every 3-D view under *widget* that can photograph itself.

    Found by capability -- a ``grab_image`` method -- rather than by class. The
    class was the mistake this replaces: ``QOpenGLWidget`` was hard-coded, and
    when the renderer stopped being one, the search stopped finding anything
    and nothing said so.

    Returns
    -------
    list of QtWidgets.QWidget
    """
    candidates = [widget, *widget.findChildren(QtWidgets.QWidget)]
    return [w for w in candidates if callable(getattr(w, "grab_image", None))]


def _as_qimage(array) -> QtGui.QImage:
    """Wrap an ``(h, w, 3)`` uint8 array as a ``QImage`` that owns its bytes.

    Parameters
    ----------
    array : numpy.ndarray

    Returns
    -------
    QtGui.QImage

    Raises
    ------
    RuntimeError
        If the array is not a picture -- an empty or wrongly shaped buffer
        would otherwise become a null image and be written as a black PNG.
    """
    import numpy as np

    rgb = np.ascontiguousarray(np.asarray(array)[..., :3], dtype=np.uint8)
    if rgb.ndim != 3 or rgb.shape[0] < 1 or rgb.shape[1] < 1:
        raise RuntimeError(f"the renderer returned {rgb.shape}, which is not a frame")
    height, width = rgb.shape[0], rgb.shape[1]
    image = QtGui.QImage(rgb.data, width, height, 3 * width, QtGui.QImage.Format_RGB888)
    # `.copy()` and not a stored reference: the QImage does not own the NumPy
    # buffer, and a view outliving the array is a use-after-free that shows up
    # as a garbled screenshot rather than as a crash.
    return image.copy()


def grab_view(widget: QtWidgets.QWidget, size: tuple[int, int] | None = None) -> QtGui.QImage:
    """Grab the 3-D view alone, from the renderer itself.

    Parameters
    ----------
    widget : QtWidgets.QWidget
        The renderer, or something containing one.
    size : tuple of int, optional
        Resize before grabbing.

    Returns
    -------
    QtGui.QImage
        The frame as the window shows it -- panel, sequence strip and all.

    Raises
    ------
    RuntimeError
        If nothing under *widget* can photograph itself. Falling back to
        ``widget.grab()`` here is what made this module return blanks.
    """
    app = ensure_app()
    targets = _renderers(widget)
    if not targets:
        raise RuntimeError("no self-rendering 3-D view to grab")
    if size is not None:
        widget.resize(int(size[0]), int(size[1]))
    if not widget.isVisible():
        _prepare(widget, size)
    _settle(app)
    return _as_qimage(targets[0].grab_image(chrome=True))


def _settle(app: QtWidgets.QApplication, rounds: int = 12) -> None:
    """Let Qt lay out, expose and paint before the shutter."""
    for _ in range(rounds):
        app.processEvents()


def force_render_canvases(widget: QtWidgets.QWidget) -> int:
    """Make every WebGPU canvas under *widget* present a frame, synchronously.

    ``request_draw`` only *schedules*: a grab taken before the first present
    captures an unpainted surface, and the result is a solid black viewport in
    an otherwise perfect screenshot -- which reads as "the renderer draws
    nothing" and is a shutter-timing bug. Pumping the event loop is not enough,
    because the canvas decides when to draw.

    Returns
    -------
    int
        How many canvases were forced, so a caller can tell "none present" from
        "none needed".
    """
    forced = 0
    candidates = [widget, *widget.findChildren(QtWidgets.QWidget)]
    for child in candidates:
        force = getattr(child, "force_draw", None)
        if not callable(force) or not child.isVisible():
            continue
        try:
            force()
        except Exception:  # pragma: no cover - a canvas without a surface yet
            continue
        forced += 1
    return forced


def _prepare(widget: QtWidgets.QWidget, size: tuple[int, int] | None) -> None:
    """Realise *widget* without putting it on the display."""
    widget.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    if size is not None:
        widget.resize(int(size[0]), int(size[1]))
    widget.show()


def _gl_children(widget: QtWidgets.QWidget) -> list[QtWidgets.QOpenGLWidget]:
    """Every GL widget inside *widget*, itself included."""
    found = []
    if isinstance(widget, QtWidgets.QOpenGLWidget):
        found.append(widget)
    found.extend(widget.findChildren(QtWidgets.QOpenGLWidget))
    return found


def grab_gl(widget: QtWidgets.QWidget, size: tuple[int, int] | None = None) -> QtGui.QImage:
    """Grab the 3-D view alone: from the renderer, or from a GL framebuffer.

    Parameters
    ----------
    widget : QtWidgets.QWidget
        A 3-D view or something containing one.
    size : tuple of int, optional
        Resize before grabbing.

    Returns
    -------
    QtGui.QImage

    Raises
    ------
    RuntimeError
        If there is no 3-D view at all, or a GL context never became valid -- a
        null image saved as a PNG is a black rectangle that reads as a bug in
        the thing being photographed.
    """
    if _renderers(widget):
        return grab_view(widget, size)
    app = ensure_app()
    _refuse_offscreen()
    targets = _gl_children(widget)
    if not targets:
        raise RuntimeError("nothing to grab: no self-rendering 3-D view and no QOpenGLWidget")
    gl = targets[0]
    if not gl.isVisible():
        _prepare(widget, size)
    elif size is not None:
        widget.resize(int(size[0]), int(size[1]))
    _settle(app)
    image = gl.grabFramebuffer()
    if image.isNull():
        raise RuntimeError("the GL framebuffer came back null; " + OFFSCREEN_REFUSED)
    return image


def assert_view_usable(
    widget: QtWidgets.QWidget,
    *,
    min_px: int = 200,
    min_aspect: float = 0.35,
) -> tuple[int, int]:
    """Refuse a 3-D viewport too small or too misshapen to judge anything from.

    A restored dock layout can hand the 3-D view a sliver -- a 1280x90 strip, or
    in the worst case a single pixel column when the scene column is narrower
    than the panel beside it. Nothing raises: the grab succeeds, the PNG is
    written, and the molecule is a speck under a full-width sequence bar. Every
    assertion taken against that image passes and means nothing.

    A plain size check does not catch it, because a strip is comfortably wider
    than any pixel floor. The shape has to be checked too.

    Parameters
    ----------
    widget : QtWidgets.QWidget
        The window or widget containing the ``QOpenGLWidget``.
    min_px : int
        Smallest acceptable width and height, in device pixels.
    min_aspect : float
        Smallest acceptable ratio of the short side to the long side.

    Returns
    -------
    tuple of int
        The usable ``(width, height)``.

    Raises
    ------
    RuntimeError
        If there is no GL widget, or its viewport is too small or too extreme to
        produce a reviewable image.
    """
    targets = _renderers(widget) or _gl_children(widget)
    if not targets:
        raise RuntimeError("no 3-D view to measure")
    gl = targets[0]
    w, h = gl.width(), gl.height()
    if w < min_px or h < min_px:
        raise RuntimeError(
            f"3-D viewport is {w}x{h}; needs at least {min_px}x{min_px}. A "
            f"persisted dock layout is the usual cause -- set CHISURF_SETTINGS_DIR "
            f"to a scratch directory so the window starts from a known layout."
        )
    aspect = min(w, h) / max(w, h)
    if aspect < min_aspect:
        raise RuntimeError(
            f"3-D viewport is {w}x{h} (aspect {aspect:.2f} < {min_aspect}); that "
            f"is a strip, not a view. The molecule will be a speck and the image "
            f"is not reviewable."
        )
    return w, h


def grab_window(widget: QtWidgets.QWidget, size: tuple[int, int] | None = None) -> QtGui.QImage:
    """Grab the whole window, with the 3-D view pasted into its place.

    ``QWidget.grab`` renders the widget tree itself and does not read back a
    child's GL surface, so a plain whole-window grab of a 3-D application comes
    out with a hole where the interesting part is. The GL children are grabbed
    from their framebuffers and composited in at their own geometry.

    Parameters
    ----------
    widget : QtWidgets.QWidget
        Usually the main window.
    size : tuple of int, optional
        Resize before grabbing.

    Returns
    -------
    QtGui.QImage
    """
    app = ensure_app()
    _prepare(widget, size)
    _settle(app)
    # A WebGPU viewport paints when its canvas decides to, not when Qt does.
    if force_render_canvases(widget):
        _settle(app)

    views = _renderers(widget)
    if not views and not _gl_children(widget):
        raise RuntimeError(
            "no 3-D view under this widget, so a whole-window grab would be a "
            "picture of everything except the part worth looking at. That is "
            "how this helper came to return blanks for a year; if the window "
            "genuinely has no 3-D view, grab it with widget.grab() directly."
        )

    shot = widget.grab().toImage()
    painter = QtGui.QPainter(shot)
    try:
        for view in views:
            if not view.isVisible() or view.width() <= 0 or view.height() <= 0:
                continue
            frame = _as_qimage(view.grab_image(chrome=True))
            top_left = view.mapTo(widget, QtCore.QPoint(0, 0))
            painter.drawImage(
                QtCore.QRect(top_left, view.size()),
                frame,
                QtCore.QRect(QtCore.QPoint(0, 0), frame.size()),
            )
        for gl in _gl_children(widget):
            if gl in views or not gl.isVisible() or gl.width() <= 0 or gl.height() <= 0:
                continue
            frame = gl.grabFramebuffer()
            if frame.isNull():
                continue
            top_left = gl.mapTo(widget, QtCore.QPoint(0, 0))
            painter.drawImage(
                QtCore.QRect(top_left, gl.size()),
                frame,
                QtCore.QRect(QtCore.QPoint(0, 0), frame.size()),
            )
    finally:
        painter.end()
    return shot


def shoot(
    widget: QtWidgets.QWidget,
    name: str,
    *,
    directory: str | pathlib.Path = "renders",
    size: tuple[int, int] | None = (1280, 860),
    area: str = "all",
) -> dict[str, pathlib.Path]:
    """Save screenshots and return where they went.

    Parameters
    ----------
    widget : QtWidgets.QWidget
        The window (or widget) to photograph.
    name : str
        Stem of the file name.
    directory : str or pathlib.Path
        Where to write.
    size : tuple of int, optional
        Window size to use.
    area : {"all", "window", "view"}
        ``window`` is the whole interface, ``view`` the 3-D view alone, ``all``
        both.

    Returns
    -------
    dict
        ``{"window": path, "view": path}`` for whichever were taken.
    """
    out = pathlib.Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, pathlib.Path] = {}

    if area in ("all", "window"):
        path = out / f"{name}_window.png"
        _save(grab_window(widget, size), path)
        written["window"] = path
    if area in ("all", "view"):
        path = out / f"{name}_view.png"
        _save(grab_gl(widget, size), path)
        written["view"] = path
    return written


def _save(image: QtGui.QImage, path: pathlib.Path) -> None:
    """Write ``image`` to ``path``, raising rather than reporting a silent success.

    ``QImage.save`` reports failure by returning ``False``; it does not raise. A
    caller that ignores the return value announces every shot as taken while the
    disk is full, and the gap is only noticed later by counting files -- which is
    exactly how a set of migration baselines came back missing its most important
    scenes with nothing in the log to say so.

    Parameters
    ----------
    image : QtGui.QImage
        The grabbed image.
    path : pathlib.Path
        Destination PNG.

    Raises
    ------
    RuntimeError
        If the image is null, or the write failed, or the file did not appear
        with a plausible size.
    """
    if image.isNull():
        raise RuntimeError(f"refusing to write a null image to {path}")
    if not image.save(str(path)):
        raise RuntimeError(
            f"QImage.save failed for {path} (disk full, or the directory is not "
            f"writable); {image.width()}x{image.height()}"
        )
    if not path.exists() or path.stat().st_size < 1024:
        raise RuntimeError(
            f"{path} is missing or implausibly small after save "
            f"({path.stat().st_size if path.exists() else 'absent'} bytes)"
        )
