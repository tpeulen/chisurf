"""The delegated 2D-FDC must keep returning the same numbers.

``flc_2d/core.py`` built the fluorescence-decay correlation matrices with numba;
they are now the photon library's (`fdc_scan_log`, `fdc_log`).
The reference is a recorded fixture, not a live comparison — a live comparison
becomes a skip the day the old code leaves, and a skip reads like a pass.

The fixture's outputs were re-recorded twice. On 2026-09-17 the linear matrices
only, when the slice that trims them was found one bin off its axis (see
``test_the_linear_matrix_trims_its_last_bin_as_the_reference_does``). Before
that, on 2026-08-16, when the log-axis tick
quantization was aligned to the reference implementation: the numba original
quantized the real-valued edges `t_Imax^(j/L) - 1` to *nearest*, while
`TK_Create2DFDC_04.m` compares the integer tick against the real-valued edge,
making the effective integer edge the *floor*. Verified by running the original
author's .m in Octave against the library (identical matrices at two factors
and three lags; nearest moved ~0.5% of pairs), and pinned permanently upstream
in tttrlib's `TestAgainstTheOriginalMatlab` against the original author's own
output. What is pinned *here* is that ChiSurf's call site still gets the
numbers the delegated path produces, including for the shapes that are easy to
get wrong.

Every assertion here is exact. The matrices are pair *counts*, accumulated as
``int64`` and summed across chunks, so there is no tolerance to argue about: a
difference of one is a difference.

The method-level checks — that the cross-peaks track the simulated exchange
rate, that a single state produces none — live upstream with the kernels
(`tttrlib test/python/fcs/test_fdc2d_simulation.py`), where the simulator is.
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


def test_the_linear_matrix_trims_its_last_bin_as_the_reference_does(recorded):
    """One bin fewer than ``lint_Imax``, and it is the padding bin that goes.

    `TK_Create2DFDC_04.m:170-172` returns bins ``1..lint_Imax-1`` of a matrix
    sized from the span *padded* by one linear bin, so the bin it drops lies
    past the gate. The library stores bin ``ceil(tau/f)`` at that index, which
    leaves index 0 empty: the reference's bins are ``[1:lint_imax]``. Until
    2026-09-17 ChiSurf sliced ``[:lint_imax-1]`` -- the right *size*, one bin
    off its axis -- which kept the empty row and dropped the last real bin: the
    654 (factor 3) and 974 (factor 5) pairs short of the brute-force 6443 that
    were once filed as a defect and then withdrawn as "the reference's trim".
    Aligned, every factor keeps all 6443, and the Octave run of the reference
    driver agrees bin for bin (``test_bootstrap.py``). The fixture's linear
    matrices were re-recorded through the aligned slice then.
    """
    from chisurf.plugins.fcs.flc_2d.core import create_2d_fdc_numba_int

    macro, micro = recorded["macro_single"], recorded["micro_single"]
    for i in range(int(recorded["n_single"])):
        dT, ddT, tmin, tmax, lint, logt = recorded[f"s_params_{i}"]
        lin, axis, _, _ = create_2d_fdc_numba_int(
            macro, micro, int(dT), int(ddT), 0, 10**12, int(tmin), int(tmax),
            int(lint), int(logt), True, 1,
        )
        span = int(tmax) - int(tmin)
        lint_imax = -(-(span + int(lint)) // int(lint))
        assert lin.shape == (lint_imax - 1, lint_imax - 1), f"factor {int(lint)}"
        assert len(axis) == lint_imax - 1
        if int(lint) in (2, 3, 5):  # the brute-force cases: nothing inside the gate is lost
            assert lin.sum() == 6443, f"factor {int(lint)}"


def test_both_kernels_put_the_log_matrix_on_the_same_axis(recorded):
    """The scan and the single-lag builder must agree, and follow the reference.

    `TK_Create2DFDC_04.m` derives `t_Imax` by rounding the span up to a whole
    number of *linear* bins and uses it for the *log* edges too, so the log axis
    depends on `lint_bin_factor`. The scan used `span + 1` unconditionally — that
    rule at factor 1 and a different axis above it, so the two entry points
    disagreed with each other and the scan disagreed with the paper.
    """
    import numpy as np

    from chisurf.plugins.fcs.flc_2d.core import _fdc_scan_log_kernel, create_2d_fdc_numba_int

    macro, micro = recorded["macro_single"], recorded["micro_single"]
    for i in range(int(recorded["n_single"])):
        dT, ddT, tmin, tmax, lint, logt = recorded[f"s_params_{i}"]
        _, _, log, _ = create_2d_fdc_numba_int(
            macro, micro, int(dT), int(ddT), 0, 10**12, int(tmin), int(tmax),
            int(lint), int(logt), True, 1,
        )
        scan = _fdc_scan_log_kernel(
            macro, micro, np.array([int(dT)], dtype=np.int64), np.int64(ddT),
            np.int64(tmin), np.int64(tmax), int(logt), 1, int(lint),
        )[0]
        np.testing.assert_array_equal(scan, log, err_msg=f"factor {int(lint)}")
