"""Native filter workflows, synthetic numerical results and Qt import isolation."""

import json
import subprocess
import sys

import numpy as np
import pytest

from chisurf.plugins.fcs.fcs_filter_calculator.gui.model import FilterModel


def test_native_example_unmix_and_filter_range():
    model = FilterModel()
    model.unmix()
    assert model._unmix_result.fractions == pytest.approx([0.7, 0.3], abs=0.02)
    assert model._result.nuisance_count == 2
    model._fit_bounds = (20, 200)
    model.compute()
    assert np.all(model._result.filters[:, :20] == 0)
    assert np.all(model._result.filters[:, 200:] == 0)
    assert model._result.filters.shape[1] == 256


def test_native_project_preserves_detectors_options_and_disabled_components(tmp_path):
    source = FilterModel()
    source.components[0].enabled = False
    source.options_model.scatter_irf = False
    source.detectors.set_shift("green", 0.1)
    source.compute()
    path = tmp_path / "project.json"
    source.save_project(path)
    restored = FilterModel(example=False)
    restored.load_project(path)
    assert len(restored.components) == 2
    assert not restored.components[0].enabled
    assert restored.detectors.shift("green") == 0.1
    assert not restored.options_model.scatter_irf
    np.testing.assert_array_equal(restored._total_vector, source._total_vector)
    np.testing.assert_allclose(restored._result.filters, source._result.filters)


def test_native_export_has_real_species_filters(tmp_path):
    model = FilterModel()
    model.compute()
    path = tmp_path / "filters.json"
    model.export_results(path)
    data = json.loads(path.read_text())
    assert len(data["filters"]) == 4
    assert data["nuisance_count"] == 2
    assert len(data["reconstruction"]) == 256


def test_native_independent_and_stacked_detector_filters():
    model = FilterModel()
    model.detectors.names = model.detectors.selected = ["green", "red"]
    model.populate_example()
    model.compute()
    assert len(model._result_multi_detector) == 2
    assert not np.array_equal(
        model._result_multi_detector[0]["result"].filters,
        model._result_multi_detector[1]["result"].filters,
    )
    model.stacked = True
    model.compute()
    assert all(entry["result"].metadata["filter_mode"] == "stacked" for entry in model.results())
    assert all(entry["result"].filters.shape[1] == 256 for entry in model.results())


def test_native_factories_and_render_forbid_qt():
    script = """
import sys
class Block:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:
            raise AssertionError('Qt import: '+fullname)
sys.meta_path.insert(0,Block())
from emtk.pil_painter import PilPainter
from chisurf.plugins.fcs.fcs_filter_calculator.gui.app import create_app
from chisurf.plugins.fcs.fcs_merger.gui.app import create_app as merger
for app in (create_app(),merger()):
    if app.job.future:
        app.job.future.result(timeout=30)
        app.job.poll()
    app.draw(PilPainter(1200,800),0,0,1200,800)
    app.close()
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_native_mfd_keeps_full_axis_and_zeros_outside_fit_range():
    model = FilterModel()
    original = [np.asarray(c.source["patterns_by_detector"]["green"]) for c in model.components]
    model._total_vectors_by_detector = {
        "routing_0": 80000 * (0.7 * original[0] + 0.3 * original[1]),
        "routing_1": 40000 * (0.7 * original[0] + 0.3 * original[1]),
    }
    for component, pattern in zip(model.components, original):
        component.source["patterns_by_detector"] = {
            "routing_0": pattern.tolist(),
            "routing_1": pattern.tolist(),
        }
    model.options_model.scatter_irf = False
    model.options_model.fit_background = False
    model.polarized = True
    model._fit_bounds = (20, 200)
    model.compute()
    result = model._result_anisotropy
    for role in ("par", "perp"):
        weights = getattr(result, "filters_" + role)
        assert weights.shape == (2, 256)
        assert np.all(weights[:, :20] == 0)
        assert np.all(weights[:, 200:] == 0)
        assert len(getattr(result, "total_decay_" + role)) == 256


def test_native_autofit_uses_real_lifetime_model():
    model = FilterModel()
    model._auto_fit_settings["n_components"] = 1
    model._auto_fit_components()
    assert len(model.components) == 1
    assert np.isfinite(model._auto_fit_result["chi2_reduced"])
    assert 0.2 <= model._auto_fit_result["lifetimes"][0] <= 8
    assert model._result is not None


def test_native_bst_routing_includes_last_photon(tmp_path, monkeypatch):
    from types import SimpleNamespace

    tttr = tmp_path / "one.ptu"
    tttr.write_bytes(b"x")
    bst = tmp_path / "one.ptu.bst"
    bst.write_text("0\t2\n")
    data = SimpleNamespace(
        micro_times=np.array([0, 1, 2, 3]),
        routing_channels=np.zeros(4, dtype=int),
        get_header=lambda: SimpleNamespace(
            number_of_micro_time_channels=8, micro_time_resolution=1e-10
        ),
    )
    monkeypatch.setattr("tttrlib.TTTR", lambda *args: data)
    model = FilterModel(example=False)
    histogram = model._load_routing_channels(bst)[0]
    np.testing.assert_array_equal(histogram[:4], [1, 1, 1, 0])


def test_native_slow_compute_keeps_frame_responsive_and_discards_stop(monkeypatch):
    from threading import Event

    from emtk.pil_painter import PilPainter

    from chisurf.plugins.fcs.fcs_filter_calculator.gui.app import create_app

    entered, release = Event(), Event()
    seen = {}

    def compute(model):
        seen["afterpulse"] = model.options_model.fit_background
        entered.set()
        assert release.wait(5)
        model.message = "Worker result"

    monkeypatch.setattr(FilterModel, "compute", compute)
    app = create_app()
    assert entered.wait(5)
    app.model.options_model.fit_background = False
    assert app.submit(lambda model: model.compute()) is False
    app.draw(PilPainter(1000, 700), 0, 0, 1000, 700)
    assert seen["afterpulse"] is True
    app.job.stop()
    release.set()
    app.job.future.result(timeout=5)
    app.job.poll()
    assert app.model.message != "Worker result"
    app.close()


def test_native_every_dock_and_component_editor_draws_with_tooltips(monkeypatch):
    from emtk import im
    from emtk.pil_painter import PilPainter

    from chisurf.plugins.fcs.fcs_filter_calculator.gui.app import create_app

    app = create_app()
    app.job.future.result(timeout=30)
    app.job.poll()
    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", lambda text: tips.append(text))
    for draw in (
        app.draw_sources,
        app.draw_setup,
        app.draw_autofit,
        app.draw_instrument,
        app.draw_info,
    ):
        with im.frame(PilPainter(1000, 700), (0, 0, 1000, 700)):
            im.begin("test dock")
            draw((0, 0, 1000, 700))
            im.end()
    for kind in (
        "lifetime",
        "lifetime_spectrum",
        "gaussian_lifetime",
        "gaussian_distance",
        "fret_species",
    ):
        app.new_component(kind)
        with im.frame(PilPainter(1000, 900), (0, 0, 1000, 900)):
            im.begin("test component")
            app.draw_component_form()
            im.end()
    assert len(tips) > 80
    assert all(tips)
    app.close()


def test_native_selects_authoritative_saved_detector_setup(monkeypatch):
    from chisurf.core.setup_channel_definition import ChannelDefinition
    from chisurf.plugins.fcs.fcs_filter_calculator.gui.app import create_app

    def refresh(store):
        store.setups = {
            "Instrument A": {"detectors": {"green": {"chs": [2, 3]}}, "tttr_reading": {}}
        }
        return ["Instrument A"]

    monkeypatch.setattr(ChannelDefinition, "refresh_setups", refresh)
    monkeypatch.setattr(ChannelDefinition, "publish_lut", lambda self: None)
    app = create_app()
    app.job.future.result(timeout=30)
    app.job.poll()
    app.refresh_saved_setups()
    app.job.future.result(timeout=5)
    app.job.poll()
    app.select_saved_setup("Instrument A")
    assert app.model._detector_settings["detectors"]["green"]["chs"] == [2, 3]
    assert app.setup_store.current_name == "Instrument A"
    app.job.future.result(timeout=5)
    app.job.poll()
    app.close()
