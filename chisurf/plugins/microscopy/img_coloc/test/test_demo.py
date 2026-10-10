"""The shipped demo has a known answer: M1 about 1, M2 about one half."""

from __future__ import annotations

import pytest

from chisurf.plugins.microscopy.img_coloc.demo import expected_m1, expected_m2, make_demo

pytest.importorskip("tttrlib")


def test_demo_is_cached_and_regenerated_on_damage(tmp_path):
    path = make_demo(tmp_path)
    stamp = path.stat().st_mtime_ns
    assert make_demo(tmp_path) == path and path.stat().st_mtime_ns == stamp
    path.with_suffix(".json").write_text("{}")
    make_demo(tmp_path)
    assert "sha256" in path.with_suffix(".json").read_text()


def test_load_example_recovers_the_asymmetric_manders_coefficients(tmp_path):
    from chisurf.plugins.microscopy.img_coloc.gui.model import ColocModel

    model = ColocModel()
    model.example_folder = tmp_path
    model.load_example()
    assert model.filename.endswith("coloc_demo.tif")
    metrics = model._metrics
    assert metrics["manders_m1"] == pytest.approx(expected_m1(), abs=0.05)
    assert metrics["manders_m2"] == pytest.approx(expected_m2(), abs=0.05)
    assert metrics["manders_m1"] > metrics["manders_m2"] + 0.3


def test_load_example_releases_the_tour_step(tmp_path):
    from chisurf.plugins.microscopy.img_coloc.gui.app import ColocApp

    app = ColocApp()
    try:
        app.model.example_folder = tmp_path
        app.tour.start(1)
        assert app.tour.awaiting
        app.model.load_example()
        assert not app.tour.awaiting
        app.tour.start(2)
        assert app.tour.awaiting  # the Run step waits for the press
    finally:
        app.close()
