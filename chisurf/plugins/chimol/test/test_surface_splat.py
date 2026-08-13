from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.renderer.pack import pack_scene
from chisurf.plugins.chimol.chimol.renderer.scene import Geometry, Scene, SceneObject
from chisurf.plugins.chimol.chimol.renderer.surface_quality import apply_surface_quality
from chisurf.plugins.chimol.chimol.renderer.view_state import pack_view_state
from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WgpuMeshRenderer

SIZE = (320, 320)


def _packed(objects):
    return pack_scene(Scene(objects=objects, center=(0.0, 0.0, 0.0), radius=6.0))


def test_apply_surface_quality_copies_and_leaves_an_unknown_level_alone():
    base_config = {
        "quality": "balanced",
        "grid_spacing": 0.5,
        "padding": 2.5,
        "cutoff_factor": 2.5,
        "iso_value": 0.2,
    }
    splat_config = apply_surface_quality(base_config, "splat")
    assert splat_config is not base_config
    assert splat_config["quality"] == "splat"
    assert base_config["quality"] == "balanced"

    # A splat name survives under any of its spellings, canonicalised -- that
    # name is what routes the object to the screen-space pipeline.
    for spelling in ("gauss", "interactive", "fastest"):
        assert apply_surface_quality(base_config, spelling)["quality"] == "splat"

    # An unknown level leaves the configuration alone. The setting is a string
    # a user can type, and the surface they already had is a better answer to a
    # typo than a surface at some other resolution -- which is what
    # `apply_surface_quality` documents.
    #
    # This test asserted `== "splat"` and the code wrote `"fast"`, so the three
    # of them disagreed three ways; the bug that hid it is that the same
    # `else` branch also swallowed the splat level. Reconciled on the
    # docstring, which is the only one of the three that gives a reason.
    unknown_config = apply_surface_quality(base_config, "nonexistent_level")
    assert unknown_config["quality"] == "balanced"
    assert unknown_config["grid_spacing"] == base_config["grid_spacing"]
    assert unknown_config is not base_config


def test_gauss_geometry_routes_to_gauss_pipeline():
    positions = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float32)
    colors = np.ones((2, 4), dtype=np.float32)
    radii = np.array([1.5, 1.5], dtype=np.float32)
    geometry = Geometry(
        kind="gauss",
        positions=positions,
        colors=colors,
        radii=radii,
        meta={"gauss": {"decay": 2.0, "iso": 0.5, "opacity": 1.0}},
    )
    packed = _packed([SceneObject(id="surface", geometry=geometry)])
    assert WgpuMeshRenderer.pipeline_for(packed.objects[0].geometry) == "gauss"


def test_splat_surface_rendered_frame_is_not_flat():
    wgpu = pytest.importorskip("wgpu")
    positions = np.array(
        [[0.0, 0.0, 0.0], [0.8, 0.0, 0.0], [0.0, 0.8, 0.0]], dtype=np.float32
    )
    colors = np.array(
        [[1.0, 0.2, 0.2, 1.0], [0.2, 1.0, 0.2, 1.0], [0.2, 0.2, 1.0, 1.0]],
        dtype=np.float32,
    )
    radii = np.array([2.0, 2.0, 2.0], dtype=np.float32)
    geometry = Geometry(
        kind="gauss",
        positions=positions,
        colors=colors,
        radii=radii,
        meta={"gauss": {"decay": 2.0, "iso": 0.5, "opacity": 1.0}},
    )
    packed = _packed([SceneObject(id="surface", geometry=geometry)])
    view = pack_view_state(np.eye(3), 10.0, (0.0, 0.0, 0.0), 0.1, 100.0)
    try:
        image = WgpuMeshRenderer(*SIZE).render(
            packed, view, background=(0.1, 0.1, 0.1), target_radius=6.0
        )
    except Exception as e:
        pytest.skip(f"GPU render skipped: {e}")

    bg = np.array([25, 25, 25], dtype=np.uint8)
    diff = np.abs(image.astype(np.int16) - bg.astype(np.int16)).sum(axis=2)
    mask = diff > 20
    assert mask.sum() > 100, "Splat surface should render visible pixels"

    rendered_pixels = image[mask]
    std = rendered_pixels.std(axis=0)
    assert std.max() > 5.0, "Splat surface relief must not be flat grey"
