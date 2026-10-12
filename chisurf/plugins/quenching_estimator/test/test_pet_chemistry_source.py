"""The PET chemistry comes from the compiled `IMP.bff` core, as plain data.

`IMP.bff.quenching` (a Python module) was removed when the quenching model moved to C++; QuEst still imported it, so every
simulation, the project template and the GUI failed with ModuleNotFoundError. The tables now come from the top-level
`IMP.bff` functions and reach the project document as plain mappings (the C++ objects cannot be copied or serialised).
"""

import copy
import json

import pytest

pytest.importorskip("IMP.bff")

from chisurf.plugins.quenching_estimator.core import dye_diffusion as dd


def test_there_is_no_python_quenching_module_to_import():
    import importlib.util

    assert (
        importlib.util.find_spec("IMP.bff.quenching") is None
    )  # the reason `_pet()` must not import it


def test_the_tables_are_plain_copyable_json():
    table = dd.default_amino_acid_interactions(slow_factor=0.1)
    assert len(table) == 20 and set(table["CYS"]) == {
        "slow_factor",
        "kQ",
        "quench_radius",
        "quench_atoms",
    }
    assert table["CYS"]["kQ"] == pytest.approx(0.8) and table["CYS"][
        "slow_factor"
    ] == pytest.approx(0.1)
    assert table["CYS"]["quench_atoms"] == ["SG"] and table["ALA"]["quench_radius"] is None
    assert copy.deepcopy(table) == table and json.loads(json.dumps(table)) == table


def test_normalising_fills_the_defaults_and_keeps_what_was_given():
    out = dd.normalize_amino_acid_interactions(
        {"CYS": {"kQ": 1.5, "quench_radius": 6.0}, "trp": 0.2}
    )
    assert len(out) == 20
    assert (
        out["CYS"]["kQ"] == 1.5
        and out["CYS"]["quench_radius"] == 6.0
        and out["CYS"]["quench_atoms"] == ["CB"]
        or out["CYS"]["quench_atoms"]
    )
    assert out["TRP"]["slow_factor"] == pytest.approx(0.2)  # a bare number is a slow factor
    assert out["ALA"]["kQ"] == 0.0
    assert (
        dd.normalize_amino_acid_interactions({"CYS": {"quench_radius": "nonsense"}})["CYS"][
            "quench_radius"
        ]
        is None
    )


def test_the_quencher_table_and_reference_are_plain_dicts():
    assert dd.DEFAULT_QUENCHER_ATOMS["CYS"] == ("SG",) and "TRP" in dd.STANDARD_AMINO_ACID_RESIDUES
    assert dd.REFERENCE_PET_QUENCHING["CYS"] == {"kQ": 0.8, "contact_distance": 3.5}
    assert json.dumps(dd.REFERENCE_PET_QUENCHING)
    assert dd.default_quencher_table()["CYS"] == {"atoms": ["SG"], "kQ": 0.8}
