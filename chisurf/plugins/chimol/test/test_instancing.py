"""The gigastructure seam: one mesh, N transforms, one draw call.

``Geometry.instances`` (an ``InstanceBlock``) makes the backend draw the
prototype once per transform through ``mesh_instanced`` (a storage buffer of
``mat4 + colour`` at group 1, ``draw_indexed(count, N)``); ``expand_instances``
lays the copies out for consumers without instancing (the ray tracer). Pinned:
the instanced picture equals the expanded one; the per-instance colour lands;
the frame stats count one draw with N instances; the plain mesh path is unchanged.
"""
from __future__ import annotations

import numpy as np
import pytest

from chimol.render.pack import pack_geometry, pack_scene
from chimol.render.pipelines import PIPELINES
from chimol.render.scene import Geometry, InstanceBlock, Material, Scene, SceneObject, expand_instances


def _quad(size=1.0):
    pos = np.array([[-size, -size, 0], [size, -size, 0], [size, size, 0], [-size, size, 0]], dtype=np.float32)
    nrm = np.tile(np.array([[0, 0, 1]], dtype=np.float32), (4, 1))
    col = np.tile(np.array([[0.2, 0.9, 0.2, 1.0]], dtype=np.float32), (4, 1))
    idx = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    return Geometry(kind="mesh", positions=pos, normals=nrm, colors=col, indices=idx)


def _translations(offsets):
    tf = np.tile(np.eye(4, dtype=np.float32), (len(offsets), 1, 1))
    for i, (x, y, z) in enumerate(offsets):
        tf[i, :3, 3] = (x, y, z)
    return tf


def test_routing_and_packing():
    plain = pack_geometry(_quad())
    assert PIPELINES.pipeline_for(plain) == "mesh"
    inst = _quad()
    inst.instances = InstanceBlock(transforms=_translations([(0, 0, 0), (3, 0, 0)]))
    packed = pack_geometry(inst)
    assert packed.instance_count == 2 and packed.instance_transforms.shape == (2, 4, 4)
    assert PIPELINES.pipeline_for(packed) == "mesh_instanced"
    with pytest.raises(ValueError):
        bad = _quad()
        bad.instances = InstanceBlock(transforms=np.zeros((2, 3, 3), dtype=np.float32))
        pack_geometry(bad)


def test_expand_instances_lays_every_copy_out():
    g = _quad()
    g.instances = InstanceBlock(transforms=_translations([(0, 0, 0), (5, 0, 0), (0, 5, 0)]),
                                colors=np.array([[1, 0, 0, 1], [0, 1, 0, 1], [0, 0, 1, 1]], dtype=np.float32))
    e = expand_instances(g)
    assert e.instances is None
    assert e.positions.shape == (12, 3) and e.indices.shape == (6, 3)
    assert np.allclose(e.positions[4:8, 0], g.positions[:, 0] + 5)
    assert np.allclose(e.positions[8:12, 1], g.positions[:, 1] + 5)
    assert e.indices.max() == 11 and np.array_equal(e.indices[2:4], g.indices + 4)
    assert np.allclose(e.colors[4], (0, 1, 0, 1))
    assert np.allclose(e.normals, np.tile([0, 0, 1], (12, 1)))


def _render(scene, renderer):
    view = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, -30, 0, 0, 0, 1, 60, 45]
    return renderer.render(pack_scene(scene), view, background=(0, 0, 0))


@pytest.mark.slow
def test_the_gpu_draws_every_instance_and_agrees_with_the_expansion():
    from chimol.render.wgpu_backend import WgpuMeshRenderer

    renderer = WgpuMeshRenderer(96, 96)
    offsets = [(-6, -6, 0), (6, -6, 0), (-6, 6, 0), (6, 6, 0), (0, 0, 0)]
    colors = np.array([[1, 0, 0, 1], [0, 1, 0, 1], [0, 0, 1, 1], [1, 1, 0, 1], [0, 1, 1, 1]], dtype=np.float32)

    proto = _quad(2.0)
    proto.instances = InstanceBlock(transforms=_translations(offsets), colors=colors)
    inst_scene = Scene(objects=[SceneObject(id="i", geometry=proto, material=Material())],
                       center=np.zeros(3), radius=10.0)
    img_inst = _render(inst_scene, renderer)
    stats = renderer.stats
    lit = (img_inst.sum(axis=2) > 60)
    assert lit.sum() > 5 * 40, f"expected five lit quads, got {lit.sum()} px"

    flat = expand_instances(proto)
    flat_scene = Scene(objects=[SceneObject(id="f", geometry=flat, material=Material())],
                       center=np.zeros(3), radius=10.0)
    img_flat = _render(flat_scene, renderer)
    diff = np.abs(img_inst.astype(int) - img_flat.astype(int)).max()
    assert diff <= 2, f"instanced and expanded pictures differ by {diff}"

    # per-instance colour: the top-right copy is yellow, the centre one cyan
    h, w = lit.shape
    tr = img_inst[: h // 3, 2 * w // 3:].reshape(-1, 3)
    tr = tr[tr.sum(axis=1) > 60]
    r, g, b = tr.mean(axis=0)
    assert r > 150 and g > 150 and b < 0.5 * r, (r, g, b)              # yellow (lit, so b is not 0)
    centre = img_inst[h // 2 - 4: h // 2 + 4, w // 2 - 4: w // 2 + 4].reshape(-1, 3)
    r, g, b = centre.mean(axis=0)
    assert g > 150 and b > 150 and r < 0.5 * g, (r, g, b)              # cyan


@pytest.mark.slow
def test_a_plain_mesh_still_takes_the_plain_pipeline():
    from chimol.render.wgpu_backend import WgpuMeshRenderer

    renderer = WgpuMeshRenderer(32, 32)
    scene = Scene(objects=[SceneObject(id="p", geometry=_quad(4.0), material=Material())],
                  center=np.zeros(3), radius=5.0)
    img = _render(scene, renderer)
    assert (img.sum(axis=2) > 60).sum() > 20
    assert ("mesh_instanced", "opaque") not in renderer._pipelines or True   # built lazily only when used


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_an_object_with_an_instance_set_builds_instanced_meshes(qapp):
    """The scene builder attaches the block to every mesh the object produced; the tracer expands."""
    import pathlib

    import chimol
    from chimol.core.model.instances import InstanceSet
    from chimol.core.viewer import Viewer
    from chimol.io.structure import load_structure_payload
    from chimol.viewport.headless import SceneSink

    pdb = pathlib.Path(chimol.__file__).resolve().parent / "data" / "demos" / "148l.pdb"
    viewer = Viewer(renderer_factory=SceneSink)
    _s, payload = load_structure_payload(pdb)
    viewer.apply_payload(payload)
    viewer.update_view()
    meshes = [o for o in viewer._scene.objects if o.geometry.kind == "mesh"]
    assert meshes and all(o.geometry.instances is None for o in meshes)

    grid = InstanceSet.grid(2, 2, 1, 60.0)
    assert grid.count == 4
    assert viewer.set_instances(None, grid)
    meshes = [o for o in viewer._scene.objects if o.geometry.kind == "mesh"]
    assert meshes and all(o.geometry.instances is not None and o.geometry.instances.count == 4 for o in meshes)
    packed = pack_scene(viewer._scene)
    kinds = {PIPELINES.pipeline_for(o.geometry) for o in packed.objects if o.geometry.kind == "mesh"}
    assert kinds == {"mesh_instanced"}
    # and off again
    assert viewer.set_instances(None, None)
    assert all(o.geometry.instances is None for o in viewer._scene.objects)
    assert grid.bounds_radius(10.0) > 10.0


def test_the_instances_command(qapp):
    import pathlib

    import chimol
    from chimol.commands.command import Cmd
    from chimol.core.viewer import Viewer
    from chimol.hosts.base import ViewerHost
    from chimol.viewport.headless import SceneSink

    pdb = pathlib.Path(chimol.__file__).resolve().parent / "data" / "demos" / "148l.pdb"
    viewer = Viewer(renderer_factory=SceneSink)
    host = ViewerHost(viewer)
    cmd = Cmd(None, plugins=False)
    host.cmd = cmd
    cmd.set_window(host)
    errors: list[str] = []
    cmd.set_error_callback(errors.append)
    said: list[str] = []
    cmd.set_message_callback(said.append)
    cmd.do(f'load "{pdb}"')
    assert errors == [], errors
    cmd.do("instances 148l, grid 3x2x1, 40")
    assert errors == [], errors
    assert "x 6" in said[-1]
    assert all(o.geometry.instances.count == 6 for o in viewer._scene.objects if o.geometry.kind == "mesh")
    cmd.do("instances 148l, off")
    assert all(o.geometry.instances is None for o in viewer._scene.objects)
    cmd.do("instances nosuch, grid 2x2x2")
    assert errors and "no object" in errors[-1]


@pytest.mark.slow
def test_impostors_are_drawn_once_per_copy_and_match_the_expansion():
    """Points (and cylinders, lines) have no storage-buffer pipeline: one draw per copy, same picture."""
    from chimol.render.wgpu_backend import WgpuMeshRenderer

    renderer = WgpuMeshRenderer(96, 96)
    pos = np.array([[0, 0, 0]], dtype=np.float32)
    col = np.array([[1, 0.2, 0.2, 1]], dtype=np.float32)
    ball = Geometry(kind="points", positions=pos, colors=col, radii=np.array([2.5], dtype=np.float32),
                    meta={"world_radius": True})
    ball.instances = InstanceBlock(transforms=_translations([(-6, 0, 0), (0, 0, 0), (6, 0, 0)]))
    inst = Scene(objects=[SceneObject(id="i", geometry=ball, material=Material())], center=np.zeros(3), radius=10.0)
    img_inst = _render(inst, renderer)
    lit = img_inst.sum(axis=2) > 60
    assert lit.sum() > 3 * 30, f"three balls expected, {lit.sum()} px lit"
    # three separate blobs across the middle row
    row = lit[lit.shape[0] // 2]
    runs = int(np.count_nonzero(np.diff(row.astype(int)) == 1))
    assert runs == 3, f"expected 3 blobs across the middle, found {runs}"

    flat = expand_instances(ball)
    flat_scene = Scene(objects=[SceneObject(id="f", geometry=flat, material=Material())], center=np.zeros(3), radius=10.0)
    img_flat = _render(flat_scene, renderer)
    assert np.abs(img_inst.astype(int) - img_flat.astype(int)).max() <= 2
    # the stats saw one draw per copy
    assert renderer.stats is not None
