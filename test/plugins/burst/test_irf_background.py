"""IRF + background extraction from the non-burst photons of a measurement.

Exercises :func:`chisurf.core.fluorescence.burst.extract_irf_background` on a real
single-molecule SPC file and its integration into the guided ``BurstWorkflow``
(``Bursts.irf_background`` / ``BurstWorkflow.estimate_irf_background``).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import chisurf

pytest.importorskip("tttrlib")

import tttrlib  # noqa: E402

from chisurf.core.fluorescence.burst import (  # noqa: E402
    extract_irf_background,
    extract_mle_irf_background,
    non_burst_mask,
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
SPC = DATA_DIR / "m000.spc"
DETECTORS = {"green": {"chs": [0, 8]}, "red": {"chs": [1, 9]}}


@pytest.fixture(scope="module")
def tttr():
    """Load one real single-molecule SPC measurement."""
    return tttrlib.TTTR(str(SPC))


def test_non_burst_mask_is_the_majority(tttr):
    """Most photons of a dilute sm measurement are background (non-burst)."""
    keep = non_burst_mask(tttr, min_photons=20)
    assert keep.dtype == bool
    assert keep.shape[0] == len(tttr)
    # Bursts are rare events; the non-burst photons dominate.
    assert keep.sum() > (~keep).sum()


def test_extract_returns_one_estimate_per_detector(tttr):
    """Each detector gets a background rate and a normalised IRF."""
    res = extract_irf_background(tttr, DETECTORS, min_photons=20)
    assert set(res) == set(DETECTORS)
    for det in res.values():
        # Background rate is a finite, non-negative kHz value.
        assert det.background_khz >= 0.0
        assert np.isfinite(det.background_khz)
        # IRF is a proper (unit-sum) distribution with a prompt inside the period.
        assert det.irf.shape == det.time_ns.shape
        assert det.irf.min() >= 0.0
        assert det.irf.sum() == pytest.approx(1.0, abs=1e-6)
        assert 0.0 <= det.prompt_ns <= det.time_ns[-1]
        # The non-burst photons are the ones used for the estimate.
        assert det.n_background_photons > det.n_burst_photons


def _far_tail_fraction(vv_vh: np.ndarray) -> float:
    """Fraction of the VV-half IRF mass sitting well past the prompt peak."""
    n = len(vv_vh) // 2
    vv = np.asarray(vv_vh[:n], dtype=float)
    pk = int(vv.argmax())
    total = float(vv.sum())
    return float(vv[pk + 15 :].sum()) / total if total > 0 else 0.0


def test_mle_irf_model_gaussian_fit_suppresses_fluorescent_tail(tttr):
    """The fitted Gaussian IRF must shed the fluorescent tail the raw prompt has.

    The non-burst prompt rides on a slow fluorescence tail; a Gaussian fitted to
    it cannot follow that tail, so the fitted-Gaussian IRF carries far less mass
    past the prompt than the raw experimental one. The switch must produce
    genuinely different IRFs.
    """
    keep = non_burst_mask(tttr, min_photons=20)
    out = {
        m: extract_mle_irf_background(tttr, DETECTORS, micro_time_binning=8, mask=keep, irf_model=m)
        for m in ("gaussian", "skewed", "experimental")
    }
    for m, res in out.items():
        assert set(res) == set(DETECTORS)
        irf = res["green"]["irf"]
        assert irf.ndim == 1 and irf.size % 2 == 0
        assert np.all(np.isfinite(irf)) and irf.min() >= 0.0 and irf.sum() > 0.0

    tails = {m: _far_tail_fraction(out[m]["green"]["irf"]) for m in out}
    # Fitted Gaussian sheds the tail; experimental keeps it.
    assert tails["gaussian"] < 0.5 * tails["experimental"]
    # 'experimental' is an alias for the raw baseline-subtracted prompt.
    exp = extract_mle_irf_background(
        tttr, DETECTORS, micro_time_binning=8, mask=keep, irf_model="raw"
    )
    np.testing.assert_allclose(exp["green"]["irf"], out["experimental"]["green"]["irf"])


def test_precomputed_mask_matches_internal_search(tttr):
    """Passing the non-burst mask explicitly reproduces the internal result."""
    keep = non_burst_mask(tttr, min_photons=20)
    a = extract_irf_background(tttr, DETECTORS, min_photons=20)
    b = extract_irf_background(tttr, DETECTORS, mask=keep)
    for name in DETECTORS:
        assert a[name].background_khz == pytest.approx(b[name].background_khz)
        np.testing.assert_allclose(a[name].irf, b[name].irf)


def test_bad_mask_length_raises(tttr):
    """A mask of the wrong length is rejected rather than silently misaligned."""
    with pytest.raises(ValueError):
        extract_irf_background(tttr, DETECTORS, mask=np.ones(5, dtype=bool))


def test_irf_prompt_is_a_real_peak(tttr):
    """The scatter-derived IRF has a localised prompt, not a flat baseline."""
    res = extract_irf_background(tttr, DETECTORS, min_photons=20)
    green = res["green"]
    # A genuine prompt peak concentrates the IRF well above a uniform baseline.
    assert green.irf.max() > 5.0 / green.irf.size


def test_workflow_irf_background_step(tmp_path):
    """The guided workflow exposes the non-burst IRF/background as one step."""
    pytest.importorskip("mmfdb")
    from chisurf.plugins.burst.burst_analysis.api import BurstWorkflow, Setup

    wf = BurstWorkflow.demo(workdir=tmp_path)
    try:
        setup = Setup.from_channels(green=(0, 8), red=(1, 9), file_type="SPC-130")
        handle = wf.register(SPC)
        result = wf.estimate_irf_background(handle, setup=setup, min_photons=20)
    finally:
        wf.close()

    assert set(result.per_detector) == {"green", "red"}
    assert set(result.background_khz) == {"green", "red"}
    table = result.table
    assert list(table["Detector"]) == ["green", "red"]
    assert (table["Background (kHz)"] >= 0.0).all()
    assert result.irf("green").sum() == pytest.approx(1.0, abs=1e-6)
