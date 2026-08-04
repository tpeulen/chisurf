"""Milestone 1a: reproducing a real static cloud's *width*, not just its position.

PRD-71's first gate, on a real BH SPC-132 single-molecule DNA measurement. The
position of an MFD cloud is easy to hit — several wrong models hit it. The width is
not, and it is the thing that matters: **any width the model fails to explain will
later be absorbed as exchange**, so a model that is too narrow here will invent
dynamics there, and one that is too wide will hide them.

So the gate is width, with **no free broadening parameter**. Nothing in the model
controls the spread of the cloud: it comes out of the measured signal distribution
and the observation spans, through the binomial partition and the ``v/N`` sampling
variance of the mean micro time.

The donor-only population is what makes this a real test rather than a
self-consistency check. Its width is fixed entirely by shot noise — it has no
distance, no efficiency, and nothing fitted to its spread — and its expected width
can be computed *from the photons themselves*, without the model. That model-free
number is what the model is held to here.

The FRET population is deliberately **not** required to match: its excess width is
physical heterogeneity, which is the quantity PRD-71 exists to fit and which no
shot-noise model should reproduce. Asserting the model stays *below* it is the
guard against the failure mode that matters — a model that broadens itself to fit
and thereby absorbs real structure.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.fluorescence.mfd.fit import MfdModel, load_mfd_data
from chisurf.core.fluorescence.mfd.histogram import HistogramAxes
from chisurf.core.fluorescence.mfd.patterns import FretState, Optics

REPO = pathlib.Path(__file__).resolve().parents[2]
ANALYSIS = (
    REPO
    / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
    / "burstwise_All 0.1000#15"
)

#: Least-squares optimum of the four position parameters on this measurement
#: (donor-only lifetime, mean distance, donor-only fraction, donor leakage). They
#: are position parameters: none of them widens or narrows the cloud, which is what
#: makes the width assertions below a prediction rather than a fit.
#:
#: ``tau_d0`` was 1.569 ns while the instrument response was taken as the
#: baseline-subtracted non-burst histogram. That histogram's prompt rides on the
#: decay of molecules too dim to cross the burst threshold, so its first moment
#: sat late, and the only parameter degenerate with it — the donor lifetime —
#: absorbed the difference and came out about half of anything a dye on DNA has.
#: Fitting a Gaussian to the prompt instead (:func:`~chisurf.core.fluorescence.
#: burst.irf_bg.gaussian_prompt`) sheds that tail, and re-deriving the optimum
#: moves ``tau_d0`` to 2.724 ns while leaving the other three within a percent —
#: which is what a genuine degeneracy looks like when it is broken.
FITTED = {
    "tau_d0": 2.724,
    "distance": 54.69,
    "donor_only": 0.3953,
    "alpha": 0.02997,
}

pytestmark = pytest.mark.skipif(
    not ANALYSIS.is_dir(), reason="the bh_spc132_sm_dna burst folder is not present"
)


@pytest.fixture(scope="module")
def data():
    """Return the measurement, loaded once."""
    return load_mfd_data(
        ANALYSIS,
        axes=HistogramAxes.default(
            n_ratio=60, n_micro_time=60, micro_time_range=(2.0, 8.0)
        ),
        min_green_photons=20,
    )


@pytest.fixture(scope="module")
def model():
    """Return the fitted static model."""
    return MfdModel(
        optics=Optics(
            r0=52.0,
            tau_d0=FITTED["tau_d0"],
            tau_a=3.0,
            sigma=6.0,
            alpha=FITTED["alpha"],
            delta=0.0,
            gamma=1.0,
        ),
        states=[FretState(distance=FITTED["distance"])],
        donor_only=FITTED["donor_only"],
    )


def _moments(weights, centres):
    """Return the weighted mean and standard deviation of a marginal."""
    total = weights.sum()
    mean = float((centres * weights).sum() / total)
    return mean, float(np.sqrt((weights * (centres - mean) ** 2).sum() / total))


@pytest.fixture(scope="module")
def marginals(data, model):
    """Return the data and model marginals of both populations."""
    predicted = model.histogram(data)
    observed = data.observed.counts
    predicted = predicted * observed.sum() / predicted.sum()
    axes = data.axes
    ratio_c = 0.5 * (axes.ratio_edges[:-1] + axes.ratio_edges[1:])
    micro_c = 0.5 * (axes.micro_time_edges[:-1] + axes.micro_time_edges[1:])

    out = {}
    for name, selection in (
        ("donor_only", ratio_c < 0.10),
        ("fret", (ratio_c > 0.25) & (ratio_c < 0.65)),
    ):
        out[name] = {
            "ratio": {
                "data": _moments(observed[selection].sum(axis=1), ratio_c[selection]),
                "model": _moments(predicted[selection].sum(axis=1), ratio_c[selection]),
            },
            "micro_time": {
                "data": _moments(observed[selection].sum(axis=0), micro_c),
                "model": _moments(predicted[selection].sum(axis=0), micro_c),
            },
        }
    return out


# ──────────────────────────────────────────────────────────────────────────────
# The measurement loads, and says what it dropped
# ──────────────────────────────────────────────────────────────────────────────
def test_the_measurement_supplies_its_own_instrument_response(data):
    """Response and background come from the non-burst photons, not a second file."""
    for name in ("green", "red"):
        response = data.responses[name]
        assert response.n_channels == 4096
        assert response.period == pytest.approx(13.5, abs=0.1)
        # A real background rate: hundreds of Hz, not zero and not a burst rate.
        assert 100.0 < response.background_rate < 5000.0
        assert response.irf.sum() == pytest.approx(1.0)


def test_the_excluded_fraction_is_reported_not_hidden(data):
    """Nearly half these bursts are too dim for a Gaussian ⟨t⟩ kernel; say so."""
    summary = data.observed.summary
    assert summary["n_input"] == 2980
    assert summary["n_used"] == 1645
    assert summary["excluded_fraction"] == pytest.approx(0.448, abs=0.01)
    assert summary["min_green_photons"] == 20


# ──────────────────────────────────────────────────────────────────────────────
# Position
# ──────────────────────────────────────────────────────────────────────────────
def test_both_populations_sit_where_the_data_puts_them(marginals):
    """The cloud's position, on both axes and for both populations."""
    donor = marginals["donor_only"]
    fret = marginals["fret"]
    assert donor["ratio"]["model"][0] == pytest.approx(
        donor["ratio"]["data"][0], abs=0.01
    )
    assert fret["ratio"]["model"][0] == pytest.approx(fret["ratio"]["data"][0], abs=0.02)
    # The lifetime axis separates the two populations the right way round: the
    # donor-only molecules are unquenched, so they arrive later.
    assert donor["micro_time"]["data"][0] > fret["micro_time"]["data"][0] + 0.5
    assert donor["micro_time"]["model"][0] > fret["micro_time"]["model"][0] + 0.5
    assert donor["micro_time"]["model"][0] == pytest.approx(
        donor["micro_time"]["data"][0], abs=0.2
    )
    assert fret["micro_time"]["model"][0] == pytest.approx(
        fret["micro_time"]["data"][0], abs=0.25
    )


# ──────────────────────────────────────────────────────────────────────────────
# The gate: width, with nothing fitted to it
# ──────────────────────────────────────────────────────────────────────────────
def test_donor_only_ratio_width_is_reproduced_with_no_free_parameter(marginals):
    """Shot noise on the FRET axis, checked where it is the *whole* width.

    A donor-only molecule has no efficiency and no distance; the spread of its
    proximity ratio is the binomial partition of its own measured signal and
    nothing else. The model reproduces it to a few percent without a single
    parameter that could have been tuned to.
    """
    data_sd = marginals["donor_only"]["ratio"]["data"][1]
    model_sd = marginals["donor_only"]["ratio"]["model"][1]
    assert data_sd == pytest.approx(0.0215, abs=0.003)
    assert model_sd == pytest.approx(data_sd, rel=0.12)


def test_donor_only_lifetime_width_matches_the_photons_own_shot_noise(data, marginals):
    """The ⟨t⟩ spread the model predicts is the one the photons imply.

    Computed here without the model at all: each burst's green photons give a
    within-burst micro-time variance ``v``, so a burst of ``N`` of them has a mean
    micro time of variance ``v/N``. Averaged over the donor-only bursts, that is
    what any correct model must produce — and it is well below the *observed*
    spread, because the sample is genuinely heterogeneous.
    """
    from chisurf.core.fluorescence.mfd.prepare import prepare_burst_folder  # noqa: F401

    preparation = data.preparation
    tttrs = preparation.summary["_tttrs"]
    green = preparation.channel_index("green")
    red = preparation.channel_index("red")
    channels = preparation.streams[green].channels

    n_green = preparation.counts[:, green]
    n_red = preparation.counts[:, red]
    micro = preparation.mean_micro_time[:, green]
    ratio = n_red / np.maximum(n_green + n_red, 1)
    rows = np.nonzero((n_green >= 20) & np.isfinite(micro) & (ratio < 0.10))[0]
    assert rows.size > 500

    dt_ns = None
    variance_over_n = []
    for row in rows:
        tttr = tttrs[preparation.file_key[row]]
        if dt_ns is None:
            dt_ns = float(tttr.header.micro_time_resolution) * 1e9
        lo = int(preparation.first_photon[row])
        hi = int(preparation.last_photon[row]) + 1
        routing = np.asarray(tttr.routing_channels)[lo:hi]
        times = np.asarray(tttr.micro_times)[lo:hi][np.isin(routing, channels)]
        values = times.astype(float) * dt_ns
        variance_over_n.append(values.var(ddof=1) / values.size)

    shot_noise_sd = float(np.sqrt(np.mean(variance_over_n)))
    model_sd = marginals["donor_only"]["micro_time"]["model"][1]
    observed_sd = marginals["donor_only"]["micro_time"]["data"][1]

    # The model reproduces the photons' own shot noise …
    assert shot_noise_sd == pytest.approx(0.322, abs=0.02)
    assert model_sd == pytest.approx(shot_noise_sd, rel=0.12)
    # … and the measurement is genuinely broader than shot noise, which is real
    # heterogeneity rather than a deficiency of the model.
    assert observed_sd > shot_noise_sd * 1.3


def test_the_model_does_not_broaden_itself_to_fit(marginals):
    """The failure that matters: a model wide enough to swallow real structure.

    The FRET population is broader than shot noise. That excess is the signal — a
    distribution of distances, or exchange. A forward model that reproduced it
    *without* being given any such structure would be fitting width with something
    that is not width, and every later dynamics result would be built on it.
    """
    fret = marginals["fret"]
    assert fret["ratio"]["model"][1] < fret["ratio"]["data"][1]
    assert fret["ratio"]["data"][1] / fret["ratio"]["model"][1] > 1.2


# ──────────────────────────────────────────────────────────────────────────────
# The compression is free
# ──────────────────────────────────────────────────────────────────────────────
def test_binning_the_nuisance_measure_costs_no_width(data, model):
    """Compressing D12 onto a grid must not narrow the predicted cloud.

    The histogram source's whole claim is that its cost does not grow with the
    number of bursts, because the bursts enter only through the binned nuisance
    measure. If binning narrowed the cloud, that speed would be bought with exactly
    the quantity the milestone tests.
    """
    axes = data.axes
    micro_c = 0.5 * (axes.micro_time_edges[:-1] + axes.micro_time_edges[1:])
    measure = data.nuisance

    widths = []
    for binned in (
        measure.binned(n_signal_bins=24, n_span_bins=6),
        measure.binned(n_signal_bins=200, n_span_bins=16),
        (
            np.ones(len(measure)),
            measure.signal.astype(float),
            [measure.spans[:, 0], measure.spans[:, 1]],
        ),
    ):
        data.binned = binned
        predicted = model.histogram(data)
        widths.append(_moments(predicted.sum(axis=0), micro_c)[1])

    coarse, fine, unbinned = widths
    assert coarse == pytest.approx(unbinned, rel=0.01)
    assert fine == pytest.approx(unbinned, rel=0.01)
