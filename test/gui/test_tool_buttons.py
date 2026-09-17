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
    assert tb.TOOL_ACTIONS["run"].icon == Glyphs.RUN  # ▶
    assert tb.TOOL_ACTIONS["pause"].icon == Glyphs.PAUSE  # ⏸
    assert tb.TOOL_ACTIONS["stop"].icon == Glyphs.STOP  # ⏹
    assert tb.TOOL_ACTIONS["restart"].icon == Glyphs.RESTART  # 🔁
    # The background is what carries the meaning, so each control owns its own
    # accent. Sharing one is what made restart indistinguishable from run.
    kinds = {k: tb.TOOL_ACTIONS[k].kind for k in ("run", "pause", "stop", "restart")}
    assert len(set(kinds.values())) == 4, "each transport control needs its own accent"
    assert set(kinds.values()) <= set(tb.BTN_STYLES), "every accent must be defined"


def test_the_control_accents_are_told_apart_by_colour(qapp):
    """Adjacent buttons must not look alike — glyphs are small and read second.

    Two collisions this pins: restart used to reuse run's green, and stop used to
    reuse clear's red while sitting next to it in the BVA toolbar.
    """
    import colorsys
    import re

    def accent(kind):
        css = tb.BTN_STYLES[kind]
        hexcol = re.search(r"background-color: #([0-9a-fA-F]{6})", css).group(1)
        rgb = [int(hexcol[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        return colorsys.rgb_to_hsv(*rgb)

    controls = {k: accent(tb.TOOL_ACTIONS[k].kind) for k in ("run", "pause", "stop", "restart")}
    hues = sorted(h * 360 for h, _, _ in controls.values())
    gaps = [b - a for a, b in zip(hues, hues[1:])]
    assert min(gaps) > 30, f"transport hues too close: {hues}"

    # Same hue family is fine when the weight differs: stop is the bright red,
    # clear the dark one.
    _, s_stop, v_stop = accent("stop")
    _, s_clear, v_clear = accent("clear")
    assert v_stop > v_clear and s_stop > s_clear, "stop must out-weigh clear"


def test_restart_is_not_refresh(qapp):
    """Redrawing a plot and redoing an analysis are different actions."""
    assert tb.TOOL_ACTIONS["restart"].icon != tb.TOOL_ACTIONS["refresh"].icon
    assert Glyphs.RESTART != Glyphs.REFRESH


def test_action_button_is_icon_only_with_object_name_and_tooltip(qapp):
    btn = tb.action_button("run", tooltip="Run BVA")
    assert btn.text() == Glyphs.RUN  # icon only, space-efficient
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
    order = [
        k for k in ("add", "folder", "batch", "run", "clear", "refresh", "save", "settings", "help")
    ]
    got = [tb.TOOL_ACTIONS[k].order for k in order]
    assert got == sorted(got)  # canonical order is monotonic in this sequence
