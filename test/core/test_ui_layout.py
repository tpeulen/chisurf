"""A project's window layout opens whatever front end opens it (``chisurf.core.project.ui_layout``).

Toolkit-neutral record + per-toolkit hints: a front end applies its own hint, else the neutral layout; other toolkits'
hints are ignored; projects written before the neutral record (top-level Qt bytes) still restore; nothing raises.
"""

from __future__ import annotations

import pytest

from chisurf.core.project import ui_layout


class FakeWindow:
    def __init__(self, kind):
        self.kind = kind
        self.applied = None
        self.hint = None


@pytest.fixture
def toolkit(monkeypatch):
    """A registered toolkit 'tk' (and only it) that records what was applied."""
    monkeypatch.setattr(ui_layout, "_BACKENDS", {})
    monkeypatch.setattr(ui_layout, "KNOWN_BACKENDS", ())

    def apply(window, layout):
        window.applied = layout
        return []

    def apply_hint(window, hint):
        window.hint = hint
        return True

    ui_layout.register_backend(ui_layout.LayoutBackend(
        "tk", lambda w: w.kind == "tk",
        lambda w: {"window": {"x": 1, "y": 2, "width": 300, "height": 200}, "docks": {"d": {"area": "left"}},
                   "views": [{"uid": "fit-1", "state": "maximized"}]},
        apply, lambda w: {"bytes": "00ff"}, apply_hint))
    return FakeWindow


def test_capture_writes_the_neutral_layout_and_the_toolkits_hint(toolkit):
    state = ui_layout.capture(toolkit("tk"))
    assert state["layout"]["window"] == {"x": 1, "y": 2, "width": 300, "height": 200, "maximized": False}
    assert state["layout"]["views"] == [{"kind": "fit", "uid": "fit-1", "state": "maximized"}]
    assert state["backend"] == {"tk": {"bytes": "00ff"}}


def test_another_toolkits_project_restores_from_the_neutral_layout(toolkit):
    """Saved by toolkit 'other' (its hint is not ours): the neutral layout is applied, the foreign hint ignored."""
    window = toolkit("tk")
    saved = {"layout": {"window": {"x": 5, "y": 6, "width": 700, "height": 500, "maximized": True}},
             "backend": {"other": {"opaque": "whatever"}}}
    assert ui_layout.restore(window, saved) == []
    assert window.hint is None and window.applied["window"]["width"] == 700


def test_own_hint_wins_for_window_and_docks_views_come_from_the_neutral_record(toolkit):
    window = toolkit("tk")
    saved = {"layout": {"window": {"x": 0, "y": 0, "width": 9, "height": 9}, "views": [{"uid": "f", "state": "minimized"}]},
             "backend": {"tk": {"bytes": "abcd"}}}
    ui_layout.restore(window, saved)
    assert window.hint == {"bytes": "abcd"}
    assert "window" not in window.applied and window.applied["views"][0]["state"] == "minimized"


def test_pre_neutral_projects_read_their_top_level_qt_bytes_as_the_qt_hint():
    old = {"geometry": "01", "dock_state": "02", "mdi_area": {"state": "03"}, "active_tabs": {}}
    assert ui_layout.backend_hint(old, "qt") == {"geometry": "01", "dock_state": "02", "mdi_area": {"state": "03"}}
    assert ui_layout.backend_hint(old, "emtk") is None


def test_malformed_layouts_are_reduced_never_raised(toolkit):
    junk = {"window": {"x": "a"}, "docks": {"": {}, "ok": {"area": "nowhere", "rect": [1, 2]}},
            "views": [{"uid": 3}, {"uid": "v", "state": "sideways", "rect": [0, 0, 10, 10]}], "extra": 1}
    out = ui_layout.normalize(junk)
    assert "window" not in out and out["docks"] == {"ok": {"visible": True, "floating": False}}
    assert out["views"] == [{"kind": "fit", "uid": "v", "state": "normal", "rect": [0, 0, 10, 10]}]
    assert ui_layout.restore(toolkit("tk"), {"layout": "garbage"}) == []


def test_a_window_no_front_end_claims_is_reported_not_raised(toolkit):
    assert ui_layout.capture(toolkit("nope")) == {}
    assert ui_layout.restore(toolkit("nope"), {"layout": {}}) == ["no front end claims this window"]


def test_the_core_module_does_not_import_a_gui_toolkit():
    import subprocess
    import sys

    code = ("import sys; import chisurf.core.project.ui_layout; "
            "print(any(m.split('.')[0] in ('qtpy', 'PyQt5', 'PySide2', 'PySide6', 'emtk') for m in sys.modules))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "False"
