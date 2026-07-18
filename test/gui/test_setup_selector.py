"""Offscreen-Qt tests for the shared SetupSelector widget."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _loader(db_path=None):
    return {
        "setups": {
            "BS": {"detectors": {"green": {}, "red": {}, "yellow": {}}},
            "PIE": {"detectors": {"g": {}, "r": {}}},
        },
        "last_used": "BS",
    }


def test_selects_last_used_and_lists_detectors(qapp):
    from chisurf.gui.widgets.setup_selector import SetupSelector

    w = SetupSelector(loader=_loader)
    assert w.current_setup() == "BS"  # restored from last_used
    assert w.detector_names() == ["green", "red", "yellow"]
    assert w.summary.text() == "green, red, yellow"


def test_setup_changed_signal_and_switch(qapp):
    from chisurf.gui.widgets.setup_selector import SetupSelector

    seen = []
    w = SetupSelector(loader=_loader)
    w.setupChanged.connect(seen.append)
    w.set_current("PIE")
    assert w.current_setup() == "PIE"
    assert w.current_detectors() == {"g": {}, "r": {}}
    assert seen[-1] == "PIE"


def test_empty_and_reload(qapp):
    from chisurf.gui.widgets.setup_selector import SetupSelector

    empty = {"setups": {}, "last_used": None}
    state = {"data": empty}
    w = SetupSelector(loader=lambda db_path=None: state["data"])
    assert w.current_setup() == ""
    assert w.detector_names() == []
    # New setups appear after a reload.
    state["data"] = _loader()
    w.refresh()
    assert w.combo.findText("BS") >= 0
