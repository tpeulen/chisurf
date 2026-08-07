"""End-to-end test of the guided MMFDB burst workflow facade.

Exercises :class:`BurstWorkflow` — the one-line-per-step interface a bench
scientist uses — against a live throwaway MMFDB server, including its general
knobs: multi-dataset registration, a declarable detector :class:`Setup`, and a
selectable burst-search method feeding BVA and photon-by-photon H2MM.

The same flow is walked interactively in
``modules/mmfdb/examples/mmfdb_00_overview.ipynb``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import column_names, numeric_column

import chisurf

# The workflow needs the compiled TTTR reader and the standalone MMFDB package.
pytest.importorskip("tttrlib")
pytest.importorskip("mmfdb")

from chisurf.plugins.burst.burst_analysis.api import (  # noqa: E402
    BurstWorkflow,
    Detector,
    Setup,
)

DATA_DIR = (
    Path(chisurf.__file__).resolve().parent
    / "plugins"
    / "burst"
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
)
DATA_FILES = [DATA_DIR / f"m00{i}.spc" for i in range(3)]


@pytest.fixture()
def workflow(tmp_path):
    """Yield a guided workflow backed by a private demo MMFDB server."""
    wf = BurstWorkflow.demo(workdir=tmp_path)
    try:
        yield wf
    finally:
        wf.close()


def test_register_returns_a_handle(workflow):
    """Registering a dataset yields a non-empty handle (object UUID)."""
    handle = workflow.register(DATA_FILES[0])
    assert isinstance(handle, str) and handle


def test_select_bursts_across_multiple_datasets(workflow):
    """Several registered datasets can be selected together in one call."""
    handles = workflow.register_all(DATA_FILES)
    assert len(handles) == len(DATA_FILES)

    bursts = workflow.select_bursts(handles, min_photons=20)
    assert len(bursts) > 0
    assert bursts.names == [f.name for f in DATA_FILES]
    assert "First Photon" in column_names(bursts.table)


def test_explicit_setup_matches_default(workflow):
    """The default setup and an equivalent explicit one agree."""
    handle = workflow.register(DATA_FILES[0])
    default = workflow.select_bursts(handle, min_photons=20)
    explicit = workflow.select_bursts(
        handle, setup=Setup.from_channels(green=(0, 8), red=(1, 9)), min_photons=20
    )
    assert len(default) == len(explicit)


def test_three_colour_setup_with_chosen_fret_pair(workflow):
    """A three-detector setup runs, with FRET reported on a chosen pair."""
    setup = Setup.from_channels(green=(0, 8), red=(1, 9), yellow=(2, 10))
    assert setup.names() == ["green", "red", "yellow"]

    handle = workflow.register(DATA_FILES[0])
    bursts = workflow.select_bursts(handle, setup=setup, min_photons=20)
    assert len(bursts) > 0
    # Pick the FRET pair explicitly; H2MM still models all three streams.
    assert 0.0 < bursts.bva("green", "red").mean_proximity_ratio < 1.0
    assert bursts.h2mm(states=(1, 2), donor="green", acceptor="red").n_states == 2


def test_microtime_gated_detectors(workflow):
    """Detectors can carry micro-time windows (PIE/ALEX gating)."""
    setup = Setup(
        detectors=[
            Detector("green", (0, 8), ((0, 4095),)),
            Detector("red", (1, 9), ((0, 2048),)),
        ],
        file_type="SPC-130",
    )
    handle = workflow.register(DATA_FILES[0])
    bursts = workflow.select_bursts(handle, setup=setup, min_photons=20)
    assert 0.0 < bursts.bva().mean_proximity_ratio < 1.0


def test_bad_setup_is_rejected():
    """A setup with fewer than two detectors is rejected."""
    with pytest.raises(ValueError):
        Setup.from_channels(green=(0, 8))
    with pytest.raises(ValueError):
        Setup(detectors=[Detector("green", (0, 8)), Detector("green", (1, 9))])


def test_bva_reports_a_sensible_proximity_ratio(workflow):
    """BVA returns a plausible mean proximity ratio and dynamic fraction."""
    handles = workflow.register_all(DATA_FILES)
    bursts = workflow.select_bursts(handles, min_photons=20)

    bva = bursts.bva()
    assert {"Proximity Ratio Mean", "Proximity Ratio Std"} <= set(column_names(bva.table))
    assert 0.0 < bva.mean_proximity_ratio < 1.0
    assert 0.0 <= bva.dynamic_fraction <= 1.0


def test_h2mm_recovers_low_and_high_fret_states(workflow):
    """H2MM recovers a low-FRET and a mid/high-FRET population."""
    handles = workflow.register_all(DATA_FILES)
    bursts = workflow.select_bursts(handles, min_photons=20)

    h2mm = bursts.h2mm(states=(1, 2))
    assert h2mm.n_states == 2
    assert h2mm.fret.shape == (2,)
    fret = np.sort(h2mm.fret)
    assert fret[0] < 0.15
    assert fret[-1] > 0.4
    assert "state" in h2mm.summary()
