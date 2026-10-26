"""The background is measured outside the bursts and taken off every burst.

A burst of duration T collects ``rate x T`` uncorrelated photons per stream;
left in, equal background in both channels pulls a low-E population towards
E = 0.5. The simulator's ground truth (one population at E = 0.2, leakage
0.06, no direct excitation, equal detection) pins that the subtraction
removes that bias.
"""
import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")
if not hasattr(tttrlib, "SimEngine"):
    pytest.skip("tttrlib without the simulator", allow_module_level=True)

from chisurf.plugins.burst.fret_check import entry, jobs  # noqa: E402
from chisurf.plugins.burst.fret_check.detect import detect_experiment  # noqa: E402
from chisurf.plugins.burst.fret_check.pipeline import BurstSettings, analyse  # noqa: E402
from chisurf.plugins.burst.fret_check.sim import Scenario, simulate  # noqa: E402

TRUE_E = 0.2
#: The simulator's leakage (``sim._species``) and the neutral other factors:
#: with these, the corrected E of the population is TRUE_E by construction.
FACTORS = {"gamma": 1.0, "alpha": 0.06, "delta": 0.0, "beta": 1.0}


@pytest.fixture(scope="module")
def bursts():
    sc = Scenario("high background", excitation="cw", populations=((TRUE_E, 1.0),),
                  donor_only=0.0, background=2.0, brightness=300.0, duration_s=5.0, seed=7)
    data = simulate(sc)
    return analyse(data, detect_experiment(data), BurstSettings())


def test_background_counts_are_rate_times_duration(bursts):
    bg = jobs.background_counts(bursts)
    for k in bursts.counts:
        np.testing.assert_allclose(bg[k], bursts.background[k] * bursts.duration)
    assert bursts.background["DD"] > 1000 and bursts.background["DA"] > 1000


def test_subtracting_the_background_recovers_the_true_efficiency(bursts):
    on, _ = jobs.corrections(bursts, FACTORS, False, subtract_background=True)
    off, _ = jobs.corrections(bursts, FACTORS, False, subtract_background=False)
    e_on = float(np.median(jobs.unpack(on["E"])))
    e_off = float(np.median(jobs.unpack(off["E"])))
    assert abs(e_on - TRUE_E) < 0.01, e_on
    # Left in, the background biases E up (towards its own 0.5).
    assert e_off - TRUE_E > 0.012, e_off


def test_the_factors_reported_stay_the_four_scalars(bursts):
    _, used = jobs.corrections(bursts, FACTORS, False)
    assert used == FACTORS


def test_the_qc_entry_point_carries_the_verdict():
    result = entry.analyse(scenario="PIE 2c", key="verdict")
    verdict = entry.qc(scenario="PIE 2c", key="verdict")
    assert verdict["level"] in ("ok", "warn", "bad")
    assert verdict["level"] == jobs.qc_from_dict(result["qc"]).level
    assert verdict["checks"]
