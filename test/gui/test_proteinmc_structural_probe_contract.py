"""RED regression: probe-level structural-edit contract (ProteinMC actual-Main).

_pins_ the two new probe helpers before they exist:

- ``_structural_edit(project, second)`` detects a coordinate-only scientific
  edit between two canonical archives (parameters unchanged, adapter_state
  structure coordinates changed) and returns the model identity + coordinates;
- ``_edit_structural_control(main, app, structural)`` drives the real GUI
  Structure file control: writes a single-model PDB with the archive's exact
  coordinates, commits it through the visible QLineEdit with real keyboard
  events, and requires the live model's active coordinates to equal the
  archive's afterwards.
"""

import json

import numpy as np
import pytest


def test_structural_edit_detected_between_archives(tmp_path):
    from test.gui.scientific_document_gui_probe import _structural_edit

    def model_state(x):
        return {
            "parameters": [
                {"uid": "p0", "name": "d", "value": 30.0, "is_output": True, "link_target": None},
            ],
            "adapter_state": {
                "proteinmc": {
                    "structure": {
                        "atoms": {
                            "fields": [
                                {
                                    "name": "xyz",
                                    "array": {"values": [[0.0, 0.0, 0.0], [x, 1.0, 2.0]]},
                                },
                            ]
                        },
                    },
                    "settings": {"kt": 1.5},
                },
            },
        }

    first = {"fits": [{"members": [{"model": model_state(0.0), "uid": "m0"}]}]}
    second = {"fits": [{"members": [{"model": model_state(0.1), "uid": "m0"}]}]}
    structural = _structural_edit(first, second)
    assert structural is not None
    member_uid, coordinates = structural
    assert member_uid == "m0"
    assert coordinates[1][0] == pytest.approx(0.1)

    # No edit or a parameter edit is NOT a structural edit.
    assert _structural_edit(first, first) is None
    changed_parameters = json.loads(json.dumps(second))
    # Output *values* follow the coordinates; any other parameter field is not.
    changed_parameters["fits"][0]["members"][0]["model"]["parameters"][0]["fixed"] = False
    assert _structural_edit(first, changed_parameters) is None


def test_structural_edit_requires_coordinate_change(tmp_path):
    from test.gui.scientific_document_gui_probe import _structural_edit

    def state():
        return {
            "parameters": [],
            "adapter_state": {
                "proteinmc": {
                    "structure": {
                        "atoms": {
                            "fields": [{"name": "xyz", "array": {"values": [[0.0, 0.0, 0.0]]}}]
                        },
                    }
                }
            },
        }

    a = {"fits": [{"members": [{"model": state(), "uid": "m"}]}]}
    # Same coordinates but a different non-structural field: not the producer's
    # coordinate edit.
    import copy

    b = copy.deepcopy(a)
    b["fits"][0]["members"][0]["model"]["adapter_state"]["proteinmc"]["settings"] = {}
    assert _structural_edit(a, b) is None


def test_recomputed_output_parameters_do_not_mask_structural_edit():
    """Real ProteinMC archives: shifting coordinates recomputes the declared
    distance *output*, so the parameter lists differ in that output's value."""
    from test.gui.scientific_document_gui_probe import _structural_edit

    def state(x, distance, fixed_input=1.0):
        return {
            "parameters": [
                {"uid": "d", "name": "47-86", "value": distance, "is_output": True},
                {"uid": "k", "name": "kt", "value": fixed_input, "is_output": False},
            ],
            "adapter_state": {
                "proteinmc": {
                    "structure": {
                        "atoms": {
                            "fields": [{"name": "xyz", "array": {"values": [[x, 0.0, 0.0]]}}]
                        },
                    }
                }
            },
        }

    first = {"fits": [{"members": [{"model": state(0.0, 36.877), "uid": "m"}]}]}
    second = {"fits": [{"members": [{"model": state(0.1, 36.903), "uid": "m"}]}]}
    assert _structural_edit(first, second) == ("m", [[0.1, 0.0, 0.0]])
    # An input parameter change alongside is not a coordinate-only edit.
    third = {"fits": [{"members": [{"model": state(0.1, 36.903, 2.0), "uid": "m"}]}]}
    assert _structural_edit(first, third) is None
