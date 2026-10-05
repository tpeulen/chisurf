"""Adding a fit opens exactly one window, even when an event loop spins mid-build.

``add_fit`` publishes ``fit.added`` and the main window also opens a window for
that event. Any nested event loop while the first window is being built (an
error box raised by a plot, a progress dialog) delivers the queued event before
the window is in the MDI area, and a second window for the same fit appeared.
The project capture then refused the document (``duplicate fit view UID``) and
every later Add fit failed with that error.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import utils

TOPDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
utils.set_search_paths(TOPDIR)

import pytest

import chisurf as cs
import chisurf.gui
import chisurf.macros

DECAY = "./test/data/tcspc/ibh_sample/Decay_577D.txt"


@pytest.fixture(scope="module", autouse=True)
def _ensure_app():
    return cs.gui.get_app()


def _load_decay():
    gui = cs.cs
    cs.core.actions.dispatch(name="fit.close_all", payload={})
    cs.imported_datasets.clear()
    gui.comboBox_experimentSelect.setCurrentIndex(gui.comboBox_experimentSelect.findText("TCSPC"))
    gui._refresh_experiment_ui()
    gui.comboBox_setupSelect.setCurrentIndex(gui.comboBox_setupSelect.findText("TXT/CSV"))
    gui._refresh_setup_ui()
    for key, value in dict(
        skiprows=11,
        reading_routine="csv",
        is_vv_vh=False,
        use_header=True,
        matrix_columns=[],
        polarization="vm",
        rep_rate=10.0,
        dt=0.0141,
    ).items():
        setattr(gui.current_setup, key, value)
    cs.macros.add_dataset(filename=DECAY)


def _windows_for(uid):
    return [
        w
        for w in cs.cs.mdiarea.subWindowList()
        if str(getattr(getattr(w, "fit", None), "unique_identifier", "")) == uid
    ]


def test_fit_added_event_during_window_build_opens_no_second_window(monkeypatch):
    from chisurf.core.project.ui_state import get_ui_state
    from chisurf.gui.widgets.fitting import FitSubWindow

    _load_decay()
    gui = cs.cs
    original_init = FitSubWindow.__init__
    delivered = []

    def init_and_deliver_queued_event(self, fit, *args, **kwargs):
        original_init(self, fit, *args, **kwargs)
        # What a nested event loop does: run the queued ``fit.added`` handler
        # while the window being built is not yet in the MDI area.
        if not delivered:
            delivered.append(fit.unique_identifier)
            gui._on_server_event({"topic": "fit.added", "fit_uid": fit.unique_identifier})

    monkeypatch.setattr(FitSubWindow, "__init__", init_and_deliver_queued_event)
    before = len(cs.fits)
    cs.core.actions.dispatch(
        name="fit.add",
        payload={"dataset_indices": [len(cs.imported_datasets) - 1], "model_name": "Lifetime"},
    )
    assert len(cs.fits) == before + 1
    assert delivered, "the window build never ran"
    assert len(_windows_for(delivered[0])) == 1
    get_ui_state(gui)  # raises ProjectUIStateError on a duplicate fit view

    # The next Add fit must still succeed (it failed with the duplicate before).
    cs.core.actions.dispatch(
        name="fit.add",
        payload={"dataset_indices": [len(cs.imported_datasets) - 1], "model_name": "Lifetime"},
    )
    assert len(cs.fits) == before + 2
    get_ui_state(gui)
