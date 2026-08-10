"""The WebGPU renderer as chimol's viewport.

These need a WebGPU adapter and a Qt widget, so they skip where there is
neither. What they cover is the seam: that the viewer accepts this backend as a
renderer, that the camera it reports is the camera the offscreen comparison
would use, and that the gestures and the chrome do what the OpenGL backend's do.
"""
from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.renderer import wgpu_view

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def renderer(qt_app):
    """A shown WebGPU renderer, or a skip when the machine cannot make one."""
    if not wgpu_view.is_available():
        pytest.skip("no WebGPU adapter")
    try:
        view = wgpu_view.WgpuRenderer()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"WebGPU renderer unavailable: {exc!r}")
    view.resize(640, 480)
    view.show()
    for _ in range(10):
        qt_app.processEvents()
    yield view
    view.close()


@pytest.fixture(scope="module")
def qt_app():
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    # Bound, not discarded: an unreferenced QApplication is collected and the
    # next QWidget aborts the interpreter with no Python traceback.
    assert app is not None
    return app


class TestFactorySelection:
    """The configuration picks the backend, and never leaves the viewer blank."""

    def test_unset_selects_wgpu(self, monkeypatch):
        """Nothing configured means the WGSL renderer -- that is the default."""
        monkeypatch.delenv("CHIMOL_RENDERER", raising=False)
        monkeypatch.setattr(wgpu_view, "is_available", lambda: True)
        from chisurf.plugins.chimol.chimol.config import _DISPLAY_CONFIG

        monkeypatch.setitem(_DISPLAY_CONFIG, "renderer", {})
        assert wgpu_view.renderer_factory_from_env(object()) is wgpu_view.WgpuRenderer

    def test_another_value_keeps_the_default(self, monkeypatch):
        monkeypatch.setenv("CHIMOL_RENDERER", "opengl")
        sentinel = object()
        assert wgpu_view.renderer_factory_from_env(sentinel) is sentinel

    def test_wgpu_selects_this_backend_when_it_can_run(self, monkeypatch):
        monkeypatch.setenv("CHIMOL_RENDERER", "wgpu")
        monkeypatch.setattr(wgpu_view, "is_available", lambda: True)
        assert wgpu_view.renderer_factory_from_env(object()) is wgpu_view.WgpuRenderer

    def test_falls_back_when_there_is_no_adapter(self, monkeypatch):
        """A window with nothing in it is worse than the old renderer."""
        monkeypatch.setenv("CHIMOL_RENDERER", "wgpu")
        monkeypatch.setattr(wgpu_view, "is_available", lambda: False)
        sentinel = object()
        assert wgpu_view.renderer_factory_from_env(sentinel) is sentinel


class TestRendererContract:
    """What ``MolView`` requires of a renderer."""

    def test_it_is_a_widget_and_returns_itself(self, renderer):
        from qtpy import QtWidgets

        assert isinstance(renderer, QtWidgets.QWidget)
        assert renderer.widget() is renderer

    def test_the_camera_round_trips(self, renderer):
        """A view tuple that does not survive a round trip cannot reproduce a frame."""
        renderer.fit_to_radius(30.0)
        before = list(renderer.get_view_state())
        renderer.set_view_state(before)
        assert renderer.get_view_state() == pytest.approx(before)

    def test_a_scene_is_packed_once_not_per_frame(self, renderer):
        from chisurf.plugins.chimol.chimol.renderer.scene import (
            Geometry,
            Scene,
            SceneObject,
        )

        geom = Geometry(
            kind="mesh",
            positions=np.zeros((3, 3), dtype=np.float32),
            indices=np.arange(3, dtype=np.int32),
        )
        renderer.set_scene(Scene(objects=[SceneObject(id="o", geometry=geom)]))
        assert renderer._packed is not None
        assert renderer._packed.objects[0].geometry.indices.dtype == np.uint32
        renderer.clear()
        assert renderer._packed is None


class TestGestures:
    """The mouse, against the same trackball the OpenGL backend uses."""

    def test_an_orbit_turns_the_camera(self, renderer):
        before = np.array(renderer.get_view_state()[:9])
        renderer.orbit((100.0, 100.0), (180.0, 140.0))
        after = np.array(renderer.get_view_state()[:9])
        assert not np.allclose(before, after)
        # Still a rotation: a drag that shears the basis is a drag that will
        # eventually turn the molecule inside out.
        r = after.reshape(3, 3)
        assert np.allclose(r @ r.T, np.eye(3), atol=1e-6)
        assert float(np.linalg.det(r)) == pytest.approx(1.0, abs=1e-6)

    def test_a_dolly_is_multiplicative(self, renderer):
        """One notch has to feel the same on a peptide and on a ribosome."""
        renderer._distance = 100.0
        renderer.dolly(1.1)
        assert renderer._distance == pytest.approx(110.0)
        renderer.dolly(1.0 / 1.1)
        assert renderer._distance == pytest.approx(100.0)

    def test_a_pan_moves_the_target_in_the_view_plane(self, renderer):
        renderer.look_at(np.zeros(3))
        renderer.pan(20.0, 0.0)
        moved = renderer._target.copy()
        assert np.linalg.norm(moved) > 0.0
        # Along the camera's right axis, which is what "the molecule stays under
        # the cursor" means.
        right, _up = renderer.camera_axes()
        assert abs(abs(float(np.dot(moved / np.linalg.norm(moved), right))) - 1.0) < 1e-6


class TestChrome:
    """The object panel and the sequence strip."""

    def test_the_panel_takes_a_column_from_the_scene(self, renderer):
        gui = renderer._internal_gui
        gui.visible = True
        gui.docked = True
        with_panel = renderer.scene_width()
        gui.visible = False
        without = renderer.scene_width()
        gui.visible = True
        assert with_panel < without, "a docked panel must reserve its column"

    def test_the_strip_takes_a_band_and_the_viewport_starts_below_it(self, renderer):
        x, y, _w, h = renderer._scene_viewport()
        assert x == 0.0
        strip = renderer._internal_gui.sequence_height()
        if strip:
            # Top-left origin in WebGPU, where GL's is bottom-left and the same
            # band falls out of a shorter viewport with no offset at all.
            assert y > 0.0
            assert h == pytest.approx(renderer.scene_height())

    def test_the_chrome_paints_something_with_transparency(self, renderer):
        chrome = renderer._chrome_image()
        assert chrome is not None
        assert chrome.shape == (renderer._height, renderer._width, 4)
        alpha = chrome[..., 3]
        assert alpha.max() == 255, "nothing was painted"
        assert alpha.min() == 0, "the chrome is opaque, so it would hide the molecule"


class TestItDrawsTheSamePictureAsTheComparisonHarness:
    """The window and the offscreen baseline comparison share one code path."""

    def test_a_frame_comes_back_with_the_scene_in_it(self, renderer):
        from chisurf.plugins.chimol.chimol.renderer.pack import (
            PackedGeometry,
            PackedObject,
            PackedScene,
        )
        from chisurf.plugins.chimol.chimol.renderer.scene import Geometry, Scene, SceneObject
        from chisurf.plugins.chimol.chimol.renderer.view_state import pack_view_state

        # One big triangle, so "did anything draw" cannot be answered by noise.
        geom = Geometry(
            kind="mesh",
            positions=np.array(
                [[-10.0, -10.0, 0.0], [10.0, -10.0, 0.0], [0.0, 10.0, 0.0]],
                dtype=np.float32,
            ),
            normals=np.tile(np.array([[0.0, 0.0, 1.0]], dtype=np.float32), (3, 1)),
            colors=np.tile(np.array([[1.0, 0.0, 0.0, 1.0]], dtype=np.float32), (3, 1)),
            indices=np.arange(3, dtype=np.int32),
        )
        renderer.set_scene(Scene(objects=[SceneObject(id="tri", geometry=geom)]))
        renderer.set_view_state(
            pack_view_state(np.eye(3), 60.0, (0.0, 0.0, 0.0), 1.0, 200.0, 20.0)
        )
        image = renderer.grab_image()
        assert image.shape[2] == 3
        red = (image[..., 0].astype(int) - image[..., 2]) > 30
        assert red.sum() > 100, "the triangle did not draw"


class TestTheDefaultBackend:
    """WGSL is what chimol uses unless something says otherwise."""

    def test_the_default_is_wgpu(self, monkeypatch):
        monkeypatch.delenv("CHIMOL_RENDERER", raising=False)
        from chisurf.plugins.chimol.chimol.config import _DISPLAY_CONFIG

        monkeypatch.setitem(_DISPLAY_CONFIG, "renderer", {})
        assert wgpu_view.selected_backend() == "wgpu"
        assert wgpu_view.DEFAULT_BACKEND == "wgpu"

    def test_the_shipped_config_says_so_too(self):
        """The default must be visible where a user would look for it."""
        import json
        import pathlib

        import chisurf.plugins.chimol.chimol as chimol_pkg

        path = pathlib.Path(chimol_pkg.__file__).with_name("chimol_display.json")
        shipped = json.loads(path.read_text())
        assert shipped["renderer"]["backend"] == "wgpu"

    def test_the_config_can_choose_opengl(self, monkeypatch):
        monkeypatch.delenv("CHIMOL_RENDERER", raising=False)
        from chisurf.plugins.chimol.chimol.config import _DISPLAY_CONFIG

        monkeypatch.setitem(_DISPLAY_CONFIG, "renderer", {"backend": "opengl"})
        assert wgpu_view.selected_backend() == "opengl"
        sentinel = object()
        assert wgpu_view.renderer_factory_from_env(sentinel) is sentinel

    def test_the_environment_overrides_the_config(self, monkeypatch):
        """What makes a bug report reproducible without editing a config file."""
        from chisurf.plugins.chimol.chimol.config import _DISPLAY_CONFIG

        monkeypatch.setitem(_DISPLAY_CONFIG, "renderer", {"backend": "opengl"})
        monkeypatch.setenv("CHIMOL_RENDERER", "wgpu")
        assert wgpu_view.selected_backend() == "wgpu"


class TestLabels:
    """``kind == "text"`` geometry, which leaves the GPU path and returns as glyphs."""

    def test_text_geometry_becomes_labels(self):
        from chisurf.plugins.chimol.chimol.renderer.pack import (
            PackedGeometry,
            PackedObject,
            PackedScene,
        )

        geom = PackedGeometry(
            kind="text",
            positions=np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32),
            colors=np.array(
                [[1.0, 0.0, 0.0, 1.0], [0.0, 1.0, 0.0, 1.0]], dtype=np.float32
            ),
            meta={"labels": ["ALA", "GLY"]},
        )
        labels = wgpu_view._collect_labels(
            PackedScene([PackedObject("l", geom)], radius=1.0)
        )
        assert [label.text for label in labels] == ["ALA", "GLY"]
        assert labels[0].color == (1.0, 0.0, 0.0, 1.0)

    def test_more_positions_than_texts_is_not_an_error(self):
        """A builder that emits a position per atom and a text per residue."""
        from chisurf.plugins.chimol.chimol.renderer.pack import (
            PackedGeometry,
            PackedObject,
            PackedScene,
        )

        geom = PackedGeometry(
            kind="text",
            positions=np.zeros((5, 3), dtype=np.float32),
            meta={"labels": ["one"]},
        )
        labels = wgpu_view._collect_labels(
            PackedScene([PackedObject("l", geom)], radius=1.0)
        )
        assert len(labels) == 1

    def test_labels_are_drawn_into_the_chrome(self, renderer):
        """A label that is collected but never painted is not a label."""
        from chisurf.plugins.chimol.chimol.renderer.gui_overlay import paint_chrome

        renderer._internal_gui.visible = False
        centre = np.array(renderer._target, dtype=float)
        labels = [wgpu_view.Label(centre, "XXXXXXXX", (1.0, 1.0, 1.0, 1.0))]
        blank = paint_chrome(renderer._internal_gui, None, 400, 300, 1.0)
        with_label = paint_chrome(
            renderer._internal_gui, None, 400, 300, 1.0,
            labels=labels, project=lambda pts: (
                np.array([200.0]), np.array([150.0]), np.array([True])
            ),
        )
        renderer._internal_gui.visible = True
        assert with_label[..., 3].sum() > blank[..., 3].sum()


class TestSilhouette:
    """The depth-outline post-pass."""

    def test_off_by_default(self):
        from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WgpuMeshRenderer
        from chisurf.plugins.chimol.chimol.renderer.view_state import unpack_view_state
        from chisurf.plugins.chimol.chimol.renderer.view_state import pack_view_state

        state = unpack_view_state(
            pack_view_state(np.eye(3), 50.0, (0, 0, 0), 1.0, 100.0, 20.0)
        )
        assert WgpuMeshRenderer._silhouette_params(state, {}) is None

    def test_enabled_resolves_the_linearising_ratio(self):
        """`depth_jump` is a fraction of the scene, which needs near/far."""
        from chisurf.plugins.chimol.chimol.renderer.view_state import (
            pack_view_state,
            unpack_view_state,
        )
        from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import WgpuMeshRenderer

        state = unpack_view_state(
            pack_view_state(np.eye(3), 50.0, (0, 0, 0), 2.0, 200.0, 20.0)
        )
        params = WgpuMeshRenderer._silhouette_params(state, {"enabled": True})
        assert params is not None
        assert params["near_far"] == pytest.approx(2.0 / 200.0)
        assert params["thickness"] == pytest.approx(1.0)

    def test_it_changes_the_picture(self, renderer):
        """Off and on must differ, and by outlines rather than by everything.

        A settings test that only asserts "the image changed" passes an
        implementation that changed it for the wrong reason -- which is how an
        inverted occlusion switch survived here once.
        """
        from chisurf.plugins.chimol.chimol.renderer.scene import (
            Geometry,
            Scene,
            SceneObject,
        )
        from chisurf.plugins.chimol.chimol.renderer.view_state import pack_view_state

        # Two offset quads, so there is an internal depth step to outline.
        quads, indices = [], []
        for k, z in enumerate((0.0, -6.0)):
            base = 4 * k
            dx = 3.0 * k
            quads += [
                [-6.0 + dx, -6.0, z], [6.0 + dx, -6.0, z],
                [6.0 + dx, 6.0, z], [-6.0 + dx, 6.0, z],
            ]
            indices += [base, base + 1, base + 2, base, base + 2, base + 3]
        geom = Geometry(
            kind="mesh",
            positions=np.array(quads, dtype=np.float32),
            normals=np.tile(np.array([[0.0, 0.0, 1.0]], dtype=np.float32), (8, 1)),
            colors=np.tile(np.array([[0.7, 0.7, 0.7, 1.0]], dtype=np.float32), (8, 1)),
            indices=np.array(indices, dtype=np.int32),
        )
        renderer.set_scene(Scene(objects=[SceneObject(id="q", geometry=geom)]))
        renderer.set_view_state(
            pack_view_state(np.eye(3), 60.0, (0.0, 0.0, 0.0), 1.0, 200.0, 20.0)
        )
        renderer._internal_gui.visible = False
        try:
            from chisurf.plugins.chimol.chimol.renderer.pack import pack_scene
            from chisurf.plugins.chimol.chimol.renderer.wgpu_backend import (
                WgpuMeshRenderer,
            )

            offscreen = WgpuMeshRenderer(400, 400, device=renderer._gpu.device)
            packed = pack_scene(renderer.scene)
            view = renderer.get_view_state()
            # White, deliberately: the outline's default colour is black, and
            # on the default black background a working silhouette is
            # invisible -- which reads as "it drew nothing".
            white = (1.0, 1.0, 1.0)
            off = offscreen.render(
                packed, view, background=white, silhouette={"enabled": False}
            )
            on = offscreen.render(
                packed, view, background=white,
                silhouette={"enabled": True, "thickness": 2.0},
            )
        finally:
            renderer._internal_gui.visible = True

        changed = (np.abs(off.astype(int) - on.astype(int)).sum(2) > 30)
        assert changed.any(), "the silhouette drew nothing"
        # Outlines are thin: a pass that repainted the whole quad is not one.
        assert changed.mean() < 0.25, "the silhouette changed far too much"


class TestPickingProjection:
    """Where a click lands, which is the projection the frame was drawn with."""

    def test_a_point_at_the_target_projects_to_the_scene_centre(self, renderer):
        renderer._internal_gui.visible = False
        try:
            renderer.look_at(np.zeros(3))
            renderer.set_view_state(
                __import__(
                    "chisurf.plugins.chimol.chimol.renderer.view_state",
                    fromlist=["pack_view_state"],
                ).pack_view_state(np.eye(3), 60.0, (0.0, 0.0, 0.0), 1.0, 200.0, 20.0)
            )
            x, y, visible = renderer.project_to_screen(np.zeros((1, 3)))
            # Read inside the block: with the panel back on, `scene_width` is a
            # column narrower and the expected centre moves with it.
            expected = renderer.scene_width() / renderer._ratio() / 2
        finally:
            renderer._internal_gui.visible = True
        assert bool(visible[0])
        assert x[0] == pytest.approx(expected, rel=0.02)

    def test_the_strip_offsets_the_projection(self, renderer):
        """A y measured from the widget's top is off by the strip's height."""
        assert renderer.scene_origin_y() == renderer._height - renderer.scene_height()

    def test_a_point_behind_the_camera_is_not_visible(self, renderer):
        from chisurf.plugins.chimol.chimol.renderer.view_state import pack_view_state

        renderer.set_view_state(
            pack_view_state(np.eye(3), 60.0, (0.0, 0.0, 0.0), 1.0, 200.0, 20.0)
        )
        # Well behind the eye, which sits 60 in front of the target.
        _x, _y, visible = renderer.project_to_screen(np.array([[0.0, 0.0, 200.0]]))
        assert not bool(visible[0])
