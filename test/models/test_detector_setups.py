import json
import os
import sys
import tempfile

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(".."))

from mmfdb.repository import MFDatabase

from chisurf.gui.widgets.wizard.tttr_channeldefinition import (
    load_detector_setups,
    save_detector_setups,
)
from chisurf.gui.widgets.wizard.tttr_channeldefinition import (
    tttr_detector_setups as detector_setups_module,
)


def test_save_detector_setups():
    """Test that save_detector_setups updates the file instead of overwriting it."""
    # Create a temporary file for testing
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp_file:
        temp_path = temp_file.name

    try:
        # Initial data
        initial_data = {
            "setups": {
                "setup1": {
                    "windows": {"prompt": [0, 2048]},
                    "detectors": {"green": {"chs": [0, 1]}},
                }
            }
        }

        # Save initial data
        save_detector_setups(initial_data, temp_path)

        # Verify initial data was saved
        loaded_data = load_detector_setups(temp_path)
        print("Initial data saved:")
        print(json.dumps(loaded_data, indent=2))

        # New data to add
        new_data = {
            "setups": {
                "setup2": {
                    "windows": {"delayed": [2048, 4095]},
                    "detectors": {"red": {"chs": [2, 3]}},
                }
            }
        }

        # Save new data (should update, not overwrite)
        save_detector_setups(new_data, temp_path)

        # Verify both setups are in the file
        updated_data = load_detector_setups(temp_path)
        print("\nUpdated data (should contain both setup1 and setup2):")
        print(json.dumps(updated_data, indent=2))

        # Check if both setups exist
        assert "setup1" in updated_data["setups"], "setup1 was overwritten!"
        assert "setup2" in updated_data["setups"], "setup2 was not added!"

        print("\nTest passed! The file was updated correctly.")

    finally:
        # Clean up the temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_default_detector_setups_store_in_mmfdb(tmp_path):
    """Default detector setup storage should persist in MMFDB, not JSON.

    Uses dependency injection (``db_path`` / ``user_id`` / ``skip_migration``)
    so the test never touches the real database — no monkeypatching.
    """
    db_path = str(tmp_path / "mmfdb.sqlite")

    setup_data = {
        "setups": {
            "BH SPC-130": {
                "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
                "detectors": {"green": {"chs": [0, 8]}, "red": {"chs": [1, 9]}},
                "tttr_reading": {"file_type": "SPC-130"},
            }
        },
        "last_used": "BH SPC-130",
    }

    assert save_detector_setups(setup_data, db_path=db_path, user_id="")
    loaded = load_detector_setups(db_path=db_path, user_id="", skip_migration=True)
    setup_id = detector_setups_module.setup_id_for_name("BH SPC-130")
    db = MFDatabase(db_path)
    row = db.get_setup(setup_id)

    assert row is not None
    assert loaded["last_used"] == "BH SPC-130"
    assert loaded["setups"]["BH SPC-130"]["detectors"]["green"]["chs"] == [0, 8]
    assert loaded["setups"]["BH SPC-130"]["detectors"]["red"]["chs"] == [1, 9]
    assert not (tmp_path / "detector_setups.json").exists()


def test_channel_luts_round_trip_mmfdb(tmp_path):
    """Per-channel LUTs / shifts / apply_lut survive an MMFDB save+load."""
    db_path = str(tmp_path / "mmfdb.sqlite")
    lut0 = [0.0, 1.5, 2.5, 4.0, 8.0]
    setup_data = {
        "setups": {
            "SPC-130 linearized": {
                "windows": {"prompt": [0, 2048]},
                "detectors": {"green": {"chs": [0, 8]}},
                "tttr_reading": {"file_type": "SPC-130"},
                "apply_lut": True,
                "channel_luts": {"0": lut0},
                "channel_shifts": {"0": 3},
                "channel_lut_sources": {"0": "uniform.spc"},
            }
        }
    }
    assert save_detector_setups(setup_data, db_path=db_path, user_id="")
    loaded = load_detector_setups(db_path=db_path, user_id="", skip_migration=True)
    s = loaded["setups"]["SPC-130 linearized"]
    assert s["apply_lut"] is True
    # keys may come back as str or int depending on serializer; normalize.
    luts = {str(k): v for k, v in s["channel_luts"].items()}
    shifts = {str(k): v for k, v in s["channel_shifts"].items()}
    assert luts["0"] == lut0
    assert int(shifts["0"]) == 3


def test_channel_luts_round_trip_json(tmp_path):
    """Same round-trip through the JSON fallback store."""
    path = str(tmp_path / "setups.json")
    lut = [0.0, 2.0, 4.0, 6.0]
    save_detector_setups(
        {
            "setups": {
                "s1": {
                    "detectors": {"g": {"chs": [1]}},
                    "apply_lut": True,
                    "channel_luts": {"1": lut},
                    "channel_shifts": {"1": -2},
                }
            }
        },
        path,
    )
    loaded = load_detector_setups(path)
    s = loaded["setups"]["s1"]
    assert s["apply_lut"] is True
    luts = {str(k): v for k, v in s["channel_luts"].items()}
    assert luts["1"] == lut
    assert int({str(k): v for k, v in s["channel_shifts"].items()}["1"]) == -2


def test_a_missing_setups_file_never_blocks_a_headless_run(tmp_path, monkeypatch):
    """The loader must return, not open a modal box nobody can dismiss.

    ``load_detector_setups`` runs while widgets are being *constructed* — every
    tool with a setup picker calls it. Its missing-file branch pops a
    ``QMessageBox`` and, on one button, a whole wizard; a modal spins its own
    event loop until a button is pressed, which under ``offscreen`` can never
    happen. Guarding on "a QApplication exists" is not enough, because in a test
    one always does: the run then hangs rather than fails, and a hang looks
    exactly like a slow suite.
    """
    from qtpy import QtWidgets

    from chisurf.gui.dialogs import is_interactive
    from chisurf.gui.widgets.warning_once import reset_warnings

    # A QApplication exists — exactly the condition the old guard tested for —
    # yet nothing here can dismiss a dialog. Bind it: an unreferenced
    # QApplication is collected again straight away, and then this test passes
    # for the wrong reason.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    assert app is not None
    assert QtWidgets.QApplication.instance() is not None
    assert not is_interactive()

    missing = tmp_path / "does_not_exist.json"
    reset_warnings()
    monkeypatch.setattr(detector_setups_module, "DETECTOR_SETUPS_FILE", missing)
    monkeypatch.setattr(detector_setups_module, "_use_mmfdb", lambda *a, **k: False)

    shown = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox, "exec_", lambda self: shown.append("box"), raising=False
    )

    result = detector_setups_module.load_detector_setups(
        file_path=str(missing), skip_migration=True
    )

    assert result == {"setups": {}}
    assert not shown, "a modal dialog was opened in a headless run"


if __name__ == "__main__":
    test_save_detector_setups()
