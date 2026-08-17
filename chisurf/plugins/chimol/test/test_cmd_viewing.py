"""Tests for the PyMOL-parity viewing/transform commands.

Covers the ``turn`` / ``move`` / ``clip`` camera commands (dispatched to the
viewer) and the ``rotate`` / ``translate`` object-transform commands.
"""

from __future__ import annotations

import numpy as np

from chimol.commands.command import Cmd
from chimol.testing.mock_viewer import MockViewer, MockWindow


def _cmd_with_object():
    viewer = MockViewer()
    window = MockWindow(viewer)
    cmd = Cmd(window)
    oid = viewer.create_object(name="m").object_id
    atoms = np.zeros(3, dtype=[("xyz", float, 3)])
    atoms["xyz"] = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    viewer.objects[oid].state.atoms = atoms
    viewer.objects[oid].state.all_atom_coords = atoms["xyz"].copy()
    viewer.set_active_object(oid)
    return cmd, viewer, oid


def test_viewing_commands_registered():
    cmd = Cmd(MockWindow(MockViewer()))
    for name in ("turn", "move", "clip", "rotate", "translate"):
        assert cmd._registry.resolve(name) is not None


def test_rotate_applies_pymol_rotation():
    """``rotate x, 90`` rotates points +90 deg about X: (0,1,0) -> (0,0,1)."""
    cmd, viewer, oid = _cmd_with_object()
    cmd.do("rotate x, 90")
    coords = viewer.objects[oid].state.all_atom_coords
    assert np.allclose(coords[0], [1.0, 0.0, 0.0], atol=1e-6)   # on axis
    assert np.allclose(coords[1], [0.0, 0.0, 1.0], atol=1e-6)   # y -> z
    assert np.allclose(coords[2], [0.0, -1.0, 0.0], atol=1e-6)  # z -> -y


def test_translate_shifts_coordinates():
    cmd, viewer, oid = _cmd_with_object()
    cmd.do("translate [5, -2, 0]")
    coords = viewer.objects[oid].state.all_atom_coords
    assert np.allclose(coords[0], [6.0, -2.0, 0.0], atol=1e-6)
    assert np.allclose(coords[1], [5.0, -1.0, 0.0], atol=1e-6)


def test_turn_move_clip_dispatch_to_viewer():
    cmd, viewer, _ = _cmd_with_object()
    cmd.do("turn y, 45")
    cmd.do("move z, 10")
    cmd.do("clip slab, 8")
    calls = getattr(viewer, "_nav_calls", [])
    assert ("turn", "y", 45.0) in calls
    assert ("move", "z", 10.0) in calls
    assert ("clip", "slab", 8.0) in calls


# --------------------------------------------------------------------------- #
# `translate` is in Angstrom, as PyMOL's is
# --------------------------------------------------------------------------- #
# The renderer holds coordinates in scene units, so a command that takes
# Angstrom has to convert. Without that `translate [100,0,0]` moved the molecule
# 10 A -- invisible on screen, and only caught once `save` wrote the result out.


def test_translate_is_in_angstrom_not_scene_units(qapp):
    """``translate`` moves atoms by Angstrom, not by scene units.

    Takes ``qapp`` rather than making its own application. It used to open with
    ``QApplication.instance() or QApplication([])`` as a bare statement, which
    keeps no reference to the application it may have just constructed -- so it
    was collected again immediately, and the ``MolView()`` below aborted the
    interpreter with ``Fatal Python error: Aborted`` rather than failing. The
    test passed anyway whenever some earlier file in the same session had left
    a live application behind, which is why it survived: it is the only test in
    this mock-based file that builds a real widget.
    """
    import pathlib

    import pytest

    cs_struct = pytest.importorskip("chisurf.core.structure")

    from chimol.commands.command import Cmd
    from chimol.io.export import unscale_coordinates
    from chimol.io.structure import _read_full_model
    from chimol.core.viewer import MolView

    pdb = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )
    view = MolView()
    view.add_structure(
        _read_full_model(cs_struct.Structure, pdb), name="148l",
        source_path=str(pdb),
    )

    class _Window:
        viewer = view

    def angstrom_x():
        return unscale_coordinates(
            view._all_atom_coords,
            float(view._scale_factor),
            view._raw_center,
        )[:, 0].mean()

    before = angstrom_x()
    Cmd(_Window()).do("translate [100, 0, 0]")
    after = angstrom_x()
    assert after - before == pytest.approx(100.0, abs=1e-6)
