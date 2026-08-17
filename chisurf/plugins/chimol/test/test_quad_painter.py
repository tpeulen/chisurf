"""The chrome's quads land where the panel asked for them.

``QuadPainter`` is where the port can go wrong quietly. It produces vertices,
so a mistake does not raise -- it moves a glyph half a row, drops a menu's
clipping, or fills a gradient with its first stop. None of that fails a
construction test, and at 10 pt none of it is obvious in a screenshot either.

So the geometry is asserted directly, and the whole panel is rasterised on the
CPU (:mod:`chisurf.plugins.chimol.test.quad_raster`) to check that nothing
silently went missing. Neither needs a GPU, which is the point: the chrome is
meant to run wherever WebGPU does, and its tests should not need the device.
"""
from __future__ import annotations

import numpy as np
import pytest

from chimol.cmtk.painter import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    ALIGN_VCENTER,
)
from chisurf.plugins.chimol.test import chrome_baseline, quad_raster


def _painter():
    """Return a fresh :class:`QuadPainter`, skipping if the atlas is unbaked."""
    from chimol.cmtk.font import load_atlas
    from chimol.cmtk.quad_painter import QuadPainter

    try:
        atlas = load_atlas()
    except FileNotFoundError as exc:
        pytest.skip(str(exc))
    return QuadPainter(atlas), atlas


def test_a_filled_rectangle_is_exactly_one_quad():
    """No hidden geometry: a fill is six vertices and nothing else."""
    p, _atlas = _painter()
    p.fill_rect(10, 20, 30, 40, (255, 0, 0))
    assert p.vertex_count == 6


def test_a_stroked_rectangle_is_a_fill_plus_four_edges():
    """A stroke is five quads, and without a fill it is four."""
    p, _atlas = _painter()
    p.stroke_rect(0, 0, 20, 10, (255, 255, 255), fill=(0, 0, 0))
    assert p.vertex_count == 5 * 6
    p.clear()
    p.stroke_rect(0, 0, 20, 10, (255, 255, 255))
    assert p.vertex_count == 4 * 6


def test_text_is_one_quad_per_glyph():
    """Every character contributes a quad; the empty string contributes none."""
    p, _atlas = _painter()
    p.text(0, 0, 200, 20, ALIGN_LEFT, "abcd", (255, 255, 255))
    assert p.vertex_count == 4 * 6
    p.clear()
    p.text(0, 0, 200, 20, ALIGN_LEFT, "", (255, 255, 255))
    assert p.vertex_count == 0


def test_a_filled_triangle_is_exactly_three_vertices_at_its_corners():
    """No expansion: a triangle is its own three corners, unlike a rect's four."""
    p, _atlas = _painter()
    p.fill_triangle((0.0, 0.0), (10.0, 0.0), (5.0, 10.0), (255, 0, 0))
    assert p.vertex_count == 3
    positions = p.vertices()[:, 0:2]
    np.testing.assert_allclose(
        positions, [[0.0, 0.0], [10.0, 0.0], [5.0, 10.0]]
    )


def test_a_triangle_coexists_with_rects_in_one_vertex_buffer():
    """Triangles ride alongside the rect-derived quads, not instead of them."""
    p, _atlas = _painter()
    p.fill_rect(0, 0, 10, 10, (255, 255, 255))
    p.fill_triangle((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (0, 255, 0))
    assert p.vertex_count == 6 + 3
    p.clear()
    assert p.vertex_count == 0


def test_a_zero_sized_rectangle_emits_nothing():
    """Degenerate boxes are dropped rather than sent as zero-area quads."""
    p, _atlas = _painter()
    p.fill_rect(5, 5, 0, 10, (255, 255, 255))
    p.fill_rect(5, 5, 10, 0, (255, 255, 255))
    assert p.vertex_count == 0


@pytest.mark.parametrize(
    "align, expected",
    [
        (ALIGN_LEFT, "left"),
        (ALIGN_RIGHT, "right"),
        (ALIGN_CENTER, "centre"),
    ],
)
def test_horizontal_alignment_places_the_string(align, expected):
    """Left, right and centre put the run where the box says.

    The panel right-aligns the mouse-mode labels and centres every button
    glyph, so an alignment that silently fell back to left would put ``Buttons``
    hard against its first value and knock every button's letter off-centre --
    which is a layout the eye reads as "slightly wrong" and never as a bug.
    """
    p, atlas = _painter()
    box_x, box_w, string = 100.0, 200.0, "abcd"
    p.text(box_x, 0, box_w, 20, align | ALIGN_VCENTER, string, (255, 255, 255))
    verts = p.vertices()
    left = float(verts[:, 0].min())
    right = float(verts[:, 0].max())
    run = atlas.advance(string)

    # A glyph's quad is its atlas *cell*, which is the advance plus a measured
    # blank margin on each side -- so the run's outer edges sit ``pad`` beyond
    # where the text itself starts and ends. That margin is the reason the
    # neighbouring glyph's ink cannot bleed in; see the baker.
    margin = atlas.pad * atlas.render_scale
    if expected == "left":
        assert left == pytest.approx(box_x - margin, abs=0.01)
    elif expected == "right":
        assert right == pytest.approx(box_x + box_w + margin, abs=0.01)
    else:
        centre = (left + right) / 2.0
        assert centre == pytest.approx(box_x + box_w / 2.0, abs=1.5)
    assert right - left > run * 0.5


def test_nested_clips_intersect_rather_than_replace():
    """A clip inside a clip is the overlap of the two.

    Menus are the only caller and they nest one deep today, but a clip that
    *replaced* its parent would let a submenu draw outside the box its parent
    is scrolling inside -- a bug that only appears with a long enough menu.
    """
    p, _atlas = _painter()
    p.push_clip(0, 0, 100, 100)
    p.push_clip(50, 50, 100, 100)
    p.fill_rect(0, 0, 200, 200, (255, 255, 255))
    box = p.vertices()[0, 8:12]
    assert tuple(float(v) for v in box) == (50.0, 50.0, 100.0, 100.0)
    p.pop_clip()
    p.pop_clip()


def test_popping_every_clip_restores_an_unclipped_painter():
    """After the last pop, quads carry the wide-open box again."""
    p, _atlas = _painter()
    p.push_clip(10, 10, 20, 20)
    p.pop_clip()
    p.fill_rect(0, 0, 5, 5, (255, 255, 255))
    box = p.vertices()[0, 8:12]
    assert box[0] < -1000.0 and box[2] > 1000.0


def test_the_gradient_varies_across_the_quad():
    """Adjacent stops give a quad whose left and right corners differ.

    The ``C`` button's rainbow is what says the button colours things; filled
    with any single stop it still looks like a button.
    """
    p, _atlas = _painter()
    p.gradient_rect(0, 0, 40, 10, [(255, 0, 0), (0, 0, 255)])
    verts = p.vertices()
    first_quad = verts[:6]
    assert not np.allclose(first_quad[0, 4:8], first_quad[1, 4:8])


def test_a_five_stop_gradient_emits_four_spans():
    """One quad per adjacent pair, plus the four edge lines when asked."""
    p, _atlas = _painter()
    p.gradient_rect(0, 0, 40, 10, [(0, 0, 0)] * 5)
    assert p.vertex_count == 4 * 6
    p.clear()
    p.gradient_rect(0, 0, 40, 10, [(0, 0, 0)] * 5, edge=(255, 255, 255))
    assert p.vertex_count == (4 + 4) * 6


@pytest.mark.parametrize("state", chrome_baseline.STATES)
def test_every_region_of_the_panel_draws_something(state):
    """Rasterised, each state paints ink where its regions are.

    A coarse check on purpose. It is not asserting appearance -- that is judged
    by looking -- but it catches the failure this port actually risks: a whole
    region emitting no quads because a call was dropped in translation, which
    leaves a plausible-looking panel with its sequence strip or its
    mouse-mode block simply absent.
    """
    from PIL import Image

    from chimol.chrome.gui import InternalGui

    p, atlas = _painter()
    width, height = chrome_baseline.SIZE
    gui = InternalGui()
    chrome_baseline._apply_state(gui, state, width, height)
    gui.paint(p)

    verts = p.vertices()
    assert len(verts) > 0, f"{state} produced no geometry at all"

    ink = np.array(Image.open(atlas.image_path).convert("RGBA"))[..., 3] / 255.0
    image = quad_raster.rasterise(verts, width, height, ink)
    alpha = image[..., 3]

    column = alpha[:, int(width - gui.column_width):]
    assert column.max() > 0, f"{state}: the panel column is empty"

    if gui.sequence_visible and gui.sequences:
        strip = alpha[: int(gui.sequence_height()), : int(width - gui.column_width)]
        assert strip.max() > 0, f"{state}: the sequence strip is empty"

    block = gui.block_rect
    band = alpha[int(block.y):int(block.y + block.h),
                 int(block.x):int(block.x + block.w)]
    assert band.max() > 0, f"{state}: the mouse-mode block is empty"
