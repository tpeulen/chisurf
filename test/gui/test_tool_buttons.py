"""Tests for the canonical shared tool-button / action registry."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("qtpy")

from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets import tool_buttons as tb


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_canonical_run_action_is_the_rocket(qapp):
    run = tb.TOOL_ACTIONS["run"]
    assert run.icon == Glyphs.ROCKET
    assert run.kind == "run"


def test_action_button_is_icon_only_with_object_name_and_tooltip(qapp):
    btn = tb.action_button("run", tooltip="Run BVA")
    assert btn.text() == Glyphs.ROCKET           # icon only, space-efficient
    assert btn.objectName() == "toolAction_run"  # stable, testable identity
    assert "Run" in btn.toolTip() and "Run BVA" in btn.toolTip()


def test_action_button_click_wires_callback(qapp):
    fired = []
    btn = tb.action_button("save", on_click=lambda: fired.append(1))
    btn.click()
    assert fired == [1]


def test_action_qaction_shares_the_same_vocabulary(qapp):
    from qtpy import QtWidgets

    parent = QtWidgets.QWidget()
    qact = tb.action_qaction("run", parent, tooltip="Detect bursts")
    assert qact.text() == Glyphs.ROCKET
    assert qact.objectName() == "toolAction_run"


def test_actions_have_a_stable_left_to_right_order(qapp):
    order = [k for k in ("add", "folder", "batch", "run", "clear", "refresh", "save",
                         "settings", "help")]
    got = [tb.TOOL_ACTIONS[k].order for k in order]
    assert got == sorted(got)  # canonical order is monotonic in this sequence
