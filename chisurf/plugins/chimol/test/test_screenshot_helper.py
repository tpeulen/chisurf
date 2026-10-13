"""The screenshot helper itself, since a broken one fails silently as a blank image.

Every other visual check in this plugin depends on it: if a grab quietly
returns nothing, the saved PNG is a uniform rectangle, and that reads as "the
renderer is broken" rather than "the camera was". So the helper asserts its own
preconditions and these tests hold it to them -- on the toolkit-free window
(the offscreen canvas ChiSurf embeds), with T4 lysozyme loaded.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("wgpu")

from native_window import PDB_148L, NativeWindow  # noqa: E402

from chisurf.plugins.chimol.test import screenshot as shot  # noqa: E402


@pytest.fixture(scope="module")
def window():
    """A 640x480 window with 148L, its view fitted."""
    win = NativeWindow(size=(640, 480))
    win.load_structure_from_path(PDB_148L)
    win.do("orient")
    yield win
    win.close()


def test_the_view_is_grabbed_at_the_canvas_size_and_shows_the_molecule(window):
    image = shot.grab_view(window)
    assert image.dtype == np.uint8 and image.ndim == 3 and image.shape[2] == 3
    height, width = image.shape[:2]
    # In physical pixels: the canvas may render at a device pixel ratio.
    ratio = width / 640.0
    assert ratio >= 1.0 and abs(height - 480 * ratio) <= 1
    assert image.std() > 5.0, "a uniform view: the molecule is not in the grab"


def test_the_window_grab_carries_the_chrome_the_bare_view_does_not(window):
    """`grab_window` is what the window shows; `grab_view` alone is the molecule."""
    full = shot.grab_window(window).astype(int)
    bare = shot.grab_view(window, chrome=False).astype(int)
    assert full.shape == bare.shape
    # The menu bar is drawn along the top of the frame; the bare scene has none.
    top = slice(0, max(full.shape[0] // 40, 4))
    assert np.abs(full[top] - bare[top]).sum() > 0, "the chrome did not make it into the grab"


def test_the_same_target_works_as_window_app_viewer_or_renderer(window):
    for target in (window, window.app, window.viewer, window.renderer):
        assert shot.renderer_of(target) is window.renderer


def test_grabbing_something_that_cannot_render_says_so():
    """A thing with no renderer is not a 3-D view, and pretending otherwise hides a mistake."""
    with pytest.raises(RuntimeError, match="no self-rendering"):
        shot.grab_view(object())


def test_a_uniform_or_empty_image_is_refused(tmp_path):
    with pytest.raises(RuntimeError, match="uniform"):
        shot.save_png(np.zeros((40, 60, 3), np.uint8), tmp_path / "blank.png")
    with pytest.raises(RuntimeError, match="not a frame"):
        shot.save_png(np.zeros((0, 0, 3), np.uint8), tmp_path / "empty.png")


def test_a_strip_of_a_viewport_is_refused():
    win = NativeWindow(size=(1280, 90))
    try:
        with pytest.raises(RuntimeError):
            shot.assert_view_usable(win)
    finally:
        win.close()


def test_shoot_writes_both_images(window, tmp_path):
    written = shot.shoot(window, "probe", directory=tmp_path, size=(640, 480))
    assert set(written) == {"window", "view"}
    for path in written.values():
        assert path.is_file() and path.stat().st_size > 1024
