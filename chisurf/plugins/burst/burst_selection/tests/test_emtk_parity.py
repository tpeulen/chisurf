"""Unit tests for EMTK Burst Selection GUI parity."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from qtpy import QtWidgets

from chisurf.plugins.burst.burst_selection import BurstSelectionTool
from chisurf.plugins.burst.burst_selection.gui.app import (
    BurstSelectionApp,
    BurstSelectionGui,
)


@pytest.fixture
def burst_tool(qapp):
    tool = BurstSelectionTool(show_channel_selection=True, embedded=True)
    yield tool
    tool.close()


def test_emtk_burst_selection_embedding(burst_tool):
    """Verify BurstSelectionTool embeds EMTK host when embedded=True."""
    assert getattr(burst_tool, "_embedded", False) is True
    assert hasattr(burst_tool, "app")
    assert isinstance(burst_tool.app, BurstSelectionApp)
    assert hasattr(burst_tool, "host")

    # Legacy dock area should be hidden
    assert not burst_tool.dock_area.isVisible()

    # Toolbars should be hidden
    toolbars = burst_tool.findChildren(QtWidgets.QToolBar)
    for tb in toolbars:
        assert not tb.isVisible()


def test_emtk_docks_and_windows(burst_tool):
    """Verify all required dock windows exist in DockManager."""
    gui = burst_tool.app.selection_gui
    expected_windows = {
        "settings",
        "files",
        "summary",
        "trace",
        "dt",
        "decay",
        "duration",
        "scatter",
        "table",
        "histogram",
    }
    assert expected_windows.issubset(set(gui.docks.windows.keys()))


def test_two_way_parameter_synchronization(burst_tool):
    """Verify parameters sync between EMTK GUI and Qt Wizard."""
    gui = burst_tool.app.selection_gui

    # Change parameters in EMTK GUI
    gui.min_photons = 75
    gui.photon_window = 12
    gui.time_window_ms = 0.85
    gui.dmt_max_ms = 0.25
    gui.merge_gap = 5
    gui._sync_to_tool(notify=False)

    # Check that wizard received them
    wiz = burst_tool.wizard
    assert int(wiz.spinBox.value()) == 75
    assert int(wiz.spinBox_7.value()) == 12
    assert pytest.approx(float(wiz.doubleSpinBox.value()), rel=1e-3) == 0.85
    assert pytest.approx(float(wiz.filter_settings.dt_max), rel=1e-3) == 0.25
    assert int(wiz.filter_settings.merge_gap) == 5

    # Change in wizard and sync back
    wiz.spinBox.setValue(45)
    wiz.spinBox_7.setValue(7)
    gui._sync_from_tool()
    assert gui.min_photons == 45
    assert gui.photon_window == 7


def test_empty_state_no_dummy_data(burst_tool):
    """Verify that when no files/bursts are loaded, empty states are clean and no dummy curves exist."""
    gui = burst_tool.app.selection_gui
    assert burst_tool._last_tttr is None
    assert burst_tool._last_frame is None
    assert gui._get_active_diagnostic() is None


def test_all_burst_selection_algorithms(burst_tool):
    """Verify that all 7 burst selection algorithms are available and switchable."""
    gui = burst_tool.app.selection_gui
    wiz = burst_tool.wizard
    combo_filter = getattr(wiz, "comboBox_burst_filter", None) or getattr(
        wiz, "comboBox_mode", None
    )
    assert combo_filter is not None
    assert combo_filter.count() >= 7

    expected_algos = [
        "Sliding window",
        "Cumulative (CUSUM / SPRT)",
        "Kalman (rate change)",
        "Bayesian changepoint (BOCPD)",
        "Coincident (multi-detector)",
        "Max-tree (threshold-free)",
        "Bayesian Blocks (optimal segmentation)",
    ]

    for idx, expected in enumerate(expected_algos):
        assert combo_filter.itemText(idx) == expected
        gui.filter_algorithm = idx
        gui._sync_to_tool(notify=False)
        assert combo_filter.currentIndex() == idx

        # Test CUSUM syncing
        if idx == 1:
            gui.cusum_alpha = 0.02
            gui.cusum_beta = 0.03
            gui.cusum_sb_ratio = 45.0
            gui._sync_to_tool(notify=False)
            assert pytest.approx(float(wiz.filter_settings.alpha), rel=1e-3) == 0.02
            assert pytest.approx(float(wiz.filter_settings.beta), rel=1e-3) == 0.03
            assert pytest.approx(float(wiz.filter_settings.sb_ratio), rel=1e-3) == 45.0

        # Test Kalman syncing
        elif idx == 2:
            gui.kalman_q = 0.005
            gui.kalman_z_thresh = 4.2
            gui.kalman_merge_gap = 8
            gui._sync_to_tool(notify=False)
            assert pytest.approx(float(wiz.filter_settings.kalman_q), rel=1e-3) == 0.005
            assert pytest.approx(float(wiz.filter_settings.kalman_z_thresh), rel=1e-3) == 4.2
            assert int(wiz.filter_settings.kalman_merge_gap) == 8

        # Test BOCPD syncing
        elif idx == 3:
            gui.bocpd_changepoint_prob = 2e-5
            gui.bocpd_prior_count = 3.5
            gui._sync_to_tool(notify=False)
            assert (
                pytest.approx(float(wiz.filter_settings.bocpd_changepoint_prob), rel=1e-3) == 2e-5
            )
            assert pytest.approx(float(wiz.filter_settings.bocpd_prior_count), rel=1e-3) == 3.5
