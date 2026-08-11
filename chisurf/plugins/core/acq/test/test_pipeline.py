"""The live acquisition pipeline computes what the batch analysis computes.

A live display is trusted the way a saved analysis is, so the bar for the
streaming consumers is equality with the batch ones on the same photons — not
"looks about right while it scrolls". The photons here are a real simulated
photon stream encoded as real B&H SPC-132 records, so the decode path under
test is the one an acquisition uses.

The other half of the bar is cost. The pipeline replaced a design whose per-
chunk work grew with elapsed run time (the batch correlator re-run over the
whole history, an MCS binning every photon to display its last second), and
that growth is invisible in any test that pushes a short stream once. It is
asserted directly below: the last chunk of a run must not cost more than the
first, and the state carried between chunks must not grow.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.plugins.core.acq.pipeline import (  # noqa: E402
    AcquisitionPipeline,
    PhotonDecoder,
    PipelineConfig,
    record_type_for_device,
)

MACRO_CLOCK = 50e-9
CHUNK = 4096


@pytest.fixture(scope="module")
def spc_words():
    """A simulated confocal photon stream, encoded as SPC-132 records."""
    from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import (
        generate_spc132_uint32,
    )

    return generate_spc132_uint32(
        {
            "N_ph_max": 50_000,
            "psf_type": "analytic_gaussian3d",
            "analytic_excitation": True,
        }
    )


@pytest.fixture(scope="module")
def photons(spc_words):
    """The same records decoded in one call — the batch oracle."""
    decoded, _ = tttrlib.decode_records(
        spc_words, tttrlib.RECORD_SPC130, tttrlib.TTTRDecodeState()
    )
    return (
        np.asarray(decoded.macro_times, dtype=np.uint64),
        np.asarray(decoded.micro_times, dtype=np.uint16),
        np.asarray(decoded.routing_channel, dtype=np.int32),
    )


def run_pipeline(words, **config_kwargs):
    """Push `words` through a pipeline in chunks, as the device delivers them."""
    config = PipelineConfig(
        record_type=tttrlib.RECORD_SPC130,
        macrotime_clock=MACRO_CLOCK,
        channels=(8, 0, 9, 1),
        **config_kwargs,
    )
    pipeline = AcquisitionPipeline(config)
    for start in range(0, len(words), CHUNK):
        pipeline.push(words[start:start + CHUNK])
    return pipeline


def batch_correlation(t1, t2):
    """The batch Wahl correlator on the same photons, on the same axis."""
    correlator = tttrlib.Correlator()
    correlator.method = "wahl"
    correlator.n_bins = 9
    correlator.n_casc = 15
    correlator.set_macrotimes(np.asarray(t1, np.uint64), np.asarray(t2, np.uint64))
    correlator.set_weights(np.ones(len(t1)), np.ones(len(t2)))
    return (
        np.asarray(correlator.x_axis, dtype=float),
        np.asarray(correlator.get_corr_normalized(), dtype=float),
    )


# ---------------------------------------------------------------------------
# One decode path
# ---------------------------------------------------------------------------

def test_chunked_decode_equals_the_whole_buffer(spc_words, photons):
    """The carried overflow counter is what makes macro times absolute.

    A decoder that starts each buffer at zero produces a plausible first chunk
    and nonsense from the second on, with nothing raising.
    """
    macro, micro, channel = photons
    decoder = PhotonDecoder(tttrlib.RECORD_SPC130)
    got = [decoder.decode(spc_words[i:i + CHUNK]) for i in range(0, len(spc_words), CHUNK)]

    np.testing.assert_array_equal(np.concatenate([g[0] for g in got]), macro)
    np.testing.assert_array_equal(np.concatenate([g[1] for g in got]), micro)
    np.testing.assert_array_equal(np.concatenate([g[2] for g in got]), channel)


def test_a_picoquant_buffer_decodes_through_the_library():
    """PicoQuant records go through the same decoder as B&H, not a copy of it.

    This is the format that used to fall through to a hand-rolled numpy
    bit-field decoder in the base class — "bits 25-30 for channel info,
    implementation may need adjustment based on exact format".
    """
    def record(nsync, dtime, channel, special=0):
        return np.uint32(
            (special << 31) | ((channel & 0x3F) << 25) | ((dtime & 0x7FFF) << 10)
            | (nsync & 0x3FF)
        )

    overflow = np.uint32((1 << 31) | (63 << 25) | 1)  # one 1024-sync wrap
    words = np.array(
        [record(5, 100, 0), record(9, 200, 1), overflow, record(3, 300, 0)],
        dtype=np.uint32,
    )

    decoder = PhotonDecoder(tttrlib.RECORD_HHT3v2)
    macro, micro, channel = decoder.decode(words)

    np.testing.assert_array_equal(macro, [5, 9, 1024 + 3])
    np.testing.assert_array_equal(micro, [100, 200, 300])
    np.testing.assert_array_equal(channel, [0, 1, 0])


def test_an_unknown_device_is_an_error_not_a_guess():
    class Mystery:
        device_type = "SOMETHING_NEW"

    with pytest.raises(ValueError, match="record type"):
        record_type_for_device(Mystery())

    class Declared:
        device_type = "SOMETHING_NEW"
        record_type = tttrlib.RECORD_HHT2v2

    assert record_type_for_device(Declared()) == tttrlib.RECORD_HHT2v2


def test_no_bit_shift_decoding_survives_in_the_plugin():
    """Acceptance criterion: one decoder, and it is the library's.

    A second decoder does not announce itself — it is a few `np.right_shift`
    calls that agree with the library on the fixtures someone happened to try.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for path in root.rglob("*.py"):
        if "test" in path.parts:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        for needle in ("np.right_shift", "np.bitwise_and(np.right_shift"):
            if needle in source:
                offenders.append(f"{path.relative_to(root)}: {needle}")
    assert not offenders, "hand-rolled record decoding is back: " + "; ".join(offenders)


# ---------------------------------------------------------------------------
# Streaming equals batch
# ---------------------------------------------------------------------------

def test_live_decay_equals_bincount_of_the_saved_stream(spc_words, photons):
    _macro, micro, channel = photons
    pipeline = run_pipeline(spc_words)

    for window, routing in enumerate(pipeline.config.channels):
        expected = np.bincount(micro[channel == routing], minlength=4096).astype(float)
        np.testing.assert_array_equal(pipeline.decay(window), expected)


def assert_agrees_per_cascade(y_live, y_batch, rtol=5e-3):
    """Compare the two curves cascade by cascade, not in aggregate.

    The two are not bit-identical and are not meant to be: the normalisation's
    overlap term (how much measurement a lag actually had) is counted from
    emitted bins in the streaming correlator and from photon times in the batch
    one, which on this stream differs by <=0.2%. What an aggregate tolerance
    would hide is the failure that matters — a lag misassignment reads as a
    *cascade-dependent* bias that grows with the cascade (measured at 1.19-2.39x
    when that defect was live), so each cascade is asserted separately.
    """
    n_bins, n_casc = 9, 15
    for cascade in range(n_casc - 3):
        lo = cascade * n_bins + 1
        hi = lo + n_bins
        live, batch = y_live[lo:hi], y_batch[lo:hi]
        keep = np.isfinite(live) & np.isfinite(batch) & (batch > 1e-6)
        if keep.sum() < n_bins // 2:
            continue
        np.testing.assert_allclose(
            live[keep], batch[keep], rtol=rtol,
            err_msg=f"cascade {cascade} disagrees with the batch correlator",
        )


def test_live_autocorrelation_equals_the_batch_correlator(spc_words, photons):
    macro, _micro, channel = photons
    pipeline = run_pipeline(spc_words, correlation_pairs=((0, 8, 8),))
    pipeline.flush()

    selected = macro[channel == 8]
    x_batch, y_batch = batch_correlation(selected, selected)
    x_live, y_live = pipeline.correlation(0)

    # The lag axis, on the other hand, must match exactly — the display's x
    # axis is in ms and the correlator's is in seconds, and one stray factor of
    # the macro-time clock puts the curve eight decades off the plot.
    np.testing.assert_allclose(x_live, x_batch * MACRO_CLOCK * 1e3, rtol=1e-12)
    assert_agrees_per_cascade(y_live, y_batch)


def test_live_crosscorrelation_equals_the_batch_correlator(spc_words, photons):
    """The lag runs a -> b in both, so the two curves are the same curve."""
    macro, _micro, channel = photons
    pipeline = run_pipeline(spc_words, correlation_pairs=((0, 8, 0),))
    pipeline.flush()

    x_batch, y_batch = batch_correlation(macro[channel == 8], macro[channel == 0])
    x_live, y_live = pipeline.correlation(0)

    np.testing.assert_allclose(x_live, x_batch * MACRO_CLOCK * 1e3, rtol=1e-12)
    assert_agrees_per_cascade(y_live, y_batch)


def test_a_pair_that_overlaps_feeds_the_photon_to_both_streams(spc_words, photons):
    """`-1` on one side means *every* photon, including the other side's.

    The correlator takes one channel per push, so such a photon has to be
    pushed twice at the same macro time. Pushing it once correlates a different
    pair of streams than the operator asked for, and the curve still looks
    like a correlation curve.
    """
    macro, _micro, channel = photons
    pipeline = run_pipeline(spc_words, correlation_pairs=((0, -1, 8),))
    pipeline.flush()

    x_batch, y_batch = batch_correlation(macro, macro[channel == 8])
    x_live, y_live = pipeline.correlation(0)

    np.testing.assert_allclose(x_live, x_batch * MACRO_CLOCK * 1e3, rtol=1e-12)
    assert_agrees_per_cascade(y_live, y_batch)


def test_live_mcs_equals_the_batch_intensity_trace(spc_words, photons):
    macro, _micro, _channel = photons
    pipeline = run_pipeline(spc_words, mcs_bin_width_ms=1.0, mcs_rollaround_ms=1e9)

    expected = np.asarray(
        tttrlib.compute_intensity_trace(
            macro, time_window_length=1e-3, macro_time_resolution=MACRO_CLOCK
        ),
        dtype=float,
    )
    _x, y = pipeline.mcs_trace()
    np.testing.assert_array_equal(y, expected)


def test_the_mcs_window_is_the_tail_of_the_batch_trace(spc_words, photons):
    """The rolling window is what bounds memory; it must not shift the bins."""
    macro, _micro, _channel = photons
    pipeline = run_pipeline(spc_words, mcs_bin_width_ms=1.0, mcs_rollaround_ms=200.0)

    full = np.asarray(
        tttrlib.compute_intensity_trace(
            macro, time_window_length=1e-3, macro_time_resolution=MACRO_CLOCK
        ),
        dtype=float,
    )
    x, y = pipeline.mcs_trace()
    assert len(y) == 200
    np.testing.assert_array_equal(y, full[-200:])
    # The window keeps its absolute place on the time axis.
    np.testing.assert_allclose(x[0], (len(full) - 200) * 1.0)


# ---------------------------------------------------------------------------
# Cost and memory
# ---------------------------------------------------------------------------

def test_per_chunk_cost_does_not_grow_with_run_length(spc_words):
    """Minute 30 must cost what minute 1 costs.

    The design this replaced re-ran a batch correlator over the whole history,
    so the *last* chunk of a run was the most expensive one — by a factor that
    grew forever. Timing is noisy, so the bar is deliberately loose (3x); the
    old behaviour on this stream exceeds it by an order of magnitude.
    """
    pipeline = AcquisitionPipeline(
        PipelineConfig(
            record_type=tttrlib.RECORD_SPC130,
            macrotime_clock=MACRO_CLOCK,
            channels=(8, 0, 9, 1),
            correlation_pairs=((0, 8, 8), (1, 0, 0), (2, 8, 0), (3, -1, -1)),
        )
    )

    chunks = [spc_words[i:i + CHUNK] for i in range(0, len(spc_words), CHUNK)]
    costs = []
    for chunk in chunks:
        start = time.perf_counter()
        pipeline.push(chunk)
        costs.append(time.perf_counter() - start)

    n = max(2, len(costs) // 5)
    first = float(np.median(costs[:n]))
    last = float(np.median(costs[-n:]))
    assert last < 3.0 * first, f"per-chunk cost grew: {first:.4f} s -> {last:.4f} s"


def test_nothing_downstream_of_decode_keeps_the_photons(spc_words):
    """RAM is bounded: the display state is sized by configuration, not by N."""
    pipeline = run_pipeline(
        spc_words[: len(spc_words) // 4], max_countrate_points=50, max_macrotime_points=100
    )
    after_quarter = {
        "count_rates": len(pipeline._count_rate_times),
        "macrotimes": len(pipeline._macrotime_diffs),
        "mcs": pipeline._mcs.n_bins(),
    }

    for start in range(len(spc_words) // 4, len(spc_words), CHUNK):
        pipeline.push(spc_words[start:start + CHUNK])

    assert len(pipeline._count_rate_times) <= 50
    assert len(pipeline._macrotime_diffs) <= 100
    assert pipeline._mcs.n_bins() <= 1000
    assert after_quarter["count_rates"] <= 50
    # No array of photons is kept anywhere on the pipeline.
    for name, value in vars(pipeline).items():
        if isinstance(value, np.ndarray):
            assert value.size < 10_000, f"{name} grows with the acquisition"


def test_snapshot_carries_display_state_only(spc_words):
    pipeline = run_pipeline(spc_words)
    snapshot = pipeline.snapshot()

    assert snapshot["total_photons"] == 50_000
    assert len(snapshot["decay_data"]) == 4
    assert snapshot["mean_count_rate_khz"] > 0
    assert snapshot["elapsed_s"] > 0
    assert snapshot["phasor"] is not None
    assert snapshot["burst_count"] is not None
    assert sum(snapshot["channel_totals"]) == 50_000


# ---------------------------------------------------------------------------
# Stop conditions
# ---------------------------------------------------------------------------

def test_the_photon_limit_stops_the_run(spc_words):
    pipeline = run_pipeline(spc_words, photon_limit=10_000)
    assert pipeline.stop_reason is not None
    assert "Photon limit" in pipeline.stop_reason


def test_the_time_limit_is_measured_in_photon_time(spc_words):
    """Elapsed time is what the photons say, not what the wall clock says."""
    pipeline = run_pipeline(spc_words, time_limit_s=1.0)
    assert pipeline.stop_reason is not None
    assert "Time limit" in pipeline.stop_reason
    assert pipeline.elapsed_s >= 1.0
