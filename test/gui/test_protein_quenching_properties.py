"""The real quenching parameter/widget properties preserve exclusion and rate semantics."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.structure import Structure
from chisurf.core.structure.av.parameters import ProteinQuenching

SOURCE = Path(__file__).resolve().parents[1] / "data/atomic_coordinates/pdb_files/148l.pdb"
RATES = {"TRP": 3.5, "TYR": 2.0}


@pytest.fixture
def structure():
    """Use the real 148L residue/atom identities and coordinates for an independent oracle."""
    return Structure(p_object=str(SOURCE), make_coarse=False)


def _indices(structure, excluded, all_atoms):
    """Compute expected atom membership from physical residue/name rules without model helpers."""
    return {
        index
        for index, atom in enumerate(structure.atoms)
        if atom["res_name"] in RATES
        and atom["atom_name"] not in excluded
        and (all_atoms or atom["atom_name"] == "CB")
    }


@pytest.mark.parametrize("all_atoms", [False, True])
def test_core_all_atoms_flag_selects_real_coordinates_and_preserves_rates(structure, all_atoms):
    """The true/false property controls selection while per-residue rates retain their units."""
    excluded = {"N", "CA", "C", "O"}
    model = ProteinQuenching(structure=structure, excluded_atoms=excluded, quench_scale=0.4)
    model.all_atoms_quench = all_atoms
    assert model.all_atoms_quench is all_atoms
    model.quencher = {residue: {"atoms": ["CB"], "rate": rate} for residue, rate in RATES.items()}
    indices = np.concatenate([model.quencher[residue]["atom_idx"] for residue in RATES])
    assert set(indices) == _indices(structure, excluded, all_atoms)
    np.testing.assert_array_equal(model.xyz, structure.xyz[indices])
    expected_rates = [0.4 * RATES[structure.atoms[index]["res_name"]] for index in indices]
    np.testing.assert_allclose(model.k_quench, expected_rates, rtol=1e-7)
    assert model.k_quench.dtype == np.float32


@pytest.mark.parametrize("all_atoms", [False, True])
def test_explicit_atom_lists_keep_their_existing_selection_contract(structure, all_atoms):
    """Explicit atom lists keep their exact atoms/default rate regardless of all-atoms mode."""
    model = ProteinQuenching(
        structure=structure,
        all_atoms_quench=all_atoms,
        excluded_atoms={"CA"},
        quench_scale=0.4,
        quenching_amino_acids={"TRP": ["CA", "CB"]},
    )
    expected = {
        i
        for i, atom in enumerate(structure.atoms)
        if atom["res_name"] == "TRP" and atom["atom_name"] in {"CA", "CB"}
    }
    assert set(model.quencher["TRP"]["atom_idx"]) == expected
    assert model.quencher["TRP"]["rate"] == 1.0
    np.testing.assert_allclose(model.k_quench, 0.4)


def test_widget_exclusions_assignment_initialization_and_text_reach_model(qtbot, structure):
    """The existing editor is writable and its actual text governs owning model exclusions."""
    # The cold-import contract is tested independently below; this is a normal
    # application import of the declared scientific module, not a replacement.
    import chisurf.core.fitting.parameter
    from chisurf.gui.widgets.fluorescence.av import ProteinQuenchingWidget

    widget = ProteinQuenchingWidget(
        structure=structure, excluded_atoms=["CA", "N"], quenching_amino_acids={"TRP": ["CB"]}
    )
    qtbot.addWidget(widget)
    assert widget.excluded_atoms == ["CA", "N"]
    widget.excluded_atoms = ["CB", "CG"]
    assert widget.lineEdit_6.text() == "CB CG"
    assert set(widget._excluded_atoms) == {"CB", "CG"}
    widget.lineEdit_6.setText("N CA CB")
    widget.all_atoms_quench = True
    config = {residue: {"atoms": ["CB"], "rate": rate} for residue, rate in RATES.items()}
    # Exercise the owning model's computation on this real subclass. Its
    # display-only quencher override intentionally still lists residue names.
    ProteinQuenching.quencher.fset(widget, config)
    computed = ProteinQuenching.quencher.fget(widget)
    indices = np.concatenate([computed[residue]["atom_idx"] for residue in RATES])
    assert set(indices) == _indices(structure, {"N", "CA", "CB"}, True)
    assert widget.quencher == {"TRP": ["CB"]}


def test_widget_constructs_cold_and_editor_updates_owning_parameter(tmp_path):
    """A fresh namespace owns its imports and keeps numeric model/editor state connected."""
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["CHISURF_SETTINGS_DIR"] = str(tmp_path)
    root = Path(__file__).resolve().parents[2]
    environment["PYTHONPATH"] = os.pathsep.join([str(root), environment.get("PYTHONPATH", "")])
    code = f"""
from qtpy import QtWidgets
from chisurf.core.parameter import Parameter
from chisurf.core.structure import Structure
from chisurf.gui.widgets.fluorescence.av import ProteinQuenchingWidget
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
structure = Structure(p_object={str(SOURCE)!r}, make_coarse=False)
assert 'chisurf.gui.widgets.fitting.widgets' not in __import__('sys').modules
widget = ProteinQuenchingWidget(structure=structure, k_quench_protein=2.5)
assert 'chisurf.gui.widgets.fitting.widgets' not in __import__('sys').modules
assert isinstance(widget._k_quench_scale, Parameter)
assert widget.kQ_scale == 2.5
widget.kQ_scale = 3.75
assert widget._k_quench_scale.value == 3.75
widget.close()
widget.deleteLater()
app.processEvents()
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, 0.01),
        ({"quench_scale": 0.4}, 0.4),
        ({"k_quench_protein": 2.5}, 2.5),
        ({"quench_scale": 0.7, "k_quench_protein": 2.5}, 0.7),
    ],
)
def test_widget_scale_binding_preserves_canonical_inputs_and_parameter_identity(
    qtbot, structure, options, expected
):
    """Default/canonical scale wins, the explicit GUI alias works, and real editor edits stay linked."""
    from chisurf.gui.widgets.fluorescence.av import ProteinQuenchingWidget

    widget = ProteinQuenchingWidget(structure=structure, **options)
    qtbot.addWidget(widget)
    parameter = widget._k_quench_scale
    editor = widget._k_quench_editor
    assert editor.fitting_parameter is parameter
    assert parameter.description and widget.lineEdit_6.toolTip() and widget.groupBox.toolTip()
    assert widget.kQ_scale == parameter.value == expected
    editor.widget_value.setValue(3.125)
    editor.widget_value.editingFinished.emit()
    assert widget._k_quench_scale is parameter
    assert widget.kQ_scale == parameter.value == 3.125
    widget.kQ_scale = 4.125
    assert editor.fitting_parameter.value == 4.125


@pytest.mark.parametrize("enabled", [False, True])
def test_widget_all_atoms_initialization_and_assignment_match_owning_flag(
    qtbot, structure, enabled
):
    """The constructor flag and existing inverted checkbox retain a writable bool contract."""
    from chisurf.gui.widgets.fluorescence.av import ProteinQuenchingWidget

    widget = ProteinQuenchingWidget(structure=structure, all_atoms_quench=enabled)
    qtbot.addWidget(widget)
    assert widget.all_atoms_quench is enabled
    assert widget.groupBox.isChecked() is (not enabled)
    widget.all_atoms_quench = not enabled
    assert widget.all_atoms_quench is (not enabled)
    assert widget._all_atoms_quench is (not enabled)
