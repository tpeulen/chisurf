"""Take real screenshots of the viewer, including the 3-D view, without a window.

Why this exists
---------------
The project rule is that a GUI change is unfinished until the widget has been
rendered and the image *looked at*. For most widgets ``widget.grab()`` under
``QT_QPA_PLATFORM=offscreen`` is enough. The 3-D view is not most widgets: it is
a ``QOpenGLWidget``, and the offscreen platform plugin **cannot create an
OpenGL context at all** ("This plugin does not support
createPlatformOpenGLContext"). So the one part of ChiMOL where appearance
matters most was the one part that could not be photographed, and judging it
meant either the ray tracer -- a different renderer, with no materials and no
transparency -- or asking a human to look.

The way out is not the offscreen plugin but the ordinary one, with
``WA_DontShowOnScreen``. The window is *realised* -- it gets a backing store and
a real GL context, so everything renders exactly as it would -- and it is never
mapped onto the display. Nothing appears, nothing steals focus, and
``grabFramebuffer`` returns what the graphics card actually drew.

Consequences worth knowing:

* it needs a window server, so it runs on a logged-in macOS session and *not*
  over a bare ssh or in CI. `QT_QPA_PLATFORM` must **not** be ``offscreen``;
  this module refuses rather than silently producing a black image;
* the GL widget is grabbed separately from the rest of the window and pasted
  in. ``QWidget.grab()`` does not capture a child GL surface, which is what
  makes a whole-window grab of a 3-D app come out with a hole in it.

Use
---
    from chisurf.plugins.chimol.test.screenshot import shoot

    paths = shoot(window, "npc_demo", area="all")
"""
from __future__ import annotations

import os
import pathlib

from qtpy import QtCore, QtGui, QtWidgets

__all__ = ["ensure_app", "grab_window", "grab_gl", "shoot", "OFFSCREEN_REFUSED"]

#: Raised as a message, not an exception type, so a caller can decide.
OFFSCREEN_REFUSED = (
    "the offscreen Qt platform cannot create an OpenGL context, so the 3-D view "
    "would come out black -- unset QT_QPA_PLATFORM and run on a logged-in session"
)


def ensure_app() -> QtWidgets.QApplication:
    """Return the application, refusing the offscreen platform.

    Returns
    -------
    QtWidgets.QApplication

    Raises
    ------
    RuntimeError
        If ``QT_QPA_PLATFORM`` is ``offscreen``: a screenshot taken there shows
        an empty 3-D view, which is worse than no screenshot because it looks
        like a rendering bug.
    """
    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        raise RuntimeError(OFFSCREEN_REFUSED)
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


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
    """Grab the 3-D view alone, straight from the framebuffer.

    Parameters
    ----------
    widget : QtWidgets.QWidget
        A ``QOpenGLWidget`` or something containing one.
    size : tuple of int, optional
        Resize before grabbing.

    Returns
    -------
    QtGui.QImage

    Raises
    ------
    RuntimeError
        If there is no GL widget, or the context never became valid -- a null
        image saved as a PNG is a black rectangle that reads as a bug in the
        thing being photographed.
    """
    app = ensure_app()
    targets = _gl_children(widget)
    if not targets:
        raise RuntimeError("no QOpenGLWidget to grab")
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
    targets = _gl_children(widget)
    if not targets:
        raise RuntimeError("no QOpenGLWidget to measure")
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

    shot = widget.grab().toImage()
    painter = QtGui.QPainter(shot)
    try:
        for gl in _gl_children(widget):
            if not gl.isVisible() or gl.width() <= 0 or gl.height() <= 0:
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
