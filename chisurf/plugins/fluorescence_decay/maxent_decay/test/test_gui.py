"""Head-less GUI smoke tests for the MaxEnt MEM tool (collected by the gui suite)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("qtpy")


@pytest.fixture(scope="module")
def qapp():
    """Return the process-wide ``QApplication``, creating it if needed."""
    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_maxent_gui_instantiates(qapp):
    """The dock layout built by ``MaxentDecayWidget._init_ui`` is the live UI path."""
    from chisurf.plugins.fluorescence_decay.maxent_decay.gui.gui import (
        MaxentDecayWidget,
    )

    w = MaxentDecayWidget()
    try:
        assert set(w.dock_area._tab_names.values()) == {
            "Settings",
            "Decay / fit / IRF",
            "Weighted residuals",
            "Distribution",
            "L-curve",
        }
        # Each plot dock is a separate widget created by _create_plot_widgets().
        for attr in ("plot_decay", "plot_wres", "plot_dist", "plot_lcurve"):
            assert getattr(w, attr) is not None
    finally:
        w.close()


def test_maxent_gui_has_no_second_ui_builder():
    """Only one module builds the MaxEnt UI — the orphaned ``gui_ui`` one is gone."""
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("chisurf.plugins.fluorescence_decay.maxent_decay.gui.gui_ui")
