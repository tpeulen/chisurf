"""The maturity flags (``experimental`` / ``deprecated``) of a tool, as every host renders them.

A tool declares its maturity once, in its ``manifest.json``; the markers and wording any shell
shows come from one table in ``chisurf.core.plugin.maturity``. The Qt navigation panel and ribbon
that rendered them are gone; the emtk shell reads the same table.
"""

from __future__ import annotations

from chisurf.core.plugin.maturity import maturity_markers, maturity_message, maturity_warnings


def test_markers_follow_the_render_order():
    assert maturity_markers({}) == []
    assert maturity_markers({"experimental": True}) == ["⚠️"]
    assert maturity_markers({"deprecated": True, "experimental": True}) == ["⛔", "⚠️"]


def test_message_prefers_the_tools_own_wording():
    meta = {"experimental": True, "experimental_message": "not validated on real data"}
    assert maturity_message(meta, "experimental", "Tool") == "not validated on real data"


def test_message_falls_back_to_the_flag_default():
    text = maturity_message({"deprecated": True}, "deprecated", "Old Tool")
    assert text.startswith("Old Tool is DEPRECATED")


def test_warnings_pair_each_marker_with_its_message():
    lines = maturity_warnings({"deprecated": True, "experimental": True}, "Tool")
    assert len(lines) == 2
    assert lines[0].startswith("⛔") and "DEPRECATED" in lines[0]
    assert lines[1].startswith("⚠️") and "EXPERIMENTAL" in lines[1]
    assert maturity_warnings({"name": "Tool"}) == []
