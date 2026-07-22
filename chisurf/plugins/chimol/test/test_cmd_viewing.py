"""Tests for the PyMOL-parity viewing/transform commands.

Covers the ``turn`` / ``move`` / ``clip`` camera commands (dispatched to the
viewer) and the ``rotate`` / ``translate`` object-transform commands.
"""

from __future__ import annotations

import numpy as np

from chisurf.plugins.chimol.chimol.cmd.command import Cmd
from chisurf.plugins.chimol.chimol.testing.mock_viewer import MockViewer, MockWindow


def _cmd_with_object():
    viewer = MockViewer()
    window = MockWindow(viewer)
    cmd = Cmd(window)
    oid = viewer._create_object(name="m")
    atoms = np.zeros(3, dtype=[("xyz", float, 3)])
    atoms["xyz"] = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    viewer._objects[oid].state.atoms = atoms
    viewer._objects[oid].state.all_atom_coords = atoms["xyz"].copy()
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
    coords = viewer._objects[oid].state.all_atom_coords
    assert np.allclose(coords[0], [1.0, 0.0, 0.0], atol=1e-6)   # on axis
    assert np.allclose(coords[1], [0.0, 0.0, 1.0], atol=1e-6)   # y -> z
    assert np.allclose(coords[2], [0.0, -1.0, 0.0], atol=1e-6)  # z -> -y


def test_translate_shifts_coordinates():
    cmd, viewer, oid = _cmd_with_object()
    cmd.do("translate [5, -2, 0]")
    coords = viewer._objects[oid].state.all_atom_coords
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
