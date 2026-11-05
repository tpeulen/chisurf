"""The reference dye's IRF deconvolved in batches gives the numbers it gave one row at a time.

``richardson_lucy`` runs several rows at once (``_richardson_lucy_rows``: one FFT call per
step for all of them), the rotation's golden-section searches of every initial anisotropy step
side by side (``_golden_lockstep``), and the dye's binned decay is kept between the rotations a
search tries. None of that may change a bit: the batched transform is the row transform and
every other operation is per element or per row. Checked against the one-row implementations
these replaced (copied here as they were) and against the per-row compositions.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.fluorescence_decay.irf_estimator.core import extraction as ex
from test.fluorescence.test_irf_from_references import DT, N, _decay_of


# -- the one-row implementations the batched ones replaced, as they were ------------------ #
def _old_kernels(n, dt_ns, tau_ns, rho_ns, r0=ex.R0):
    n, dt = int(n), float(dt_ns)
    oversample = 32
    u = (np.arange(n * oversample) + 0.5) / oversample
    left = np.floor(u).astype(int)
    frac = u - left

    def binned(rate):
        f = np.exp(-rate * u * dt) * (dt / oversample)
        out = np.bincount(left, weights=f * (1.0 - frac), minlength=n + 1)
        out[1:] += np.bincount(left, weights=f * frac, minlength=n + 1)[:-1]
        return out[:n]

    decay = binned(1.0 / float(tau_ns))
    if rho_ns is None or rho_ns <= 0:
        return decay, decay.copy()
    rotating = float(r0) * binned(1.0 / float(tau_ns) + 1.0 / float(rho_ns))
    return decay + 2.0 * rotating, decay - rotating


def _old_rl(data, kernel, *, mask=None, iterations=None, floor=0.0, observed=None,
            max_iterations=ex.MAX_ITERATIONS):
    y = np.clip(np.asarray(data, dtype=float), 0.0, None)
    m = np.ones_like(y) if mask is None else np.asarray(mask, dtype=float)
    k = np.asarray(kernel, dtype=float)
    k = k / k.sum()
    kf = np.fft.rfft(k, y.size)
    kt = np.conj(kf)
    norm = np.fft.irfft(np.fft.rfft(m) * kt, y.size)
    norm = np.where(norm > 1e-12, norm, 1.0)
    x = np.full_like(y, max(float((y * m).sum()) / max(float(m.sum()), 1.0), 1e-12))
    inside = m > 0
    counts = (y + floor if observed is None else np.asarray(observed, dtype=float))[inside]
    history = []
    for it in range(1, int(iterations or max_iterations) + 1):
        model = np.maximum(np.fft.irfft(np.fft.rfft(x) * kf, y.size), 1e-12)
        x = x * np.fft.irfft(np.fft.rfft(m * y / model) * kt, y.size) / norm
        np.clip(x, 0.0, None, out=x)
        if iterations is None and it % 10 == 0:
            fit = np.fft.irfft(np.fft.rfft(x) * kf, y.size)[inside] + floor
            chi2r = float(np.mean((counts - fit) ** 2 / np.maximum(fit, 1.0)))
            history.append(chi2r)
            if chi2r <= 1.0 or (len(history) > 5 and history[-6] - chi2r < 1e-3 * chi2r):
                break
    return x


def _old_golden(f, a, b, tol):
    g = (np.sqrt(5.0) - 1.0) / 2.0
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d)
    while b - a > tol:
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = f(d)
    return 0.5 * (a + b)


def _dye(seed=7, tau=4.0, rho=0.2, photons=6e5, floor=200.0):
    rng = np.random.default_rng(seed)
    vv, vh = _decay_of(tau, rho=rho)
    total = vv.sum() + vh.sum()
    return (rng.poisson(vv / total * photons + floor).astype(float),
            rng.poisson(vh / total * photons + floor).astype(float))


# -- the pieces ------------------------------------------------------------------------------- #
@pytest.mark.parametrize("rho", [None, 0.05, 0.2, 1.3])
def test_the_kernels_are_the_ones_binned_per_call(rho):
    for got, old in zip(ex.polarised_kernels(N, DT, 4.0, rho), _old_kernels(N, DT, 4.0, rho)):
        np.testing.assert_array_equal(got, old)
    got = ex.polarised_kernels(N, DT, 4.0, rho)[0]
    got[:] = 0.0  # a caller's kernel is its own: the kept decay is not touched
    np.testing.assert_array_equal(ex.polarised_kernels(N, DT, 4.0, rho)[0], _old_kernels(N, DT, 4.0, rho)[0])


@pytest.mark.parametrize("iterations", [None, 100, 37])
def test_richardson_lucy_is_bit_identical(iterations):
    vv, vh = _dye()
    kv, kh = _old_kernels(N, DT, 4.0, 0.2)
    mask = np.zeros(N)
    mask[20:600] = 1.0
    for counts, kernel in ((vv, kv), (vh, kh)):
        floor = float(np.quantile(counts[20:600], 0.1))
        y = np.clip(counts - floor, 0.0, None) * mask
        np.testing.assert_array_equal(
            ex.richardson_lucy(y, kernel, mask=mask, iterations=iterations, floor=floor, observed=counts),
            _old_rl(y, kernel, mask=mask, iterations=iterations, floor=floor, observed=counts))
    # no mask, a kernel shorter and one longer than the data
    np.testing.assert_array_equal(ex.richardson_lucy(vv, kv[:300], iterations=iterations),
                                  _old_rl(vv, kv[:300], iterations=iterations))
    np.testing.assert_array_equal(ex.richardson_lucy(vv[:500], kv, iterations=iterations),
                                  _old_rl(vv[:500], kv, iterations=iterations))


def test_rows_deconvolved_together_are_the_rows_alone():
    # rows that stop at different iterations (other kernels, other noise)
    rows, kernels = [], []
    for seed, rho in ((1, 0.1), (2, 0.4), (3, 1.0)):
        vv, vh = _dye(seed, rho=rho, photons=10 ** (4 + seed))
        kv, kh = ex.polarised_kernels(N, DT, 4.0, rho)
        rows += [vv, vh]
        kernels += [kv, kh]
    together = ex._reference_irfs(rows, kernels, window=(20, 600))
    for row, kernel, got in zip(rows, kernels, together):
        np.testing.assert_array_equal(got, ex.reference_irf(row, kernel, window=(20, 600)))
    # a gate that shows no decay gives zeros, beside rows that do
    flat = np.random.default_rng(0).poisson(50.0, N).astype(float)
    mixed = ex._reference_irfs([flat, rows[0]], [kernels[0], kernels[0]], window=(20, 600))
    assert not mixed[0].any()
    np.testing.assert_array_equal(mixed[1], together[0])


def test_the_golden_searches_side_by_side_take_their_own_steps():
    fs = [lambda x, c=c: (x - c) ** 2 + 0.1 * np.sin(5 * x) for c in (-3.1, -1.0, 0.4, 1.2)]
    a, b = np.log(0.02), np.log(3.0)
    side = ex._golden_lockstep(lambda pts: [fs[s](x) for s, x in pts], len(fs), a, b, 0.03)
    assert side == [_old_golden(f, a, b, 0.03) for f in fs]
    assert ex._golden(fs[0], a, b, 0.03) == _old_golden(fs[0], a, b, 0.03)


def test_the_rotation_is_the_one_searched_alone():
    vv, vh = _dye(rho=0.2)

    def old_rotation(r0):
        def mismatch(log_rho):
            kv, kh = _old_kernels(N, DT, 4.0, float(np.exp(log_rho)), r0)
            fv, fh = (ex.reference_irf(c, k, iterations=100) for c, k in ((vv, kv), (vh, kh)))
            return ex._aligned_distance(fv, fh, DT)

        return float(np.exp(_old_golden(mismatch, np.log(0.02), np.log(3.0), 0.03)))

    r0s = [0.38, 0.3, 0.2, 0.1]
    assert ex._reference_rotations(vv, vh, DT, 4.0, r0s) == [old_rotation(r) for r in r0s]
    assert ex.reference_rotation(vv, vh, DT, 4.0) == old_rotation(ex.R0)


def test_a_dye_below_the_ideal_anisotropy_is_extracted_as_trial_by_trial():
    # r0 0.15 simulated, 0.38 assumed: the fit is poor and every initial anisotropy step is tried
    rng = np.random.default_rng(11)
    vv, vh = _decay_of(1.0, rho=1.0, r0=0.15)
    total = vv.sum() + vh.sum()
    vv = rng.poisson(vv / total * 8e5 + 100.0).astype(float)
    vh = rng.poisson(vh / total * 8e5 + 100.0).astype(float)
    got = ex._irf_from_reference(vv, vh, DT, tau_ns=1.0, g_factor=1.0, window=(10, 600))
    assert got.info["r0"] < ex.R0, "the steps were tried"

    # the same trials one at a time, from the one-row pieces
    def one(r0):
        rho = ex.reference_rotation(vv, vh, DT, 1.0, window=(10, 600), r0=r0)
        kv, kh = ex.polarised_kernels(N, DT, 1.0, rho, r0)
        parts = [ex.reference_irf(vv, kv, window=(10, 600)), ex.reference_irf(vh, kh, window=(10, 600))]
        fit = ex.reference_fit([vv, vh], [ex._normalised(p) for p in parts], DT, tau_ns=1.0,
                               rho_ns=rho, r0=r0, g_factor=1.0, window=(10, 600)).chi2r
        return fit, r0, rho, parts

    trials = [one(r) for r in (ex.R0, *[s for s in ex.R0_STEPS if s < ex.R0])]
    chi2r, r0, rho, parts = min(trials, key=lambda t: t[0])
    assert (got.info["r0"], got.info["rho_ns"], got.info["fit_chi2r"]) == (r0, rho, chi2r)
    scale = 1.0 - np.exp(-DT / 1.0)
    np.testing.assert_array_equal(got.irf, np.hstack([ex._normalised(p * scale) for p in parts]))
