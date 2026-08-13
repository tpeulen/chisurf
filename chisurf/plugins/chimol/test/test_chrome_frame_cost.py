"""What one frame of chrome costs, and the two caches that make it cost nothing.

Why this exists
---------------
The chrome is immediate mode, and two separate pieces of work follow from that.
The **CPU** half builds ~2,100 quads out of Python floats and converts them to
float32; the **GPU** half allocates a vertex buffer, two uniform buffers, two
bind groups and a texture view, and uploads 150,000 floats. Both used to happen
every frame.

``canvas_base._chrome_quads`` already fixed the first for the common case, by
reusing the vertex array while ``chrome_fingerprint`` has not moved. What that
left behind:

* the vertex *build* still cost 4.8 ms whenever the chrome did change -- which
  is every hover, every keystroke and every menu move, i.e. precisely while
  somebody is using the interface;
* the GPU half ran **regardless**, because ``_draw_ui`` was handed the cached
  array and rebuilt its buffers from it anyway.

These tests hold both fixes in place. They are not timing tests -- a wall clock
in CI measures the machine, not the code -- so they assert the two things that
*cause* the cost instead: how many floats Python has to produce per quad, and
how many GPU resources a repeated frame allocates.
"""
from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.cmtk import quad_painter as qp
from chisurf.plugins.chimol.chimol.cmtk.quad_painter import QuadPainter


# --------------------------------------------------------------------------
# The CPU half: four corners in, six vertices out
# --------------------------------------------------------------------------
def test_a_quad_costs_sixteen_floats_in_python_and_six_vertices_on_the_gpu():
    """The duplication happens in NumPy, not in the interpreter.

    Emitting the six vertices directly is 72 floats a quad, and two thirds of
    them are redundant: four vertices are copies of two, the colour and the
    clip box are the same at every corner, and each axis has two values. The
    record carries each distinct number once -- and each one is a ``PyFloat``
    that has to be tuple-built, appended and converted, so the count *is* the
    cost.
    """
    painter = QuadPainter(scale=1.0)
    painter.fill_rect(0.0, 0.0, 10.0, 10.0, (255, 255, 255, 255))
    assert len(painter._data) == qp.FLOATS_PER_QUAD == 16
    assert painter.vertices().shape == (qp.VERTICES_PER_QUAD, qp.FLOATS_PER_VERTEX)
    assert painter.vertex_count == qp.VERTICES_PER_QUAD


def test_the_six_vertices_are_the_two_triangles_in_the_winding_order():
    """Top-left, top-right, bottom-right; then top-left, bottom-right, bottom-left.

    The pipeline was built for this winding. Reordering it turns the panel
    inside out under back-face culling, which is a whole-chrome failure from a
    one-line change, so the order is asserted rather than commented.
    """
    painter = QuadPainter(scale=1.0)
    painter.fill_rect(10.0, 20.0, 30.0, 40.0, (255, 128, 0, 255))
    corners = painter.vertices()[:, :2]
    assert [tuple(one) for one in corners] == [
        (10.0, 20.0), (40.0, 20.0), (40.0, 60.0),
        (10.0, 20.0), (40.0, 60.0), (10.0, 60.0),
    ]


def test_a_gradient_still_carries_a_colour_per_corner():
    """The one caller that does not use the single-colour fast path."""
    painter = QuadPainter(scale=1.0)
    painter.gradient_rect(0.0, 0.0, 40.0, 10.0, [(255, 0, 0), (0, 0, 255)])
    colours = {tuple(one) for one in painter.vertices()[:, 4:8]}
    assert len(colours) == 2


def test_the_device_scale_is_applied_once_per_corner_and_to_the_clip():
    """A ratio applied twice puts the panel off the edge of the window."""
    painter = QuadPainter(scale=2.0)
    painter.push_clip(0.0, 0.0, 100.0, 50.0)
    painter.fill_rect(10.0, 20.0, 30.0, 40.0, (255, 255, 255, 255))
    painter.pop_clip()
    vertices = painter.vertices()
    assert vertices[0, 0] == pytest.approx(20.0)
    assert vertices[0, 1] == pytest.approx(40.0)
    assert tuple(vertices[0, 8:12]) == pytest.approx((0.0, 0.0, 200.0, 100.0))


def test_popping_the_last_clip_restores_the_unclipped_box():
    """The scaled clip is cached, so the stack has to keep it in step."""
    painter = QuadPainter(scale=1.0)
    painter.push_clip(0.0, 0.0, 10.0, 10.0)
    painter.pop_clip()
    painter.fill_rect(0.0, 0.0, 4.0, 4.0, (255, 255, 255, 255))
    assert tuple(painter.vertices()[0, 8:12]) == pytest.approx(qp._NO_CLIP)


def test_clear_resets_the_clip_as_well_as_the_vertices():
    """A painter reused for the next frame must not inherit a clip box."""
    painter = QuadPainter(scale=1.0)
    painter.push_clip(1.0, 2.0, 3.0, 4.0)
    painter.clear()
    painter.fill_rect(0.0, 0.0, 4.0, 4.0, (255, 255, 255, 255))
    assert tuple(painter.vertices()[0, 8:12]) == pytest.approx(qp._NO_CLIP)


def test_glyphs_go_through_the_same_geometry_as_rectangles():
    """The text loop is emitted inline, so it is the one that can drift.

    Same four corners, same winding, same clip box -- checked against a
    rectangle drawn over the same span rather than against literals, because
    what matters is that the two paths agree.
    """
    painter = QuadPainter(scale=1.0)
    painter.text(0.0, 0.0, 200.0, 20.0, 0, "ab", (255, 255, 255, 255))
    glyphs = painter.vertices()
    assert glyphs.shape[0] == 2 * qp.VERTICES_PER_QUAD
    for start in (0, qp.VERTICES_PER_QUAD):
        one = glyphs[start:start + qp.VERTICES_PER_QUAD]
        assert one[0, 0] == one[3, 0] == one[5, 0]      # left edge
        assert one[1, 0] == one[2, 0] == one[4, 0]      # right edge
        assert one[0, 1] == one[1, 1] == one[3, 1]      # top edge


def test_an_empty_painter_still_returns_the_right_shape():
    """A frame with no chrome must not be a special case downstream."""
    assert QuadPainter(scale=1.0).vertices().shape == (0, qp.FLOATS_PER_VERTEX)


def test_a_zero_sized_quad_is_dropped_on_both_paths():
    """Collapsed rows and empty labels are normal, not errors."""
    painter = QuadPainter(scale=1.0)
    painter.fill_rect(0.0, 0.0, 0.0, 10.0, (255, 255, 255, 255))
    painter.fill_rect(0.0, 0.0, 10.0, -1.0, (255, 255, 255, 255))
    painter._quad(0.0, 0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 0.0,
                  ((1.0, 1.0, 1.0, 1.0),) * 4)
    assert painter.vertices().shape == (0, qp.FLOATS_PER_VERTEX)


# --------------------------------------------------------------------------
# The GPU half: a repeated frame allocates nothing
# --------------------------------------------------------------------------
class _Recorder:
    """A stand-in for the wgpu device that counts what a frame allocates."""

    def __init__(self) -> None:
        self.buffers = 0
        self.bind_groups = 0
        self.queue = self

    def create_buffer_with_data(self, data, usage):
        """Count a buffer and return something with a size."""
        self.buffers += 1
        return type("Buffer", (), {"size": int(np.asarray(data).nbytes)})()

    def create_bind_group(self, layout, entries):
        """Count a bind group."""
        self.bind_groups += 1
        return object()


class _Pass:
    """A render pass that records the draw calls made into it."""

    def __init__(self) -> None:
        self.draws: list[int] = []

    def set_pipeline(self, pipeline) -> None:
        """Ignored."""

    def set_bind_group(self, index, group) -> None:
        """Ignored."""

    def set_vertex_buffer(self, index, buffer) -> None:
        """Ignored."""

    def draw(self, count, instances, first, base) -> None:
        """Record the vertex count."""
        self.draws.append(count)


class _Texture:
    """A texture whose view is free to make."""

    def create_view(self):
        """Return anything; the recorder does not inspect it."""
        return object()


class _Backend:
    """The smallest object ``_draw_ui`` will run against.

    A real device is not needed to test a cache: what is being asserted is how
    many times ``_draw_ui`` reaches for one.
    """

    UNIFORM_FLOATS = 4 * 16 + 7 * 4

    def __init__(self) -> None:
        from chisurf.plugins.chimol.chimol.renderer.frame_stats import FrameStats

        self.device = _Recorder()
        #: The real backend always has one; `_draw_ui` counts into it.
        self.stats = FrameStats()
        self.width = 800
        self.height = 600
        self._wgpu = type("W", (), {"BufferUsage": type(
            "U", (), {"VERTEX": 1, "UNIFORM": 2})})()
        self._ui_atlas_size = (512, 512)
        self._ui_layout = object()
        self._ui_sampler = object()
        self._bind_layout = object()
        self._ui_frame_cache = None
        self._texture = _Texture()

    def _build_ui_pipeline(self):
        """The pipeline is built once and is not what this measures."""
        return object()

    def upload_ui_atlas(self):
        """The same texture every frame, as the real one keeps."""
        return self._texture

    def _flush_glyph_cache(self, texture) -> bool:
        """No new glyphs."""
        return False


@pytest.fixture()
def backend():
    """A stub backend carrying the real ``_draw_ui``."""
    from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WgpuMeshRenderer

    stub = _Backend()
    stub._draw_ui = WgpuMeshRenderer._draw_ui.__get__(stub, _Backend)
    return stub


def _frame(backend, vertices):
    """Draw one chrome frame; returns the pass it drew into."""
    render_pass = _Pass()
    backend._draw_ui(render_pass, vertices)
    return render_pass


def test_the_first_chrome_frame_allocates_its_buffers(backend):
    """A vertex buffer, two uniform buffers and two bind groups."""
    vertices = np.zeros((12, 12), dtype=np.float32)
    _frame(backend, vertices)
    assert backend.device.buffers == 3
    assert backend.device.bind_groups == 2


def test_an_unchanged_chrome_frame_allocates_nothing_and_still_draws(backend):
    """The point of the whole exercise.

    ``_chrome_quads`` returns the *same array object* while the fingerprint has
    not moved, so identity is the key -- and the array is held, so a freed one
    cannot land at the same address and be mistaken for it.
    """
    vertices = np.zeros((12, 12), dtype=np.float32)
    _frame(backend, vertices)
    before = (backend.device.buffers, backend.device.bind_groups)
    for _ in range(10):
        render_pass = _frame(backend, vertices)
        assert render_pass.draws == [12]
    assert (backend.device.buffers, backend.device.bind_groups) == before


def test_changed_chrome_rebuilds(backend):
    """A different array is a different chrome, whatever it contains."""
    _frame(backend, np.zeros((12, 12), dtype=np.float32))
    before = backend.device.buffers
    _frame(backend, np.zeros((12, 12), dtype=np.float32))
    assert backend.device.buffers > before


def test_a_resize_rebuilds_even_though_the_vertices_are_the_same(backend):
    """The uniform block carries the viewport, so it is part of the key.

    Missing this would be invisible until the window was resized without the
    panel changing -- at which point the chrome would be drawn against the old
    viewport and land in the wrong half of the window.
    """
    vertices = np.zeros((12, 12), dtype=np.float32)
    _frame(backend, vertices)
    before = backend.device.buffers
    backend.width = 1024
    _frame(backend, vertices)
    assert backend.device.buffers > before


def test_a_newly_rasterised_glyph_rebuilds(backend):
    """The texels behind an unchanged bind group moved; do not trust the cache."""
    vertices = np.zeros((12, 12), dtype=np.float32)
    _frame(backend, vertices)
    before = backend.device.buffers
    backend._flush_glyph_cache = lambda texture: True
    _frame(backend, vertices)
    assert backend.device.buffers > before
