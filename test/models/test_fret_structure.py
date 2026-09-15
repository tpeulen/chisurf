"""The structure-ensemble FRET model: PDB files in, one fraction each.

The fit itself is IMP.bff's tcspc_fret_tabulated (pinned against the classic
model in test/fitting/test_fret_views.py); these check what the ChiSurf side
owns -- loading structures, their label settings, the editor and persistence.
"""
import pathlib

import numpy as np
import pytest

import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.structure
import chisurf.core.models.tcspc.fret_structure as fret_structure

PDBS = pathlib.Path(__file__).resolve().parents[1] / "data" / "atomic_coordinates" / "pdb_files"


def _fit():
    x = np.arange(256) * 0.05
    data = chisurf.core.data.DataCurve(x=x, y=np.ones_like(x), ey=np.ones_like(x))
    return chisurf.core.fitting.fit.FitGroup(data=chisurf.core.data.DataGroup([data]))


def test_structures_append_and_pop():
    model = fret_structure.FRETStructure(fit=_fit(), res_1=18, res_2=577, atom_name_1="CB", atom_name_2="CB")
    model.append(chisurf.core.structure.Structure(str(PDBS / "hGBP1_closed.pdb")), amplitude=0.6)
    assert model.names == ["hGBP1_closed"] or len(model.names) == 1
    assert model.get_scalar("number_of_distributions") == 1.0
    assert model.res_2 == 577
    model.pop()
    assert model.names == []


def test_the_editor_offers_labels_and_the_structure_list(qtbot):
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    model = fret_structure.FRETStructure(fit=_fit())
    titles = [getattr(s, "title", "") for s in model.view_spec().sections]
    assert "Labels / AV" in titles and "Structures" in titles
    model.res_1 = 18
    assert model.res_1 == 18
    qtbot.addWidget(build_model_editor(model))


def test_a_classic_project_reopens_with_its_structures():
    classic_state = {"extra": {"res_1": 18, "res_2": 577, "atom_name_1": "CB", "atom_name_2": "CB",
                               "structures": [{"name": "hGBP1_closed", "filename": str(PDBS / "hGBP1_closed.pdb"),
                                               "amplitude": 0.6}]}}
    model = fret_structure.FRETStructure(fit=_fit())
    model.set_state(classic_state)
    assert model.res_1 == 18 and model.atom_name_2 == "CB"
    assert model.structure_files == [str(PDBS / "hGBP1_closed.pdb")]
