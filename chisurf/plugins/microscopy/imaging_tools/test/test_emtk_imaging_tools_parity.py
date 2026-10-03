"""The native Imaging Tools hub against the Qt tool it replaces: the tool list, the pipeline order, the shared context.

Hermetic: settings, MMFDB and HOME are temporary folders (the detector-setup store is the temporary settings folder), no
network. The Qt tool is the committed ``ImagingToolsTool`` built offscreen. Children are fakes (recording what the hub
hands them) except in the tests that draw the real native children. A module guard fails the run if anything appears
in the real ``~/.chisurf`` other than its ``logs`` folder.
"""

from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

import pytest
from emtk.app import ImApp
from emtk.testing import RecordingPainter

from chisurf.emtk.validation import BlockQt
from chisurf.plugins.core.project_browser.test.driving import clipped_texts, draw_clip, layout_problems
from chisurf.plugins.microscopy.imaging_tools.gui.app import PANELS, ImagingToolsApp, make_app

HERE = Path(__file__).parent
BIG, SMALL = (1200, 800), (800, 600)
REAL_CHISURF = Path(os.path.expanduser("~")) / ".chisurf"


def _snapshot(root: Path) -> dict:
    out = {}
    if root.exists():
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if (rel.parts and rel.parts[0] == "logs") or "__pycache__" in rel.parts:
                continue
            stat = path.stat()
            out[str(rel)] = (stat.st_size, stat.st_mtime_ns)
    return out


@pytest.fixture(scope="module", autouse=True)
def real_chisurf_untouched():
    before = _snapshot(REAL_CHISURF)
    yield
    assert _snapshot(REAL_CHISURF) == before


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    for name in ("settings", "mmfdb", "home"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


class Client:
    def __init__(self):
        self.setup = {}

    def get_current(self):
        return self.setup

    def set_current(self, setup):
        self.setup = copy.deepcopy(setup)


class Child(ImApp):
    """A tool that records what the hub hands it."""

    def __init__(self, coordinator=None, **kwargs):
        self.coordinator = coordinator
        self.received = {}
        self.events = []
        self.value = 3
        self.dropped = []
        super().__init__(lambda: None)

    def apply_setup_settings(self, payload):
        self.received["setup"] = payload

    def apply_pipeline_context(self, payload):
        self.received["pipeline"] = payload

    def apply_calibration(self, payload):
        self.received["calibration"] = payload

    def export_settings(self):
        return {"value": self.value}

    def restore_settings(self, data):
        self.value = data["value"]

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        self.events.append(("press", round(x), round(y), button))

    def pointer_release(self, x, y, button, modifiers=0):
        self.events.append(("release", round(x), round(y), button))

    def wheel(self, x, y, steps, modifiers=0):
        self.events.append(("wheel", round(x), round(y), steps))

    def key(self, key, text="", modifiers=0):
        self.events.append(("key", key, text))
        return False

    def on_files_dropped(self, paths):
        self.dropped.append(list(paths))
        return True


ROLES = [row[0] for row in PANELS]


def fake_hub(**kw):
    return ImagingToolsApp(client=Client(), factories={r: Child for r in ROLES}, **kw)


def draw(app, size=BIG, frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


@pytest.fixture(scope="module")
def qt_module():
    pytest.importorskip("qtpy.QtWidgets")
    from qtpy import QtWidgets

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.microscopy.imaging_tools.gui import tool

    tool._qapp = qapp
    return tool


# -- parity with the Qt tool ------------------------------------------------------------------------------------------ #


def test_the_tool_list_equals_the_qt_lists_names_order_roles_and_descriptions(qt_module):
    qt = [p for p in qt_module.IMAGING_PANELS if not p.get("separator")]
    assert [p["role"] for p in qt] == ROLES
    assert [p["name"] for p in qt] == [row[2] for row in PANELS]
    assert [p["description"] for p in qt] == [row[3] for row in PANELS]  # the tooltip and header texts, word for word


def test_the_separator_sits_where_the_qt_list_has_it(qt_module):
    roles = [p["role"] for p in qt_module.IMAGING_PANELS]
    assert roles[roles.index("separator") + 1] == "clsm_draw"
    from chisurf.plugins.microscopy.imaging_tools.gui.app import SEPARATOR_BEFORE

    assert SEPARATOR_BEFORE == "clsm_draw"


def test_the_pipeline_order_and_the_analysis_roles_equal_the_qt_tools(qt_module):
    assert ImagingToolsApp.PIPELINE_ORDER == qt_module.ImagingToolsTool.PIPELINE_ORDER
    assert ImagingToolsApp.ANALYSIS_ROLES == qt_module.ImagingToolsTool.ANALYSIS_ROLES


def test_every_listed_tool_has_a_native_factory_in_its_manifest():
    app = ImagingToolsApp(client=Client())
    missing = [role for role in ROLES if not app.factory(role)]
    assert missing == [], missing


# -- the shared context (the Qt tool's coordinator duties) ---------------------------------------------------------------- #


def test_lazy_context_navigation_snapshot_and_state():
    app = fake_hub()
    app.set_setup({"detectors": {"green": {"chs": [0]}}})
    app.set_pipeline(source="image.ptu", hdf5="image.h5")
    calibration = {"green": {"bg_vv": 4}}
    app.set_calibration(calibration)
    assert not app.children
    assert app.goto_role("pixel_intensity")
    child = app.child
    assert child.coordinator is app
    assert child.received["pipeline"] == {"source": "image.ptu", "hdf5": "image.h5"}
    assert child.received["setup"] == app.setup
    calibration["green"]["bg_vv"] = 999
    assert child.received["calibration"]["green"]["bg_vv"] == 4
    child.value = 12
    app.advance_from("pixel_intensity")
    assert app.selected == "pixel_nb"
    app.previous_from("pixel_nb")
    assert app.child is child
    saved = app.export_settings()
    restored = fake_hub()
    restored.restore_settings(saved)
    assert restored.child.value == 12 and restored.child.received == child.received
    app.close()
    restored.close()


def test_the_stepper_walks_the_list_order_like_the_qt_shell(qt_module):
    app = fake_hub()
    roles = app.list_roles()
    qt_roles = [p["role"] for p in qt_module.IMAGING_PANELS if not p.get("separator")]
    assert roles == qt_roles
    app.goto_role("setup")
    visited = ["setup"]
    while app.step_list(1):
        visited.append(app.selected)
    assert visited == roles and not app.step_list(1)
    app.goto_role("browser")
    assert app.fast_forward_queue()[-1] == "pixel_mle"  # the Qt queue stops at the separator
    app.close()


def test_next_and_previous_hand_offs_walk_the_pipeline_order_and_stop_at_its_ends():
    app = fake_hub()
    app.goto_role("browser")
    visited = ["browser"]
    for _ in range(len(app.PIPELINE_ORDER) + 2):
        app.advance_from(app.selected)
        visited.append(app.selected)
    assert visited[: len(app.PIPELINE_ORDER)] == list(app.PIPELINE_ORDER) and visited[-1] == "pixel_mle"
    app.goto_role("clsm_draw")
    app.advance_from("clsm_draw")  # not a step of the pipeline: stays
    assert app.selected == "clsm_draw"
    app.goto_role("browser")
    app.previous_from("browser")
    assert app.selected == "browser"
    app.close()


def test_an_unknown_role_and_a_pending_tool_are_refused_with_a_reason():
    app = ImagingToolsApp(client=Client(), factories={"browser": Child})
    assert not app.goto_role("nonsense")
    assert not app.goto_role("pixel_mle") and "pending" in app.error
    assert app.goto_role("browser") and app.error == ""
    app.close()


def test_a_child_that_fails_to_build_reports_the_error_and_the_next_one_still_opens():
    def broken(**kwargs):
        raise RuntimeError("boom in the factory")

    app = ImagingToolsApp(client=Client(), factories={"browser": broken, "drift": Child})
    assert not app.goto_role("browser") and "boom in the factory" in app.error
    assert "boom in the factory" in " ".join(draw(app).strings)
    assert app.goto_role("drift") and app.error == ""
    app.close()


def test_the_auto_run_starts_only_the_analysis_steps_that_have_a_source_and_no_result():
    started = []

    class Runner(Child):
        def __init__(self, coordinator=None, **kw):
            super().__init__(coordinator)
            self.model = type("M", (), {"_columns": None, "pipeline_sink": None})()
            self.job = type("J", (), {"busy": False})()

        def start(self, name):
            started.append(name)

    app = ImagingToolsApp(client=Client(), factories={r: Runner for r in ROLES})
    app.goto_role("pixel_nb")
    assert started == []  # no source yet
    app.set_pipeline(source="a.ptu")
    app.goto_role("pixel_micro_time")
    app.goto_role("calibration")
    app.goto_role("pixel_mle")
    assert started == ["compute_job"]  # micro-time ran; calibration and MLE are settings / manual steps
    app.close()


def test_the_pipeline_context_reaches_open_tools_and_a_new_source_is_remembered():
    app = fake_hub()
    app.goto_role("pixel_nb")
    app.set_pipeline(source="s1.ptu")
    assert app.child.received["pipeline"] == {"source": "s1.ptu", "hdf5": ""}
    app.set_pipeline(hdf5="shared.h5")
    assert app.child.received["pipeline"] == {"source": "s1.ptu", "hdf5": "shared.h5"}
    assert "s1.ptu" in " ".join(draw(app).strings) and "shared.h5" in " ".join(draw(app).strings)
    app.close()


# -- drawing, layout, tooltips, Qt-free, settings -------------------------------------------------------------------------- #


@pytest.mark.parametrize("size", [BIG, SMALL])
def test_the_hub_draws_without_clipped_or_overlapping_text_around_a_child(size):
    app = fake_hub()
    painter = draw_clip(app, size, frames=3)
    assert {"Back", "Next", "Run all", "Help", "Guide"} <= set(painter.strings) | {"Search..."}
    left = app.child_box[0]
    hub = [t for t in painter.shown if t[0][0] < left or t[0][1] < app.child_box[1]]
    problems = layout_problems(type("P", (), {"shown": hub})(), size)
    assert problems == [], problems
    cut = clipped_texts(type("P", (), {"shown": hub})())
    assert cut == [], cut
    app.close()


def test_a_long_description_and_an_error_grow_the_header_instead_of_overlapping_the_child():
    app = fake_hub()
    app.goto_role("flow")  # the longest description
    draw(app, SMALL)
    short_header = app.child_box[1]
    app.error = "x" * 400
    draw(app, SMALL)
    assert app.child_box[1] > short_header > 60
    app.close()


@pytest.mark.parametrize("role", ROLES)
def test_all_native_children_render_without_qt(role):
    blocker = BlockQt()
    sys.meta_path.insert(0, blocker)
    app = ImagingToolsApp(client=Client())
    try:
        assert app.goto_role(role), app.error
        for width, height in (BIG, SMALL):
            painter = draw(app, (width, height), frames=2)
            assert painter.strings
        assert app.child._coordinator is app and app.child._pipeline_role == role
    finally:
        app.close()
        sys.meta_path.remove(blocker)


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    assert emtk_inventory(build_emtk_app("imaging_tools"))["controls_without_tooltip"] == []


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("imaging_tools")
    assert result["ok"], result["output"]


def test_settings_round_trip_keeps_search_selection_and_the_context():
    app = fake_hub()
    app.search = "pixel"
    app.goto_role("pixel_phasor")
    app.set_pipeline(source="a.ptu", hdf5="a.h5")
    app.set_setup({"detectors": {"g": {"chs": [1]}}})
    app.set_calibration({"g": {"bg": 1}})
    saved = app.export_settings()
    other = fake_hub()
    other.restore_settings(copy.deepcopy(saved))
    assert (other.search, other.selected, other._pipeline, other.setup, other._calibration) == (
        "pixel", "pixel_phasor", {"source": "a.ptu", "hdf5": "a.h5"}, {"detectors": {"g": {"chs": [1]}}}, {"g": {"bg": 1}})
    app.close()
    other.close()


@pytest.mark.parametrize("locale", ["en", "de", "fr", "es", "pt", "ru"])
def test_existing_catalog_locales_render_native_hub(locale):
    from chisurf.emtk.i18n import install, set_locale

    install(locale)
    app = ImagingToolsApp(client=Client(), factories={"browser": Child})
    try:
        assert draw(app, SMALL, frames=2).strings
    finally:
        app.close()
        set_locale("en")


def test_make_app_builds_the_hub():
    app = make_app(client=Client(), factories={"browser": Child})
    assert draw(app).strings and not app.animating()
    app.close()


@pytest.mark.parametrize("role", ["pixel_intensity", "pixel_nb", "pixel_micro_time", "pixel_phasor", "calibration"])
def test_current_native_pipeline_receives_setup_source_hdf5_and_calibration(role, monkeypatch):
    import numpy as np

    from chisurf.core.fluorescence import imaging

    def fake_compute(filename, windows, kind, progress=None):
        return {"green": {"n_par": np.ones((4, 4)) * 10, "n_perp": np.ones((4, 4)), "durations": np.ones(4) * 0.01,
                          "n_pixel": 4, "bg": 0.0, "frames": np.ones((3, 4, 4))}}

    monkeypatch.setattr(imaging, "compute_windows", fake_compute)
    app = ImagingToolsApp(client=Client())
    try:
        assert app.goto_role(role), app.error
        child = app.child
        app.set_setup({"detectors": {"green": {"chs": [0, 1], "ch_p": [0], "ch_s": [1], "micro_time_ranges": [[0, 4095]]}}})
        app.set_pipeline(source="selected.ptu", hdf5="shared.imaging.h5")
        app.set_calibration({"green": {"bg_vv": 2.0, "bg_vh": 3.0}})
        job = getattr(child, "job", None)
        if job and job.thread:
            job.thread.join(5)
            job.poll()
            child.draw(RecordingPainter(), 0, 0, 950, 650)
        assert "green" in child.model.detectors and child.model.filename == "selected.ptu"
        if role != "calibration":
            assert child.model.pipeline_hdf5 == "shared.imaging.h5" and child.model.pipeline_sink == app.set_pipeline
        else:
            assert child.model.publish == app.set_calibration
    finally:
        for child in app.children.values():
            child.model.flush_to_hdf5 = lambda: None
        app.close()
