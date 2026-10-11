"""Correlator step settings pressed through the real controls, checked on streams with a known answer.

Poisson light has G = 1 at every lag; molecules crossing the focus give an amplitude of one over the effective number
of molecules (:func:`.streams.expected_amplitude`). Each setting is typed or chosen at its drawn control and the
computed curve is read back.
"""

from __future__ import annotations

import numpy as np
import pytest

from .streams import diffusion_spc, expected_amplitude, poisson_spc
from .test_emtk_workflow import _hub, hermetic  # noqa: F401


def _open(path, **fields):
    hub = _hub()
    hub.child.add_paths([str(path)])
    hub.nav("correlator")
    hub.type_into("channel_a", "0")
    hub.type_into("channel_b", "1")
    for key, text in fields.items():
        hub.type_into(key, text)
    return hub


def _curve(hub):
    hub.click("correlate")
    hub.wait_correlated()
    result = hub.child.model._correlations[0]
    return np.asarray(result["x"]), np.asarray(result["y"]), result


def _amplitude(x, y):
    return float(np.interp(0.02, x, y) - 1.0)


@pytest.fixture(scope="module")
def streams(tmp_path_factory):
    folder = tmp_path_factory.mktemp("streams")
    return {
        "poisson": poisson_spc(folder, "poisson.spc"),
        "dense": diffusion_spc(folder, "dense.spc", rate_hz=1000.0),
        "dilute": diffusion_spc(folder, "dilute.spc", rate_hz=250.0, duration_s=4.0),
    }


def test_poisson_light_is_flat_at_one_and_diffusion_has_amplitude_one_over_n(streams):
    hub = _open(streams["poisson"])
    x, y, _ = _curve(hub)
    window = (x > 0.05) & (
        x < 20.0
    )  # shorter lags hold too few photon pairs to be flat by noise alone
    assert window.sum() > 10
    assert np.max(np.abs(y[window] - 1.0)) < 0.08, "Poisson light must correlate to G = 1"
    assert abs(np.mean(y[window]) - 1.0) < 0.01
    hub.app.close()

    hub = _open(streams["dense"])
    x, y, _ = _curve(hub)
    assert _amplitude(x, y) == pytest.approx(expected_amplitude(1000.0), rel=0.2)
    assert abs(np.interp(5.0, x, y) - 1.0) < 0.12  # decayed: the crossing lasts 0.25 ms
    dense = _amplitude(x, y)
    hub.app.close()

    hub = _open(streams["dilute"])
    x, y, _ = _curve(hub)
    dilute = _amplitude(x, y)
    assert dilute == pytest.approx(expected_amplitude(250.0), rel=0.25)
    assert dilute / dense == pytest.approx(
        4.0, rel=0.3
    )  # a quarter of the molecules, four times the amplitude
    hub.app.close()


def test_bins_and_cascades_shape_the_lag_axis(streams):
    hub = _open(streams["poisson"], n_bins="3", n_casc="12")
    x3, _, result = _curve(hub)
    assert result["correlation_settings"]["n_bins"] == 3
    hub.type_into("n_bins", "8")
    x8, _, result = _curve(hub)
    assert result["correlation_settings"]["n_bins"] == 8
    assert len(x8) > 1.8 * len(x3)  # more bins per cascade: a denser lag grid
    hub.type_into("n_casc", "6")
    x6, _, result = _curve(hub)
    assert result["correlation_settings"]["n_casc"] == 6
    assert x6[-1] < x8[-1] / 20 and len(x6) < len(x8)  # fewer cascades stop at a shorter lag
    hub.app.close()


def test_typed_values_are_clamped_to_the_declared_range(streams):
    hub = _open(streams["poisson"])
    hub.type_into("n_bins", "0")
    assert hub.child.model.n_bins == 1
    hub.type_into("n_casc", "500")
    assert hub.child.model.n_casc == 64
    hub.type_into("n_splits", "-3")
    assert hub.child.model.n_splits == 1
    hub.app.close()


def test_splits_make_one_curve_per_chunk(streams):
    hub = _open(streams["dense"], n_splits="2")
    hub.click("correlate")
    hub.wait_correlated()
    curves = hub.child.model._correlations
    assert len(curves) == 2 and hub.shown("2 chunk(s) correlated.")
    amplitudes = [_amplitude(np.asarray(c["x"]), np.asarray(c["y"])) for c in curves]
    assert all(a == pytest.approx(expected_amplitude(1000.0), rel=0.3) for a in amplitudes)
    assert amplitudes[0] != amplitudes[1]  # the chunks are independent realisations
    hub.app.close()


def test_method_choice_reaches_the_curve(streams):
    hub = _open(streams["dense"])
    base_x, base_y, result = _curve(hub)
    assert result["correlation_settings"]["method"] == "laurence"
    hub.click("method")
    hub.press_text("wahl")
    assert hub.child.model.method == "wahl"
    x, y, result = _curve(hub)
    assert result["correlation_settings"]["method"] == "wahl"
    assert len(x) == len(base_x) and not np.allclose(y, base_y)  # same lags, other normalisation
    assert (
        _amplitude(x, y) > 0.5
    )  # still correlated; Wahl's normalisation just reads a higher amplitude
    assert _amplitude(base_x, base_y) == pytest.approx(expected_amplitude(1000.0), rel=0.1)
    hub.app.close()


def test_fine_correlation_and_microtime_binning_set_the_lag_resolution(streams):
    hub = _open(streams["dense"])
    coarse_x, _, _ = _curve(hub)
    hub.click("make_fine")
    assert hub.child.model.make_fine
    fine_x, fine_y, _ = _curve(hub)
    assert fine_x[1] < coarse_x[1] / 1000  # micro-time ticks (ps) instead of macro-time ticks (ns)
    hub.click("microtime_binning")
    hub.press_text("4")
    assert hub.child.model.microtime_binning == 4
    binned_x, _, _ = _curve(hub)
    assert binned_x[1] == pytest.approx(4 * fine_x[1], rel=0.01)
    hub.app.close()
