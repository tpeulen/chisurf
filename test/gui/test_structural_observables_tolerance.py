"""Structural edits round-trip through PDB text (~1e-7 Å), so their observables
are compared with a documented bound; scalar-port edits stay exact."""

import importlib.util
import pathlib
import sys

spec = importlib.util.spec_from_file_location(
    "scientific_document_gui_probe",
    pathlib.Path(__file__).resolve().parents[1] / "gui" / "scientific_document_gui_probe.py",
)
probe = importlib.util.module_from_spec(spec)
sys.modules.setdefault("test.gui.scientific_document_gui_probe", probe)
spec.loader.exec_module(probe)


def test_pdb_precision_difference_is_within_bound():
    expected = [
        {
            "distances": {"47-86": 36.9027713801158},
            "coordinates": [[0.0, 1.0, 2.0], [3.1000000001, 4.0, 5.0]],
            "energy": [1.5],
            "chi2r": [],
        }
    ]
    actual = [
        {
            "distances": {"47-86": 36.90277141},
            "coordinates": [[0.0, 1.0, 2.0], [3.1, 4.0, 5.0]],
            "energy": [1.5],
            "chi2r": [],
        }
    ]
    assert actual != expected
    assert probe._observables_close(actual, expected)


def test_real_differences_and_shape_changes_are_rejected():
    expected = [{"distances": {"47-86": 36.9}, "coordinates": [[0.0, 1.0]]}]
    assert not probe._observables_close(
        [{"distances": {"47-86": 36.8}, "coordinates": [[0.0, 1.0]]}], expected
    )
    assert not probe._observables_close(
        [{"distances": {"47-86": 36.9}, "coordinates": [[0.0, 1.0, 2.0]]}], expected
    )
    assert not probe._observables_close(
        [{"distances": {"x": 36.9}, "coordinates": [[0.0, 1.0]]}], expected
    )


def test_structural_reference_records_the_file_load():
    """The GUI edit loads a PDB: the source is that file and the sampler's
    current structure is the loaded copy; nothing else in the archive moves."""
    structure = {"kind": "structure", "filename": "/data/148l.pdb", "xyz": [[0.1, 0.0, 0.0]]}
    fits = [
        {
            "members": [
                {
                    "uid": "m",
                    "model": {
                        "adapter_state": {
                            "proteinmc": {
                                "structure_source": "/data/148l.pdb",
                                "structure": structure,
                                "current_structure": None,
                                "settings": {"kt": 1.5},
                            }
                        }
                    },
                },
                {"uid": "other", "model": {"adapter_state": {}}},
            ]
        }
    ]
    reference = probe._structural_reference(fits, "m", "/edit/structure-edit-m.pdb")
    payload = reference[0]["members"][0]["model"]["adapter_state"]["proteinmc"]
    assert payload["structure_source"] == "/edit/structure-edit-m.pdb"
    loaded = dict(structure, filename="/edit/structure-edit-m.pdb")
    assert payload["structure"] == loaded
    assert payload["current_structure"] == loaded
    assert payload["settings"] == {"kt": 1.5}
    assert reference[0]["members"][1] == fits[0]["members"][1]
    # The producer archive itself is untouched.
    assert (
        fits[0]["members"][0]["model"]["adapter_state"]["proteinmc"]["structure_source"]
        == "/data/148l.pdb"
    )
