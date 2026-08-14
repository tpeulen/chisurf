"""``ray`` traces what the viewport draws, not only the atoms as spheres.

The tracer has handled triangle meshes for as long as ``render_scene`` has
existed, and the scene the viewport draws is triangle meshes -- cartoon, sticks,
surface. But `ray` decided what to do from the *sphere* count: on a cartoon-only
display, PyMOL's default and chimol's, that count is zero, so the command
returned early with a message stating a limitation the tracer no longer had.
Nobody could get a ray-traced cartoon out of it, and nothing failed.

Guarded here:

* the decision is made from the scene, so a cartoon-only display renders;
* line geometry becomes round-capped cylinders, the way PyMOL's ray does;
* a line's width is a pixel width, so it survives a change of resolution;
* the depth cue grades across the *scene*, not from the camera to a far plane
  that nothing is fitted to;
* what the tracer cannot draw is named rather than dropped;
* the fallback cannot contradict the viewport about what is shown.
"""

from __future__ import annotations

import numpy as np
import pytest

from chimol.renderer.raytracer import (
    TRACEABLE_KINDS,
    RayCamera,
    Sphere,
    _line_segments,
    _sausages,
    line_radius_for_camera,
    render_scene,
    trace,
    traceable_geometry_counts,
)
from chimol.renderer.scene import Geometry, Scene, SceneObject


def _camera(distance: float = 10.0, fov: float = 45.0, far: float | None = None) -> RayCamera:
    return RayCamera(
        origin=np.array([0.0, 0.0, distance]),
        forward=np.array([0.0, 0.0, -1.0]),
        up=np.array([0.0, 1.0, 0.0]),
        fov_degrees=fov,
        far_clip=distance * 2.0 if far is None else far,
    )


#: A flat, unlit surface: whatever brightness comes back is the albedo times the
#: fog, with no shading to confuse the measurement.
_FLAT = dict(
    ambient=1.0, diffuse=0.0, specular=0.0, direct_specular=0.0,
    shadow=False, gamma=0.0, color_blend=False,
)


def _line_scene(mode: str = "lines") -> Scene:
    geom = Geometry(
        kind="line",
        positions=np.array([[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        colors=np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]),
        meta={"mode": mode},
    )
    return Scene(
        objects=[SceneObject(id="lines", geometry=geom)],
        center=np.zeros(3),
        radius=1.0,
    )


# --------------------------------------------------------------------------- #
# What is in the scene
# --------------------------------------------------------------------------- #
def test_counts_report_every_kind_the_scene_holds():
    scene = Scene(
        objects=[
            SceneObject(id="cartoon", geometry=Geometry(kind="mesh", positions=np.zeros((6, 3)))),
            SceneObject(id="label:1", geometry=Geometry(kind="text", positions=np.zeros((1, 3)))),
        ]
    )
    assert traceable_geometry_counts(scene) == {"mesh": 6, "text": 1}


def test_text_is_the_kind_that_cannot_be_traced():
    """`ray` names what it leaves out; that list comes from this constant."""
    assert "text" not in TRACEABLE_KINDS
    # `cylinders` is here because bonds became analytic cylinders on the GPU and
    # the tracer was taught them in the same change -- a rasteriser primitive
    # missing from this list is a `ray` that refuses the representation.
    assert set(TRACEABLE_KINDS) == {"points", "mesh", "line", "cylinders"}


def test_an_empty_scene_counts_nothing():
    assert traceable_geometry_counts(Scene()) == {}
    assert traceable_geometry_counts(None) == {}


# --------------------------------------------------------------------------- #
# Lines become sausages
# --------------------------------------------------------------------------- #
def test_pairs_and_strips_are_split_the_way_the_gl_backend_draws_them():
    pos = np.array([[0.0, 0, 0], [1.0, 0, 0], [2.0, 0, 0], [3.0, 0, 0]])
    pairs = Geometry(kind="line", positions=pos)
    strip = Geometry(kind="line", positions=pos, meta={"mode": "line_strip"})
    assert _line_segments(pairs)[0].shape[0] == 2   # (0,1) and (2,3)
    assert _line_segments(strip)[0].shape[0] == 3   # (0,1), (1,2), (2,3)


def test_a_segment_becomes_a_shaft_with_two_round_caps():
    p0 = np.array([[0.0, 0.0, 0.0]])
    p1 = np.array([[2.0, 0.0, 0.0]])
    c0 = np.array([[1.0, 0.0, 0.0]])
    c1 = np.array([[0.0, 0.0, 1.0]])
    caps, verts, norms, cols = _sausages(p0, p1, c0, c1, radius=0.1, sides=8)

    # Two caps, at the ends and not at the midpoint: PyMOL's `sausage3fv`.
    assert len(caps) == 2
    assert {tuple(np.round(c.center, 6)) for c in caps} == {(0.0, 0.0, 0.0), (2.0, 0.0, 0.0)}
    assert all(c.radius == pytest.approx(0.1) for c in caps)

    # Two halves x 8 sides x 2 triangles.
    assert verts.shape == (2 * 8 * 2, 3, 3)
    assert norms.shape == verts.shape
    assert cols.shape == (2 * 8 * 2, 3)

    # Every shaft vertex sits one radius off the axis...
    off_axis = np.linalg.norm(verts[..., 1:], axis=-1)
    assert np.allclose(off_axis, 0.1)
    # ...and its normal is radial, which is what makes eight facets read as round.
    assert np.allclose(np.linalg.norm(norms, axis=-1), 1.0)
    assert np.allclose(norms[..., 0], 0.0)


def test_each_half_keeps_its_own_end_colour():
    """PyMOL splits a two-coloured line at the midpoint (`CGO_SPLITLINE`)."""
    caps, verts, _, cols = _sausages(
        np.array([[0.0, 0, 0]]), np.array([[2.0, 0, 0]]),
        np.array([[1.0, 0, 0]]), np.array([[0.0, 0, 1.0]]),
        radius=0.1, sides=8,
    )
    first_half, second_half = cols[:16], cols[16:]
    assert np.allclose(first_half, [1.0, 0.0, 0.0])
    assert np.allclose(second_half, [0.0, 0.0, 1.0])
    # The split is at the midpoint: the red half spans x in [0, 1].
    assert verts[:16, :, 0].max() == pytest.approx(1.0)
    assert verts[16:, :, 0].min() == pytest.approx(1.0)


def test_a_zero_length_segment_is_dropped_rather_than_dividing_by_zero():
    caps, verts, _, _ = _sausages(
        np.zeros((1, 3)), np.zeros((1, 3)), np.ones((1, 3)), np.ones((1, 3)), radius=0.1
    )
    assert caps == [] and verts.shape[0] == 0


@pytest.mark.parametrize("axis", [0, 1, 2])
def test_an_axis_aligned_segment_still_gets_a_frame(axis):
    """An axis-aligned segment still gets a frame around its axis.

    The helper vector is chosen per segment, so the cross product cannot
    collapse -- and axis-aligned is the common case in a wireframe, not the rare
    one.
    """
    p1 = np.zeros((1, 3))
    p1[0, axis] = 1.0
    _, verts, norms, _ = _sausages(np.zeros((1, 3)), p1, np.ones((1, 3)), np.ones((1, 3)), 0.1)
    assert np.all(np.isfinite(verts))
    assert np.allclose(np.linalg.norm(norms, axis=-1), 1.0)


# --------------------------------------------------------------------------- #
# How thick a line comes out
# --------------------------------------------------------------------------- #
def test_line_radius_is_a_pixel_width_so_resolution_cannot_change_it():
    """PyMOL: `radius = PixelRadius * line_width / 2` (layer1/CGO.cpp)."""
    cam = _camera()
    r_small = line_radius_for_camera(cam, height=100, depth=10.0, line_width=2.0)
    r_large = line_radius_for_camera(cam, height=400, depth=10.0, line_width=2.0)
    # Four times the pixels, a quarter of the world radius: the same two pixels.
    assert r_large == pytest.approx(r_small / 4.0)
    # And exactly one pixel's world size per unit of width.
    pixel = 2.0 * 10.0 * np.tan(np.radians(45.0) / 2.0) / 100
    assert r_small == pytest.approx(pixel * 2.0 / 2.0)


def test_an_explicit_line_radius_wins_outright():
    """PyMOL uses `line_radius` when it is positive and derives one otherwise."""
    cam = _camera()
    assert line_radius_for_camera(cam, 200, 10.0, line_width=8.0, line_radius=0.25) == 0.25


def test_lines_actually_reach_the_image():
    scene = _line_scene()
    img = render_scene(
        scene=scene, camera=_camera(), light_directions=np.array([[0.0, 0.0, 1.0]]),
        width=64, height=64, ssaa=1, background=(0, 0, 0), line_width=6.0,
    )
    assert img.shape == (64, 64, 3)
    assert int((img.max(axis=2) > 8).sum()) > 0, "the wireframe drew nothing"


def test_a_strip_draws_the_joins_a_pair_list_does_not():
    """A strip connects 0-1-2; read as pairs it would only draw 0-1."""
    lit = {}
    for mode in ("lines", "line_strip"):
        geom = Geometry(
            kind="line",
            positions=np.array([[-1.0, 0, 0], [0.0, 0, 0], [1.0, 0, 0]]),
            colors=np.ones((3, 3)),
            meta={"mode": mode},
        )
        scene = Scene(objects=[SceneObject(id="l", geometry=geom)], radius=1.0)
        img = render_scene(
            scene=scene, camera=_camera(), light_directions=np.array([[0.0, 0.0, 1.0]]),
            width=64, height=64, ssaa=1, background=(0, 0, 0), line_width=6.0,
        )
        lit[mode] = int((img.max(axis=2) > 8).sum())
    assert lit["line_strip"] > lit["lines"]


# --------------------------------------------------------------------------- #
# The depth cue
# --------------------------------------------------------------------------- #
#: Camera 100 units from a unit sphere, with a far plane 10 % beyond it -- the
#: shape of a real chimol view, where the molecule occupies a thin slice near the
#: back of the camera's range.
_FOG_CAM = _camera(distance=100.0, far=110.0)


def _fog_probe(**kw) -> tuple[float, float]:
    """``(mean, brightest)`` over one mid-grey sphere at the centre of the view."""
    img = trace(
        spheres=[Sphere(center=np.zeros(3), radius=1.0, color=np.full(3, 0.6))],
        camera=_FOG_CAM,
        light_directions=np.array([[0.0, 0.0, 1.0]]),
        width=48, height=48, ssaa=1, background=(0, 0, 0),
        **_FLAT, **kw,
    )
    lit = img.reshape(-1, 3)
    lit = lit[lit.max(axis=1) > 4]
    return float(lit.mean()), float(lit.max())


def test_the_depth_cue_grades_across_the_scene_not_the_far_plane():
    """``best_t / far_clip`` fogged a whole molecule uniformly.

    A far plane that is not fitted to the object puts every one of its pixels at
    a similar fraction of the range, so *nothing* comes back unfogged and the cue
    reads as a flat dimming rather than as depth. PyMOL normalises over its
    front-to-back clipping range (``layer1/Ray.cpp``), which is fitted around the
    object -- so its front face is untouched and its back face is fully faded.
    """
    off_mean, off_max = _fog_probe(depth_cue=False)
    fitted_mean, fitted_max = _fog_probe(depth_cue=True, fog_front=99.0, fog_back=101.0)
    far_mean, far_max = _fog_probe(depth_cue=True)  # 0 .. far_clip, the old range

    # Fitted to the scene, the face nearest the camera keeps its colour exactly.
    assert fitted_max == pytest.approx(off_max)
    # Over the camera's range, even the nearest pixel loses most of it.
    assert far_max < 0.5 * off_max
    assert far_mean < 0.5 * fitted_mean


def test_render_scene_fits_the_depth_cue_to_the_scene_by_default():
    """A caller that says nothing still gets the scene-fitted range."""
    scene = Scene(
        objects=[
            SceneObject(
                id="atoms",
                geometry=Geometry(
                    kind="points",
                    positions=np.zeros((1, 3)),
                    colors=np.full((1, 3), 0.6),
                    radii=np.array([1.0]),
                ),
            )
        ],
        center=np.zeros(3),
        radius=1.0,
    )
    common = dict(
        camera=_FOG_CAM,
        light_directions=np.array([[0.0, 0.0, 1.0]]),
        width=48, height=48, ssaa=1, background=(0, 0, 0),
        **_FLAT,
    )
    fitted = render_scene(scene=scene, **common)
    far_plane = render_scene(scene=scene, fog_front=0.0, fog_back=110.0, **common)

    def lit(a: np.ndarray) -> float:
        flat = a.reshape(-1, 3)
        return float(flat[flat.max(axis=1) > 4].mean())

    assert lit(fitted) > lit(far_plane)
