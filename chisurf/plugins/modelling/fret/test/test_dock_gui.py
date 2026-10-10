"""Headless test of the FRET docking model: the form fields map to the right api.operations request."""

from __future__ import annotations


def test_build_params_dock():
    from chisurf.plugins.modelling.fret.gui.docking_model import DockingModel as _DockingModel

    m = _DockingModel()
    m.pdb_paths = "a.pdb, b.pdb"
    m.fps_json = "x.fps.json"
    m.output_dir = "out"
    m.operation = "dock"
    m.sigma_da = 8.0
    op, params = m.build_params()
    assert op == "dock"
    assert params["pdb_paths"] == ["a.pdb", "b.pdb"]
    assert params["fps_json"] == "x.fps.json"
    assert params["sigma_da"] == 8.0


def test_build_params_screen():
    from chisurf.plugins.modelling.fret.gui.docking_model import DockingModel as _DockingModel

    m = _DockingModel()
    m.pdb_paths = "lib/"
    m.fps_json = "x.fps.json"
    m.operation = "screen"
    op, params = m.build_params()
    assert op == "screen"
    assert params["pdb_inputs"] == ["lib/"]


def test_repeats_route_to_errors():
    """Dock + n_repeats>1 becomes an 'errors' (repeated-docking) request."""
    from chisurf.plugins.modelling.fret.gui.docking_model import DockingModel as _DockingModel

    m = _DockingModel()
    m.pdb_paths = "a.pdb"
    m.fps_json = "x.fps.json"
    m.output_dir = "out"
    m.operation = "dock"
    m.n_repeats = 5
    op, params = m.build_params()
    assert op == "errors"
    assert params["n_trials"] == 5
