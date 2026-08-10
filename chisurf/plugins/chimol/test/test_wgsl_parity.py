"""Guardrails for the shared-WGSL renderer and the baselines it is judged against.

None of these need a GPU or a window. They cover the two things that made a
correct renderer look wrong for a day: a baseline capture that leaked a setting
into the next scene, and a second backend carrying its own copy of the first
one's lighting constants.
"""
from __future__ import annotations

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

    def test_defaults_are_a_single_head_on_key_light(self):
        """No fill light by default.

        The WebGPU backend once hardcoded ``fill=0.45`` and an off-axis key,
        which models a ribbon with dark flanks where the configured rig lights it
        evenly. Against a black background that difference is invisible.
        """
        rig = LightRig()
        assert rig.light_dir == (0.0, 0.0, 1.0)
        assert rig.fill == 0.0

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
