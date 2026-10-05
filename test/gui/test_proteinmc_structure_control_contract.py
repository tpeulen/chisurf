"""RED regression: ProteinMC GUI-edit contract via the real Structure file control.

The catalogue producer's scientific edit for ProteinMCModel shifts the
residue-86 CA x coordinate by +0.1 A. Coordinates are structural inputs — not
FittingParameters — so the actual-Main probe's parameter diff is empty and it
aborts with 'requires an explicit exposed scientific edit: []'.

The GUI-declared control that performs the SAME scientific operation is the
view's Structure file input (AutoForm 'value' kind='file', call
load_starting_structure): committing a shifted single-model PDB through it
resets the trajectory and recomputes the distance outputs from the file's
coordinates. This test pins that contract at the model level:

- after committing the shifted PDB path through setattr + load_starting_structure,
  the active coordinates equal the shifted PDB's coordinates exactly;
- the distance output CHANGED relative to the unshifted model;
- a second model driven through the identical path produces the identical
  distance value (file-controlled inputs are deterministic);
- the trajectory is reset (sampling would restart from the new structure).
"""

import os
import pathlib
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from test.project.test_structure_snapshot_contracts import _configured_proteinmc


def _shifted_pdb(work: pathlib.Path, model) -> pathlib.Path:
    atoms = model.structure.atoms
    sel = (atoms["res_id"] == 86) & (atoms["atom_name"] == "CA")
    xyz = model.structure.xyz.copy()
    xyz[sel, 0] += 0.1
    shifted_atoms = atoms.copy()
    shifted_atoms["xyz"] = xyz
    from chisurf.core.fio.structure.coordinates import write_pdb

    shifted_pdb = work / "148l-gui-shifted.pdb"
    write_pdb(str(shifted_pdb), shifted_atoms, append_model=False)
    return shifted_pdb


def _commit_structure_file(model, path) -> None:
    """Exactly what the AutoForm file control does on editingFinished.

    ``_BoundControlMixin._commit`` sets ``attr`` and then calls the declared
    ``call`` method *with the new value*.
    """
    model.structure_file = str(path)
    model.load_starting_structure(str(path))


def test_structure_file_control_performs_producer_coordinate_edit(tmp_path):
    model, pdb, labeling = _configured_proteinmc(tmp_path)
    atoms = model.structure.atoms
    sel = (atoms["res_id"] == 86) & (atoms["atom_name"] == "CA")
    expected_xyz = model.structure.xyz.copy()
    expected_xyz[sel, 0] += 0.1
    base_distance = model._distance_parameters["47-86"].value

    shifted_pdb = _shifted_pdb(tmp_path, model)
    _commit_structure_file(model, shifted_pdb)

    got = model._active_coordinates()
    assert np.array_equal(got, expected_xyz) or np.max(np.abs(got - expected_xyz)) < 1e-6
    assert model._distance_parameters["47-86"].value != base_distance
    # The loaded file is the *starting* structure: it is what the project
    # persists beside ``structure_source``, so it must not stay stale.
    assert np.max(np.abs(np.asarray(model.structure.xyz) - expected_xyz)) < 1e-6
    assert model.structure is not model.proteinmc_structure


def test_structure_file_control_is_deterministic(tmp_path):
    first, pdb, labeling = _configured_proteinmc(tmp_path)
    shifted_pdb = _shifted_pdb(tmp_path, first)
    _commit_structure_file(first, shifted_pdb)

    second, _, _ = _configured_proteinmc(tmp_path)
    _commit_structure_file(second, shifted_pdb)
    assert first._distance_parameters["47-86"].value == second._distance_parameters["47-86"].value


def test_trajectory_resets_on_structure_commit(tmp_path):
    model, pdb, labeling = _configured_proteinmc(tmp_path)
    model.trajectory_frames = [model.structure.xyz.copy()]
    model.current_frame_index = 0
    shifted_pdb = _shifted_pdb(tmp_path, model)
    _commit_structure_file(model, shifted_pdb)
    assert model.trajectory_frames == []
    assert model.current_frame_index == 0


def test_view_calls_accept_the_committed_value():
    """Every bound control's ``call`` receives the committed value.

    The Structure, Labelling and Score-set controls declared zero-argument
    methods; ``_commit`` raised TypeError inside its ``try`` and logged a
    warning, so editing them in the GUI silently did nothing.
    """
    import inspect
    import json

    from chisurf.core.models.structure.proteinmc_model import ProteinMCModel

    view = pathlib.Path(inspect.getfile(ProteinMCModel)).with_name("proteinmc.view.json")

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") in {"value", "choice"} and node.get("call"):
                yield node["call"]
            for child in node.values():
                yield from walk(child)
        elif isinstance(node, list):
            for child in node:
                yield from walk(child)

    calls = list(walk(json.loads(view.read_text())))
    assert {"load_starting_structure", "on_labeling_file_changed", "reload_distances"} <= set(calls)
    for call in calls:
        inspect.signature(getattr(ProteinMCModel, call)).bind(object(), "committed")
