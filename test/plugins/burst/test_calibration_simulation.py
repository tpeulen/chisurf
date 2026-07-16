"""End-to-end calibration recovery on simulated bursts (known E + known gamma).

Simulates two static smFRET populations with tttrlib, baking a known detection
factor ``gamma`` into the counts (so the raw proximity ratio is gamma-distorted),
selects bursts through the guided ``BurstWorkflow``, and checks that the
three-cube correction with the known gamma recovers the true FRET efficiencies
while the uncorrected proximity ratio does not.

Walked interactively in
``chisurf/plugins/burst/burst_analysis/examples/FRET_Calibration.ipynb``.
"""

from __future__ import annotations

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")
pytest.importorskip("mmfdb")

if not hasattr(tttrlib, "SimEngine"):
    pytest.skip("tttrlib build lacks the SimEngine simulator", allow_module_level=True)

from chisurf.core.fluorescence.burst.es import corrected_es  # noqa: E402
from chisurf.plugins.burst.burst_analysis.api import BurstWorkflow  # noqa: E402

GROUND_TRUTH = (0.25, 0.75)
GAMMA = 1.6


@pytest.fixture(scope="module")
def analyzed(tmp_path_factory):
    """Simulate two gamma-distorted FRET populations; return sim + per-burst PR."""
    wf = BurstWorkflow.demo(workdir=tmp_path_factory.mktemp("calib_sim"))
    sim = wf.simulate(
        fret=GROUND_TRUTH, exchange_rate=0.0, gamma=GAMMA,
        n_photons=400_000, seed=2024,
    )
    bursts = wf.select_bursts(sim.handle, setup=sim.setup, min_photons=40)
    bva = bursts.bva("green", "red")
    pr = bva.table["Proximity Ratio Mean"].to_numpy(dtype=float)
    pr = pr[np.isfinite(pr)]
    try:
        yield sim, pr
    finally:
        wf.close()


def test_ground_truth_records_gamma(analyzed):
    """The simulation records the injected gamma."""
    sim, _ = analyzed
    assert sim.truth.gamma == pytest.approx(GAMMA)
    assert np.allclose(np.sort(sim.truth.fret), GROUND_TRUTH)


def test_corrected_proximity_ratio_recovers_true_efficiencies(analyzed):
    """Correcting the apparent proximity ratio with the known gamma recovers E.

    With a gamma-only correction the corrected efficiency depends only on the
    proximity ratio ``PR``: feeding ``green=1-PR``, ``red=PR`` into the three-cube
    correction gives ``E = PR / (PR + gamma*(1-PR))``.
    """
    _, pr = analyzed
    assert pr.size > 100

    e_app = pr  # apparent proximity ratio
    e_corr = corrected_es(1.0 - pr, pr, gamma=GAMMA)["E"]

    # Two static populations -> split at the apparent midpoint.
    lo = e_app < 0.5
    hi = ~lo
    assert lo.sum() > 20 and hi.sum() > 20

    corr_lo, corr_hi = e_corr[lo].mean(), e_corr[hi].mean()
    assert corr_lo == pytest.approx(0.25, abs=0.06)
    assert corr_hi == pytest.approx(0.75, abs=0.06)

    # The uncorrected proximity ratio is gamma-distorted (biased away from truth).
    app_lo, app_hi = e_app[lo].mean(), e_app[hi].mean()
    assert abs(app_lo - 0.25) > 0.03 or abs(app_hi - 0.75) > 0.03
