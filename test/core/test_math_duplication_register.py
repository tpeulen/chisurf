"""PRD-122: two rows of the phase-4 duplication register, closed or not.

Richardson-Lucy (``core/math/linalg`` + ``core/math/optimization``) had a
generic matrix-operator implementation with zero callers anywhere in the
tree and no faithful engine counterpart (``tttrlib.richardson_lucy_2d/3d``
assume a translation-invariant image/PSF pair, not an arbitrary dense
operator matrix) -- deleted rather than forwarded. This guards the deletion.

The ``models/tcspc/nusiance.py`` ``"full"``-mode convolution
(``np.convolve(data, irf_y, mode="full")[:n_points]``) is the opposite
finding: it is live (``parse`` and ``av_decay``
models all pass ``mode="full"``), and the only generic two-array
convolution primitive tttrlib exposes -- ``sconv``, already wrapped as
:func:`chisurf.core.fluorescence.tcspc.convolve.convolve_decay` -- computes
a *different* integral (trapezoidal, half-weighting the two ends of each
partial sum) than the plain discrete convolution ``np.convolve`` performs.
Forwarding would silently move every fit that uses ``"full"`` mode, so this
row stays open pending an owner decision (see PRD-105's decisions list) --
this test pins the current numpy behaviour and records the size of the
mismatch so nobody has to re-derive it.
"""

from __future__ import annotations

import numpy as np
import pytest
import scipy.stats

import chisurf.core.math.linalg
import chisurf.core.math.optimization
from chisurf.core.curve import Curve
from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.tcspc.lifetime import LifetimeModel

X = np.arange(64, dtype=float)


# --------------------------------------------------------------- Richardson-Lucy


def test_the_generic_matrix_richardson_lucy_duplicate_is_gone():
    """``solve_richardson_lucy`` is deleted from both in-tree copies.

    Guards against the dead duplicate growing back: zero callers were found
    anywhere in the tree (only the two copies called each other), and the
    named engine owner, ``tttrlib.richardson_lucy_2d/3d``, does not accept
    an arbitrary dense operator matrix, so there is no version of this
    function that could be a faithful forward. The one Richardson-Lucy
    implementation left in the tree is
    :func:`chisurf.core.fluorescence.imaging.restoration.richardson_lucy`,
    already ``tttrlib``-backed (pinned against scikit-image in
    ``test/core/test_restoration.py``).
    """
    assert not hasattr(chisurf.core.math.linalg, "solve_richardson_lucy")
    assert not hasattr(chisurf.core.math.optimization, "solve_richardson_lucy")


def test_the_deleted_algorithm_is_reproducible_for_the_record():
    """Reproduce the deleted numpy algorithm's own reference case.

    Not a call into chisurf any more -- the function is gone -- but a
    provenance record: if a *matrix-operator* Richardson-Lucy is ever needed
    again (as opposed to the image/PSF form the engine already covers), this
    is the exact math that used to live at ``math/linalg.solve_richardson_lucy``
    plus ``math/optimization.solve_richardson_lucy``'s transpose-and-seed
    wrapper, so a reimplementation can be checked against it instead of
    against nothing.
    """
    n = 16
    # A banded row-stochastic (blur-like) operator -- the shape "point-spread
    # matrix" naming implies, and the shape Richardson-Lucy is designed to
    # invert. An arbitrary dense matrix (no blur structure) does not
    # necessarily converge in a few hundred iterations; this one does.
    kernel = np.array([0.1, 0.2, 0.4, 0.2, 0.1])
    half = kernel.size // 2
    p_op = np.zeros((n, n))
    for i in range(n):
        for j, kv in enumerate(kernel):
            idx = i + j - half
            if 0 <= idx < n:
                p_op[i, idx] = kv
    p_op /= p_op.sum(axis=1, keepdims=True)

    truth = np.full(n, 0.05)
    truth[6], truth[7], truth[9] = 1.05, 0.65, 0.35
    d = p_op @ truth

    # math/optimization.solve_richardson_lucy(A, d, x0, max_iter):
    #     A = A.T; u = ones(n_i) if x0 is None else copy(x0)
    #     u = math/linalg.solve_richardson_lucy(A, u, d, max_iter)
    # math/linalg.solve_richardson_lucy(p, u, d, max_iter):
    #     for _ in range(max_iter): c = p @ u; u = u * (d / c @ p)
    a = p_op.T
    u = np.ones(n)
    resid_before = np.linalg.norm(a @ u - d)
    for _ in range(500):
        c = a @ u
        u = u * (d / c @ a)
    resid_after = np.linalg.norm(a @ u - d)

    assert resid_after < 1e-2 * resid_before
    np.testing.assert_allclose(u, truth, atol=0.02)


# --------------------------------------------------------- convolution straggler


def _convolve():
    """A `Convolve` on a 64-channel decay carrying a wide, shifted IRF.

    Same fixture shape as ``test/tcspc/test_convolve_do_convolution.py``.
    """
    data = DataCurve(x=X, y=1000.0 * np.exp(-X / 4.0))
    fit = Fit(model_class=LifetimeModel, data=data)
    convolve = fit.model.convolve
    convolve._irf = Curve(x=X, y=scipy.stats.norm.pdf(X, loc=5.0, scale=1.0))
    convolve._irf_start.value = 0.0
    convolve._irf_stop.value = float(len(X))
    convolve._stop.value = float(len(X))
    return convolve


def test_full_mode_convolution_is_pinned():
    """Pin ``nusiance.py``'s ``"full"``-mode ``np.convolve`` output.

    Guards the exact numbers ``parse``/``av_decay``
    models fit against, in case a future change (e.g. a forward to an
    engine kernel) is made without re-deriving this parity check.
    """
    convolve = _convolve()
    given = np.exp(-X / 2.0)

    decay = convolve.convolve(given, mode="full")

    # Reproduce nusiance.py's own normalisation of the IRF exactly (resize to
    # the data shape, normalise to unit sum) and the raw numpy computation it
    # runs at line ~945, so this test fails the moment either changes.
    irf_y = np.resize(convolve._irf.y, X.shape)
    irf_y = irf_y / irf_y.sum()
    n_points = irf_y.shape[0]
    expected = np.convolve(given, irf_y, mode="full")[:n_points]

    # Not bit-exact: the model path caches ``irf_y`` (see nusiance.py's
    # ``_irf_y_cache``) while this recomputes it, and float summation order
    # differs between the two -- both are float64, so tight is still tight.
    np.testing.assert_allclose(decay, expected, rtol=1e-12, atol=1e-15)


def test_sconv_is_not_a_drop_in_for_full_mode_np_convolve():
    """The only generic engine convolution primitive is not a faithful forward.

    ``tttrlib.sconv`` (wrapped as
    :func:`chisurf.core.fluorescence.tcspc.convolve.convolve_decay`) computes
    a trapezoidal-rule discrete convolution -- it half-weights the two ends
    of each partial sum -- while ``nusiance.py``'s ``"full"`` mode computes a
    plain (rectangular) discrete convolution via ``np.convolve``. They are
    different integrals of the same physical quantity, not two spellings of
    one algorithm, so forwarding ``"full"`` mode to ``sconv`` would silently
    move every fit built on ``parse`` or ``av_decay`` -- this is why that forward was not made in
    PRD-122; it needs an owner decision, the same way the ``i0`` digit and
    ``distance_between_gaussian`` rows do.

    This test documents the size of the mismatch (not a tight-tolerance
    match, deliberately) so nobody re-derives it by hand and so a future
    attempt to swap ``sconv`` in silently trips this assertion instead of
    landing quietly.
    """
    pytest.importorskip("tttrlib")
    from chisurf.core.fluorescence.tcspc.convolve import convolve_decay

    rng = np.random.default_rng(1)
    n = 32
    decay = np.zeros(n)
    decay[0] = 1.0
    for i in range(1, n):
        decay[i] = decay[i - 1] * np.exp(-0.3)
    irf = np.zeros(n)
    irf[2:6] = rng.random(4) + 0.1
    irf /= irf.sum()

    rectangular = np.convolve(decay, irf, mode="full")[:n]
    trapezoidal = convolve_decay(decay, irf, start=0, stop=n, dt=1.0)

    # Not close at any reasonable tolerance -- e.g. index 2 differs by 2x
    # (half-weighted first nonzero term vs. the full term).
    assert not np.allclose(rectangular, trapezoidal, rtol=1e-3, atol=1e-9)
    max_rel_diff = np.max(
        np.abs(rectangular - trapezoidal) / np.maximum(np.abs(rectangular), 1e-12)
    )
    assert max_rel_diff > 0.1
