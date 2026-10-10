"""The demo stream and the dataset/fit it opens in ChiSurf, headlessly."""

from __future__ import annotations

import json
import time

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.plugins.core.acq import demo  # noqa: E402


@pytest.fixture(scope="module")
def demo_file(tmp_path_factory):
    """The demo SPC file, made once in a scratch folder."""
    return demo.make_demo(tmp_path_factory.mktemp("acq-demo"))


def test_demo_is_readable_by_tttrlib_and_has_enough_photons(demo_file):
    """The SPC file is a real photon stream in two routing channels."""
    tttr = tttrlib.TTTR(str(demo_file), "SPC-130")
    assert len(tttr) > 10_000
    assert len(np.unique(np.asarray(tttr.routing_channels))) == 2


def test_demo_is_cached_and_keyed_on_its_settings(tmp_path):
    """A second call reuses the file; a changed setting or overwrite regenerates it."""
    path = demo.make_demo(tmp_path)
    stamp = path.stat().st_mtime_ns
    assert demo.make_demo(tmp_path) == path
    assert path.stat().st_mtime_ns == stamp
    side = json.loads(path.with_suffix(".json").read_text())
    assert side["settings"] == json.loads(json.dumps(demo.DEMO))
    side["fingerprint"] = "stale"
    path.with_suffix(".json").write_text(json.dumps(side))
    demo.make_demo(tmp_path)
    assert path.stat().st_mtime_ns != stamp
    stamp = path.stat().st_mtime_ns
    demo.make_demo(tmp_path, overwrite=True)
    assert path.stat().st_mtime_ns != stamp


def test_demo_folder_is_under_the_settings_directory():
    """The cache lives with the plugin's other demos."""
    assert demo.demo_folder().parts[-2:] == ("demos", "acq")


def test_open_demo_registers_dataset_and_a_fit_naming_the_four_pages(monkeypatch, tmp_path):
    """Headless ``open_demo`` appends a dataset and an Acquisition fit; pages come from its spec."""
    from chisurf.core.api import ChiSurfAPI
    from chisurf.core.models.acquisition import AcquisitionModel, acquisition_dataset
    from chisurf.gui.widgets.models.model_editor import model_plot_specs
    from chisurf.plugins.core.acq import dataset as dataset_module

    monkeypatch.setattr(demo, "demo_folder", lambda: tmp_path)
    api = ChiSurfAPI(mode="local")
    datasets, fits = len(api.list_datasets()), len(api.list_fits())
    ds = dataset_module.open_demo()
    try:
        assert len(api.list_datasets()) == datasets + 1
        assert len(api.list_fits()) == fits + 1
        fit = ds.fit
        assert fit.name == "Acquisition"
        assert isinstance(fit.model, AcquisitionModel)
        assert acquisition_dataset(fit) is ds
        titles = [cls.name for cls, _ in model_plot_specs(fit.model)]
        assert titles[:4] == ["Decay", "Correlation", "MCS", "Macro time"]
        deadline = time.monotonic() + 30
        while ds.streaming and time.monotonic() < deadline:
            ds.refresh()
            time.sleep(0.05)
        assert not ds.streaming
        ds.refresh()
        assert ds.snapshot["total_photons"] > 10_000
        assert float(np.sum(ds.y)) > 0
        assert ds.update_fit()
        assert np.array_equal(fit.model.y, ds.y)
        for key in ("decay", "correlation", "mcs", "macro"):
            assert ds.live.series[key], key
    finally:
        ds.close()
        api.clear_fits()
        api.clear_datasets()


def test_load_example_button_opens_the_dataset_and_fit(monkeypatch, tmp_path):
    """A pointer click on Load example registers the demo dataset and its Acquisition fit."""
    from chisurf.core.api import ChiSurfAPI
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

    monkeypatch.setattr(demo, "demo_folder", lambda: tmp_path)
    api = ChiSurfAPI(mode="local")
    app = AcquisitionApp()
    try:
        ui = Driver(app, (1200, 800))
        ui.draw(3)
        assert app.model.dataset is None
        ui.click("load_example")
        assert app.model.dataset is not None
        assert [f["name"] for f in api.list_fits()][-1] == "Acquisition"
        assert app.model.enabled("load_example")
        deadline = time.monotonic() + 30
        while app.model.dataset.streaming and time.monotonic() < deadline:
            ui.draw(1)
            time.sleep(0.05)
        ui.draw(2)
        assert app.model.dataset.snapshot["total_photons"] > 10_000
    finally:
        app.close()
        api.clear_fits()
        api.clear_datasets()
