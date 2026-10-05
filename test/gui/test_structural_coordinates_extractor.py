"""Array-adapter coordinates: the structural extractor must read the atoms field."""

import importlib.util
import pathlib
import sys

spec = importlib.util.spec_from_file_location(
    "scientific_document_gui_probe",
    pathlib.Path(__file__).resolve().parents[1] / "gui" / "scientific_document_gui_probe.py",
)
probe = importlib.util.module_from_spec(spec)
sys.modules["test.gui.scientific_document_gui_probe"] = probe
spec.loader.exec_module(probe)


def test_atoms_field_xyz_extracted():
    state = {
        "proteinmc": {
            "structure": {
                "atoms": {
                    "fields": [
                        {"name": "res_id", "array": {"values": [47, 86]}},
                        {"name": "xyz", "array": {"values": [[0.0, 0.0, 0.0], [0.1, 1.0, 2.0]]}},
                    ],
                },
            },
        },
    }
    assert probe._structural_coordinates(state) == [[0.0, 0.0, 0.0], [0.1, 1.0, 2.0]]


def test_plain_xyz_fallback_and_absent():
    state = {"proteinmc": {"structure": {"xyz": [[1.0, 2.0, 3.0]]}}}
    assert probe._structural_coordinates(state) == [[1.0, 2.0, 3.0]]
    assert probe._structural_coordinates({"proteinmc": {}}) is None
    assert probe._structural_coordinates({}) is None
