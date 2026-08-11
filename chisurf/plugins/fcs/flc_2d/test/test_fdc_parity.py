"""The delegated 2D-FDC must return what the numba kernels returned.

``flc_2d/core.py`` built the fluorescence-decay correlation matrices with numba;
they are now the photon library's (`fdc_scan_log`, `fdc_log`, tttrlib PRD-036).
The reference is a fixture recorded from the numba originals **before** they
were deleted — not a live comparison, which becomes a skip the day numba leaves
and a skip reads like a pass.

Every assertion here is exact. The matrices are pair *counts*, accumulated as
``int64`` and summed across chunks, so there is no tolerance to argue about: a
difference of one is a difference.

The method-level checks — that the cross-peaks track the simulated exchange
rate, that a single state produces none — live upstream with the kernels
(`tttrlib test/python/fcs/test_fdc2d_simulation.py`), where the simulator is.
What is pinned here is that ChiSurf's call site still gets the same numbers,
including for the shapes that are easy to get wrong.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

#: parents[5] is the repo root: test/ -> flc_2d/ -> fcs/ -> plugins/ ->
#: chisurf/ -> repo. Getting this wrong makes every test below skip, which
#: reads exactly like passing.
_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[5]
    / "test" / "data" / "numba_parity" / "flc_2d_fdc.npz"
)


@pytest.fixture(scope="module")
def recorded():
    """The recorded (input, output) pairs from the numba kernels."""
    # Not a skip: the fixture is committed beside this test, so its absence
    # means the path is wrong or the file was lost -- both of which a skip would
    # hide.
    assert _FIXTURE.is_file(), f"committed fixture is missing: {_FIXTURE}"
    with np.load(_FIXTURE) as data:
        return {k: data[k] for k in data.files}


def _scan_cases(recorded):
    for i in range(int(recorded["n_cases"])):
        ddT, tmin, tmax, logt_imax, n_chunks = recorded[f"params_{i}"]
        yield {
            "name": str(recorded["names"][i]),
            "macro": recorded[f"macro_{i}"], "micro": recorded[f"micro_{i}"],
            "lags": recorded[f"lags_{i}"], "ddT": int(ddT), "tmin": int(tmin),
            "tmax": int(tmax), "logt_imax": int(logt_imax),
            "n_chunks": int(n_chunks), "mats": recorded[f"mats_{i}"],
        }


def test_the_fixture_covers_the_shapes_that_are_easy_to_get_wrong(recorded):
    """A parity fixture of ordinary streams proves the easy half only."""
    names = {c["name"] for c in _scan_cases(recorded)}
    assert {"lag_inside_window", "narrow_gate", "empty_gate",
            "single_photon", "dense"} <= names
    totals = {c["name"]: int(c["mats"].sum()) for c in _scan_cases(recorded)}
    assert totals["empty_gate"] == 0 and totals["single_photon"] == 0
    assert totals["dense"] > 100_000, "no case with a heavy pair count"
    assert totals["lag_inside_window"] > 0, "the self-pair case counts nothing"


def test_the_scan_matches_the_numba_reference(recorded):
    """Same counts, every case, exactly."""
    from chisurf.plugins.fcs.flc_2d.core import _fdc_scan_log_kernel

    for c in _scan_cases(recorded):
        got = _fdc_scan_log_kernel(
            c["macro"], c["micro"], c["lags"], np.int64(c["ddT"]),
            np.int64(c["tmin"]), np.int64(c["tmax"]), c["logt_imax"], c["n_chunks"],
        )
        assert got.shape == c["mats"].shape, c["name"]
        np.testing.assert_array_equal(got, c["mats"], err_msg=c["name"])


def test_the_single_lag_builder_matches_the_numba_reference(recorded):
    """All four returned arrays, not just the log matrix."""
    from chisurf.plugins.fcs.flc_2d.core import create_2d_fdc_numba_int

    macro, micro = recorded["macro_single"], recorded["micro_single"]
    for i in range(int(recorded["n_single"])):
        dT, ddT, tmin, tmax, lint, logt = recorded[f"s_params_{i}"]
        lin, lint_axis, log, logt_axis = create_2d_fdc_numba_int(
            macro, micro, int(dT), int(ddT), 0, 10**12, int(tmin), int(tmax),
            int(lint), int(logt), True, 1,
        )
        np.testing.assert_array_equal(lin, recorded[f"s_lin_{i}"], err_msg=f"lin {i}")
        np.testing.assert_array_equal(lint_axis, recorded[f"s_lint_{i}"], err_msg=f"lint {i}")
        np.testing.assert_array_equal(log, recorded[f"s_log_{i}"], err_msg=f"log {i}")
        np.testing.assert_array_equal(logt_axis, recorded[f"s_logt_{i}"], err_msg=f"logt {i}")


def test_the_chunk_count_still_changes_nothing(recorded):
    """Integer counts summed across chunks: the partition cannot matter."""
    from chisurf.plugins.fcs.flc_2d.core import _fdc_scan_log_kernel

    c = next(x for x in _scan_cases(recorded) if x["name"] == "dense")
    reference = None
    for n_chunks in (1, 2, 5, 64):
        got = _fdc_scan_log_kernel(
            c["macro"], c["micro"], c["lags"], np.int64(c["ddT"]),
            np.int64(c["tmin"]), np.int64(c["tmax"]), c["logt_imax"], n_chunks,
        )
        if reference is None:
            reference = got
        np.testing.assert_array_equal(got, reference, err_msg=f"n_chunks={n_chunks}")


def test_a_gate_that_admits_nothing_returns_zeros_rather_than_raising(recorded):
    """Idle gating is a normal user action, not an error."""
    from chisurf.plugins.fcs.flc_2d.core import _fdc_scan_log_kernel

    c = next(x for x in _scan_cases(recorded) if x["name"] == "empty_gate")
    got = _fdc_scan_log_kernel(
        c["macro"], c["micro"], c["lags"], np.int64(c["ddT"]),
        np.int64(c["tmin"]), np.int64(c["tmax"]), c["logt_imax"], 1,
    )
    assert got.sum() == 0 and got.shape == c["mats"].shape
