"""Packed scenes must be in the one layout a GPU can accept.

This is the contract every backend relies on and none of them can check for
itself: float32 attributes, uint32 indices, C-contiguous, in-range, finite. The
Qt backend used to coerce each array at upload time, so the guarantee lived in
one backend rather than in the scene, and a second backend had no way to know
what it was being handed.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("CHISURF_SETTINGS_DIR", tempfile.mkdtemp(prefix="chimol_pack_"))

_PDB = Path("test/data/atomic_coordinates/pdb_files/148l.pdb")
REPRESENTATIONS = ("cartoon", "sticks", "spheres", "surface", "lines")


@pytest.fixture(scope="module")
def qapp():
    """Keep the QApplication alive for the module.

    It has to be *bound*: an unreferenced ``QApplication([])`` is collected as
    soon as the expression ends, and the next ``QWidget`` construction aborts the
    interpreter rather than raising.
    """
    pytest.importorskip("qtpy")
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def scenes(qapp):
    """One assembled Scene per representation, built without a display."""
    from chimol.cmd.command import Cmd
    from chimol.io.structure import load_structure_payload
    from chimol.renderer.headless import SceneSink
    from chimol.renderer.view import MolView

    viewer = MolView(renderer_factory=SceneSink)
    _structure, payload = load_structure_payload(_PDB)
    viewer.apply_payload(payload)

    class _Window:
        def __init__(self, v):
            self.viewer = v

    cmd = Cmd(None)
    cmd.set_window(_Window(viewer))
    out = {}
    for rep in REPRESENTATIONS:
        cmd.do(f"hide everything; show {rep}")
        out[rep] = viewer._scene
    return out


@pytest.mark.parametrize("representation", REPRESENTATIONS)
def test_packed_arrays_are_upload_ready(scenes, representation):
    """Every array must be float32/uint32, contiguous, in range and finite."""
    from chimol.renderer.pack import pack_scene

    packed = pack_scene(scenes[representation])
    assert packed.objects, f"{representation}: nothing was assembled"

    for obj in packed.objects:
        geom = obj.geometry
        for name in ("positions", "normals", "colors", "radii", "occlusion"):
            arr = getattr(geom, name)
            if arr is None:
                continue
            assert arr.dtype == np.float32, f"{obj.id}.{name} is {arr.dtype}, not float32"
            assert arr.flags["C_CONTIGUOUS"], f"{obj.id}.{name} is not contiguous"
            assert np.isfinite(arr).all(), f"{obj.id}.{name} has NaN or inf"
        if geom.indices is not None:
            assert geom.indices.dtype == np.uint32, (
                f"{obj.id}.indices is {geom.indices.dtype}, not uint32"
            )
            assert geom.indices.flags["C_CONTIGUOUS"]
            if geom.indices.size:
                assert int(geom.indices.max()) < geom.vertex_count, (
                    f"{obj.id}: index out of range"
                )


def test_packing_preserves_the_geometry(scenes):
    """Packing changes dtype and nothing else."""
    from chimol.renderer.pack import pack_scene

    scene = scenes["cartoon"]
    packed = pack_scene(scene)
    assert [o.id for o in packed.objects] == [o.id for o in scene.objects]
    for src, dst in zip(scene.objects, packed.objects):
        a = np.asarray(src.geometry.positions, dtype=np.float64)
        b = dst.geometry.positions.astype(np.float64)
        assert a.shape == b.shape
        # float32 rounding only -- relative to the model's own extent
        extent = max(float(np.abs(a).max()), 1.0)
        assert np.abs(a - b).max() <= extent * 1e-6, "positions moved"
        assert src.render_mode == dst.render_mode


def test_a_bad_array_is_reported_not_repaired():
    """NaNs and out-of-range indices must raise, not be silently dropped."""
    from chimol.renderer.pack import pack_geometry
    from chimol.renderer.scene import Geometry

    good = np.zeros((3, 3), dtype=np.float64)
    with pytest.raises(ValueError, match="NaN"):
        bad = good.copy()
        bad[1, 1] = np.nan
        pack_geometry(Geometry(kind="mesh", positions=bad, indices=np.array([0, 1, 2])))
    with pytest.raises(ValueError, match="indices"):
        pack_geometry(Geometry(kind="mesh", positions=good, indices=np.array([0, 1, 9])))
    with pytest.raises(ValueError, match="multiple of 3"):
        pack_geometry(Geometry(kind="mesh", positions=good, indices=np.array([0, 1])))
