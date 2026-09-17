"""The maximum-entropy design matrices, now TCSPCDecay's basis, against the numba recording.

``maxent_decay``'s solver once built its design matrix from three numba kernels,
then from tttrlib's builders; the MaxEnt analysis now runs in BFF
(``tcspc_maxent_lifetime`` / ``tcspc_maxent_fret``) and a column is the
instrument's own basis. ``test/data/numba_parity/maxent_tcspc.npz`` holds the
inputs and the matrices the numba solver produced, recorded before the first
port, and stays the reference.

What the comparison finds, and pins:

* A single excitation reproduces to rounding, up to one factor: BFF convolves a
  response of unit area, the recording the lamp as measured (background taken
  off), so every column differs by the lamp's area and by nothing else.
* Under periodic excitation the columns differ by about 1.6e-3 of their peak.
  The recorded convolution started the wrap-around tail of the earlier pulses
  at the lamp's first non-zero channel rather than at the start of the period;
  BFF's periodic kernel does not carry that offset.
* The tool's ``timeshift`` moves the lamp the other way from TCSPCDecay's; the
  solver translates, so the tool's numbers keep their meaning.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

pytest.importorskip("IMP.bff")

from chisurf.plugins.fluorescence_decay.maxent_decay.core import solver

_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[1] / "data" / "numba_parity" / "maxent_tcspc.npz"
)


@pytest.fixture(scope="module")
def reference():
    with np.load(_FIXTURE) as data:
        return {key: data[key] for key in data.files}


def _cases(reference):
    for i in range(int(reference["n_design"])):
        prefix = f"design{i}_"
        yield {k[len(prefix) :]: reference[k] for k in reference if k.startswith(prefix)}


def _design(reference, case):
    period = float(case["period"])
    common = dict(
        dt=float(case["dt"]),
        fitrange=(int(case["fitstart"]), int(case["fitstop"])),
        timeshift=float(case["timeshift"]),
        background=float(case["background"]),
        lamp_scatter=float(case["lamp_scatter"]),
        period=period if period > 0 else None,
        max_iter=5,
    )
    if str(case["kind"]) == "life":
        result = solver.solve_lifetime_mem(
            reference["decay"], reference["irf"], tau=case["tau"], irf_background=0.0, **common
        )
        lamp_background = 0.0
    else:
        result = solver.solve_fret_mem(
            reference["decay"],
            reference["irf"],
            R=case["R"],
            tau0=float(case["tau0"]),
            R0=float(case["R0"]),
            donly=case["donly"],
            x_donly=float(case["x_donly"]),
            irf_background=float(case["irf_background"]),
            **common,
        )
        lamp_background = float(case["irf_background"])
    lamp_area = float(np.clip(reference["irf"] - lamp_background, 0.0, None).sum())
    return (
        result["Fi"] * result["sigma"][:, None] * lamp_area,
        case["Fi"] * case["sigma"][:, None],
        result,
    )


def test_the_fixture_covers_both_axes_and_both_convolutions(reference):
    cases = list(_cases(reference))
    assert {str(c["kind"]) for c in cases} == {"life", "dist"}
    assert {float(c["period"]) for c in cases} == {0.0, 16.0}


@pytest.mark.parametrize("period, tolerance", [(0.0, 1e-12), (16.0, 2e-3)])
def test_the_basis_is_the_recorded_design_matrix(reference, period, tolerance):
    seen = 0
    for case in _cases(reference):
        if float(case["period"]) != period:
            continue
        seen += 1
        got, want, _ = _design(reference, case)
        assert got.shape == want.shape
        assert np.max(np.abs(got - want)) <= tolerance * np.max(np.abs(want)), str(case["kind"])
    assert seen == 3


def test_the_fitted_window_and_the_weights_are_the_recorded_ones(reference):
    for case in _cases(reference):
        _, _, result = _design(reference, case)
        np.testing.assert_array_equal(result["y"], case["y"])
        assert result["fitrange"] == (int(case["fitstart"]), int(case["fitstop"]))
        assert result["timeshift"] == pytest.approx(float(case["timeshift"]))
