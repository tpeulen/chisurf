"""The shipped demo has a known answer: two lifetime plateaus."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.microscopy.img_pixel_mle.demo import DEMO, irf_path, make_demo

tttrlib = pytest.importorskip("tttrlib")


def test_demo_is_cached_and_regenerated_on_damage(tmp_path):
    image = make_demo(tmp_path)
    stamp = image.stat().st_mtime_ns
    assert make_demo(tmp_path) == image and image.stat().st_mtime_ns == stamp
    assert irf_path(tmp_path).is_file()
    image.with_suffix(".json").write_text("{}")
    make_demo(tmp_path)
    assert "sha256" in image.with_suffix(".json").read_text()


def test_load_example_then_run_recovers_both_lifetimes(tmp_path):
    from chisurf.plugins.microscopy.img_pixel_mle.gui.model import PixelMleModel

    model = PixelMleModel()
    model.example_folder = tmp_path
    model.load_example()
    assert model.can_run() == (True, "")
    model.run()
    tau = np.asarray(model.results[0].tau)
    half = tau.shape[-1] // 2
    assert np.nanmedian(tau[..., :half]) == pytest.approx(DEMO["tau_left_ns"], rel=0.05)
    assert np.nanmedian(tau[..., half:]) == pytest.approx(DEMO["tau_right_ns"], rel=0.05)


def test_load_example_releases_the_tour_step(tmp_path):
    from chisurf.plugins.microscopy.img_pixel_mle.gui.app import PixelMleApp

    app = PixelMleApp()
    try:
        app.model.example_folder = tmp_path
        app.tour.start(1)
        assert app.tour.awaiting
        app.model.load_example()
        assert not app.tour.awaiting
        assert app.model.files and app.model.irf_files
    finally:
        app.close()
