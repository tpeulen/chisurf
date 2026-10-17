"""The structure-ensemble FRET model: PDB files in, one fraction each.

The fit itself is IMP.bff's tcspc_fret_tabulated (pinned against the classic
model in test/fitting/test_fret_views.py); these check what the ChiSurf side
owns -- loading structures, their label settings, the editor and persistence.
"""

import pathlib

import numpy as np

import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.tcspc.fret_structure as fret_structure
import chisurf.core.structure

PDBS = pathlib.Path(__file__).resolve().parents[1] / "data" / "atomic_coordinates" / "pdb_files"


def _fit():
    x = np.arange(256) * 0.05
    data = chisurf.core.data.DataCurve(x=x, y=np.ones_like(x), ey=np.ones_like(x))
    return chisurf.core.fitting.fit.FitGroup(data=chisurf.core.data.DataGroup([data]))


def test_structures_append_and_pop():
    model = fret_structure.FRETStructure(
        fit=_fit(), res_1=18, res_2=577, atom_name_1="CB", atom_name_2="CB"
    )
    model.append(chisurf.core.structure.Structure(str(PDBS / "hGBP1_closed.pdb")), amplitude=0.6)
    assert model.names == ["hGBP1_closed"] or len(model.names) == 1
    assert model.get_scalar("number_of_distributions") == 1.0
    assert model.res_2 == 577
    model.pop()
    assert model.names == []


def test_the_view_spec_offers_labels_and_the_structure_list():
    model = fret_structure.FRETStructure(fit=_fit())
    titles = [getattr(s, "title", "") for s in model.view_spec().sections]
    assert "Labels / AV" in titles and "Structures" in titles
    model.res_1 = 18
    assert model.res_1 == 18


def test_a_classic_project_reopens_with_its_structures():
    classic_state = {
        "extra": {
            "res_1": 18,
            "res_2": 577,
            "atom_name_1": "CB",
            "atom_name_2": "CB",
            "structures": [
                {
                    "name": "hGBP1_closed",
                    "filename": str(PDBS / "hGBP1_closed.pdb"),
                    "amplitude": 0.6,
                }
            ],
        }
    }
    model = fret_structure.FRETStructure(fit=_fit())
    model.set_state(classic_state)
    assert model.res_1 == 18 and model.atom_name_2 == "CB"
    assert model.structure_files == [str(PDBS / "hGBP1_closed.pdb")]


def test_without_structures_the_model_has_every_parameter_and_no_fret():
    """An empty ensemble is no FRET, not an incomplete model: the editor shows every row."""
    model = fret_structure.FRETStructure(fit=_fit())
    model.find_parameters()
    names = {p.name for p in model.parameters_all}
    assert {"tD0", "R0", "kappa2", "r0", "g", "background", "irf width"} <= names
    assert model._fraction_parameter_rows() == []
    model.load_structures(["no-such-file.pdb"])
    assert model.names == [] and model.problem is not None


def test_t4l_ca_labels_give_a_distance_distribution():
    """148L at FPS's linker width, CA sites: a distribution, not a skipped structure.

    N132's CA was walled in by its bonded neighbours at the 0.5 A grid the
    model used (and found at 0.7 A): the accessible-volume search left the
    anchor one stencil step at a time. IMP.bff's search now takes FPS's first
    step (three-voxel hops from the W/2 seed), and the model's labels take
    FPS's and Olga's defaults, an AV1 on the 0.9 A grid.
    """
    import pytest

    structure = chisurf.core.structure.Structure(str(PDBS / "148l.pdb"))
    axis = np.linspace(0.0, 150.0, 301)
    p = fret_structure.av_distance_distribution(structure, axis, res_1=44, res_2=132)
    assert p.shape == axis.shape and np.all(np.isfinite(p)) and p.sum() > 0
    mean = float(np.sum(axis * p) / p.sum())
    assert 20.0 < mean < 70.0

    # I100 sits in the T4L core: that label has no volume, and the error says which.
    with pytest.raises(ValueError, match=r"label 2 \(residue 100 CA\)"):
        fret_structure.av_distance_distribution(structure, axis, res_1=44, res_2=100)


def test_the_label_defaults_are_imp_bffs_av_defaults():
    """The structure fit's labels are FPS's defaults as IMP.bff declares them."""
    from chisurf.core.structure.av import av_defaults

    defaults = av_defaults()
    labels = fret_structure.LABEL_DEFAULTS
    for k in (1, 2):
        assert labels[f"linker_length_{k}"] == defaults["linker_length"]
        assert labels[f"linker_width_{k}"] == defaults["linker_width"]
        assert labels[f"radius1_{k}"] == defaults["radius1"]
        assert (labels[f"radius2_{k}"], labels[f"radius3_{k}"]) == defaults["av3_radii"][1:]
    assert labels["simulation_grid_resolution"] == defaults["simulation_grid_resolution"]
