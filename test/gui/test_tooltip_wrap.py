"""Tests for app-wide tooltip folding and settings deep-merge."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_LONG = (
    "Reject nuisance photons: keep the afterpulse (AP) and scatter/IRF filters so "
    "they still absorb afterpulse/scatter counts, but drop those nuisance rows from "
    "the correlation-facing filter output."
)


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_wrap_tooltip_folds_long_text(qapp):
    from chisurf.gui.tooltip import tooltip_wrap_width, wrap_tooltip

    width = tooltip_wrap_width()
    wrapped = wrap_tooltip(_LONG)
    assert "\n" in wrapped
    assert all(len(line) <= width for line in wrapped.splitlines())


def test_wrap_tooltip_leaves_richtext_and_short(qapp):
    from chisurf.gui.tooltip import wrap_tooltip

    assert wrap_tooltip("<b>already rich</b>") == "<b>already rich</b>"
    assert "\n" not in wrap_tooltip("short tip")


def test_global_filter_shows_and_consumes_tooltip(qapp):
    from qtpy import QtCore, QtGui, QtWidgets

    from chisurf.gui.tooltip import _TooltipWrapFilter

    filt = _TooltipWrapFilter()
    event = QtGui.QHelpEvent(QtCore.QEvent.ToolTip, QtCore.QPoint(0, 0), QtCore.QPoint(0, 0))

    # Widget with a tooltip: the filter displays the folded text and consumes.
    with_tip = QtWidgets.QLabel("x")
    with_tip.setToolTip(_LONG)
    assert filt.eventFilter(with_tip, event) is True

    # Widget without a tooltip: pass through so Qt can inherit from a parent.
    without_tip = QtWidgets.QLabel("y")
    assert filt.eventFilter(without_tip, event) is False


def test_settings_deep_merge_exposes_new_keys():
    from chisurf.core.settings.settings_utils import _deep_merge

    defaults = {"gui": {"tooltip": {"enabled": True, "wrap_width": 72}, "keep": 1}}
    user = {"gui": {"keep": 2}}  # older user file without the new tooltip block
    merged = _deep_merge(defaults, user)
    assert merged["gui"]["tooltip"]["wrap_width"] == 72  # new default surfaces
    assert merged["gui"]["keep"] == 2  # user override still wins


def test_tooltip_settings_present():
    from chisurf.core.settings import cs_settings

    gui = cs_settings.get("gui", {})
    assert gui.get("tooltip", {}).get("wrap_width") == 72
    assert gui.get("application_font_size") == 13
