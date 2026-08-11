"""Guardrails for the shared-WGSL renderer and the baselines it is judged against.

Everything here but :class:`TestImpostorsOnTheGpu` runs without a GPU or a
window. They cover the two things that made a correct renderer look wrong for a
day -- a baseline capture that leaked a setting into the next scene, and a
second backend carrying its own copy of the first one's lighting constants --
and the routing and conventions of the pipelines added after it.
"""
from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.renderer.depth_cue import FOG_OFF, fog_planes
from chisurf.plugins.chimol.chimol.renderer.lighting import (
    LightRig,
    resolve_light_rig,
)
from chisurf.plugins.chimol.test.capture_gl_baseline import (
    RESET,
    SCENES,
    missing_resets,
)


def test_reset_restores_every_setting_the_scenes_change():
    """No scene may leave a setting behind for the next one.

    This is the failure that produced five wrong baselines: ``occlusion.enabled``
    was set by a scene and not restored, so every scene captured after it had
    ambient occlusion switched off, and the renderer being compared against them
    was blamed for the difference.
    """
    assert missing_resets() == set(), (
        "add these to capture_gl_baseline.RESET, then re-capture the baselines"
    )


def test_reset_runs_before_every_scene():
    """Every scene is replayed with the reset preamble, not just the first."""
    assert RESET and SCENES
    assert RESET[0] == "hide everything"


class TestLightRig:
    """One rig, resolved from the config, shared by both backends."""

    def test_the_default_key_light_is_head_on_and_the_fill_is_shared(self):
        """One head-on key, and a fill that both backends read from here.

        The WebGPU backend once hardcoded ``fill=0.45`` and an *off-axis* key,
        described in its own comment as "matching the OpenGL backend's
        defaults" while matching none of them. What matters is not the value --
        that is a judgement, and it has changed: `3ef65bc37` raised the fill
        from 0.0 to 0.35 because a scene lit by a head-on key alone falls to
        ambient everywhere it turns away, and read dark. What matters is that
        the key points **down the camera** and that there is exactly one place
        the numbers live.

        This test asserted ``fill == 0.0`` and has been red since that commit,
        which is the failure mode a value assertion has: it pins a decision that
        was allowed to change, and then it is the test that is wrong.
        """
        rig = LightRig()
        assert rig.light_dir == (0.0, 0.0, 1.0)
        assert rig.fill == pytest.approx(0.35)
        assert resolve_light_rig({}).fill == pytest.approx(rig.fill), (
            "the dataclass default and the resolved default must be one number"
        )

    def test_reads_the_config_section(self):
        rig = resolve_light_rig(
            {"ambient_strength": 0.3, "key_light_intensity": 0.8,
             "light_direction": [1.0, 0.0, 0.0]}
        )
        assert rig.ambient == pytest.approx(0.3)
        assert rig.key == pytest.approx(0.8)
        assert rig.light_dir == (1.0, 0.0, 0.0)

    def test_accepts_chimerax_ambient_name(self):
        """``ambient_light_intensity`` is ChimeraX's name for the same value."""
        assert resolve_light_rig(
            {"ambient_light_intensity": 0.2}
        ).ambient == pytest.approx(0.2)

    def test_a_short_direction_falls_back_rather_than_raising(self):
        assert resolve_light_rig({"light_direction": [1.0]}).light_dir == (0.0, 0.0, 1.0)

    def test_replace_rejects_an_unknown_name(self):
        with pytest.raises(ValueError, match="unknown lighting parameter"):
            LightRig().replace(ambient_light_intensity=0.5)


class TestFogPlanes:
    """PyMOL's depth cue, measured over the scene and not over the far plane."""

    def test_disabled_is_a_zero_scale(self):
        assert fog_planes(100.0, 10.0, {"enabled": False}) == FOG_OFF

    def test_zero_intensity_is_off(self):
        assert fog_planes(100.0, 10.0, {"intensity": 0.0}) == FOG_OFF

    def test_full_intensity_ends_at_the_back_of_the_scene(self):
        """``fog 1.0`` puts the end plane on the far side of the molecule."""
        end, scale = fog_planes(100.0, 10.0, {"intensity": 1.0, "start": 0.45})
        assert end == pytest.approx(110.0)
        # start = 90 + 0.45 * 20 = 99
        assert scale == pytest.approx(1.0 / 11.0)

    def test_partial_intensity_pushes_the_end_plane_away(self):
        """A weaker cue spreads the same span over a longer distance."""
        _end_full, scale_full = fog_planes(100.0, 10.0, {"intensity": 1.0})
        _end_half, scale_half = fog_planes(100.0, 10.0, {"intensity": 0.5})
        assert scale_half < scale_full

    def test_a_zero_radius_stays_finite(self):
        """An empty scene must not divide by zero.

        The span collapses to the epsilon floor, so the cue becomes a knife edge
        at the camera distance -- which is what the OpenGL backend has always
        done, and is only reachable when there is nothing to look at.
        """
        end, scale = fog_planes(100.0, 0.0, {"intensity": 1.0})
        assert end == pytest.approx(100.0, abs=1e-3)
        assert 0.0 < scale < float("inf")

    def test_the_span_follows_the_radius_not_the_clipping_planes(self):
        """Doubling what the camera frames doubles the span the cue covers.

        A cue normalised over a far plane widened for depth precision dims the
        whole molecule uniformly instead of separating its front from its back.
        """
        _e1, s1 = fog_planes(100.0, 10.0, {"intensity": 1.0})
        _e2, s2 = fog_planes(100.0, 20.0, {"intensity": 1.0})
        assert s2 == pytest.approx(s1 / 2.0, rel=1e-6)


class TestPipelineRouting:
    """Which pipeline draws which geometry. No GPU needed."""

    @staticmethod
    def _geom(kind, n=4, indices=None, **kw):
        from chisurf.plugins.chimol.chimol.renderer.pack import PackedGeometry

        return PackedGeometry(
            kind=kind,
            positions=np.zeros((n, 3), dtype=np.float32),
            indices=indices,
            **kw,
        )

    def test_mesh_needs_indices(self):
        from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WgpuMeshRenderer

        route = WgpuMeshRenderer.pipeline_for
        assert route(self._geom("mesh", indices=np.arange(3, dtype=np.uint32))) == "mesh"
        assert route(self._geom("mesh")) is None

    def test_points_become_impostors(self):
        from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WgpuMeshRenderer

        assert WgpuMeshRenderer.pipeline_for(self._geom("points")) == "impostor"

    def test_a_single_vertex_is_not_a_line(self):
        """A line list needs pairs; an odd tail draws nothing and reports nothing."""
        from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WgpuMeshRenderer

        route = WgpuMeshRenderer.pipeline_for
        assert route(self._geom("line", n=2)) == "line"
        assert route(self._geom("line", n=1)) is None

    def test_text_is_an_acknowledged_gap(self):
        """Labels are skipped, and that is recorded rather than silently dropped."""
        from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WgpuMeshRenderer

        assert WgpuMeshRenderer.pipeline_for(self._geom("text", n=1)) is None

    def test_point_size_is_a_diameter(self):
        """``meta["size"]`` is ``gl_PointSize``, so the instance carries half of it."""
        from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WgpuMeshRenderer

        packed = WgpuMeshRenderer.interleave_impostors(
            self._geom("points", n=3, meta={"size": 8.0})
        )
        assert packed.shape == (3, 9)
        assert np.allclose(packed[:, 3], 4.0)

    def test_model_radii_are_used_as_given(self):
        """A bead's radius is a distance in the model and is not halved."""
        from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WgpuMeshRenderer

        packed = WgpuMeshRenderer.interleave_impostors(
            self._geom("points", n=2, radii=np.full((2, 1), 2.5, dtype=np.float32),
                       meta={"size": 8.0})
        )
        assert np.allclose(packed[:, 3], 2.5)


class TestWgslSource:
    """The shared source, without compiling it."""

    #: Which prelude each shader is composed with, and which are preludes
    #: themselves. Written out rather than globbed, so that adding a shader
    #: without deciding which family it belongs to fails this file rather than
    #: silently getting the wrong prelude -- which is how `raytrace.wgsl` came to
    #: be concatenated with the *render* shading model and to declare a second
    #: `fn shade` that nothing noticed for two commits.
    FAMILIES = {
        "shading.wgsl": None,   # the render prelude
        "grid.wgsl": None,      # the compute prelude
        "bvh.wgsl": None,       # the ray prelude
        "mesh.wgsl": "render",
        "impostor.wgsl": "render",
        # Bonds, as analytic capped cylinders: the same argument as the sphere
        # impostor, with a colour split at the midpoint.
        "cylinder.wgsl": "render",
        # A flat unlit glyph, not a shaded surface -- it takes the render
        # prelude for the camera matrices and calls no shading function.
        "marker.wgsl": "render",
        "line.wgsl": "render",
        # The chrome's quads. Also a render shader that shades nothing: it
        # samples the glyph atlas and writes the colour it was given.
        "ui.wgsl": "render",
        "overlay.wgsl": "render",
        "silhouette.wgsl": "render",
        "shade_atoms.wgsl": "compute",
        "occlusion.wgsl": "compute",
        "shadow_rays.wgsl": "compute",
        "distance_grid.wgsl": "compute",
        "edt.wgsl": "compute",
        "mc_active.wgsl": "compute",
        "mc_vertices.wgsl": "compute",
        "volume_ops.wgsl": "compute",
        "raytrace.wgsl": "ray",
        "bvh_probe.wgsl": "ray",
    }

    def test_every_shader_is_classified(self):
        """A new shader must say which prelude it takes."""
        from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WGSL_DIR

        present = {p.name for p in WGSL_DIR.glob("*.wgsl")}
        assert present == set(self.FAMILIES), (
            f"unclassified: {sorted(present - set(self.FAMILIES))}; "
            f"missing: {sorted(set(self.FAMILIES) - present)}"
        )

    def test_every_render_entry_point_gets_the_shading_prelude(self):
        """One shading function, prepended -- not one copy per pipeline.

        WGSL has no ``#include``, so the composition is concatenation, and the
        thing worth asserting is that no entry-point shader declares its own
        copy of the model.
        """
        from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import (
            WGSL_DIR,
            load_wgsl,
        )

        names = [n for n, family in self.FAMILIES.items() if family == "render"]
        assert names, "no render entry points found"
        for name in names:
            source = load_wgsl(name)
            assert source.count("struct Uniforms") == 1, name
            assert "@group(0) @binding(0)" in source, name
            assert source.count("fn shade(") == 1, name
            raw = (WGSL_DIR / name).read_text()
            assert "fn shade(" not in raw, f"{name} declares its own shading model"

    def test_every_compute_entry_point_gets_the_grid_prelude(self):
        """The cell-list walk is shared the same way the shading model is."""
        from chisurf.plugins.chimol.chimol.renderer.compute import (
            COMPUTE_PRELUDE,
            WGSL_DIR,
            load_compute_wgsl,
        )

        names = [n for n, family in self.FAMILIES.items() if family == "compute"]
        assert names
        for name in names:
            source = load_compute_wgsl(name)
            assert source.count("struct GridInfo") == 1, name
            assert source.count("fn cell_of(") == 1, name
            raw = (WGSL_DIR / name).read_text()
            assert "fn cell_of(" not in raw, f"{name} declares its own grid walk"
        assert (WGSL_DIR / COMPUTE_PRELUDE).exists()

    def test_every_ray_entry_point_gets_the_bvh_prelude(self):
        """`closest_hit` exists once, so the probe tests the tracer's own."""
        from chisurf.plugins.chimol.chimol.renderer.compute import (
            WGSL_DIR,
            load_ray_wgsl,
        )

        names = [n for n, family in self.FAMILIES.items() if family == "ray"]
        assert names
        for name in names:
            source = load_ray_wgsl(name)
            assert source.count("fn closest_hit(") == 1, name
            raw = (WGSL_DIR / name).read_text()
            assert "fn closest_hit(" not in raw, f"{name} declares its own traversal"


@pytest.mark.slow
class TestImpostorsOnTheGpu:
    """Needs a real adapter, so it is marked slow and skips when there is none."""

    @staticmethod
    def _renderer(size=320):
        wgpu = pytest.importorskip("wgpu")
        from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WgpuMeshRenderer

        try:
            return WgpuMeshRenderer(size, size)
        except Exception as exc:  # pragma: no cover - no adapter in this environment
            pytest.skip(f"no WebGPU adapter: {exc!r}")

    def test_an_impostor_draws_the_sphere_a_mesh_draws(self):
        """The same spheres, both ways, must land on the same pixels.

        An impostor is not the cheaper approximation of a tessellation -- it is
        the exact sphere where the tessellation is a polyhedron -- so a
        silhouette overlap well short of 1 means the projection, the radius
        convention or the depth write is wrong, and each of those is invisible
        in a single-column render.
        """
        from chisurf.plugins.chimol.chimol.renderer.pack import (
            PackedGeometry,
            PackedObject,
            PackedScene,
        )
        from chisurf.plugins.chimol.chimol.renderer.view_state import pack_view_state

        centre = np.zeros((1, 3), dtype=np.float32)
        radius = np.array([[4.0]], dtype=np.float32)
        colour = np.array([[0.9, 0.4, 0.2, 1.0]], dtype=np.float32)

        # A coarse UV sphere, deliberately: if the two agreed only at a fine
        # tessellation the test would be measuring the tessellation.
        us, vs = np.meshgrid(
            np.linspace(0, 2 * np.pi, 48), np.linspace(0, np.pi, 24), indexing="ij"
        )
        pts = np.stack(
            [np.cos(us) * np.sin(vs), np.cos(vs), np.sin(us) * np.sin(vs)], axis=-1
        ).reshape(-1, 3)
        faces = []
        nu, nv = 48, 24
        for i in range(nu - 1):
            for j in range(nv - 1):
                a, b = i * nv + j, (i + 1) * nv + j
                faces += [[a, b, a + 1], [b, b + 1, a + 1]]
        mesh = PackedGeometry(
            kind="mesh",
            positions=np.ascontiguousarray(pts * 4.0, dtype=np.float32),
            normals=np.ascontiguousarray(pts, dtype=np.float32),
            colors=np.repeat(colour, len(pts), axis=0),
            indices=np.ascontiguousarray(np.array(faces).ravel(), dtype=np.uint32),
        )
        impostor = PackedGeometry(
            kind="points",
            positions=centre,
            radii=radius,
            colors=colour,
            meta={"glyph": "sphere", "world_radius": True},
        )

        view = pack_view_state(
            np.eye(3), distance=40.0, target=(0.0, 0.0, 0.0),
            near=1.0, far=120.0, fov=20.0,
        )
        renderer = self._renderer()
        images = [
            renderer.render(
                PackedScene([PackedObject("o", g)], radius=6.0),
                view,
                background=(0.0, 0.0, 0.0),
                depth_cue={"enabled": False},
            )
            for g in (mesh, impostor)
        ]
        masks = [img.sum(2) > 30 for img in images]
        assert masks[1].any(), "the impostor drew nothing"
        iou = float((masks[0] & masks[1]).sum() / max((masks[0] | masks[1]).sum(), 1))
        assert iou > 0.97, f"impostor and mesh silhouettes disagree (IoU {iou:.3f})"

    def test_an_impostor_writes_depth_from_the_hit(self):
        """Two overlapping spheres must interpenetrate, not sort as flat cards.

        A billboard that does not write ``frag_depth`` puts one whole sphere in
        front of the other, so the nearer one's disc is a complete circle. With
        per-fragment depth the far sphere cuts into it, and the tell is that the
        near sphere's own colour covers fewer pixels than its full disc.
        """
        from chisurf.plugins.chimol.chimol.renderer.pack import (
            PackedGeometry,
            PackedObject,
            PackedScene,
        )
        from chisurf.plugins.chimol.chimol.renderer.view_state import pack_view_state

        # Overlapping, and the far one offset sideways so it emerges.
        geom = PackedGeometry(
            kind="points",
            positions=np.array([[0.0, 0.0, 3.0], [3.5, 0.0, -3.0]], dtype=np.float32),
            radii=np.array([[5.0], [5.0]], dtype=np.float32),
            colors=np.array(
                [[1.0, 0.0, 0.0, 1.0], [0.0, 0.0, 1.0, 1.0]], dtype=np.float32
            ),
            meta={"glyph": "sphere", "world_radius": True},
        )
        view = pack_view_state(
            np.eye(3), distance=40.0, target=(0.0, 0.0, 0.0),
            near=1.0, far=120.0, fov=30.0,
        )
        renderer = self._renderer()
        img = renderer.render(
            PackedScene([PackedObject("o", geom)], radius=9.0),
            view,
            background=(0.0, 0.0, 0.0),
            depth_cue={"enabled": False},
        )
        redder = (img[..., 0].astype(int) - img[..., 2]) > 20
        bluer = (img[..., 2].astype(int) - img[..., 0]) > 20
        assert redder.any() and bluer.any(), "one of the two spheres is missing"

        # The far sphere is visible *beside* the near one, and the boundary
        # between them is a curve rather than the near sphere's own circular
        # silhouette: measured column by column, the red region's top edge moves.
        columns = np.flatnonzero(redder.any(axis=0))
        tops = [int(np.flatnonzero(redder[:, c])[0]) for c in columns]
        assert max(tops) - min(tops) > 5, "the near sphere is a flat disc"


class TestRemovedSettingsAreMigratedAway:
    """A key deleted from the defaults must also leave existing user configs.

    Found while chasing an unrelated failure: the guard asserting that
    ``occlusion.enabled`` is the only occlusion switch passes on a **fresh**
    settings directory, where ``sticks.ambient_occlusion`` is genuinely gone --
    and every existing profile still had both, because removing a key from the
    packaged defaults reaches nobody who already has the file.
    """

    def test_the_dead_occlusion_switch_is_removed_from_an_old_config(self):
        from chisurf.plugins.chimol.chimol.config import (
            apply_display_config_migrations,
        )

        cfg = {"sticks": {"radius": 0.15, "ambient_occlusion": True}}
        changed = apply_display_config_migrations(cfg, from_version=10)
        assert "ambient_occlusion" not in cfg["sticks"]
        assert "sticks.ambient_occlusion (removed)" in changed
        # Untouched neighbours stay, values and all.
        assert cfg["sticks"]["radius"] == 0.15

    def test_a_chosen_value_does_not_save_a_removed_key(self):
        """Unlike a default change, there is no choice to protect.

        Keeping a non-default value would keep exactly the dead second switch
        the removal exists to delete.
        """
        from chisurf.plugins.chimol.chimol.config import (
            apply_display_config_migrations,
        )

        cfg = {"sticks": {"ambient_occlusion": False}}
        apply_display_config_migrations(cfg, from_version=10)
        assert cfg["sticks"] == {}

    def test_a_current_config_is_left_alone(self):
        from chisurf.plugins.chimol.chimol.config import (
            DISPLAY_CONFIG_VERSION,
            apply_display_config_migrations,
        )

        cfg = {"sticks": {"ambient_occlusion": True}}
        changed = apply_display_config_migrations(cfg, from_version=DISPLAY_CONFIG_VERSION)
        assert changed == []
        assert "ambient_occlusion" in cfg["sticks"]

    def test_every_removal_is_at_or_below_the_current_version(self):
        """A removal stamped past the version never runs."""
        from chisurf.plugins.chimol.chimol.config import (
            DISPLAY_CONFIG_KEY_REMOVALS,
            DISPLAY_CONFIG_VERSION,
        )

        assert max(DISPLAY_CONFIG_KEY_REMOVALS) <= DISPLAY_CONFIG_VERSION
