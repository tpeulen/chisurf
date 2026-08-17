"""Rendering tests for the FRET accessible-volume 3D viewer.

AVs are rendered as a transparent isosurface *envelope* of the point cloud, not
as a cloud of thousands of transparent sphere sprites (which is fragment-overdraw
bound and slow to rotate). These tests pin that contract.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtWidgets

from chimol.core.viewer import _DISPLAY_CONFIG
from chisurf.plugins.modelling.fret.core.av_viewer_3d import AVViewer3D


@pytest.fixture
def _qt_app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def _dense_av(n: int = 60000) -> np.ndarray:
    """Return a dense, ellipsoidal accessible-volume-like point cloud."""
    rng = np.random.default_rng(1)
    p = rng.standard_normal((n, 3))
    p = p / np.linalg.norm(p, axis=1, keepdims=True) * rng.uniform(0, 1, (n, 1)) ** (1 / 3)
    return p * np.array([16.0, 11.0, 11.0])


def test_show_av_renders_a_transparent_surface_mesh(_qt_app):
    viewer = AVViewer3D()
    viewer.mol_view._update_view = lambda *a, **k: None
    viewer.mol_view.set_coordinates(np.random.default_rng(0).standard_normal((200, 3)) * 10)

    av = _dense_av(60000)
    viewer.show_av("donor", av, color=(0.0, 1.0, 0.5, 0.5))

    objs = viewer.mol_view._update_custom_overlays(_DISPLAY_CONFIG.get("surface", {})) or []
    assert objs, "show_av produced no overlay geometry"

    surf = [o for o in objs if o.geometry.kind == "mesh"]
    assert surf, "AV overlay is not a surface mesh (a transparent point cloud is what we avoid)"
    obj = surf[0]
    assert obj.render_mode == "transparent"
    # A closed envelope is a few thousand triangles, orders of magnitude fewer
    # primitives than the 60k input points would be as sprites.
    n_tris = obj.geometry.indices.shape[0]
    assert 0 < n_tris < av.shape[0], f"surface has {n_tris} tris, expected far fewer than {av.shape[0]}"


def test_point_overlay_caps_dense_clouds(_qt_app):
    """The point-overlay path (dye densities etc.) subsamples huge clouds."""
    viewer = AVViewer3D()
    viewer.mol_view._update_view = lambda *a, **k: None
    viewer.mol_view.set_coordinates(np.random.default_rng(0).standard_normal((200, 3)) * 10)

    cloud = np.random.default_rng(2).standard_normal((150000, 3)) * 15
    viewer.mol_view.add_point_overlay("d", cloud, alpha=0.5, transform_to_scene=False, max_points=25000)
    assert viewer.mol_view._point_overlays["d"]["coords"].shape[0] == 25000
