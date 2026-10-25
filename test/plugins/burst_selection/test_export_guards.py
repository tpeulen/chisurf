"""Headless tests for the Burst Selection export entries (flrCIF).

Pins the guards of :meth:`BurstSelectionModel.export_flr_cif`: a table with no rows reports
"No burst data to export." and writes nothing, and a table with rows exports. The tool's tables are
``tttrlib.DataStore`` values, which have no truth value and no ``.empty`` -- the pandas spellings here are exactly what
the guards used to trip over.

The ``.bur``/``.bg4`` exports are no longer the model's: the legacy formats moved to the legacy
export plugin (``chisurf.plugins.core.legacy_export``), and the model must not grow them back --
``test_export_bur_is_not_part_of_the_tool_anymore`` pins that.
"""

from __future__ import annotations

import pytest

from chisurf.core.datastore import store_from_rows


@pytest.fixture
def model(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    (tmp_path / "settings").mkdir()
    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel

    return BurstSelectionModel()


@pytest.fixture
def frame():
    """Build a minimal burst table with the columns the exporters walk.

    Built through ``store_from_rows``, the way the analysis pipeline builds the tables the exporters receive.
    """
    return store_from_rows(
        [
            {"Duration (ms)": 1.5, "Number of Photons": 120, "Proximity Ratio": 0.1},
            {"Duration (ms)": 2.5, "Number of Photons": 240, "Proximity Ratio": 0.5},
            {"Duration (ms)": 3.5, "Number of Photons": 360, "Proximity Ratio": 0.9},
        ]
    )


def test_export_bur_is_not_part_of_the_tool_anymore(model):
    """The Seidel/Margarita formats belong to the legacy export plugin."""
    assert not hasattr(model, "export_bur")
    assert not hasattr(model, "export_bg4")


def test_export_flr_cif_writes_non_empty_frame(model, frame, tmp_path):
    target = tmp_path / "bursts.cif"
    model.display_frame = frame

    model.export_flr_cif(target)

    assert target.exists()
    assert "Exported to" in model.status_text
    text = target.read_text()
    assert "loop_" in text
    for column in frame.names:
        assert f"_{column}" in text


@pytest.mark.parametrize("empty", [None, store_from_rows([])], ids=["none", "empty-store"])
def test_export_without_data_reports_instead_of_writing(model, tmp_path, empty):
    target = tmp_path / "should-not-appear"
    model.display_frame = empty

    with pytest.raises(ValueError, match="No burst data to export."):
        model.export_flr_cif(target)

    assert not target.exists()
