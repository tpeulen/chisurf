"""Tests for the NavigationPanelTool left-pane search filter."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("qtpy")

from chisurf.gui.widgets.navigation import NavigationPanelTool


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _panels():
    from qtpy import QtWidgets

    leaf = lambda p: QtWidgets.QLabel()  # noqa: E731
    return [
        {"name": "Overview", "factory": leaf},
        {"name": "Samples", "separator": True},
        {"name": "Sample Conditions", "factory": leaf},
        {"name": "Entities", "factory": leaf},
        {"name": "Experiments", "separator": True},
        {"name": "Setups", "factory": leaf},
    ]


def _visible(w):
    return [
        w.panels[i]["name"] for i in range(w.nav_list.count()) if not w.nav_list.item(i).isHidden()
    ]


def test_search_on_by_default(qapp):
    w = NavigationPanelTool(title="t", panels=_panels())
    assert w.nav_search is not None


def test_search_filters_to_hits_with_group_headers(qapp):
    w = NavigationPanelTool(title="t", panels=_panels())
    w.nav_search.setText("sample")
    # Only the matching leaf and its group header remain.
    assert _visible(w) == ["Samples", "Sample Conditions"]


def test_search_hides_groups_without_matches(qapp):
    w = NavigationPanelTool(title="t", panels=_panels())
    w.nav_search.setText("setup")
    assert _visible(w) == ["Experiments", "Setups"]


def test_clearing_search_restores_all(qapp):
    w = NavigationPanelTool(title="t", panels=_panels())
    w.nav_search.setText("setup")
    w.nav_search.setText("")
    assert _visible(w) == [p["name"] for p in _panels()]


def test_searchable_false_has_no_search_box(qapp):
    w = NavigationPanelTool(title="t", panels=_panels(), searchable=False)
    assert w.nav_search is None


def test_selected_step_stays_readable(qapp):
    """The current step must be drawn on the highlight, not white-on-white.

    Styling ``QListWidget::item`` at all hands item painting to the stylesheet
    style, which then draws no selection background — the selected row's label
    disappeared, leaving only its emoji visible.
    """
    w = NavigationPanelTool(title="t", panels=_panels())
    w.resize(500, 320)
    w.show()
    w.nav_list.setCurrentRow(0)
    qapp.processEvents()

    image = w.nav_list.grab().toImage()
    rect = w.nav_list.visualItemRect(w.nav_list.item(0))
    counts: dict[tuple[int, int, int], int] = {}
    for x in range(rect.left() + 2, rect.right() - 2):
        for y in range(rect.top() + 2, rect.bottom() - 2):
            rgb = image.pixelColor(x, y).getRgb()[:3]
            counts[rgb] = counts.get(rgb, 0) + 1

    palette = w.nav_list.palette()
    highlight = palette.highlight().color().getRgb()[:3]
    text = palette.highlightedText().color().getRgb()[:3]

    assert counts.get(highlight, 0) > 100, f"no selection background drawn: {counts}"
    assert counts.get(text, 0) > 20, f"the selected label is invisible: {counts}"
    w.close()
