"""The real Burst Browser consumes primary geometry and retains its native workflow."""

import copy
import json
from pathlib import Path

import numpy as np
from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep metadata and native preferences in private storage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))


def test_factory_consumes_primary_window_without_mutating_it(tmp_path, monkeypatch):
    """A different authored window reaches the actual application before a host exists."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_browser.gui import app as module

    path = Path(module.__file__).with_name("burst_browser.view.json")
    original = path.read_bytes()
    spec = json.loads(original)
    assert spec["window"] == {"width": 1200, "height": 800}
    spec["window"] = {"width": 960, "height": 640}
    read_text = Path.read_text

    def read(source, *args, **kwargs):
        """Supply another primary declaration without changing the shipped file."""
        return json.dumps(spec) if source == path else read_text(source, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    app = module.create_app()
    try:
        assert app.window_size == (960, 640)
        assert path.read_bytes() == original
    finally:
        app.close()


def test_saved_geometry_and_docks_win_on_reopen(tmp_path, monkeypatch):
    """Saved host geometry survives construction and a differently sized render."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_browser.gui.app import create_app

    first = attach_native_state("burst_browser", create_app())
    first.window_resized(1340, 900)
    state = copy.deepcopy(first.browser_gui.docks.state())
    first.close()
    reopened = attach_native_state("burst_browser", create_app())
    try:
        assert reopened.window_size == (1340, 900)
        assert reopened.browser_gui.docks.state() == state
        reopened.draw(RecordingPainter(), 0, 0, 900, 650)
        assert reopened.window_size == (1340, 900)
        assert reopened.table is None  # Existing workflow rebuilds data after reopening.
    finally:
        reopened.close()


def test_default_preserves_real_burst_gating_histogram_and_exports(tmp_path, monkeypatch):
    """All original docks/actions remain reachable and actual loaded science is preserved."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.burst.burst_browser.gui.app import create_app
    from chisurf.plugins.burst.burst_browser.test.demo_folder import build

    folder = build(tmp_path / "measurement")
    app = create_app()
    try:
        assert app.window_size == (1200, 800)
        app.load_folder(folder)
        app.controller._future.result(timeout=20)
        app.controller.poll()
        model = app.model
        driver = Driver(app, size=(1200, 800))
        driver.draw(3)
        for key in ("controls", "gates", "table", "histogram"):
            assert app.browser_gui.docks.window(key) is not None
            app.browser_gui.docks.focus(key)
            driver.draw(2)
        assert {
            "open_folder",
            "open_file",
            "export_gated",
            "export_selected",
            "detector",
            "hist_column",
            "table",
            "browser_histogram",
        } <= app.item_rects.keys()
        for key, value in {"e_min": 0.5, "e_max": 0.9, "s_min": 0.3, "s_max": 0.7}.items():
            setattr(model, key, value)
        model.hist_column = "E"
        model.refresh()
        mask = model.masked_row_indices().copy()
        histogram = model.histogram()
        assert len(mask) == 120
        assert sum(histogram["counts"]) == 120
        export = tmp_path / "gated.csv"
        app.controller.export(export)
        content = export.read_bytes()
        app.draw(RecordingPainter(), 0, 0, 900, 650)
        np.testing.assert_array_equal(model.masked_row_indices(), mask)
        np.testing.assert_array_equal(model.histogram()["counts"], histogram["counts"])
        app.controller.export(export)
        assert export.read_bytes() == content
    finally:
        app.close()


def _loaded_browser(tmp_path):
    """Load the existing measurement fixture through the actual controller."""
    from chisurf.plugins.burst.burst_browser.gui.app import create_app
    from chisurf.plugins.burst.burst_browser.test.demo_folder import build

    app = create_app()
    app.load_folder(build(tmp_path / "measurement"))
    app.controller._future.result(timeout=20)
    app.controller.poll()
    return app


def test_every_measurement_column_is_reachable_without_moving_toolbar(tmp_path, monkeypatch):
    """Real horizontal input reveals the final column while vertical scrolling keeps headers fixed."""
    isolate(tmp_path, monkeypatch)
    app = _loaded_browser(tmp_path)
    try:
        from chisurf.core.datastore import column_names

        driver = Driver(app, size=(1200, 800))
        driver.draw(3)
        x, y, width, height = app.item_rects["table"]
        last = column_names(app.model.table)[-1]
        toolbar = next(t[:4] for t in driver.painter.texts if t[5].startswith("Page "))
        visible = False
        for _ in range(len(column_names(app.model.table)) + 1):
            driver.wheel(0, at=(x + width / 2, y + height / 2), dx=-1)
            visible = any(
                t[5] == last and t[2] > 0 and x <= t[0] < x + width and y <= t[1] < y + height
                for t in driver.painter.visible_texts
            )
            if visible:
                break
        assert visible, f"Final measurement column {last!r} is unreachable"
        driver.wheel(-5, at=(x + width / 2, y + height / 2))
        assert next(t[:4] for t in driver.painter.texts if t[5].startswith("Page ")) == toolbar
    finally:
        app.close()


def test_padded_gate_limits_are_visible_and_rendering_does_not_clamp_science(tmp_path, monkeypatch):
    """Corrected efficiencies and stoichiometries outside [0,1] remain visible and unchanged."""
    isolate(tmp_path, monkeypatch)
    app = _loaded_browser(tmp_path)
    try:
        app.model.e_min = -0.125
        app.model.e_max = 1.125
        app.model.s_min = -0.25
        app.model.s_max = 1.25
        Driver(app, size=(1200, 800)).draw(3)
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 1200, 800)
        assert "-0.125" in painter.strings
        assert "1.125" in painter.strings
        assert "-0.250" in painter.strings
        assert "1.250" in painter.strings
        assert (app.model.e_min, app.model.e_max, app.model.s_min, app.model.s_max) == (
            -0.125,
            1.125,
            -0.25,
            1.25,
        )
    finally:
        app.close()


def test_table_clicks_toggle_original_burst_identity_and_selected_histogram(tmp_path, monkeypatch):
    """The declarative table preserves single-click toggles for histogram selection."""
    isolate(tmp_path, monkeypatch)
    app = _loaded_browser(tmp_path)
    try:
        driver = Driver(app, size=(1200, 800))
        driver.draw(3)
        x, y, width, height = app.item_rects["table"]
        row = int(app.model.masked_row_indices()[0])
        app.model.use_selection = True
        app.model.selected_indices.clear()
        driver.click((x + 12, y + 34))
        assert app.model.selected_indices == [row]
        assert sum(app.model.histogram()["counts"]) == 1
        driver.click((x + 12, y + 34))
        assert app.model.selected_indices == []
    finally:
        app.close()


def test_numeric_table_sort_keeps_source_values_and_four_digit_display(tmp_path, monkeypatch):
    """Sortable measurement headers order numbers numerically without changing their display."""
    isolate(tmp_path, monkeypatch)
    app = _loaded_browser(tmp_path)
    try:
        Driver(app, size=(1200, 800)).draw(3)
        table = app.browser_gui._burst_table.control
        key = "Number of Photons"
        table.sort_by(key, descending=False)
        Driver(app, size=(1200, 800)).draw(2)
        values = [table.value(index, key) for index in table.order()]
        assert values == sorted(values)
        assert not any(isinstance(value, str) for value in values)
        columns = {column.key: column for column in table.columns}
        assert columns["E"].text(0.1234567) == "0.1235"
        assert columns["E"].text(None) == ""
        assert columns[key].text(12345) == "12345"
        table.sort_by(key, descending=True)
        assert [table.value(index, key) for index in table.order()] == sorted(values, reverse=True)
        index = table.order()[0]
        identity = table.records[index]["_burst_index"]
        app.browser_gui.toggle_burst_row(table.records[index])
        assert identity in app.model.selected_indices
    finally:
        app.close()
