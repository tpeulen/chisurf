"""The simulate -> real pipeline -> fit loop, on photons with known truth.

The photons come from the confocal simulator in the TTTR library — C++ written
for another purpose, with molecules diffusing through a focus and switching
conformation on the simulated clock — and go through the *same* burst tables,
reader and response estimation as a measurement. ChiSurf used to carry a second,
hand-rolled simulator so the model could be checked against a different route;
that route is now the other repository, which is a stronger separation than a
second file here ever was.

These are the gates the benchmark rests on. If the simulator's kinetics or the
folder it writes are wrong, every recovery number downstream is wrong too, and
looks fine.
"""
import pathlib
import tempfile

import numpy as np
import pytest

from chisurf.core.fluorescence.burst.simulate import (
    MFD_STREAMS,
    SmfretParameters,
    simulate_smfret,
)

pytestmark = pytest.mark.skipif(
    not hasattr(pytest.importorskip("tttrlib"), "SimEngine"),
    reason="the installed tttrlib has no SimEngine simulator",
)

#: A small polarized MFD measurement: two states, no corrections, fast to run.
MFD = dict(
    n_photons=60_000, seed=11, alex=False, polarized=True,
    efficiencies=(0.2, 0.8), donor_only=0.0, acceptor_only=0.0,
    gamma=1.0, alpha=0.0, beta=1.0, delta=0.0,
    concentration=1.0, brightness=300.0, background=0.0, rho=1.0,
)


def test_polarized_mode_emits_the_four_mfd_detectors():
    """Green and red, each split parallel/perpendicular, on the pipeline's channels."""
    sim = simulate_smfret(**MFD)
    found = {name: int(np.count_nonzero(sim.stream == ch))
             for name, ch in MFD_STREAMS.items()}
    assert all(count > 0 for count in found.values()), found

    # Equal populations at E=0.2/0.8 with no corrections put the raw proximity
    # ratio at the mean of the two efficiencies.
    green = found["g_par"] + found["g_perp"]
    red = found["r_par"] + found["r_perp"]
    assert red / (green + red) == pytest.approx(0.5, abs=0.05)


def test_the_polarization_split_follows_perrin():
    """The parallel/perpendicular ratio tracks r0/(1 + tau/rho), not a constant."""
    from chisurf.core.fluorescence.anisotropy.integrals import (
        perrin_steady_state_anisotropy,
    )

    for rho in (0.5, 4.0):
        sim = simulate_smfret(**{**MFD, "rho": rho})
        found = {name: int(np.count_nonzero(sim.stream == ch))
                 for name, ch in MFD_STREAMS.items()}
        ratio = found["g_par"] / found["g_perp"]
        # p_par/(1-p_par) = (1+2r)/(1-r) at G=1, l1=l2=0 -> invert for r
        measured = (ratio - 1.0) / (2.0 + ratio)
        tau = float(np.mean(sim.parameters.expected_lifetimes()))
        expected = perrin_steady_state_anisotropy(
            tau, rho, r0=sim.parameters.r0_fundamental
        )
        assert measured == pytest.approx(expected, rel=0.25), (rho, measured, expected)


def test_exchange_reaches_the_photons():
    """A molecule that switches conformation emits photons from both states.

    Guards the two conversions between chisurf's ``K[target, source]`` in Hz and
    the engine's row-major source->target per millisecond. Either mistake leaves a
    simulation that runs and is silently static, or a thousand times too fast.
    """
    purity = {}
    for rate in (0.0, 1_000.0, 20_000.0):
        matrix = None if rate == 0 else np.array([[0.0, rate], [rate, 0.0]])
        sim = simulate_smfret(**MFD, rate_matrix=matrix)
        keep = sim.species >= 0
        molecule, species = sim.molecule[keep], sim.species[keep]
        order = np.argsort(molecule, kind="stable")
        molecule, species = molecule[order], species[order]
        parts = np.split(species, np.flatnonzero(np.diff(molecule)) + 1)
        purity[rate] = float(np.mean([
            np.bincount(part, minlength=2).max() / part.size
            for part in parts if part.size >= 20
        ]))

    assert purity[0.0] == 1.0                       # static: never switches
    assert purity[1_000.0] < 0.95                   # exchange is visible
    assert purity[20_000.0] < purity[1_000.0]       # and grows with the rate


def test_the_irf_shifts_the_mean_micro_time_by_its_centre():
    """A Gaussian IRF convolves the decay rather than being ignored."""
    green = [MFD_STREAMS["g_par"], MFD_STREAMS["g_perp"]]

    def mean_micro(**changes):
        sim = simulate_smfret(**{**MFD, **changes})
        micro = np.asarray(sim.tttr.micro_times, dtype=float)
        return float(micro[np.isin(sim.stream, green)].mean()
                     * sim.parameters.microtime_resolution)

    bare = mean_micro()
    shifted = mean_micro(irf_centre=2.0, irf_width=0.12)
    assert shifted - bare == pytest.approx(2.0, abs=0.1)


def test_truth_bursts_are_single_molecule_transits():
    """The burst search a measurement cannot have: one transit, by definition."""
    sim = simulate_smfret(**MFD)
    bursts = sim.true_bursts(min_photons=20)
    assert len(bursts) > 20

    molecule, species = np.asarray(sim.molecule), np.asarray(sim.species)
    distinct = [
        len(set(molecule[a:b + 1][species[a:b + 1] >= 0].tolist()))
        for a, b in bursts
    ]
    # Two molecules can overlap in the focus; the point is that it is rare, so a
    # difference against searched bursts is the search's doing and not this.
    assert np.mean(np.asarray(distinct) == 1) > 0.9


@pytest.mark.parametrize("definition", ["truth", "search"])
def test_the_written_folder_reproduces_the_emitted_photons(tmp_path, definition):
    """Both burst routes write a folder the ordinary reader accepts, losing nothing.

    The per-detector columns are compared against the photons actually emitted in
    each span: a channel definition that is plausible but wrong makes everything
    downstream wrong and believable.
    """
    from chisurf.core.fluorescence.mfd.fit import load_mfd_data

    sim = simulate_smfret(**MFD)
    spans = (sim.true_bursts(min_photons=20) if definition == "truth"
             else sim.searched_bursts(min_photons=20))
    folder = sim.write_folder(tmp_path / definition, bursts=spans)

    data = load_mfd_data(folder, min_green_photons=20)
    preparation = data.preparation
    assert "green" in preparation.verified_channels
    assert "red" in preparation.verified_channels
    assert len(preparation) == len(spans)

    stream = np.asarray(sim.stream)
    green = [MFD_STREAMS["g_par"], MFD_STREAMS["g_perp"]]
    emitted = np.array([np.isin(stream[a:b + 1], green).sum() for a, b in spans])
    assert np.array_equal(emitted, preparation.counts[:, preparation.channel_index("green")])


def test_the_exchange_matrix_is_transposed_and_rescaled():
    """``K[target, source]`` in Hz becomes row-major source->target per millisecond."""
    params = SmfretParameters(
        efficiencies=(0.2, 0.8), donor_only=0.0, acceptor_only=0.0,
        rate_matrix=np.array([[0.0, 300.0], [700.0, 0.0]]),
    )
    flat = np.asarray(params.exchange_matrix_ms()).reshape(2, 2)
    # source 0 -> target 1 is K[1, 0] = 700 Hz = 0.7 / ms, and it lands in row 0.
    assert flat[0, 1] == pytest.approx(0.7)
    assert flat[1, 0] == pytest.approx(0.3)


def test_the_non_burst_photons_are_the_complement_of_the_analysis(tmp_path):
    """The response is estimated from the reverse of *this folder's* burst cut.

    Not from a fresh burst search at its own thresholds. Separating molecules from
    the empty acquisition is what the cut was for, so running a second one answers
    a different question: at other thresholds, bursts the analysis kept land back
    on the instrument's side of the line and their fluorescence is read as
    response. Every photon in a burst table row must be excluded, and every photon
    outside one kept.
    """
    from chisurf.core.fluorescence.mfd.fit import load_mfd_data, non_burst_masks

    sim = simulate_smfret(**MFD)
    spans = sim.searched_bursts(min_photons=20)
    folder = sim.write_folder(tmp_path / "complement", bursts=spans)
    preparation = load_mfd_data(folder, min_green_photons=20).preparation

    masks = non_burst_masks(preparation)
    assert len(masks) == 1
    mask = next(iter(masks.values()))
    assert mask.size == np.asarray(sim.stream).size

    inside = np.zeros(mask.size, dtype=bool)
    for a, b in spans:
        inside[a:b + 1] = True
    assert np.array_equal(mask, ~inside)
    # And it is a real split, not everything on one side.
    assert 0 < int(mask.sum()) < mask.size


@pytest.mark.slow
@pytest.mark.parametrize("rate", [1000.0, 5000.0])
def test_photons_do_not_sample_a_burst_uniformly_in_time(rate):
    """The photon-weighted state fraction is not the time-weighted one.

    Both forward models — chisurf's closed-form path and the transcribed Sim2D
    Monte Carlo — hand a burst's photons out over the states in proportion to the
    *time* spent in each. A molecule is brightest at the centre of its transit,
    so its photons over-sample whichever state it held then, and the effective
    averaging window is shorter than the burst's first-to-last-photon span.

    The consequence is a systematically **low** exchange rate: the observed
    histogram is less averaged than the model predicts at the true rate, and the
    fit compensates by lowering it. Measured at −20% (1 kHz) to −33% (5 kHz) with
    a declared instrument response, identically in both engines — which is why
    their agreement never exposed it.

    This test pins the mechanism rather than the bias, because the mechanism is
    what a fix has to address: time-weighted occupancy must track the closed form,
    and photon-weighted occupancy must sit measurably above it.
    """
    from chisurf.core.fluorescence.mfd.occupation import two_state_occupation_variance

    matrix = np.array([[0.0, rate / 2.0], [rate / 2.0, 0.0]])
    sim = simulate_smfret(**{**MFD, "n_photons": 300_000, "donor_only": 0.05},
                          rate_matrix=matrix)
    species = np.asarray(sim.species)
    molecule = np.asarray(sim.molecule)
    resolution = float(sim.tttr.header.macro_time_resolution)
    macro = np.asarray(sim.tttr.macro_times, dtype=float) * resolution

    photon_f, time_f, expected = [], [], []
    for a, b in sim.true_bursts(min_photons=20):
        state, who = species[a:b + 1], molecule[a:b + 1]
        real = state >= 0
        if real.sum() < 20 or len(set(who[real].tolist())) != 1:
            continue
        state, times = state[real], macro[a:b + 1][real]
        if np.any(state == 2):  # a donor-only molecule has nothing to exchange
            continue
        gaps = np.diff(times)
        if gaps.sum() <= 0:
            continue
        photon_f.append(float((state == 0).mean()))
        time_f.append(float(gaps[state[:-1] == 0].sum() / gaps.sum()))
        # Var(f | T) is convex in T, so the closed form has to be averaged over the
        # durations actually seen, not evaluated at their mean.
        expected.append(two_state_occupation_variance(matrix, float(times[-1] - times[0]))[1])

    assert len(photon_f) > 500
    reference = float(np.mean(expected))
    by_time = float(np.var(time_f))
    by_photon = float(np.var(photon_f))

    # Neither number is asserted against the closed form tightly, because the
    # time-weighted estimate is itself photon-limited: a dwell's trailing gap is
    # credited to it, which inflates it a little and more so when the exchange is
    # fast. What is asserted is the *contrast*, which is the claim — time-weighted
    # occupancy tracks the closed form, photon-weighted occupancy does not.
    assert by_time == pytest.approx(reference, rel=0.2)
    assert abs(by_time - reference) < 0.5 * abs(by_photon - reference)
    assert by_photon > by_time


@pytest.mark.slow
def test_the_photon_weighted_window_recovers_the_generating_rate():
    """The end of the chain: a known exchange rate, and what the fit gives back.

    Everything but the rate is pinned at truth, so the one free parameter has
    nowhere to hide what the model gets wrong. With the occupation law taking the
    burst's span as its averaging window the answer is 33% low; with the window
    the photons actually measure it is within a few percent.
    """
    import numpy as np
    from scipy.optimize import minimize_scalar

    from chisurf.core.fluorescence.mfd.fit import MfdKineticModel, load_mfd_data
    from chisurf.core.fluorescence.mfd.patterns import FretState, Optics

    true_rate = 5000.0
    matrix = np.array([[0.0, true_rate / 2.0], [true_rate / 2.0, 0.0]])
    sim = simulate_smfret(
        **{**MFD, "n_photons": 300_000, "donor_only": 0.05, "background": 0.02,
           "brightness": 400.0, "irf_centre": 1.0, "irf_width": 0.1},
        rate_matrix=matrix,
    )
    folder = sim.write_folder(pathlib.Path(tempfile.mkdtemp()) / "rate",
                              bursts="truth", stem="rate")
    data = load_mfd_data(folder, min_green_photons=20)

    optics = Optics(r0=52.0, tau_d0=4.0, sigma=6.0, gamma=1.0, alpha=0.0, delta=0.0)
    states = [FretState(distance=d, name=n)
              for d, n in zip((66.2, 39.3), ("low", "high"))]

    def recover():
        def objective(log_rate):
            rate = float(np.exp(log_rate))
            model = MfdKineticModel(
                optics=optics, states=states, populations=[0.5, 0.5],
                donor_only=0.05,
                rate_matrix=np.array([[0.0, rate / 2.0], [rate / 2.0, 0.0]]),
            )
            return float(np.sum(model.score(data, mask_empty_model=False).residuals ** 2))

        return float(np.exp(minimize_scalar(
            objective, bounds=(np.log(200.0), np.log(40000.0)),
            method="bounded", options={"xatol": 5e-3}).x))

    recovered = recover()

    # Close, and without overshooting into invented dynamics. Taking the burst's
    # span as the averaging window instead put this at 0.67x the truth; that
    # assumption is gone rather than switchable, so what is asserted here is the
    # result and not the comparison.
    assert 0.85 * true_rate < recovered < 1.15 * true_rate


@pytest.mark.slow
def test_exchange_builds_a_dynamic_bridge_off_the_static_line():
    """Exchange must put bursts *between* the states, and off the line joining them.

    The gate the recovery numbers rest on. A static mixture puts every burst on
    the static FRET line and leaves the middle of the ratio axis to shot-noise
    stragglers; if the simulator only shifted the populations without populating
    the space between them, the exchange rate would not be identifiable from a 2D
    histogram at all and every recovered rate would be luck.

    Two things are asserted, and the second is the one that is easy to fake:

    * the middle of the ratio axis fills as the rate rises;
    * the bursts there sit **above** the chord joining the two populations. A
      burst caught mid-exchange has donor photons from both states, and their
      mean delay is dominated by the long-lifetime one, so it is longer than
      linear interpolation between the endpoints. A bridge that lay *on* the
      chord would mean the micro times were being mixed by occupancy rather than
      by donor-photon share.
    """
    from chisurf.core.fluorescence.mfd.fit import load_mfd_data
    from chisurf.core.fluorescence.mfd.histogram import HistogramAxes

    axes = HistogramAxes.default(n_ratio=48, n_micro_time=48,
                                 micro_time_range=(0.5, 6.5))
    ratio = 0.5 * (axes.ratio_edges[:-1] + axes.ratio_edges[1:])
    micro = 0.5 * (axes.micro_time_edges[:-1] + axes.micro_time_edges[1:])
    middle = (ratio > 0.35) & (ratio < 0.65)
    root = pathlib.Path(tempfile.mkdtemp())

    filled = {}
    for rate in (0.0, 1000.0):
        matrix = None if rate == 0 else np.array([[0.0, rate / 2], [rate / 2, 0.0]])
        sim = simulate_smfret(
            **{**MFD, "n_photons": 300_000, "donor_only": 0.05,
               "background": 0.02, "brightness": 400.0,
               "irf_centre": 1.0, "irf_width": 0.1},
            rate_matrix=matrix,
        )
        folder = sim.write_folder(root / f"r{int(rate)}", bursts="truth",
                                  stem=f"r{int(rate)}")
        counts = load_mfd_data(folder, axes=axes,
                               min_green_photons=20).observed.counts
        column = counts.sum(axis=1)
        filled[rate] = float(column[middle].sum() / column.sum())

        if rate:
            mean = np.where(column > 0,
                            (counts * micro[None, :]).sum(axis=1)
                            / np.maximum(column, 1), np.nan)
            low, high = ratio < 0.15, ratio > 0.85
            ends = (np.nanmean(mean[low]), np.nanmean(mean[high]))
            span = (np.nanmean(ratio[low]), np.nanmean(ratio[high]))
            chord = ends[0] + (ratio - span[0]) * (ends[1] - ends[0]) / (
                span[1] - span[0])
            assert np.nanmean((mean - chord)[middle]) > 0.1

    assert filled[0.0] < 0.05          # static: the middle is empty
    assert filled[1000.0] > 0.20       # exchange fills it


def test_the_declared_response_is_the_one_that_was_simulated():
    """``true_responses`` must describe the photons, not a plausible reconstruction.

    It exists so a fit can be handed the instrument instead of estimating it, which
    makes it the reference every "is the estimate contaminated?" measurement is read
    against. A response that merely looks right would shift those conclusions
    silently, so both halves are checked against the stream itself: the response's
    first moment against the declared pulse centre, and its background rate against
    a molecule-free run.
    """
    sim = simulate_smfret(
        **{**MFD, "n_photons": 20_000, "donor_only": 0.0, "concentration": 1e-9,
           "brightness": 1e-6, "background": 0.02,
           "irf_centre": 1.0, "irf_width": 0.1},
    )
    responses = sim.true_responses()
    assert set(responses) == set(sim.detectors())

    green = responses["green"]
    irf = np.asarray(green.irf, dtype=float)
    times = np.arange(irf.size) * green.dt
    assert float((irf * times).sum() / irf.sum()) == pytest.approx(1.0, abs=0.01)

    # Every photon here is background, so its rate is measurable directly.
    resolution = float(sim.tttr.header.macro_time_resolution)
    macro = np.asarray(sim.tttr.macro_times, dtype=float) * resolution
    duration = float(macro[-1] - macro[0])
    stream = np.asarray(sim.stream)
    for name in ("green", "red"):
        channels = sim.detectors()[name]["chs"]
        measured = float(np.isin(stream, channels).sum()) / duration
        assert measured == pytest.approx(responses[name].background_rate, rel=0.15)
