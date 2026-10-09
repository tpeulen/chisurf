"""Burst FCS uses the same half-open detector windows as its burst-table inputs."""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import tttrlib

from chisurf.plugins.burst.burst_fcs_correlator.core.algorithms import (
    BurstFcsSettings,
    PairConfig,
    correlate_burst_file,
    correlate_single_burst,
)


def _wahl_reference(times, weights_a, weights_b, n_bins, n_casc):
    """Count weighted event pairs directly on each integer Wahl cascade."""
    times = np.asarray(times, dtype=np.uint64)
    axis = [0]
    step = 1
    for index in range(1, n_bins * n_casc + 1):
        axis.append(axis[-1] + step)
        if index % n_bins == 0:
            step *= 2
    axis = np.asarray(axis, dtype=np.uint64)
    counts = np.zeros(len(axis))
    pair_weights = weights_a[:, None] * weights_b[None, :]
    for cascade in range(n_casc):
        coarse = times >> np.uint64(cascade)
        difference = coarse[None, :] - coarse[:, None]
        offset = int(axis[cascade * n_bins]) >> cascade
        for increment in range(1, n_bins + 1):
            counts[cascade * n_bins + increment] = np.sum(
                pair_weights[difference == offset + increment]
            )
    duration = float(int(times[-1]) - int(times[0]))
    rate_a = weights_a.sum() / max(1.0, duration)
    rate_b = weights_b.sum() / max(1.0, duration)
    widths = np.exp2(np.maximum(np.arange(len(axis)) - 1, 0) // n_bins)
    with np.errstate(divide="ignore", invalid="ignore"):
        normalized = counts / (widths * rate_a * rate_b * (duration - axis.astype(float)))
    return axis, normalized


def _assert_reference(tttr, weights_a, weights_b, tau, correlation, fine, bins=3, cascades=8):
    """Compare the SDK's curve and clock with independently counted event pairs."""
    times = np.asarray(tttr.macro_times, dtype=np.uint64)
    tick = tttr.header.macro_time_resolution
    if fine:
        times = times * np.uint64(tttr.get_number_of_micro_time_channels())
        times += np.asarray(tttr.micro_times, dtype=np.uint64)
        tick = tttr.header.micro_time_resolution
    axis, expected = _wahl_reference(times, weights_a, weights_b, bins, cascades)
    np.testing.assert_array_equal(tau, axis.astype(float) * (tick * 1000.0))
    np.testing.assert_allclose(correlation, expected, rtol=1e-12, atol=1e-12, equal_nan=True)


def _boundary_photons():
    """Build photons occupying every small gate boundary with known multiplicity."""
    micro = np.tile(np.arange(8, dtype=np.uint16), 40)
    macro = np.cumsum(np.random.default_rng(15).integers(1, 5, len(micro))).astype(np.uint64)
    tttr = tttrlib.TTTR()
    tttr.append_events(
        macro, micro, np.zeros(len(micro), np.int8), np.zeros(len(micro), np.int8), False, 0
    )
    tttr.header.set_macro_time_resolution(1e-6)
    tttr.header.set_micro_time_resolution(1e-9)
    return tttr


@pytest.mark.parametrize("fine", [False, True])
@pytest.mark.parametrize(
    "ranges,accepted",
    [
        ([[2, 5]], [2, 3, 4]),
        ([[0, 5]], [0, 1, 2, 3, 4]),
        ([[0, 1]], [0]),
        ([[0, 4], [4, 8]], list(range(8))),
        ([[1, 5], [3, 7]], [1, 2, 3, 4, 5, 6]),
        ([], list(range(8))),
        ([[2, 2]], []),
    ],
    ids=["lower", "upper", "zero", "adjacent", "overlap", "ungated", "empty-width"],
)
def test_gate_boundary_weights_match_independent_wahl(ranges, accepted, fine):
    """Lower edges count, upper edges do not; unions never double-count a photon."""
    photons = _boundary_photons()
    weights_a = np.isin(photons.micro_times, accepted).astype(float)
    weights_b = np.ones(len(photons), dtype=float)
    cascades = 14 if fine else 8
    tau, correlation = correlate_single_burst(photons, [0], [0], ranges, [], 3, cascades, fine)
    if not accepted:
        assert tau is None and correlation is None
        return
    _assert_reference(photons, weights_a, weights_b, tau, correlation, fine, cascades=cascades)
    # Both sides apply the convention; testing B separately rules out an
    # asymmetric change that only fixes one channel's normalization.
    tau, correlation = correlate_single_burst(photons, [0], [0], [], ranges, 3, cascades, fine)
    _assert_reference(photons, weights_b, weights_a, tau, correlation, fine, cascades=cascades)


@pytest.mark.parametrize("fine", [False, True])
def test_actual_burst_worker_includes_zero_microtime_photon(tmp_path, monkeypatch, fine):
    """The measured 216-photon green gate agrees with its BUR detector definition."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    source = (
        Path(__file__).resolve().parents[2]
        / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m000.spc"
    )
    path = tmp_path / "m000.spc"
    shutil.copyfile(source, path)
    from chisurf.core.fio import lut_context
    from chisurf.plugins.burst.burst_fcs_correlator.core.algorithms import open_tttr

    definition = json.loads(
        (source.parent / "burst_analysis_handoff/burst_analysis_handoff.json").read_text()
    )["channel_settings"]
    monkeypatch.setattr(lut_context, "_active", {})
    lut_context.set_active_setup_lut(
        definition["channel_luts"], definition["channel_shifts"], definition["apply_lut"]
    )
    photons = open_tttr(path, "SPC-130")
    segment = photons[1551:2076]
    channels = [0, 3, 8]
    weights = (
        np.isin(segment.routing_channels, channels)
        & (np.asarray(segment.micro_times) >= 0)
        & (np.asarray(segment.micro_times) < 2048)
    ).astype(float)
    assert int(weights.sum()) == 216
    sdk_mask = tttrlib.TTTRMask()
    sdk_mask.select_microtime_ranges(segment, [[0, 2048]])
    sdk_mask.flip()
    sdk_weights = sdk_mask.mask.astype(bool) & np.isin(segment.routing_channels, channels)
    assert int(sdk_weights.sum()) == 215  # SDK's different public contract is preserved.
    settings = BurstFcsSettings(
        n_bins=3, n_casc=20, make_fine=fine, padding_ms=0.0, fit_mode="none"
    )
    pair = PairConfig("green_ACF", channels, channels, [[0, 2048]], [[0, 2048]])
    curves = correlate_burst_file(path, [(1551, 2075)], [pair], settings, filetype="SPC-130")
    assert len(curves) == 1
    curve = curves[0]
    _assert_reference(
        segment, weights, weights, curve["tau_raw"], curve["g_raw"], fine, bins=3, cascades=20
    )
