"""Accurate FRET on a simulated photon stream with declared parameters.

``test_accurate_fret.py`` feeds the estimators Poisson channel counts; this feeds
them *photons*. A tttrlib confocal simulation produces molecules diffusing
through a focus under two alternating lasers, with the correction factors baked
into the per-stream brightness and the donor decay taken from the same
Gaussian-broadened distance the static FRET line is built from. The whole chain
then runs as it would on a measurement — burst search, per-burst channel counts,
per-burst lifetime, automatic calibration — and is judged against the declared
truth.

That is a harder and more honest test: burst search clips bursts, the photon
numbers are small (~70 per burst), and the populations must be found in a cloud
that shot noise has smeared. The tolerances below are what the method actually
achieves there, measured across several seeds — not what it achieves on
noiseless input.
"""

from __future__ import annotations

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

if not hasattr(tttrlib, "SimEngine"):
    pytest.skip("tttrlib build lacks the SimEngine simulator", allow_module_level=True)

from tttrlib import apparent_es

from chisurf.core.fluorescence.burst.simulate import (  # noqa: E402
    STREAMS,
    SmfretParameters,
    simulate_smfret,
)
from chisurf.core.fluorescence.fret.accurate import auto_calibrate  # noqa: E402
from chisurf.core.fluorescence.fret.lines import static_fret_line  # noqa: E402

#: A two-population ALEX experiment with every factor declared.
PARAMETERS = SmfretParameters(
    efficiencies=(0.30, 0.75),
    gamma=0.65,
    alpha=0.08,
    beta=1.40,
    delta=0.06,
    tau_d0=4.0,
    linker_sigma=6.0,
    r0=52.0,
    n_photons=350_000,
    alex_period=0.1,
    seed=3,
)


@pytest.fixture(scope="module")
def experiment():
    """One simulated measurement, reused by every test in this module."""
    return simulate_smfret(PARAMETERS)


@pytest.fixture(scope="module")
def bursts(experiment):
    """Return the burst table of that measurement."""
    table = experiment.burst_table(min_photons=50)
    if table["i_dd"].size < 300:
        pytest.skip("the simulation produced too few bursts to calibrate")
    return table


# ---------------------------------------------------------------------------
# the simulation itself
# ---------------------------------------------------------------------------


def test_photon_streams_carry_the_declared_brightness(experiment):
    """The ALEX streams hold the photon ratios the parameters declare.

    The correction factors *are* these ratios, so this pins the ground truth
    itself: if the simulated streams drifted, every recovery test below would be
    measuring the wrong thing.
    """
    counts = experiment.photon_counts()
    assert counts["i_ad"] == 0  # no donor emission under acceptor excitation
    assert counts["i_dd"] > 10_000 and counts["i_aa"] > 10_000

    species = experiment.species
    stream = experiment.stream
    weights = np.asarray(PARAMETERS.population_sizes(), dtype=float)
    expected = PARAMETERS.stream_brightness()
    for index, entry in enumerate(expected):
        photons = species == index
        if not np.any(photons):
            continue
        dd = np.count_nonzero(photons & (stream == STREAMS["i_dd"]))
        da = np.count_nonzero(photons & (stream == STREAMS["i_da"]))
        if dd < 500 or entry["i_dd"] <= 0:
            continue
        # the DA/DD ratio of a species is fixed by the declared brightnesses
        assert da / dd == pytest.approx(entry["i_da"] / entry["i_dd"], rel=0.06), entry["name"]
    assert weights.size == len(expected)


def test_donor_decays_land_on_the_static_fret_line(experiment, bursts):
    """Each population's mean donor micro-time is the lifetime the line predicts.

    The mean arrival time of an IRF-free decay is its fluorescence-averaged
    lifetime, and the simulated decay is the one the static line integrates — so
    the simulated populations must sit on the line, which is what makes the
    lifetime-assisted calibration meaningful.
    """
    expected = PARAMETERS.expected_lifetimes()
    for index, tau_expected in enumerate(expected):
        selected = bursts["species"] == index
        if np.count_nonzero(selected) < 50 or not np.isfinite(tau_expected):
            continue
        tau = bursts["tau_f"][selected]
        tau = tau[np.isfinite(tau)]
        assert float(np.mean(tau)) == pytest.approx(tau_expected, abs=0.08), index


def test_burst_table_shape(bursts):
    """The burst table exposes the channels, the lifetime and the truth label."""
    for key in ("i_dd", "i_da", "i_aa", "tau_f", "n_photons", "duration", "species"):
        assert key in bursts and bursts[key].size == bursts["i_dd"].size
    assert np.all(bursts["n_photons"] >= 50)
    assert np.all(bursts["duration"] > 0)
    # both doubly labelled populations and both reference populations are present
    assert set(np.unique(bursts["species"])) >= {0, 1, 2, 3}


# ---------------------------------------------------------------------------
# recovering the declared parameters
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def calibration(bursts):
    """Automatic calibration of the simulated measurement."""
    line = static_fret_line(PARAMETERS.tau_d0, r0=PARAMETERS.r0, sigma=PARAMETERS.linker_sigma)
    return auto_calibrate(
        bursts["i_dd"],
        bursts["i_da"],
        bursts["i_aa"],
        tau_f=bursts["tau_f"],
        line=line,
        donor_lifetime=PARAMETERS.tau_d0,
        n_bootstrap=0,
    )


def test_reference_populations_are_found(calibration, bursts):
    """The donor-only and acceptor-only bursts are gated out of the data itself."""
    split = calibration.split
    truth = bursts["species"]
    assert np.count_nonzero(split.donor_only) > 50
    assert np.count_nonzero(split.acceptor_only) > 50
    # species 2 = donor-only, 3 = acceptor-only in the simulated truth
    assert np.mean(truth[split.donor_only] == 2) > 0.9
    assert np.mean(truth[split.acceptor_only] == 3) > 0.9
    assert np.mean(truth[split.fret] <= 1) > 0.95
    assert split.counts["fret_populations"] == 2


def test_leakage_and_direct_excitation_are_recovered(calibration):
    """Leakage and direct excitation come back from the found reference bursts."""
    assert calibration.factors["alpha"] == pytest.approx(PARAMETERS.alpha, abs=0.012)
    assert calibration.factors["delta"] == pytest.approx(PARAMETERS.delta, abs=0.010)


def test_detection_factor_is_recovered_by_both_routes(calibration):
    """The E-S fit and the static FRET line both find gamma, and agree.

    Neither is exact on ~70-photon bursts — burst-averaged E-S centres carry a
    shot-noise bias, which is why Hellenkamp's protocol asks for bright bursts —
    but the two are independent, so their agreement is the practical consistency
    check a user runs on a new sample.
    """
    gamma_es = calibration.gamma_estimates["es"]
    gamma_tau = calibration.gamma_estimates["lifetime"]
    assert gamma_es == pytest.approx(PARAMETERS.gamma, rel=0.08)
    assert gamma_tau == pytest.approx(PARAMETERS.gamma, rel=0.06)
    assert gamma_es == pytest.approx(gamma_tau, rel=0.10)


def test_excitation_flux_ratio_is_recovered(calibration):
    """The excitation-flux ratio comes back from the same E-S fit."""
    assert calibration.factors["beta"] == pytest.approx(PARAMETERS.beta, rel=0.05)


def test_efficiencies_are_recovered(calibration):
    """The accurate efficiencies match the simulated ones."""
    recovered = sorted(p["E"] for p in calibration.populations)
    assert len(recovered) == 2
    for value, expected in zip(recovered, sorted(PARAMETERS.efficiencies)):
        assert value == pytest.approx(expected, abs=0.03)


def test_populations_sit_on_the_static_line(calibration):
    """A static simulated sample lands on the static FRET line after calibration."""
    for population in calibration.populations:
        assert abs(population["deviation"]) < 0.04


def test_correction_beats_the_raw_proximity_ratio(calibration, bursts):
    """The uncorrected proximity ratio misses the truth; the accurate E does not.

    Note that a single population proves nothing: leakage and direct excitation
    push the raw ratio up while ``gamma < 1`` pushes it down, and at some
    efficiency the two happen to cancel (here almost exactly at ``E = 0.3``).
    Across the populations they do not, which is why the comparison is made on
    the whole set.
    """
    split = calibration.split
    raw = apparent_es(bursts["i_dd"], bursts["i_da"])["E"]
    truth = np.asarray(sorted(PARAMETERS.efficiencies))
    raw_errors, accurate_errors = [], []
    for index, expected in enumerate(truth):
        selected = split.fret & (split.fret_labels == index)
        if np.count_nonzero(selected) < 100:
            continue
        raw_errors.append(float(np.mean(raw[selected])) - expected)
        accurate = [p for p in calibration.populations if p["label"] == index]
        accurate_errors.append(accurate[0]["E"] - expected)
    assert len(raw_errors) == 2
    rms_raw = float(np.sqrt(np.mean(np.square(raw_errors))))
    rms_accurate = float(np.sqrt(np.mean(np.square(accurate_errors))))
    assert rms_accurate < 0.5 * rms_raw
    # the high-FRET population is where the uncorrected ratio is plainly wrong
    assert abs(raw_errors[1]) > 0.04
