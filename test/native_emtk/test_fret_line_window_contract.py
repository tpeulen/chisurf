"""FRET calculator defaults, restored layouts, tour reveal and real text commits."""

from __future__ import annotations

import pytest
from emtk import keys
from emtk.docking import Region
from emtk.events import CONTROL_MODIFIER
from emtk.testing import Driver

from chisurf.plugins.fret_line.gui.app import FRETLineApp


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Build an isolated calculator and close its registered models afterward."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))
    instance = FRETLineApp()
    yield instance
    instance.close()


def test_compact_default_reset_and_later_resize_keep_full_width_editor(app):
    """The first narrow viewport declares a usable layout and its Reset default."""
    assert app.window_size == (640, 480)
    driver = Driver(app, (640, 480))
    driver.draw(3)
    assert app.docks.region_of("editor") == "controls"
    assert app.docks.region_of("efficiency") == "efficiency"
    assert app.docks.region_of("lifetime") == "lifetime"
    app.show_advanced("editor")
    driver.draw(3)
    driver.click("Live model editor")
    assert app.docks.region_boxes["controls"][2] > 600
    assert "RDA0" in driver.painter.strings
    app.docks.reset()
    assert app.docks.region_of("editor") == "controls"
    driver.draw(3, size=(1200, 800))
    assert app.docks.region_of("editor") == "controls"


def test_wide_first_viewport_retains_side_by_side_editor(app):
    """The initial wide layout preserves the established control arrangement."""
    Driver(app, (1200, 800)).draw(3)
    assert app.docks.region_of("editor") == "editor"


def test_saved_layout_wins_over_narrow_first_viewport(app):
    """A meaningful restored layout is never replaced by automatic defaults."""
    saved = app.docks.state()
    app.docks.restore(saved)
    Driver(app, (640, 480)).draw(3)
    assert app.docks.region_of("editor") == "editor"
    assert app.docks.state()["layout"] == saved["layout"]


def test_custom_saved_workspace_keeps_every_placement(app):
    """A restored custom workspace preserves its tree and complete tab inventory."""
    assert app.docks.configure_default_layout(
        Region("workspace"), {key: "workspace" for key in app.docks.windows}
    )
    saved = app.docks.state()
    reopened = FRETLineApp()
    try:
        reopened.docks.restore(saved)
        Driver(reopened, (640, 480)).draw(3)
        actual = reopened.docks.state()
        assert actual["layout"] == saved["layout"]
        assert actual["regions"] == saved["regions"]
        assert all(reopened.docks.region_of(key) == "workspace" for key in reopened.docks.windows)
    finally:
        reopened.close()


def test_empty_restore_keeps_default_configuration_available(app):
    """Empty preferences do not block the first viewport's layout declaration."""
    app.docks.restore({})
    Driver(app, (640, 480)).draw(3)
    assert app.docks.region_of("editor") == "controls"


def test_tour_callback_reveals_targets_and_hidden_rectangles_disappear(app):
    """All shipped targets select their tab before their active rect is read."""
    driver = Driver(app, (640, 480))
    driver.draw(3)
    for index, step in enumerate(app.tour.steps):
        if step["target"].get("name") == "show_components":
            app.form.folds["Advanced"] = True
        app.tour.on_step_change(index, step)
        driver.draw(3)
        target = step["target"]
        name = target.get("name") or target.get("attr")
        assert name in driver.ids(), name
    app.tour.on_step_change(0, {"target": {"name": "parameter_rows"}})
    driver.draw(3)
    assert app.docks.active_tab("controls") == "editor"
    assert "editor" in driver.ids()
    app.tour.on_step_change(0, {"target": {"name": "component_rows"}})
    driver.draw(3)
    assert app.docks.active_tab("controls") == "components"
    assert "editor" not in driver.ids()


def test_enter_commits_an_emptied_sweep_filter(app):
    """A real clear-and-Enter edit reaches the AutoForm model callback."""
    driver = Driver(app, (640, 480))
    driver.draw(3)
    app.show_advanced("sweep")
    driver.draw(3)
    driver.click("Sweep")
    driver.click("sweep_filter")
    driver.type("fraction")
    driver.press(keys.KEY_ENTER)
    assert app.model.sweep_filter == "fraction"
    driver.click("sweep_filter")
    driver.press(ord("a"), CONTROL_MODIFIER)
    driver.press(keys.KEY_BACKSPACE)
    driver.press(keys.KEY_ENTER)
    assert app.model.sweep_filter == ""


def test_compact_parameter_editor_select_all_commits_value(app):
    """Double-clicking a compact table cell supports Ctrl+A and typed values."""
    driver = Driver(app, (640, 480))
    driver.draw(3)
    app.show_advanced("editor")
    driver.draw(3)
    driver.click("Live model editor")
    _, row_y, _, row_h = driver.rect("RDA0")
    value_x = driver.rect("Value")[0] + 6
    point = (value_x, row_y + row_h / 2)
    driver.hover(point)
    app.pointer_press(*point, 1, 0, 2)
    driver.draw(2)
    app.pointer_release(*point, 1, 0)
    driver.draw(1)
    driver.press(ord("a"), CONTROL_MODIFIER)
    driver.type("70")
    driver.press(keys.KEY_ENTER)
    parameter = next(
        item
        for item in app.model.selected["model"].parameters_all
        if item.canonical_id == "distance.mean.0"
    )
    assert parameter.value == 70.0
