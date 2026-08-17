"""A selection is visible, is the right size, and is built outside the widget.

Three separate claims, and the third is the one that decides whether a browser
can select anything:

* the **marker** is PyMOL's indicator -- three concentric squares -- and not a
  sphere. It was drawn by the impostor pipeline, which reads only the size, so a
  selection came out as a scatter of shaded pink dots over the molecule. That is
  what "the selection does not show" looked like.
* the **size** is in pixels and stays the same on screen at any depth, which is
  what an indicator is for.
* the **geometry** is built by :mod:`chimol.render.markers`, an engine module
  with no toolkit, so the Qt widget and the browser cannot disagree about what a
  selection looks like.

The rendering half needs a GPU and skips without one; everything else is
arithmetic.
"""
from __future__ import annotations

import numpy as np
import pytest

from chimol.render import markers
from chimol.render.pack import pack_scene
from chimol.render.scene import Scene
from chimol.core.view_state import pack_view_state


# ── the geometry ─────────────────────────────────────────────────────────
def test_markers_carry_the_glyph_that_routes_them():
    objects = markers.selection_markers([[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]], 6.0)
    assert len(objects) == 1
    geometry = objects[0].geometry
    assert geometry.kind == "points"
    assert geometry.meta["glyph"] == "selection"
    assert geometry.meta["size"] == 6.0
    assert geometry.meta["world_radius"] is False, (
        "a world radius makes the marker grow with the camera; it is pixels"
    )
    assert objects[0].render_mode == "overlay"
    assert np.allclose(geometry.colors[0], markers.SELECTION_COLOR)


def test_nothing_selected_builds_nothing():
    assert markers.selection_markers([], 6.0) == []


def test_the_width_follows_pymols_clamped_rule():
    # Zoomed far out: the marker would be sub-pixel, so the floor applies.
    wide = markers.screen_vertex_scale(30.0, 10_000.0, 800)
    assert markers.marker_width(wide) == markers.DEFAULT_WIDTH
    # Close in: it would be huge, so the ceiling applies.
    tight = markers.screen_vertex_scale(30.0, 1.0, 800)
    assert markers.marker_width(tight) == markers.DEFAULT_WIDTH_MAX
    # And in between it is the rule itself.
    middle = markers.screen_vertex_scale(30.0, 100.0, 800)
    assert markers.DEFAULT_WIDTH < markers.marker_width(middle) < markers.DEFAULT_WIDTH_MAX


def test_no_camera_yet_gives_the_widest_marker():
    """Zero pixels is a selection that silently did not draw."""
    assert markers.marker_width(0.0) == markers.DEFAULT_WIDTH_MAX


def test_a_strip_column_is_not_an_atom_index():
    """The mapping that is silent when it is wrong."""
    # Four atoms in two residues, numbered from 20 -- the ordinary case for a
    # chain that does not start at one.
    atom_residues = [20, 20, 21, 21, 22]
    residue_numbers = [20, 21, 22]

    mask = markers.atoms_in_columns(atom_residues, residue_numbers, [1])
    assert mask.tolist() == [False, False, True, True, False]

    both = markers.atoms_in_columns(atom_residues, residue_numbers, [0, 2])
    assert both.tolist() == [True, True, False, False, True]

    assert not markers.atoms_in_columns(atom_residues, residue_numbers, []).any()
    assert not markers.atoms_in_columns(atom_residues, residue_numbers, [99]).any()


def test_the_backend_routes_the_glyph_to_the_marker_pipeline():
    from chimol.render.wgpu_backend import WgpuMeshRenderer

    objects = markers.selection_markers([[0.0, 0.0, 0.0]], 6.0)
    packed = pack_scene(Scene(objects=objects, center=(0, 0, 0), radius=1.0))
    assert WgpuMeshRenderer.pipeline_for(packed.objects[0].geometry) == "marker"


def test_a_plain_point_cloud_still_gets_impostors():
    """The routing is by glyph, so nothing else changes pipeline."""
    from chimol.render.scene import Geometry, SceneObject
    from chimol.render.wgpu_backend import WgpuMeshRenderer

    geometry = Geometry(
        kind="points",
        positions=np.zeros((3, 3), dtype=np.float32),
        colors=np.ones((3, 4), dtype=np.float32),
    )
    packed = pack_scene(
        Scene(objects=[SceneObject(id="dots", geometry=geometry)],
              center=(0, 0, 0), radius=1.0)
    )
    assert WgpuMeshRenderer.pipeline_for(packed.objects[0].geometry) == "impostor"


# ── the picture ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def renderer():
    """An offscreen renderer, or a skip where there is no adapter."""
    from chimol.render.wgpu_backend import WgpuMeshRenderer

    try:
        return WgpuMeshRenderer(240, 240)
    except Exception as exc:  # noqa: BLE001 - no GPU on this runner
        pytest.skip(f"no WebGPU adapter: {exc}")


def _frame(renderer, width: float, distance: float = 40.0) -> np.ndarray:
    """Render one marker at the origin and return the image."""
    objects = markers.selection_markers([[0.0, 0.0, 0.0]], width)
    packed = pack_scene(Scene(objects=objects, center=(0, 0, 0), radius=1.0))
    view = pack_view_state(
        rotation=np.eye(3), distance=distance, target=(0.0, 0.0, 0.0),
        near=distance - 10.0, far=distance + 10.0,
    )
    return renderer.render(packed, view, background=(0.0, 0.0, 0.0))


def test_the_marker_draws_three_concentric_bands(renderer):
    """Pink outside, black between, white in the middle -- PyMOL's indicator."""
    frame = _frame(renderer, width=40.0)
    centre = frame[120, 120].astype(int)
    assert centre.min() > 200, f"the core should be white, got {centre}"

    # Along a row through the middle: white core, a dark ring, then the
    # selection colour, then the background.
    row = frame[120].astype(int)
    reddish = np.flatnonzero((row[:, 0] > 150) & (row[:, 2] > 80) & (row[:, 1] < 120))
    assert reddish.size, "no selection-coloured band in the marker"
    dark = np.flatnonzero(row.max(axis=1) < 40)
    inner_dark = dark[(dark > reddish.min()) & (dark < reddish.max())]
    assert inner_dark.size, "no black ring between the pink and the white"


def test_the_marker_is_square_and_not_a_sphere(renderer):
    """A sphere impostor is round and shaded; this is a flat stamp.

    Measured as the corner: a disc of the same width has nothing at 45 degrees
    from the centre where a square has its corner. This is the assertion that
    fails if the glyph is ever routed back to the impostor pipeline.
    """
    frame = _frame(renderer, width=40.0)
    background = frame[10, 10].astype(int)
    # Just inside the corner of a 40 px marker centred at (120, 120).
    corner = frame[120 - 17, 120 - 17].astype(int)
    assert np.abs(corner - background).max() > 40, (
        f"the corner is background, so the glyph is round: {corner}"
    )


def test_the_marker_keeps_its_pixel_size_as_the_camera_pulls_back(renderer):
    """The point of an indicator: it does not shrink with the molecule."""
    near = _frame(renderer, width=30.0, distance=30.0)
    far = _frame(renderer, width=30.0, distance=300.0)

    def _covered(frame: np.ndarray) -> int:
        return int((frame.max(axis=2) > 30).sum())

    close, distant = _covered(near), _covered(far)
    assert close > 0 and distant > 0
    assert abs(close - distant) <= 0.1 * close, (
        f"the marker changed size with depth: {close} -> {distant} pixels"
    )
