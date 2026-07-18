"""GUI tests for the synthetic decay generator tool."""

from __future__ import annotations


def test_tool_builds_and_generates(qapp, qtbot):
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.tool import SyntheticDecayTool

    tool = SyntheticDecayTool()
    qtbot.addWidget(tool)
    m = tool.model
    assert m.decay_series() == []  # nothing yet
    m.generate()
    series = m.decay_series()
    assert series and len(series[0]["y"]) == m.n_bins
    assert "Generated" in m.status


def test_spectrum_edit_add_remove(qapp, qtbot):
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.view_model import (
        SyntheticDecayViewModel,
    )

    m = SyntheticDecayViewModel()
    n0 = len(m.spectrum_rows)
    m.add_row()
    assert len(m.spectrum_rows) == n0 + 1
    m.update_spectrum(0, "tau", 3.5)
    assert m.spectrum_rows[0]["tau"] == 3.5
    m.selected_row = len(m.spectrum_rows) - 1
    m.remove_row()
    assert len(m.spectrum_rows) == n0


def test_shot_noise_path_changes_output(qapp, qtbot):
    from chisurf.plugins.fluorescence_decay.synthetic_decay.gui.view_model import (
        SyntheticDecayViewModel,
    )

    m = SyntheticDecayViewModel()
    m.generate()
    ideal = list(m._y)
    m.shot_noise = True
    m.photon_count = 20000
    m.generate()
    noisy = list(m._y)
    assert ideal != noisy  # noisy realization differs from the ideal pattern
    assert sum(noisy) > 1.0  # counts, not a unit-sum pattern
