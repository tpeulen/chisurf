"""A plugin can register a render pipeline -- a shader of its own -- and the backend draws it.

``render/pipelines.py`` is the table the WebGPU backend always had (shader,
vertex layout, topology, step mode) plus the three ladders that had to agree
with it (kind routing, interleave, draw call), as one ``PipelineSpec`` per
kind. Pinned: the built-ins route as before; a plugin kind registered *after*
the backend exists is built on first use and its pixels land; unloading
removes it.
"""

from __future__ import annotations

import numpy as np
import pytest
from chimol.plugins import load_plugins
from chimol.render.pipelines import PIPELINES, DrawRule, PipelineSpec
from chimol.render.scene import Geometry, Material, Scene, SceneObject


def _geom(kind, n=4, **kw):
    """A packed geometry, which is what the backend routes on."""
    from chimol.render.pack import pack_geometry

    pos = np.zeros((n, 3), dtype=np.float32)
    return pack_geometry(Geometry(kind=kind, positions=pos, **kw))


def test_the_builtin_routing_is_unchanged():
    from chimol.render.wgpu_backend import WgpuMeshRenderer

    pf = WgpuMeshRenderer.pipeline_for
    assert pf(_geom("mesh", indices=np.zeros(3, dtype=np.uint32))) == "mesh"
    assert pf(_geom("mesh")) is None  # a mesh needs indices
    assert pf(_geom("points")) == "impostor"
    assert pf(_geom("points", meta={"glyph": "selection"})) == "marker"
    assert pf(_geom("points", n=0)) is None
    assert pf(_geom("cylinders", n=4)) == "cylinder"
    assert pf(_geom("cylinders", n=1)) is None
    assert pf(_geom("line", n=2)) == "line"
    assert pf(_geom("line", n=1)) is None
    assert pf(_geom("text")) is None
    assert set(PIPELINES.kinds()) >= {"mesh", "impostor", "marker", "cylinder", "line"}
    assert PIPELINES.get("mesh").closed and not PIPELINES.get("line").closed


_FLAT_WGSL = """
struct VertexIn {
    @location(0) position : vec3<f32>,
    @location(1) colour   : vec4<f32>,
};
struct VertexOut {
    @builtin(position) clip : vec4<f32>,
    @location(0) colour     : vec4<f32>,
};
@vertex
fn vs_main(in: VertexIn) -> VertexOut {
    var out : VertexOut;
    out.clip = u.mvp * vec4<f32>(in.position, 1.0);
    out.colour = in.colour;
    return out;
}
@fragment
fn fs_main(in: VertexOut) -> @location(0) vec4<f32> {
    return in.colour;
}
"""


def _interleave_flat(geometry):
    n = geometry.vertex_count
    out = np.zeros((n, 7), dtype=np.float32)
    out[:, 0:3] = geometry.positions
    cols = (
        np.asarray(geometry.colors, dtype=np.float32)
        if geometry.colors is not None
        else np.ones((n, 4), np.float32)
    )
    out[:, 3:7] = cols[:, :4]
    return np.ascontiguousarray(out)


class _FlatPlugin:
    def __init__(self, shader_path):
        self.shader_path = shader_path

    name = "flat"

    def register(self, api):
        api.add_pipeline(
            PipelineSpec(
                kind="flat",
                geometry_kind="flat_tris",
                shader=str(self.shader_path),
                attributes=(("float32x3", 3), ("float32x4", 4)),
                topology="triangle-list",
                step_mode="vertex",
                interleave=_interleave_flat,
                draw=DrawRule("vertex_list"),
            )
        )


@pytest.mark.slow
def test_a_plugin_pipeline_registered_after_the_backend_draws(tmp_path):
    from chimol.commands.command import Cmd
    from chimol.render.pack import pack_scene
    from chimol.render.wgpu_backend import WgpuMeshRenderer

    shader = tmp_path / "flat.wgsl"
    shader.write_text(_FLAT_WGSL)
    renderer = WgpuMeshRenderer(64, 64)  # built before the plugin exists
    cmd = Cmd(None, plugins=False)
    loaded = load_plugins(cmd, [_FlatPlugin(shader)])
    try:
        # one big magenta triangle across the view, at the camera origin
        pos = np.array([[-5, -5, 0], [5, -5, 0], [0, 5, 0]], dtype=np.float32)
        col = np.tile(np.array([[1, 0, 1, 1]], dtype=np.float32), (3, 1))
        geom = Geometry(kind="flat_tris", positions=pos, colors=col)
        assert WgpuMeshRenderer.pipeline_for(geom) == "flat"
        scene = Scene(
            objects=[SceneObject(id="t", geometry=geom, material=Material())],
            center=np.zeros(3),
            radius=5.0,
        )
        view = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, -20, 0, 0, 0, 1, 40, 45]
        img = renderer.render(pack_scene(scene), view, background=(0, 0, 0))
        assert img.shape == (64, 64, 3)
        magenta = (img[..., 0] > 200) & (img[..., 1] < 50) & (img[..., 2] > 200)
        assert magenta.sum() > 200, f"the plugin pipeline drew nothing ({magenta.sum()} px)"
    finally:
        loaded.unload("flat")
    assert PIPELINES.get("flat") is None
    assert WgpuMeshRenderer.pipeline_for(_geom("flat_tris")) is None
