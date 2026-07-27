"""Tests for the maturity flags (``experimental`` / ``deprecated``) of a panel.

A tool declares its maturity once — in its ``manifest.json`` — and every shell
that embeds it marks the navigation entry and tops the panel with a banner.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("qtpy")

from chisurf.gui.widgets import navigation
from chisurf.gui.widgets.navigation import NavigationPanelTool, apply_manifest_flags


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _panels():
    from qtpy import QtWidgets

    leaf = lambda p: QtWidgets.QLabel("panel body")  # noqa: E731
    return [
        {"name": "Plain", "factory": leaf},
        {"name": "Young", "factory": leaf, "experimental": True},
        {
            "name": "Old",
            "factory": leaf,
            "deprecated": True,
            "deprecation_message": "Old is gone after the next release",
        },
        {"name": "Both", "factory": leaf, "experimental": True, "deprecated": True},
    ]


def _banner_texts(window, row: int) -> list[str]:
    """Return the banner texts above the panel in *row* (top to bottom)."""
    from qtpy import QtWidgets

    window.nav_list.setCurrentRow(row)
    wrapper = window.stacked_widget.currentWidget()
    return [
        label.text()
        for label in wrapper.findChildren(QtWidgets.QLabel)
        if label.text().startswith(("⚠️", "⛔"))
    ]


def test_deprecated_panel_is_marked_in_the_selector(qapp):
    """A deprecated tool is flagged in the navigation list, like an experimental one."""
    w = NavigationPanelTool(title="t", panels=_panels())
    labels = [w.nav_list.item(i).text() for i in range(w.nav_list.count())]
    assert labels[0] == "Plain"
    assert labels[1].endswith("⚠️")
    assert labels[2].endswith("⛔")
    assert labels[3].endswith("⛔  ⚠️")
    w.close()


def test_deprecated_panel_carries_its_manifest_message(qapp):
    """The banner shows the tool's own deprecation message, not the generic text."""
    w = NavigationPanelTool(title="t", panels=_panels())
    texts = _banner_texts(w, 2)
    assert texts == ["⛔  Old is gone after the next release"]
    w.close()


def test_experimental_panel_still_gets_its_banner(qapp):
    """The pre-existing experimental banner is unchanged by the shared flag seam."""
    w = NavigationPanelTool(title="t", panels=_panels())
    texts = _banner_texts(w, 1)
    assert len(texts) == 1
    assert texts[0].startswith("⚠️")
    assert "EXPERIMENTAL" in texts[0]
    w.close()


def test_both_flags_render_both_banners_deprecated_first(qapp):
    """A tool that is both gets both banners; the harder warning comes first."""
    w = NavigationPanelTool(title="t", panels=_panels())
    texts = _banner_texts(w, 3)
    assert len(texts) == 2
    assert texts[0].startswith("⛔") and "DEPRECATED" in texts[0]
    assert texts[1].startswith("⚠️") and "EXPERIMENTAL" in texts[1]
    w.close()


def test_unflagged_panel_has_no_banner(qapp):
    """A mature tool is not topped with anything."""
    w = NavigationPanelTool(title="t", panels=_panels())
    assert _banner_texts(w, 0) == []
    w.close()


def test_apply_manifest_flags_reads_the_real_manifest():
    """The flag is taken from the named manifest, not written in the host."""
    panels = apply_manifest_flags(
        [
            {"name": "Lazy Lifetime", "manifest": "fluorescence_decay/lltf"},
            {"name": "Microtime Histogram", "manifest": "tttr/microtime_histogram"},
            {"name": "No manifest named"},
        ]
    )
    assert panels[0]["experimental"] is True
    assert "experimental" in panels[0]["experimental_message"].lower()
    assert "experimental" not in panels[1]
    assert "experimental" not in panels[2]


def test_apply_manifest_flags_reads_deprecated(tmp_path, monkeypatch):
    """``deprecated`` / ``deprecation_message`` travel the same path as ``experimental``."""
    plugin_dir = tmp_path / "group" / "retired_tool"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": "retired_tool",
                "version": "1.0.0",
                "display_name": "Group:Retired Tool",
                "deprecated": True,
                "deprecation_message": "Retired Tool is replaced by New Tool",
            }
        )
    )
    monkeypatch.setattr(navigation, "_PLUGINS_DIR", tmp_path)

    panel = apply_manifest_flags([{"name": "Retired", "manifest": "group/retired_tool"}])[0]
    assert panel["deprecated"] is True
    assert panel["deprecation_message"] == "Retired Tool is replaced by New Tool"


def test_apply_manifest_flags_tolerates_a_missing_manifest(tmp_path, monkeypatch):
    """A panel naming a manifest that is not there stays as it was."""
    monkeypatch.setattr(navigation, "_PLUGINS_DIR", tmp_path)
    panel = apply_manifest_flags([{"name": "Gone", "manifest": "group/absent"}])[0]
    assert panel == {"name": "Gone", "manifest": "group/absent"}
