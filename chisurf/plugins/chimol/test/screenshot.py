"""Take real screenshots of the viewer, including the 3-D view, without a window.

Why this exists
---------------
The project rule is that a GUI change is unfinished until the view has been
rendered and the image *looked at*. ChiMOL's window is the toolkit-free host
(:class:`chimol.hosts.native.app.ChimolApp`, the viewer ChiSurf embeds): a
``rendercanvas`` surface drawn by WebGPU. Its pixels are the renderer's, so the
screenshot is taken from the renderer:

* :func:`grab_window` -- the frame the window shows (scene, panel, sequence
  strip, menus, prompt): the offscreen canvas' ``draw`` hands it back, and a
  canvas with a real window re-renders it offscreen
  (``CanvasRenderer.grab_image(chrome=True)``);
* :func:`grab_view` -- the 3-D view alone (``grab_image(chrome=False)``), or
  with the chrome composited (``chrome=True``).

No window server, no GL context and no GUI toolkit: it runs over ssh and in CI
wherever a WebGPU adapter exists.

What this replaced, because it cost a rule its teeth once already: the helper
was written for a ``QOpenGLWidget`` and captured with ``grabFramebuffer()``.
When the renderer became a plain ``QWidget`` presenting a WebGPU surface the
search for the GL widget found nothing, the grab fell through to
``QWidget.grab()``, and **every chimol screenshot was a blank** -- silently.
So a grab here never falls back to "something": no renderer is an error, and
:func:`save_png` refuses an empty or uniform image rather than writing one.

Use
---
    from native_window import NativeWindow
    from chisurf.plugins.chimol.test.screenshot import shoot

    win = NativeWindow(size=(1280, 860))
    win.load_structure_from_path(PDB_148L)
    paths = shoot(win, "t4l", area="all")
"""

from __future__ import annotations

import pathlib

import numpy as np

__all__ = [
    "assert_view_usable",
    "grab_view",
    "grab_window",
    "renderer_of",
    "save_png",
    "shoot",
]


def renderer_of(target):
    """The renderer behind *target*: a window, an app, a viewer or the renderer itself.

    Found by capability -- ``grab_image`` -- rather than by class. The class was
    the mistake this module once made: a hard-coded widget type that stopped
    matching, and nothing said so.

    Raises
    ------
    RuntimeError
        If nothing under *target* can photograph itself.
    """
    seen = target
    for _ in range(3):
        if callable(getattr(seen, "grab_image", None)):
            return seen
        nxt = getattr(seen, "renderer", None)
        if nxt is None or nxt is seen:
            break
        seen = nxt
    raise RuntimeError(f"no self-rendering 3-D view under {type(target).__name__}")


def _app_of(target):
    """The object whose ``draw_frame`` renders the window (an app, a window or the canvas)."""
    for candidate in (target, getattr(target, "app", None), renderer_of(target)):
        if candidate is not None and callable(getattr(candidate, "draw_frame", None)):
            return candidate
    return None


def _rgb(image) -> np.ndarray:
    """``(h, w, 3)`` uint8 from what a renderer returns, or an error naming what came back."""
    if image is None:
        raise RuntimeError("the renderer returned no frame")
    rgb = np.ascontiguousarray(np.asarray(image)[..., :3], dtype=np.uint8)
    if rgb.ndim != 3 or rgb.shape[0] < 1 or rgb.shape[1] < 1:
        raise RuntimeError(f"the renderer returned {rgb.shape}, which is not a frame")
    return rgb


def _resize(target, size) -> None:
    if size is not None:
        renderer_of(target).resize(int(size[0]), int(size[1]))


def grab_window(target, size: tuple[int, int] | None = None, frames: int = 2) -> np.ndarray:
    """Grab the whole window: the 3-D view with the chrome over it.

    Parameters
    ----------
    target : NativeWindow, ChimolApp, Viewer or CanvasView
        What to photograph.
    size : tuple of int, optional
        Resize the canvas (logical pixels) before grabbing.
    frames : int
        Frames drawn first, so what a frame computes (layout, readouts) is
        current -- the first frame after a change can still show the moment before.

    Returns
    -------
    numpy.ndarray
        ``(h, w, 3)`` uint8.
    """
    _resize(target, size)
    app = _app_of(target)
    image = None
    if app is not None:
        for _ in range(max(1, int(frames))):
            image = app.draw_frame()
    if image is None:
        # A canvas with a real window presents rather than returns its frame.
        image = renderer_of(target).grab_image(chrome=True)
    return _rgb(image)


def grab_view(target, size: tuple[int, int] | None = None, chrome: bool = False) -> np.ndarray:
    """Grab the 3-D view, re-rendered offscreen by the renderer.

    Parameters
    ----------
    target : NativeWindow, ChimolApp, Viewer or CanvasView
        What to photograph.
    size : tuple of int, optional
        Resize the canvas before grabbing.
    chrome : bool
        Composite the panel, sequence strip and labels too (what the window
        shows); ``False`` is the bare molecule.

    Returns
    -------
    numpy.ndarray
        ``(h, w, 3)`` uint8.
    """
    _resize(target, size)
    renderer = renderer_of(target)
    app = _app_of(target)
    if app is not None:
        app.draw_frame()  # the scene is built and laid out before the re-render
    return _rgb(renderer.grab_image(chrome=bool(chrome)))


def assert_view_usable(
    target,
    *,
    min_px: int = 200,
    min_aspect: float = 0.35,
) -> tuple[int, int]:
    """Refuse a 3-D viewport too small or too misshapen to judge anything from.

    A strip of a viewport grabs fine and every assertion taken against it passes
    and means nothing: the molecule is a speck. The shape is checked as well as
    the size, because a strip is comfortably wider than any pixel floor.

    Parameters
    ----------
    target : NativeWindow, ChimolApp, Viewer or CanvasView
        What will be photographed.
    min_px : int
        Smallest acceptable width and height, in logical pixels.
    min_aspect : float
        Smallest acceptable ratio of the short side to the long side.

    Returns
    -------
    tuple of int
        The usable ``(width, height)``.

    Raises
    ------
    RuntimeError
        If the viewport is too small or too extreme to produce a reviewable image.
    """
    renderer = renderer_of(target)
    w, h = int(renderer.width()), int(renderer.height())
    if w < min_px or h < min_px:
        raise RuntimeError(
            f"3-D viewport is {w}x{h}; needs at least {min_px}x{min_px}. Give the "
            f"window a size (NativeWindow(size=...), or size= here)."
        )
    aspect = min(w, h) / max(w, h)
    if aspect < min_aspect:
        raise RuntimeError(
            f"3-D viewport is {w}x{h} (aspect {aspect:.2f} < {min_aspect}); that "
            f"is a strip, not a view. The molecule will be a speck and the image "
            f"is not reviewable."
        )
    return w, h


def save_png(image, path: str | pathlib.Path) -> pathlib.Path:
    """Write *image* to *path*, raising rather than reporting a silent success.

    A blank grab saved as a PNG reads as "the renderer draws nothing" when only
    the camera failed, so an empty or perfectly uniform image is refused.

    Parameters
    ----------
    image : numpy.ndarray
        ``(h, w, 3)`` or ``(h, w, 4)`` uint8.
    path : str or pathlib.Path
        Destination PNG.

    Returns
    -------
    pathlib.Path

    Raises
    ------
    RuntimeError
        If the image is empty or uniform, or the file did not appear with a
        plausible size.
    """
    from PIL import Image

    rgb = _rgb(image)
    if int(rgb.max()) == int(rgb.min()):
        raise RuntimeError(f"refusing to write a uniform {rgb.shape[1]}x{rgb.shape[0]} image to {path}")
    path = pathlib.Path(path)
    Image.fromarray(rgb, "RGB").save(path)
    if not path.exists() or path.stat().st_size < 1024:
        raise RuntimeError(
            f"{path} is missing or implausibly small after save "
            f"({path.stat().st_size if path.exists() else 'absent'} bytes)"
        )
    return path


def shoot(
    target,
    name: str,
    *,
    directory: str | pathlib.Path = "renders",
    size: tuple[int, int] | None = (1280, 860),
    area: str = "all",
) -> dict[str, pathlib.Path]:
    """Save screenshots and return where they went.

    Parameters
    ----------
    target : NativeWindow, ChimolApp, Viewer or CanvasView
        What to photograph.
    name : str
        Stem of the file name.
    directory : str or pathlib.Path
        Where to write.
    size : tuple of int, optional
        Canvas size to use.
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
        written["window"] = save_png(grab_window(target, size), out / f"{name}_window.png")
    if area in ("all", "view"):
        written["view"] = save_png(grab_view(target, size), out / f"{name}_view.png")
    return written
