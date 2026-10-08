"""Photon inspection and LUT tools keep declared geometry and scientific state."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.tttr.photon_table.gui.app import make_app
from chisurf.plugins.tttr.tttr_lut_tools.gui.app import create_app


@pytest.fixture
def tools(tmp_path, monkeypatch):
    """Use independent settings and a private real183657-photonSPC input."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    sample = tmp_path / "uniform.spc"
    source = Path(__file__).parents[1] / "data/tttr/BH/132/BH_SPC132.spc"
    shutil.copyfile(source, sample)
    return {"photon_table": make_app, "tttr_lut_tools": create_app}, sample


@pytest.mark.parametrize("plugin_id", ["photon_table", "tttr_lut_tools"])
def test_declared_default_and_saved_geometry_keep_custom_docks(tools, plugin_id):
    """A real persistence cycle keeps the user resize and custom dock layout."""
    factories, _ = tools
    app = factories[plugin_id]()
    assert app.window_size == (1100, 720)
    attach_native_state(plugin_id, app)
    Driver(app, (1100, 720)).draw(3)
    key = next(iter(app.docks.windows))
    app.docks.undock(key, (40, 50, 440, 400))
    app.window_resized(1390, 910)
    saved = app.docks.state()
    app.close()
    restored = attach_native_state(plugin_id, factories[plugin_id]())
    try:
        assert restored.window_size == (1390, 910)
        assert restored.docks.state()["layout"] == saved["layout"]
        assert restored.docks.state()["windows"] == saved["windows"]
        Driver(restored, restored.window_size).draw(2)
    finally:
        restored.close()


def test_loaded_photon_rows_and_timing_survive_resize_and_persistence(tools):
    """Geometry cannot change measured photons or remembered page preferences."""
    from chisurf.core.fio.staging import open_tttr

    factories, sample = tools
    reference = open_tttr(sample)
    assert len(reference) == 183657
    app = attach_native_state("photon_table", factories["photon_table"]())
    try:
        assert app.model.load_path(str(sample))
        app.model.set_rows(37)
        app.model.go_next()
        rows = list(app.model.rows)
        assert rows[0]["photon"] == 37
        assert app.model.count == len(reference)
        before = app.export_settings()
        Driver(app, (1100, 720)).draw(3, size=(1390, 910))
        assert app.model.rows == rows
        assert app.export_settings() == before
        app.window_resized(1390, 910)
    finally:
        app.close()
    reopened = attach_native_state("photon_table", factories["photon_table"]())
    try:
        assert reopened.window_size == (1390, 910)
        assert reopened.export_settings() == before
        assert reopened.model.load_path(str(sample))
        assert reopened.model.count == 183657
    finally:
        reopened.close()


def test_actual_lut_workspace_arrays_and_configuration_survive_resize(tools):
    """Actual LUT histograms, corrected preview and assignments remain exact."""
    factories, sample = tools
    app = factories["tttr_lut_tools"]()
    try:
        app.model.load_files_job([str(sample)])
        app.model.preview_photons = 1000
        raw = tuple(np.asarray(x).copy() for x in app.model.raw_plot()[:2])
        corrected = tuple(np.asarray(x).copy() for x in app.model.corrected_plot())
        app.model.add_all_job()
        bundle = app.model.ws.bundle()
        settings = app.export_settings()
        driver = Driver(app, (1100, 720))
        driver.draw(3)
        driver.draw(3, size=(1390, 910))
        for before, after in zip(raw, app.model.raw_plot()[:2]):
            np.testing.assert_array_equal(before, after)
        for before, after in zip(corrected, app.model.corrected_plot()):
            np.testing.assert_array_equal(before, after)
        assert app.model.ws.bundle() == bundle
        assert app.export_settings() == settings
    finally:
        app.close()


@pytest.mark.parametrize("plugin_id", ["photon_table", "tttr_lut_tools"])
def test_primary_declaration_is_read_by_factory(tools, monkeypatch, plugin_id):
    """The factory consumes the sharedreader rather than another hardcoded size."""
    import chisurf.plugins.tttr.photon_table.gui.app as photon
    import chisurf.plugins.tttr.tttr_lut_tools.gui.app as lut

    factories, _ = tools
    module = photon if plugin_id == "photon_table" else lut
    original = module.window_size
    seen = []

    def read(spec, default):
        """Observe the actual declaredprimary passed to the sharedreader."""
        seen.append((spec["window"], default))
        return original({**spec, "window": {"width": 1234, "height": 789}}, default)

    monkeypatch.setattr(module, "window_size", read)
    app = factories[plugin_id]()
    try:
        assert app.window_size == (1234, 789)
        assert seen == [({"width": 1100, "height": 720}, (1100, 720))]
    finally:
        app.close()


@pytest.mark.parametrize("size", [(736, 552), (1100, 720)])
def test_lut_normalize_caption_is_visible_and_real_toggle_round_trip_preserves_arrays(tools, size):
    """The actual initialhost caption fits; toggling twice returns exact LUT/preview data."""
    factories, sample = tools
    app = factories["tttr_lut_tools"]()
    try:
        app.model.load_files_job([str(sample)])
        app.model.preview_photons = 1000
        app.model.param_changed()
        table = {key: np.asarray(value).copy() for key, value in app.model.ws.compute.current_table.items()}
        corrected = tuple(np.asarray(value).copy() for value in app.model.corrected_plot())
        driver = Driver(app, size)
        driver.draw(3)
        index = next(i for i, row in enumerate(driver.painter.texts) if row[5] == "Normalize")
        metrics = driver.painter.text_metadata[index]
        assert metrics["visible_bounds"] == metrics["measured_bounds"], "The caption must not be clipped"
        assert "normalize" in driver.ids()
        before = app.model.normalize
        driver.click("normalize")
        assert app.model.normalize is not before
        np.testing.assert_array_equal(corrected[0], app.model.corrected_plot()[0])
        assert not np.array_equal(table["NTAC_fract"], app.model.ws.compute.current_table["NTAC_fract"])
        assert not np.array_equal(corrected[1], app.model.corrected_plot()[1])
        driver.click("normalize")
        assert app.model.normalize is before
        for key, value in table.items():
            np.testing.assert_array_equal(value, app.model.ws.compute.current_table[key])
        for value, actual in zip(corrected, app.model.corrected_plot()):
            np.testing.assert_array_equal(value, actual)
    finally:
        app.close()


@pytest.mark.parametrize("filename", ["lut_tools_emtk.view.json", "lut_compute.view.json"])
def test_normalize_help_describes_threshold_masking_and_correction_effect(filename):
    """Declaredhelp must explain the actual normalizedthreshold masking behavior."""
    spec = Path(__file__).parents[2] / "chisurf/plugins/tttr/tttr_lut_tools/gui" / filename

    def controls(node):
        """Walk nested declarations tofind the unchangednormalizationcontrol."""
        if isinstance(node, dict):
            yield node
            for value in node.values():
                yield from controls(value)
        elif isinstance(node, list):
            for value in node:
                yield from controls(value)

    normalize = next(node for node in controls(json.loads(spec.read_text())) if node.get("attr") == "normalize")
    help_text = normalize["description"].lower()
    for concept in ("region mean", "before comparing", "threshold", "masked", "lut", "corrected preview"):
        assert concept in help_text
    assert "display only" not in help_text
