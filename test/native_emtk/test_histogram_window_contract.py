"""Histogram host geometry comes from its primary form without overriding saved state."""

import copy
import json

from emtk.testing import Driver, RecordingPainter

from chisurf.emtk.state import attach_native_state


def isolate(tmp_path, monkeypatch):
    """Keep native window, detector and metadata preferences in a scratch tree."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "metadata.sqlite"))


def test_real_factory_uses_primary_geometry_before_form_partition(tmp_path, monkeypatch):
    """Partitioning Run and options sections retains the primary default on the app."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.microtime_histogram.gui.app import HERE, create_app

    original = (HERE / "histogram.view.json").read_bytes()
    app = create_app()
    try:
        assert json.loads(original)["window"] == {"width": 1100, "height": 720}
        assert app.window_size == (1100, 720)
        Driver(app, size=(1100, 720)).draw()
        assert (HERE / "histogram.view.json").read_bytes() == original
    finally:
        app.close()


def test_saved_geometry_and_configuration_win_on_reopen(tmp_path, monkeypatch):
    """Saved dimensions survive construction and rendering preserves model settings."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app

    first = attach_native_state("microtime_histogram", create_app())
    try:
        first.model.binning = 3
        first.window_resized(1340, 900)
    finally:
        first.close()
    reopened = attach_native_state("microtime_histogram", create_app())
    try:
        assert reopened.window_size == (1340, 900)
        assert reopened.model.binning == 3
        state = copy.deepcopy(reopened.export_settings())
        reopened.draw(RecordingPainter(), 0, 0, 900, 650)
        assert reopened.window_size == (1340, 900)
        assert reopened.export_settings() == state
    finally:
        reopened.close()


def test_default_geometry_retains_both_pages_and_plot_controls(tmp_path, monkeypatch):
    """All three docks and each existing decay visibility control remain reachable."""
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app

    app = create_app()
    try:
        drv = Driver(app, size=(1100, 720))
        drv.draw()
        assert {
            "load_example",
            "compute",
            "log_y",
            "show_vv",
            "show_vh",
            "show_combined",
        } <= app.item_rects.keys() | app.form.rects.keys()
        for key in ("inputs", "setup", "plot"):
            assert app.docks.window(key) is not None
            app.docks.focus(key)
            drv.draw()
        before = app.show_vv
        drv.click("show_vv")
        assert app.show_vv is not before
    finally:
        app.close()


def test_default_setup_table_reveals_detector_row_actions(tmp_path, monkeypatch):
    """G/Delete of a detector row are reachable without altering the definition.

    At both 1100x720 and 800x600 the setup dock shows them outright: since 49e773134 a narrow
    host drops gch/l1/l2 and shortens the headers before it would scroll sideways, so the table
    fits and a click on Delete's own cell reaches it.
    """
    isolate(tmp_path, monkeypatch)
    from chisurf.plugins.tttr.microtime_histogram.demo import SETUP
    from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app

    for size in ((1100, 720), (800, 600)):
        app = create_app()
        try:
            app.editor.load_definition(copy.deepcopy(SETUP))
            before = copy.deepcopy(app.editor.model.get_settings())
            app.docks.focus("setup")
            drv = Driver(app, size=size)
            drv.draw()
            table = app.editor._detector_table.control
            assert table._hbar_box is None, size
            buttons = app.editor._detector_buttons
            cell = next(cell for cell in buttons.cells() if cell[2] == "delete")
            x, y, width, height = cell[3]
            hit = buttons.hit(x + width / 2, y + height / 2)
            assert hit is not None and hit[1] == "delete", (size, cell)
            assert app.editor.model.get_settings() == before
        finally:
            app.close()
