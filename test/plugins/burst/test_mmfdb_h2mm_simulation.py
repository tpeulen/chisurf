"""H2MM on MMFDB with simulated ground truth.

Simulates a two-state smFRET dataset with tttrlib (so the FRET efficiencies are
known), stores it in a live demo MMFDB server, and checks that the guided
``BurstWorkflow`` recovers the defined states — exercising the analysis modes
(engines, model-selection criteria) and the H2MM plot methods.

The same flow is walked interactively in
``chisurf/plugins/burst/burst_h2mm/examples/H2MM_02_MMFDB_GroundTruth.ipynb``.
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

# The workflow needs the compiled TTTR reader (with the 0.27 simulator) and MMFDB.
tttrlib = pytest.importorskip("tttrlib")
pytest.importorskip("mmfdb")

if not hasattr(tttrlib, "SimEngine"):
    pytest.skip("tttrlib build lacks the SimEngine simulator", allow_module_level=True)

from chisurf.plugins.burst.burst_analysis.api import BurstWorkflow  # noqa: E402

GROUND_TRUTH = (0.25, 0.75)


@pytest.fixture(scope="module")
def analyzed(tmp_path_factory):
    """Simulate, register, select bursts, and fit H2MM once for the module."""
    wf = BurstWorkflow.demo(workdir=tmp_path_factory.mktemp("h2mm_sim"))
    sim = wf.simulate(fret=GROUND_TRUTH, exchange_rate=2.0, seed=12345)
    bursts = wf.select_bursts(sim.handle, setup=sim.setup, min_photons=20)
    h2mm = bursts.h2mm(states=(1, 2, 3))
    try:
        yield wf, sim, bursts, h2mm
    finally:
        wf.close()


def test_simulation_records_ground_truth(analyzed):
    """simulate() stores a dataset in MMFDB and reports the defined truth."""
    _, sim, _, _ = analyzed
    assert isinstance(sim.handle, str) and sim.handle
    assert sim.truth.n_states == 2
    assert np.allclose(np.sort(sim.truth.fret), GROUND_TRUTH)


def test_h2mm_recovers_the_simulated_states(analyzed):
    """H2MM recovers the two simulated FRET efficiencies."""
    _, _, bursts, h2mm = analyzed
    assert len(bursts) > 100
    assert h2mm.n_states == 2
    assert np.allclose(np.sort(h2mm.fret), GROUND_TRUTH, atol=0.07)


def test_model_selection_scan_is_exposed(analyzed):
    """The model-selection scan is available as a table."""
    _, _, _, h2mm = analyzed
    # The table is a tttrlib DataStore, not a frame: its column names live on
    # `.names` (`.columns` is the list of Column objects).
    assert list(h2mm.scan.names) == ["n_states", "loglik", "bic", "icl"]
    assert set(h2mm.scan["n_states"]) == {1, 2, 3}


def test_analysis_modes_agree(analyzed):
    """Both engines and both criteria recover the same two states."""
    _, _, bursts, _ = analyzed
    for criterion in ("bic", "icl"):
        assert bursts.h2mm(states=(1, 2, 3), criterion=criterion).n_states == 2
    for engine in ("em", "em-float32"):
        fret = np.sort(bursts.h2mm(states=(2,), engine=engine).fret)
        assert np.allclose(fret, GROUND_TRUTH, atol=0.07)


def test_plot_methods_return_axes(analyzed):
    """Every H2MM plot helper draws onto and returns an Axes."""
    _, _, _, h2mm = analyzed
    for method in (
        h2mm.plot_states,
        h2mm.plot_model_selection,
        h2mm.plot_transitions,
        h2mm.plot_dwell_times,
    ):
        ax = method()
        assert ax is not None
