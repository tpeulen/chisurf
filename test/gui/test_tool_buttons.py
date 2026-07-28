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


def test_the_controls_are_the_transport_symbols_everyone_knows(qapp):
    """Run/pause/stop/restart read as media controls, not as invented icons."""
    assert tb.TOOL_ACTIONS["run"].icon == Glyphs.RUN        # ▶
    assert tb.TOOL_ACTIONS["pause"].icon == Glyphs.PAUSE    # ⏸
    assert tb.TOOL_ACTIONS["stop"].icon == Glyphs.STOP      # ⏹
    assert tb.TOOL_ACTIONS["restart"].icon == Glyphs.RESTART  # 🔁
    assert tb.TOOL_ACTIONS["run"].kind == "run"
    # Each control carries its own accent, so the row reads as a colour language
    # even where the glyph itself has no colour presentation.
    kinds = {k: tb.TOOL_ACTIONS[k].kind for k in ("run", "pause", "stop", "restart")}
    assert kinds["pause"] == "pause" and kinds["stop"] == "clear"
    assert len(set(kinds.values())) == 3, "play and restart share the 'go' accent"


def test_restart_is_not_refresh(qapp):
    """Redrawing a plot and redoing an analysis are different actions."""
    assert tb.TOOL_ACTIONS["restart"].icon != tb.TOOL_ACTIONS["refresh"].icon
    assert Glyphs.RESTART != Glyphs.REFRESH


def test_action_button_is_icon_only_with_object_name_and_tooltip(qapp):
    btn = tb.action_button("run", tooltip="Run BVA")
    assert btn.text() == Glyphs.RUN              # icon only, space-efficient
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
    assert qact.text() == Glyphs.RUN
    assert qact.objectName() == "toolAction_run"


def test_the_controls_lay_out_in_transport_order(qapp):
    """Left to right: run, restart, pause, stop — as on any player."""
    order = [tb.TOOL_ACTIONS[k].order for k in ("run", "restart", "pause", "stop")]
    assert order == sorted(order)


def test_attention_actually_changes_how_the_button_is_drawn(qapp):
    """The accent has to reach the stylesheet, not only a property.

    A ``[attention="true"]`` rule does not reliably re-evaluate on a widget that
    carries its own stylesheet — the outline silently never appeared. Asserting
    on the property alone would not have caught that, so assert on the rule.
    """
    btn = tb.action_button("restart")
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
