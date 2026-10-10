"""The shipped demo has a known answer: the brightness set in the simulation."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.pch.demo import DEMO, expected_brightness, make_demo


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    """Load the demo into a model and run compute and fit once."""
    from chisurf.plugins.pch.gui.model import PchModel

    model = PchModel()
    model.example_folder = tmp_path_factory.mktemp("pch-demo")
    model.load_example_now()
    assert model.filename, model.error_text
    model.compute_now()
    model.fit_now()
    assert model.fit_result is not None, model.error_text
    return model


def test_demo_is_cached_and_regenerated_on_damage(tmp_path):
    path = make_demo(tmp_path)
    stamp = path.stat().st_mtime_ns
    assert make_demo(tmp_path) == path and path.stat().st_mtime_ns == stamp
    path.with_suffix(".json").write_text("{}")
    make_demo(tmp_path)
    assert '"epsilon"' in path.with_suffix(".json").read_text()


def test_load_example_sets_the_matching_detector_and_bin_time(example):
    assert example.channels == "0"
    assert example.bin_time_us == DEMO["bin_time_us"]


def test_the_fit_recovers_the_simulated_brightness(example):
    (eps,) = example.fit_result.epsilons
    assert eps == pytest.approx(expected_brightness(), rel=0.1)


def test_the_fitted_occupancy_reproduces_the_mean_count_rate(example):
    from chisurf.core.models.pch.pch import pch_open_system

    k = np.asarray(example.result.k_vals)
    (eps,), (n,) = example.fit_result.epsilons, example.fit_result.avg_Ns
    p = pch_open_system(k, eps, n)
    measured = (k * np.asarray(example.result.p_exp)).sum()
    assert (k * p).sum() / p.sum() == pytest.approx(measured, rel=0.03)
    assert example.fit_result.reduced_chi2 < 5
