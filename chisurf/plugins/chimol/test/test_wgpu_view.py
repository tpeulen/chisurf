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
    """``CHIMOL_RENDERER`` picks the backend, and never leaves the viewer blank."""

    def test_unset_keeps_the_default(self, monkeypatch):
        monkeypatch.delenv("CHIMOL_RENDERER", raising=False)
        sentinel = object()
        assert wgpu_view.renderer_factory_from_env(sentinel) is sentinel

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
