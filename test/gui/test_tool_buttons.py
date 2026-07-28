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


def test_recompute_sits_next_to_run_and_is_legible(qapp):
    """The reuse override belongs beside the action it overrides."""
    recompute = tb.TOOL_ACTIONS["recompute"]
    assert recompute.icon == Glyphs.RECOMPUTE
    assert tb.TOOL_ACTIONS["run"].order < recompute.order < tb.TOOL_ACTIONS["auto"].order
    # ⟳ is a text glyph, not an emoji: without an explicit size it renders
    # visibly smaller than the emoji it sits beside.
    assert recompute.font_px > 0
    assert f"font-size: {recompute.font_px}px" in tb.action_button("recompute").styleSheet()


def test_attention_actually_changes_how_the_button_is_drawn(qapp):
    """The accent has to reach the stylesheet, not only a property.

    A ``[attention="true"]`` rule does not reliably re-evaluate on a widget that
    carries its own stylesheet — the outline silently never appeared. Asserting
    on the property alone would not have caught that, so assert on the rule.
    """
    btn = tb.action_button("recompute")
    plain = btn.styleSheet()

    tb.flag_attention(btn, True)
    assert btn.property("attention") is True
    assert tb.ATTENTION_RULE.strip() in btn.styleSheet()

    tb.flag_attention(btn, True)  # idempotent: no accumulation
    assert btn.styleSheet().count("#f0b429") == 1

    tb.flag_attention(btn, False)
    assert btn.property("attention") is False
    assert btn.styleSheet() == plain


def test_actions_have_a_stable_left_to_right_order(qapp):
    order = [k for k in ("add", "folder", "batch", "run", "clear", "refresh", "save",
                         "settings", "help")]
    got = [tb.TOOL_ACTIONS[k].order for k in order]
    assert got == sorted(got)  # canonical order is monotonic in this sequence
