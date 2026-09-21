"""Changing the current experiment/setup from code updates the main window.

This replaces a stale macro that assigned to ``chisurf.current_setup`` — a
module-level *read-only* accessor, so the assignment only shadowed it with a
string and every following line raised ``AttributeError`` at **import** time
(which took the whole ``test/gui`` collection down with it). The selection API
lives on the main window (``chisurf.cs``), which takes names and drives the
combo boxes.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import utils  # noqa: E402

utils.set_search_paths(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chisurf as cs  # noqa: E402
import chisurf.gui  # noqa: E402


@pytest.fixture(scope="module")
def cs_app():
    return cs.gui.get_app()


@pytest.fixture
def main_window(cs_app):
    """The bootstrapped ChiSurf main window."""
    assert cs_app is not None  # the QApplication must exist before the window
    return cs.cs


def test_experiment_and_setup_selection_by_name(main_window):
    main_window.current_experiment = "TCSPC"
    assert main_window.comboBox_experimentSelect.currentText() == "TCSPC"

    main_window.current_setup = "TXT/CSV"
    assert main_window.current_setup_name == "TXT/CSV"
    assert main_window.comboBox_setupSelect.currentText() == "TXT/CSV"


def test_setup_properties_survive_a_ui_refresh(main_window):
    main_window.current_experiment = "TCSPC"
    main_window.current_setup = "TXT/CSV"

    setup = main_window.current_setup
    setup.is_vv_vh = True
    setup.use_header = False
    setup.matrix_columns = []
    setup.g_factor = 0.95
    setup.polarization = "vm"
    setup.rep_rate = 20.0
    setup.rebin = (1, 1)
    setup.dt = 0.02

    main_window.update_setup_ui()

    setup = main_window.current_setup
    assert setup.is_vv_vh is True
    assert setup.g_factor == pytest.approx(0.95)
    assert setup.polarization == "vm"
    assert setup.rep_rate == pytest.approx(20.0)


def test_unknown_experiment_name_is_rejected(main_window):
    with pytest.raises(ValueError):
        main_window.current_experiment = "NoSuchExperiment"
