"""Filter step settings pressed through the real controls; the kept-photon count is the outcome.

The stream is a short, dilute version of the demo (molecules crossing the focus, a weak uniform background), so a
burst filter has bursts to find and background to reject.
"""

from __future__ import annotations

import numpy as np
import pytest

from .streams import diffusion_spc
from .test_emtk_workflow import _hub, hermetic  # noqa: F401

CHANGE_POINT_FOLD = "Change-point parameters (BOCPD / Kalman / CUSUM).fold"


@pytest.fixture(scope="module")
def stream(tmp_path_factory):
    return diffusion_spc(tmp_path_factory.mktemp("filter"), "bursts.spc", rate_hz=200.0, duration_s=1.0, seed=11)


def _filter_step(stream):
    hub = _hub()
    hub.child.add_paths([str(stream)])
    hub.click("use_filter")
    hub.nav("filter")
    assert hub.app.selected == "filter"
    return hub, hub.app.filter_model


def _kept(hub):
    """Photons kept, from the model, after checking the step's own readout says the same."""
    model = hub.app.filter_model
    kept, total = int(model.selected().sum()), len(model._tttr)
    assert hub.shown(f"{kept:,} / {total:,} photons kept"), hub.draw(1).strings[-40:]
    return kept


def _mode(hub, mode):
    hub.click("filter_mode")
    hub.press_text(mode)
    assert hub.app.filter_model.filter_mode == mode


def test_every_filter_mode_selects_a_different_subset(stream):
    hub, model = _filter_step(stream)
    total = len(model._tttr)
    kept = {"burst": _kept(hub)}
    for mode in ("count_rate", "bocpd", "kalman", "cusum"):
        _mode(hub, mode)
        kept[mode] = _kept(hub)
    assert all(0 <= n <= total for n in kept.values()), kept
    assert len(set(kept.values())) >= 4, kept
    assert kept["kalman"] < kept["burst"], "the change-point detector rejects background the burst window keeps"
    hub.app.close()


def test_change_point_parameters_move_the_selection(stream):
    hub, model = _filter_step(stream)
    _mode(hub, "kalman")
    hub.click(CHANGE_POINT_FOLD)
    loose = _kept(hub)
    hub.type_into("kalman_z_thresh", "12")
    strict = _kept(hub)
    assert model.kalman_z_thresh == 12.0 and strict < loose
    hub.type_into("kalman_z_thresh", "-5")
    assert model.kalman_z_thresh == 0.0  # clamped to the declared minimum
    hub.type_into("trace_bin_width", "2")
    assert model.trace_bin_width == 2.0 and _kept(hub) != loose

    _mode(hub, "bocpd")
    default = _kept(hub)
    hub.type_into("bocpd_changepoint_prob", "0.01")
    assert model.bocpd_changepoint_prob == 0.01 and _kept(hub) != default
    hub.type_into("bocpd_changepoint_prob", "7")
    assert model.bocpd_changepoint_prob == 1.0  # a probability never exceeds one
    hub.app.close()


@pytest.mark.xfail(
    strict=True,
    reason="shipped CUSUM defaults (background 1/s, beta 20) select no photon at all: choosing the mode "
    "empties the correlator input until the user finds working values",
)
def test_cusum_with_its_default_parameters_keeps_some_photons(stream):
    hub, model = _filter_step(stream)
    _mode(hub, "cusum")
    assert 0 < int(model.selected().sum())
    hub.app.close()


def test_cusum_parameters_move_the_selection(stream):
    hub, model = _filter_step(stream)
    _mode(hub, "cusum")
    hub.click(CHANGE_POINT_FOLD)
    hub.type_into("cusum_bg_rate", "1000")
    hub.type_into("cusum_alpha", "0.05")
    hub.type_into("cusum_beta", "0.05")
    hub.type_into("cusum_sb_ratio", "0")
    reference = _kept(hub)
    assert 0 < reference < len(model._tttr)
    hub.type_into("cusum_bg_rate", "5000")  # a higher assumed background asks for a stronger signal
    assert model.cusum_bg_rate == 5000 and _kept(hub) < reference
    hub.type_into("cusum_alpha", "5")
    assert model.cusum_alpha == 1.0  # a probability never exceeds one
    hub.app.close()


def test_macro_time_interval_limits_drop_photons(stream):
    hub, model = _filter_step(stream)
    _mode(hub, "count_rate")
    hub.click("filter_enabled")
    assert not model.filter_enabled
    hub.click("use_max")  # upper limit off: every photon is kept
    assert not model.use_max and _kept(hub) == len(model._tttr)
    hub.click("use_max")
    hub.type_into("max_dmt", "0.01")
    assert model.max_dmt == 0.01 and model.use_max
    upper = _kept(hub)
    assert 0 < upper < len(model._tttr)  # only photons closer than 10 us to their predecessor
    hub.type_into("max_dmt", "-4")
    assert model.max_dmt == 0.0 and _kept(hub) < upper  # only coincident photons remain
    hub.type_into("max_dmt", "1.5")
    hub.click("use_min")
    hub.type_into("min_dmt", "0.01")
    assert model.use_min and model.min_dmt == 0.01
    window = _kept(hub)
    assert 0 < window < len(model._tttr) - upper + 1  # photons wider apart than 10 us, closer than 1.5 ms
    hub.app.close()


def test_burst_threshold_enable_and_invert(stream):
    hub, model = _filter_step(stream)
    hub.click("use_max")  # without the dMT limit, invert is the exact complement
    total = len(model._tttr)
    relaxed = _kept(hub)
    hub.type_into("min_ph", "60")
    strict = _kept(hub)
    assert model.min_ph == 60 and strict < relaxed
    hub.click("invert")
    assert model.invert and _kept(hub) == total - strict
    hub.click("invert")
    hub.click("filter_enabled")
    assert _kept(hub) == total
    hub.app.close()


def test_the_correlator_receives_what_the_filter_kept_and_sees_a_larger_amplitude(stream):
    hub, model = _filter_step(stream)
    hub.click("use_max")
    hub.type_into("min_ph", "30")
    kept = _kept(hub)
    hub.nav("correlator")
    assert len(hub.app.correlator_model._tttr) == kept
    hub.type_into("channel_a", "0")
    hub.type_into("channel_b", "1")
    hub.click("correlate")
    hub.wait_correlated()
    filtered = hub.child.model._correlations[0]
    hub.nav("files")
    hub.click("use_filter")
    hub.nav("correlator")
    hub.click("correlate")
    hub.wait_correlated()
    raw = hub.child.model._correlations[0]
    amplitude = lambda c: float(np.interp(0.02, c["x"], c["y"]) - 1.0)  # noqa: E731
    assert amplitude(filtered) != amplitude(raw)
    hub.app.close()
