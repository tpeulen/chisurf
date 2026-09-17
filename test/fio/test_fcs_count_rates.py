"""The mean count rate feeds the noise model, so getting it wrong reweights the fit.

Correlator files store the intensity trace as a *rate* per time bin. The mean
count rate is therefore the mean of that trace. Summing the trace and dividing
by the duration instead divides by the number of bins per unit time — a factor
that depends only on how the trace happened to be binned, and that silently
rescales every weight derived from it.

Two readers did exactly that, and the errors are measurable against values the
instruments themselves recorded.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

FCS = pathlib.Path(__file__).parent.parent / "data" / "fcs"


# ── Zeiss ConfoCor ────────────────────────────────────────────────────


@pytest.fixture()
def confocor():
    """Return the curves of the FCCS sample, keyed by correlation type."""
    import collections

    from chisurf.core.fio.fluorescence.fcs.confocor3 import read_zeiss_fcs

    path = FCS / "confocor3" / "Zeiss_Confocor3_LSM780_FCCS_HeLa_2015" / "017_cp_KIND+BFA.fcs"
    if not path.is_file():
        pytest.skip(f"no ConfoCor sample at {path}")

    by_type = collections.defaultdict(list)
    for record in read_zeiss_fcs(str(path)):
        by_type[record["correlation_type"]].append(record)
    return by_type


def test_a_cross_correlation_count_rate_is_the_mean_of_its_two_detectors(confocor):
    """The regression: it used to be 6.5 kHz for detectors running at 147 and 184.

    The cross-correlation branch summed the rate trace and divided by the
    acquisition time in milliseconds, so the result was low by the number of
    bins per millisecond — 25x on this file's 25.6 ms bins.
    """
    for repeat in range(4):
        ac1 = confocor["AC1"][repeat]["mean_count_rate"]
        ac2 = confocor["AC2"][repeat]["mean_count_rate"]
        for kind in ("CC12", "CC21"):
            cross = confocor[kind][repeat]["mean_count_rate"]
            assert cross == pytest.approx(0.5 * (ac1 + ac2), rel=1e-6), (
                f"{kind} repeat {repeat}: {cross} is not the mean of {ac1} and {ac2}"
            )


def test_the_cross_correlation_weights_match_the_shot_noise_of_the_same_photons(confocor):
    """A physical cross-check that needs no reference value.

    At short lag the correlation noise is shot-noise dominated, so the claimed
    error of a cross-correlation curve must be of the same order as that of the
    autocorrelations built from the same photons. With the count rate 25x too
    low it was ~20x too large instead.
    """

    def short_lag_error(record):
        lag = np.asarray(record["correlation_times"])
        weights = np.asarray(record["correlation_amplitude_weights"])
        band = (lag >= 1e-3) & (lag < 1e-1)
        return float(np.median(1.0 / weights[band]))

    auto = np.mean([short_lag_error(confocor[k][0]) for k in ("AC1", "AC2")])
    cross = short_lag_error(confocor["CC12"][0])
    assert 0.3 < cross / auto < 3.0, (
        f"cross-correlation error {cross:.3g} is not comparable to {auto:.3g}"
    )


# ── ALV correlator ────────────────────────────────────────────────────


def test_the_alv_fallback_agrees_with_the_rate_the_instrument_recorded():
    """One sample file records its own count rate; it is the ground truth.

    ``ALV-7004.ASC`` states 60.78 kHz. The mean of its trace gives 60.27, and
    the sum-over-duration the reader used to fall back to gives 30.25.
    """
    from chisurf.core.fio.fluorescence.fcs.asc_alv import openASC

    path = FCS / "asc" / "ALV-7004.ASC"
    if not path.is_file():
        pytest.skip(f"no ALV sample at {path}")

    data = openASC(str(path))
    recorded = data["Count rates"][0]
    trace = np.asarray(data["Trace"][0])
    seconds = trace[:, 0] / 1000.0
    rate = trace[:, 1]

    assert float(np.mean(rate)) == pytest.approx(recorded, rel=0.02)
    # The old expression is still wrong, which is what makes the fix
    # load-bearing rather than cosmetic.
    assert float(np.sum(rate) / seconds[-1]) != pytest.approx(recorded, rel=0.2)


def test_a_file_without_a_recorded_rate_takes_the_corrected_path():
    """``ALV-5000E-WIN.ASC`` has no count rate, so it exercises the fallback."""
    from chisurf.core.fio.fluorescence.fcs.asc_alv import openASC, read_asc

    path = FCS / "asc" / "ALV-5000E-WIN.ASC"
    if not path.is_file():
        pytest.skip(f"no ALV sample at {path}")

    assert openASC(str(path)).get("Count rates") is None, "this file must have no recorded rate"

    trace = np.asarray(openASC(str(path))["Trace"][0])
    expected = float(np.mean(trace[:, 1]))
    reported = read_asc(str(path))[0]["mean_count_rate"]

    assert reported == pytest.approx(expected, rel=1e-6)
    assert reported > 90.0, f"the old sum-over-duration gave about half this ({reported})"
