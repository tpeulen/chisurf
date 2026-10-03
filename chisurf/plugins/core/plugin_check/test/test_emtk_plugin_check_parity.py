"""The native Plugin Check against the Qt tool it replaces: the plugin list, the cells, the details, the sweep rules.

Hermetic: settings, MMFDB and HOME are temporary folders, no sweep starts a real child process (``_check`` is stubbed
except in the two tests that run the real validator on the built-in ``about`` plugin, whose child gets its own
temporary HOME), no network. A module guard fails the run if anything appears in the real ``~/.chisurf`` other than
its ``logs`` folder (every ChiSurf process writes a log there).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.core.plugin_check.gui import model as model_module
from chisurf.plugins.core.plugin_check.gui.app import PluginCheckApp, make_app
from chisurf.plugins.core.plugin_check.gui.model import (
    BLACKLIST_AFTER,
    ERROR_CELL,
    SAFE_COUNT,
    PluginCheckModel,
    dependency_summary,
    discover,
    render_bounds,
)
from chisurf.plugins.core.project_browser.test.driving import ClipPainter, clipped_texts, draw_clip, layout_problems

HERE = Path(__file__).parent
PLUGIN = HERE.parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
EVIDENCE = REPO / "okf/plugins/emtk-ports/plugin_check"
SPEC = PLUGIN / "gui/plugin_check_emtk.view.json"
BIG = (1200, 800)
SMALL = (800, 600)
REAL_CHISURF = Path(os.path.expanduser("~")) / ".chisurf"


def _snapshot(root: Path) -> dict:
    """``{path: (size, mtime_ns)}`` under *root*, ignoring ``logs`` (written by every ChiSurf process)."""
    out = {}
    if not root.exists():
        return out
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] == "logs" or "__pycache__" in rel.parts:
            continue
        stat = path.stat()
        out[str(rel)] = (stat.st_size, stat.st_mtime_ns)
    return out


@pytest.fixture(scope="module", autouse=True)
def real_chisurf_untouched():
    """Nothing in the real ``~/.chisurf`` (apart from ``logs``) changes while this module runs."""
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


def draw(app, size=BIG, frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def small_catalog(n=12):
    """A fixed catalog standing in for discovery: every kind of row the table has."""
    catalog = {}
    for i in range(n):
        catalog[f"p{i:02d}"] = {"id": f"p{i:02d}", "plugin_name": f"Group:Tool {i:02d}", "version": f"1.{i}",
                                "source": "user" if i == 3 else "built-in", "module_path": f"chisurf.plugins.p{i:02d}",
                                "description": f"Plugin number {i}.", "requires": {"p00": ">=1"} if i == 1 else {},
                                "optional_requires": {"p02": "*", "p04": "*"} if i == 5 else {},
                                "entrypoints": {"emtk": f"pkg{i}:make_app"} if i % 3 else {"gui": f"pkg{i}:Tool"}}
    return catalog


@pytest.fixture(scope="module")
def discovered():
    """The real plugin list, discovered once (reads manifests, imports no plugin)."""
    return discover()


@pytest.fixture(scope="module")
def qt_tool():
    """The Qt Plugin Check window, built offscreen on the same discovery."""
    pytest.importorskip("qtpy.QtWidgets")
    from qtpy import QtWidgets

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])  # kept alive by the generator frame
    from chisurf.plugins.core.plugin_check.gui.tool import PluginCheckTool

    tool = PluginCheckTool()
    yield tool
    tool.close()
    del qapp


def qt_rows(tool):
    tree = tool.plugin_tree
    return [[tree.topLevelItem(i).text(c) for c in range(5)] for i in range(tree.topLevelItemCount())]


# -- numeric parity with the Qt tool --------------------------------------------------------------------------------- #


def test_the_list_equals_the_qt_trees_rows_in_the_same_order(discovered, qt_tool):
    model = PluginCheckModel(*discovered)
    rows = model.check_rows()
    qt = qt_rows(qt_tool)
    assert len(rows) == len(qt) > 100
    assert [r["plugin"] for r in rows] == [q[0] for q in qt]  # the menu path, every row, in the tree's order
    assert [r["source"] for r in rows] == [q[2] for q in qt]
    assert [r["depends"] for r in rows] == [q[3] for q in qt]  # hard names, "(+N optional)"
    assert {r["status"] for r in rows} == {"pending"} and {q[1] for q in qt} == {qt_tool.plugin_tree.topLevelItem(0).text(1)}


def test_the_baseline_rows_the_qt_tool_showed_are_matched_cell_for_cell(discovered):
    """The committed Qt capture (``qt_rows_listed.json``) is the independent reference for the Depends-on cells."""
    baseline = json.loads((EVIDENCE / "qt_rows_listed.json").read_text())["rows"]
    rows = PluginCheckModel(*discovered).check_rows()
    now = {r["plugin"]: r["depends"] for r in rows}
    old = {name: depends for name, _status, _source, depends, _error in baseline}
    common = set(now) & set(old)
    assert len(common) > 100
    assert {n: now[n] for n in common} == {n: old[n] for n in common}


def test_the_status_line_counts_plugins_and_dependency_problems_like_the_qt_tool(discovered, qt_tool):
    model = PluginCheckModel(*discovered)
    found = len(qt_rows(qt_tool))
    assert str(found) in model.message and "plugin(s) found" in model.message
    assert str(found) in qt_tool.status_label.text()
    qt_problems = qt_tool._dependency_report.problems() if qt_tool._dependency_report is not None else []
    assert model.problems() == qt_problems
    if qt_problems:
        assert f"{len(qt_problems)} dependency problem(s)" in model.message


def test_the_details_equal_the_qt_details_pane(discovered, qt_tool):
    model = PluginCheckModel(*discovered)
    tree = qt_tool.plugin_tree
    compared = 0
    for index in (0, 1, 7, 20, 60):
        item = tree.topLevelItem(index)
        info = item.data(0, 0x0100)  # Qt.UserRole
        qt_tool.update_plugin_result(item.text(0), True, None)
        qt_tool.on_plugin_selected(item, 0)
        text = qt_tool.details_label.text()
        model.selected_key = info.get("manifest_id") or info["module_path"]
        blocks = dict(model.details())
        assert blocks["Plugin"] == item.text(0)
        assert f"<b>Module:</b> {info['module_path']}" in text and blocks["Module"] == info["module_path"]
        assert blocks["Source"] == info["source"]
        for caption, key in (("Requires (load order)", "requires"), ("Optional", "optional_requires")):
            value = render_bounds(info.get(key) or {})
            if value:
                assert blocks[caption] == value and f"<b>{caption}:</b> {value}" in text
            else:
                assert caption not in blocks
        if info.get("description"):
            assert blocks["Description"] == info["description"].strip()
        compared += 1
    assert compared == 5


def test_dependency_cells_follow_the_qt_rules():
    assert dependency_summary({}, {}) == ""
    assert dependency_summary({"b": "*", "a": ">=1"}, {}) == "a, b"
    assert dependency_summary({"a": "*"}, {"x": "*", "y": "*"}) == "a (+2 optional)"
    assert dependency_summary({}, {"x": "*"}) == "(+1 optional)"
    assert render_bounds({"b": "*", "a": ">=1.2", "c": " "}) == "a >=1.2, b, c"


def test_an_error_is_cut_at_fifty_characters_with_dots_like_the_qt_tool(qt_tool):
    long = "ImportError: " + "x" * 80
    item = qt_tool.plugin_tree.topLevelItem(0)
    qt_tool.update_plugin_result(item.text(0), False, long)
    qt_cell = item.text(4)
    catalog = small_catalog(3)
    model = PluginCheckModel(catalog)
    model._events.put(("p00", {"status": "fail", "error": long + "\nsecond line"}))
    model.poll()
    cell = model.check_rows()[0]["error"]
    assert cell == qt_cell == long[:50] + "..." and len(long[:ERROR_CELL]) == 50
    assert model.error_text.startswith(long) and "second line" in model.error_text  # the whole text is in the details


def test_the_qt_status_glyphs_map_to_the_native_status_words(qt_tool):
    model = PluginCheckModel(small_catalog(4))
    for key, result in (("p00", {"status": "pass"}), ("p01", {"status": "fail", "error": "boom"}),
                        ("p02", {"status": "skipped", "error": "Blacklisted after repeated failures"})):
        model._events.put((key, result))
    model.poll()
    assert [model.status_of(k) for k in ("p00", "p01", "p02", "p03")] == ["pass", "fail", "skipped", "pending"]
    item = qt_tool.plugin_tree.topLevelItem(0)
    glyphs = []
    for success, error in ((True, None), (False, "boom"), (False, "Skipped: gui execution blocked")):
        qt_tool.update_plugin_result(item.text(0), success, error)
        glyphs.append(item.text(1))
    assert len(set(glyphs)) == 3  # Qt told pass / fail / skipped apart; so do the three words


# -- the options and their limits ---------------------------------------------------------------------------------- #


def test_the_sweep_options_have_the_qt_defaults_and_limits(qt_tool):
    spec = json.loads(SPEC.read_text())
    delay = next(s for s in _walk(spec["sections"]) if s.get("attr") == "delay")
    spin = qt_tool.delay_spinbox
    assert (delay["minimum"], delay["maximum"], delay["step"]) == (spin.minimum(), spin.maximum(), spin.singleStep())
    assert PluginCheckModel(small_catalog(2)).delay == 0.5 == spin.value()
    assert PluginCheckModel(small_catalog(2)).skip_blacklisted is True is qt_tool.skip_blacklisted_checkbox.isChecked()


def _walk(sections):
    for section in sections:
        yield section
        yield from _walk(section.get("sections", []))


def test_safe_sweep_checks_the_first_ten_plugins_like_the_qt_tool(discovered, qt_tool, monkeypatch):
    model = PluginCheckModel(*discovered)
    model.delay = 0
    checked = []
    monkeypatch.setattr(model, "_check", lambda factory, timeout: checked.append((factory, timeout)) or {"status": "pass"})
    assert model.test_safe()
    model._thread.join(10)
    model.poll()
    qt_first = [r[0] for r in qt_rows(qt_tool)[:SAFE_COUNT]]
    assert model.total == SAFE_COUNT == 10 and sorted(model.results) == sorted(
        k for k in model.catalog if model.name_of(k) in qt_first)
    assert all(timeout <= 5.0 for _factory, timeout in checked)  # the short timeout of a safe sweep
    assert "complete" in model.message and not model.running


def test_test_all_visits_every_plugin_and_sorts_the_rest_by_what_they_declare(monkeypatch):
    catalog = small_catalog(7)
    catalog["nogui"] = {"id": "nogui", "plugin_name": "Lib:Nothing", "entrypoints": {}}
    model = PluginCheckModel(catalog)
    model.delay = 0
    monkeypatch.setattr(model, "_check", lambda factory, timeout: {"status": "pass"})
    assert model.test_all()
    model._thread.join(10)
    model.poll()
    assert model.current == model.total == 8
    assert model.status_of("nogui") == "no GUI"
    assert model.status_of("p00") == "Qt only" and model.status_of("p01") == "pass"
    assert "2 pass" not in model.message and "pass" in model.message


def test_a_second_start_while_running_is_refused_and_refresh_waits(monkeypatch):
    model = PluginCheckModel(small_catalog(4))
    model.delay = 0
    release = []
    monkeypatch.setattr(model, "_check", lambda f, t: (time.sleep(0.2), {"status": "pass"})[1])
    assert model.start() and not model.start() and not model.test_safe()
    assert not model.refresh() and not model.enabled("test_all") and not model.enabled("clear_blacklist")
    assert model.enabled("stop")
    model._thread.join(10)
    model.poll()
    assert model.enabled("test_all") and not model.enabled("stop") and release == []


def test_blacklist_after_five_failures_skip_and_clear(monkeypatch):
    model = PluginCheckModel({"bad": {"id": "bad", "entrypoints": {"emtk": "bad:make_app"}}})
    model.delay = 0
    monkeypatch.setattr(model, "_check", lambda factory, timeout: {"status": "fail", "error": "Failure"})
    for _ in range(BLACKLIST_AFTER):
        assert "bad" not in model.blacklisted
        model.start()
        model._thread.join(5)
        model.poll()
    assert "bad" in model.blacklisted
    model.start()
    model._thread.join(5)
    model.poll()
    assert model.results["bad"] == {"status": "skipped", "error": "Blacklisted after repeated failures"}
    model.skip_blacklisted = False
    model.start()
    model._thread.join(5)
    model.poll()
    assert model.results["bad"]["status"] == "fail"
    model.clear_blacklist()
    assert not model.blacklisted and not model.failures and model.message == "Blacklist cleared"


def test_a_pass_resets_the_failure_count():
    model = PluginCheckModel(small_catalog(1))
    model.failures["p00"] = 4
    model._events.put(("p00", {"status": "pass"}))
    model.poll()
    model._events.put(("p00", {"status": "fail"}))
    model.poll()
    assert model.failures["p00"] == 1 and "p00" not in model.blacklisted


def test_refresh_rescans_clears_results_and_keeps_a_valid_selection(monkeypatch):
    model = PluginCheckModel(small_catalog(3))
    model._events.put(("p01", {"status": "fail", "error": "x"}))
    model.poll()
    model.selected_key = "p02"
    fresh = small_catalog(2)
    monkeypatch.setattr(model_module, "discover", lambda: (fresh, None))
    assert model.refresh()
    assert model.results == {} and list(model.catalog) == ["p00", "p01"] and model.selected_key == "p00"
    assert model.message == "Ready: 2 plugin(s) found"


def test_the_empty_catalog_says_so(monkeypatch):
    model = PluginCheckModel({})
    assert model.message == "Ready: 0 plugin(s) found" and not model.start()
    assert model.message == "No plugins to test" and model.details() == [] and model.error_text == ""


# -- the real validator on a real plugin ------------------------------------------------------------------------------- #


def test_the_real_child_check_passes_the_about_plugin_and_uses_a_temporary_home(tmp_path):
    home_before = _snapshot(REAL_CHISURF)
    model = PluginCheckModel({"about": {"id": "about", "plugin_name": "Help:About",
                                        "entrypoints": {"emtk": "chisurf.plugins.core.about.gui.app:make_app"}}})
    model.delay = 0
    assert model.start()
    end = time.monotonic() + 90
    while model.running and time.monotonic() < end:
        model.poll()
        time.sleep(0.02)
    model.poll()
    assert model.results["about"]["status"] == "pass", model.results
    assert _snapshot(REAL_CHISURF) == home_before


def test_a_failing_native_factory_is_reported_with_its_error(tmp_path, monkeypatch):
    (tmp_path / "broken_native.py").write_text("def make_app():\n    raise RuntimeError('boom from the factory')\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    model = PluginCheckModel({"broken": {"id": "broken", "entrypoints": {"emtk": "broken_native:make_app"}}})
    model.delay = 0
    model.start()
    model._thread.join(60)
    model.poll()
    result = model.results["broken"]
    assert result["status"] == "fail" and "boom from the factory" in json.dumps(result)


def test_stop_terminates_the_plugin_being_checked(tmp_path, monkeypatch):
    (tmp_path / "slow_native.py").write_text("import time\ndef make_app():\n    time.sleep(30)\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    model = PluginCheckModel({"slow": {"id": "slow", "entrypoints": {"emtk": "slow_native:make_app"}}})
    model.delay = 0
    model.start()
    end = time.monotonic() + 10
    while model._process is None and time.monotonic() < end:
        time.sleep(0.01)
    process = model._process
    assert process is not None
    model.stop()
    model._thread.join(6)
    model.poll()
    assert not model.running and process.poll() is not None and model.message == "Cancelled"


# -- drawing and layout ---------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("size", [BIG, SMALL])
def test_draws_empty_and_populated_without_clipped_or_overlapping_text(size):
    app = PluginCheckApp(PluginCheckModel(small_catalog(30)))
    empty = draw_clip(app, size)
    assert "Test all plugins" in empty.strings and "Plugin" in " ".join(empty.strings)
    model = app.model
    for key, result in (("p01", {"status": "pass"}), ("p02", {"status": "fail", "error": "Traceback\nImportError: foo"}),
                        ("p04", {"status": "skipped", "error": "Blacklisted after repeated failures"})):
        model._events.put((key, result))
    model.current, model.total = 3, 30
    model.selected_key = "p02"
    painter = draw_clip(app, size, frames=4)
    assert {"pass", "fail", "skipped", "pending"} <= set(painter.strings)
    assert "Startup error" in painter.strings and "Module" in painter.strings
    editor = [app.form.rects["error_text"]]  # the editor draws a line as separate coloured spans: not label text
    assert layout_problems(painter, size, ignore=editor) == []
    assert clipped_texts(painter, ignore=editor) == []


def test_an_idle_window_does_not_ask_for_frames_and_a_running_sweep_does(monkeypatch):
    app = PluginCheckApp(PluginCheckModel(small_catalog(3)))
    draw(app)
    assert not app.animating()
    monkeypatch.setattr(app.model, "_check", lambda f, t: (time.sleep(0.2), {"status": "pass"})[1])
    app.model.delay = 0
    app.model.start()
    assert app.animating()
    app.model._thread.join(10)
    draw(app)
    assert not app.animating()


def test_the_error_pane_is_only_there_for_a_failed_check():
    app = PluginCheckApp(PluginCheckModel(small_catalog(4)))
    app.model.selected_key = "p01"
    assert "Startup error" not in draw(app).strings
    app.model._events.put(("p01", {"status": "fail", "error": "Traceback\nImportError: foo", "traceback": "line A\nline B"}))
    painter = draw(app)
    assert "Startup error" in painter.strings
    assert app._error_editor.text == "Traceback\nImportError: foo\nline A\nline B"


# -- spec, tooltips, Qt-free, settings --------------------------------------------------------------------------------- #


def test_every_spec_attribute_call_and_action_exists_on_the_model():
    model = PluginCheckModel(small_catalog(2))
    spec = json.loads(SPEC.read_text())
    for section in _walk(spec["sections"]):
        opts = section.get("options") or {}
        for attr in (section.get("attr"), section.get("text_source"), section.get("source"), opts.get("source"),
                     opts.get("selected_call"), section.get("call")):
            if attr:
                assert hasattr(model, attr), attr
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button
            assert model.enabled(button["action"]) in (True, False)
        assert section.get("description"), f"{section.get('type')} {section.get('title') or section.get('attr')}"
        for column in opts.get("columns", []):
            assert column.get("tooltip"), column
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inventory = emtk_inventory(build_emtk_app("plugin_check"))
    assert inventory["controls_without_tooltip"] == [], inventory["controls_without_tooltip"]
    names = {c["name"] if isinstance(c, dict) else c for c in inventory.get("controls", [])}
    assert {"Help", "Guide"} <= {str(n) for n in names} or inventory["controls"]


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("plugin_check")
    assert result["ok"], result["output"]


def test_settings_round_trip_and_invalid_values_are_ignored():
    app = PluginCheckApp(PluginCheckModel(small_catalog(5)))
    app.model.selected_key = "p03"
    app.model.delay = 2.5
    app.model.skip_blacklisted = False
    draw(app)
    saved = app.export_settings()
    assert saved["selected"] == "p03" and saved["delay"] == 2.5 and saved["skip_blacklisted"] is False
    other = PluginCheckApp(PluginCheckModel(small_catalog(5)))
    other.restore_settings(json.loads(json.dumps({**saved, "query": "Tool 03"})))
    draw(other)
    assert (other.model.selected_key, other.model.delay, other.model.skip_blacklisted) == ("p03", 2.5, False)
    assert other.export_settings()["query"] == "Tool 03"
    other.restore_settings({"selected": "nope", "delay": 99, "skip_blacklisted": "x"})
    other.restore_settings({"delay": "abc"})
    assert (other.model.selected_key, other.model.delay, other.model.skip_blacklisted) == ("p03", 2.5, False)


def test_make_app_builds_the_real_catalog_and_draws():
    app = make_app()
    painter = draw(app)
    assert len(app.model.catalog) > 100 and "Test all plugins" in painter.strings
    app.close()
