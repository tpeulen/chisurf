"""Native detector calibration metadata and close callbacks preserve scientific state."""
from __future__ import annotations

import pytest

from chisurf.plugins.vv_vh_g_factor.gui.model import GFactorModel


def model():
    """Return a measured result snapshot without replacing any calculation algorithm."""
    result = GFactorModel()
    result.fast_file = "reference.dat"
    result.result = {"g_factor": 1.25, "g_factor_uncorrected": 1.2,
                     "g_factor_corrected": 1.25, "g_factor_stddev_uncorrected": 0.1,
                     "g_factor_stddev_corrected": 0.12, "bg_parallel_avg": 3.0,
                     "bg_perpendicular_avg": 4.0}
    result.background = True
    result.region = [400.0, 300.0]
    result.background_region = [10.0, 20.0]
    return result


@pytest.mark.parametrize("mix", [None, float("nan")])
def test_detector_parameters_preserve_existing_mixing_and_use_real_sd(mix):
    snapshot = model()
    snapshot.fp_result = {"l1": mix, "l2": mix}
    parameters = snapshot.detector_parameters(prior_l1=0.17, prior_l2=0.23,
                                             micro_time_resolution=50.0)
    assert parameters["l1"] == 0.17 and parameters["l2"] == 0.23
    assert parameters["g_factor_stddev"] == 0.12
    assert parameters["g_factor_uncorrected"] == 1.2
    assert parameters["g_factor_corrected"] == 1.25
    assert [parameters["region_min"], parameters["region_max"]] == [300, 400]
    assert parameters["bg_region_bounds"] == [10, 20]
    assert parameters["micro_time_resolution"] == 50.0


def test_manual_zero_mixing_is_an_explicit_value():
    snapshot = model()
    snapshot.manual_l = True
    snapshot.l_override = 0.0
    snapshot.fp_result = {"l1": 0.0, "l2": 0.0}
    parameters = snapshot.detector_parameters(prior_l1=0.17, prior_l2=0.23)
    assert parameters["l1"] == parameters["l2"] == 0.0


def test_native_close_publishes_once_and_error_or_busy_close_publishes_nothing():
    from chisurf.plugins.vv_vh_g_factor.gui.app import create_app

    closed: list[GFactorModel | None] = []
    app = create_app(on_close=closed.append)
    app.model = model()
    app.close()
    app.close()
    assert len(closed) == 1
    assert closed[0] is not None and closed[0].g_factor == 1.25
    app = create_app(on_close=closed.append)
    app.model = model()
    app.model.message = "Error: reference load failed"
    app.close()
    assert closed[-1] is None


@pytest.mark.parametrize("state", ["busy", "cancelled", "no-result"])
def test_unfinished_native_close_does_not_publish_a_calibration(state):
    """Closing a running or failed-to-produce job must not archive an older result."""
    from concurrent.futures import Future

    from chisurf.plugins.vv_vh_g_factor.gui.app import create_app

    closed: list[GFactorModel | None] = []
    app = create_app(on_close=closed.append)
    app.model = model()
    if state == "no-result":
        app.model.result = {}
    else:
        app.job.future = Future()
        if state == "cancelled":
            app.job.stop()
    app.close()
    app.close()
    assert closed == [None]
    assert app.job.cancelled.is_set()
