"""Spheres and sticks are analytic primitives, not tessellations.

Both representations used to be meshes built in NumPy on every scene rebuild:
124,704 triangles for `show spheres` on T4 lysozyme and 11,072 for `show
sticks`. They are now two triangles per atom and two per bond, intersected in
the fragment shader.

That is not a cheaper approximation. A tessellated sphere is a polyhedron and a
twelve-sided tube is a prism; the impostor is the exact primitive. So what these
tests check is the pair of claims that makes the change safe:

* the **inventory** -- the scene carries the primitive, not a mesh, and carries
  what a ray tracer needs alongside it;
* the **picture** -- the silhouette matches the mesh it replaced, closely enough
  that no one looking at a molecule can tell which drew it.

The rendering half needs a GPU and skips without one.
"""
from __future__ import annotations

import numpy as np
import pytest

from chimol.render.pack import pack_scene
from chimol.render.scene import Geometry, Scene, SceneObject
from chimol.core.view_state import pack_view_state
from chimol.render.wgpu_backend import WgpuMeshRenderer

SIZE = (320, 320)


def _packed(objects):
    return pack_scene(Scene(objects=objects, center=(0.0, 0.0, 0.0), radius=6.0))


# ── routing and packing ──────────────────────────────────────────────────
def test_a_bond_geometry_routes_to_the_cylinder_pipeline():
    geometry = Geometry(
        kind="cylinders",
        positions=np.array([[-2.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype=np.float32),
        colors=np.ones((2, 4), dtype=np.float32),
        meta={"radius": 0.4},
    )
    packed = _packed([SceneObject(id="sticks", geometry=geometry)])
    assert WgpuMeshRenderer.pipeline_for(packed.objects[0].geometry) == "cylinder"


def test_one_instance_per_bond_carrying_both_ends_and_both_colours():
    """The pack is per *bond*, from two rows of positions and two of colours."""
    positions = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 2.0, 0.0]],
        dtype=np.float32,
    )
    colors = np.array(
        [[1, 0, 0, 1], [0, 1, 0, 1], [0, 0, 1, 1], [1, 1, 0, 1]], dtype=np.float32
    )
    geometry = Geometry(
        kind="cylinders", positions=positions, colors=colors, meta={"radius": 0.3}
    )
    packed = _packed([SceneObject(id="sticks", geometry=geometry)])
    rows = WgpuMeshRenderer.interleave_cylinders(packed.objects[0].geometry)

    assert rows.shape == (2, 17)
    assert np.allclose(rows[0, 0:3], positions[0])
    assert np.allclose(rows[0, 4:7], positions[1])
    assert np.allclose(rows[:, 3], 0.3), "the radius comes from the meta"
    assert np.allclose(rows[0, 8:12], colors[0])
    assert np.allclose(rows[0, 12:16], colors[1]), (
        "each half of a stick carries its own atom's colour"
    )


def test_spheres_carry_their_centres_for_the_ray_tracer():
    """A rasteriser wants triangles; a tracer wants the spheres themselves.

    The mesh path recorded ``meta["spheres"]`` so the tracer could use its exact
    primitive -- 0.3 s against 114 s for 148L. The impostor path has to carry
    the same record, or switching representation silently makes ``ray`` slow.
    """
    from chimol.core.viewer import MolView

    centres = np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0]])
    colours = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    radii = np.array([1.2, 1.8])

    obj = MolView._build_balls_impostors(
        MolView.__new__(MolView), centres, colours, radii
    )
    assert obj.geometry.kind == "points"
    assert obj.geometry.meta["world_radius"] is True
    spheres = obj.geometry.meta["spheres"]
    assert np.allclose(spheres["centers"], centres)
    assert np.allclose(spheres["radii"], radii)


def test_the_impostor_floor_is_a_setting_and_defaults_to_every_sphere():
    from chimol.core.viewer import MolView

    assert MolView._spheres_as_impostors(1) is True
    assert MolView._spheres_as_impostors(100_000) is True


# ── the picture ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def renderer():
    try:
        return WgpuMeshRenderer(*SIZE)
    except Exception as exc:  # noqa: BLE001 - no GPU on this runner
        pytest.skip(f"no WebGPU adapter: {exc}")


def _render(renderer, objects) -> np.ndarray:
    view = pack_view_state(
        rotation=np.eye(3), distance=24.0, target=(0.0, 0.0, 0.0),
        near=12.0, far=40.0,
    )
    return renderer.render(
        _packed(objects), view, background=(0.0, 0.0, 0.0), target_radius=6.0
    )


def _silhouette(frame: np.ndarray) -> np.ndarray:
    return frame.max(axis=2) > 12


def test_a_cylinder_impostor_matches_the_tube_it_replaces(renderer):
    """Silhouette IoU against the twelve-sided mesh, on the same bond."""
    from chimol.geometry.primitives import _build_stick_mesh

    start = np.array([-3.0, -1.0, 0.0])
    end = np.array([3.0, 1.5, 0.0])
    radius = 0.6

    mesh = _build_stick_mesh(
        np.array([[0, 1]]), np.vstack((start, end)),
        np.ones((2, 4)), radius=radius, segments_circle=12,
    )
    verts, norms, faces, cols = mesh
    tube = SceneObject(
        id="tube",
        geometry=Geometry(
            kind="mesh", positions=verts, indices=faces, normals=norms, colors=cols
        ),
    )
    impostor = SceneObject(
        id="cyl",
        geometry=Geometry(
            kind="cylinders",
            positions=np.vstack((start, end)).astype(np.float32),
            colors=np.ones((2, 4), dtype=np.float32),
            meta={"radius": radius},
        ),
    )

    a = _silhouette(_render(renderer, [tube]))
    b = _silhouette(_render(renderer, [impostor]))
    assert a.sum() > 500 and b.sum() > 500, "one of the two drew nothing"
    iou = float((a & b).sum()) / float((a | b).sum())
    assert iou > 0.95, f"silhouette IoU {iou:.3f}: the cylinder is not the tube"


def test_a_stick_is_split_between_its_two_atoms(renderer):
    """The colour changes at the midpoint, which is what PyMOL's sticks do."""
    impostor = SceneObject(
        id="cyl",
        geometry=Geometry(
            kind="cylinders",
            positions=np.array([[-4.0, 0.0, 0.0], [4.0, 0.0, 0.0]], dtype=np.float32),
            colors=np.array(
                [[1.0, 0.0, 0.0, 1.0], [0.0, 0.0, 1.0, 1.0]], dtype=np.float32
            ),
            meta={"radius": 0.8},
        ),
    )
    frame = _render(renderer, [impostor]).astype(int)
    height, width = frame.shape[:2]
    row = frame[height // 2]
    left = row[: width // 2]
    right = row[width // 2:]
    assert (left[:, 0] > left[:, 2] + 30).any(), "the left half is not red"
    assert (right[:, 2] > right[:, 0] + 30).any(), "the right half is not blue"


def test_the_cylinder_is_capped(renderer):
    """End-on, a stick is a disc and not a hole.

    Without caps a bond pointing at the camera is a tube you can see down, and
    at the end of a chain there is no atom to plug it.
    """
    impostor = SceneObject(
        id="cyl",
        geometry=Geometry(
            kind="cylinders",
            # Along the view axis: the camera looks down -z, so this points at it.
            positions=np.array([[0.0, 0.0, -3.0], [0.0, 0.0, 3.0]], dtype=np.float32),
            colors=np.ones((2, 4), dtype=np.float32),
            meta={"radius": 1.5},
        ),
    )
    frame = _render(renderer, [impostor])
    centre = frame[frame.shape[0] // 2, frame.shape[1] // 2]
    assert int(centre.max()) > 30, f"the cap is missing; centre reads {centre}"
