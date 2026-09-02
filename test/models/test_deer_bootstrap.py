"""DEER bootstrap C++ director path parity (PRD-132).

The bootstrap confidence band runs through one C++ ``IMP.bff.Minimizer`` for
the whole band (the director path), not scipy LM.  Pinned here:

* the C++ director minimiser recovers the same P(r) as a manual fit for a
  single replica (point parity);
* the full bootstrap band brackets the point estimate and has non-negative
  width (statistical coverage);
* the band infrastructure (``_bootstrap_band`` / ``_bootstrap_replica``)
  returns ``None`` for models that don't override it (Tikhonov/MaxEnt use
  fast re-inversion, not the director path).
"""
import numpy as np
import pytest

from chisurf.core.models.deer import kernel as K


def _make_deer_data(r_mean=40.0, sigma=3.0, lam=0.35, bg_k=0.05, noise=0.0):
    from chisurf.core.data import DataCurve

    t = np.linspace(0.0, 3.0, 256)
    r = np.linspace(15.0, 80.0, 200)
    p = K.dd_gauss(r, r_mean, sigma)
    v = K.deer_signal(t, r, p, mod_depth=lam, bg_model="hom3d", bg_k=bg_k, scale=1.0)
    if noise:
        rng = np.random.default_rng(1)
        v = v + rng.normal(0.0, noise, size=v.shape)
    deer = {"t": t, "V": v, "V_imag": np.zeros_like(t), "phase": 0.0,
            "t0": 0.0, "exp_type": "4pDEER", "scale": 1.0}
    return DataCurve(name="synthetic-deer", load_filename_on_init=False,
                     x=t, y=v, ey=np.full_like(v, max(noise, 1e-3)),
                     meta_data={"deer": deer})


def _make_fit(model_class, **kw):
    import chisurf.core.fitting.fit as fit_mod
    return fit_mod.Fit(model_class=model_class, data=_make_deer_data(**kw))


# ---------------------------------------------------------------------------


def test_gaussian_bootstrap_single_replica_matches_manual_fit():
    """One replica through the C++ director path == one manual fit."""
    from chisurf.core.models.deer.deer import DeerGaussianModel
    from chisurf.core.models.deer.kernel import dd_gauss_multi, deer_signal

    fit = _make_fit(DeerGaussianModel, r_mean=40.0, sigma=3.0, lam=0.35, noise=0.01)
    fit.xmin, fit.xmax = 0, len(fit.data.y)
    fit.run()
    model = fit.model

    # Build the band infrastructure
    v_model = np.asarray(model.y, dtype=float)
    sigma_noise = model._data_sigma()
    rng = np.random.default_rng(42)
    replica = v_model + rng.normal(0.0, sigma_noise, size=v_model.shape)

    replicas = [replica]
    band = model._bootstrap_band(replicas)
    assert band is not None, "Gaussian model must support the C++ band path"

    # Fit the replica through the C++ director
    p_director = model._bootstrap_replica(band, replica)
    assert p_director is not None
    p_director = np.asarray(p_director, dtype=float)

    # Manual fit: same residual function, same starting point, via the
    # same director_objective the band uses
    from chisurf.core.fitting.minimizer import director_objective

    g = model.gaussians
    n = len(g)
    m0, s0 = g.means, g.sigmas
    a0 = np.array([abs(p.value) for p in g._amps], dtype=float)
    x0 = np.concatenate([m0, s0, a0[1:]]) if n > 1 else np.concatenate([m0, s0])

    t_raw, _ = model._time_and_data()
    t = t_raw - model.modulation.zero_time
    r = model._r
    k_mat = model._get_kernel(t, r)
    mo, bg = model.modulation, model.background

    def unpack(x):
        mm = x[:n]
        ss = np.abs(x[n:2 * n])
        aa = np.concatenate([[a0[0]], np.abs(x[2 * n:])]) if n > 1 else np.array([a0[0]])
        return mm, ss, aa

    def resid(x):
        mm, ss, aa = unpack(x)
        p = dd_gauss_multi(r, mm, ss, aa)
        vm = deer_signal(t, r, p, mo.mod_depth, bg.model, bg.k, bg.d, mo.scale, kernel=k_mat)
        return vm - replica

    m, node = director_objective(resid, x0)
    m.set_initial_values([float(v) for v in x0])
    m.maxfev = 60
    m.run()
    x_fit = np.asarray(m.x)
    mm, ss, aa = unpack(x_fit)
    p_manual = dd_gauss_multi(r, mm, ss, aa)

    np.testing.assert_allclose(p_director, p_manual, rtol=1e-8, atol=1e-10,
                               err_msg="director replica != manual fit")


def test_gaussian_bootstrap_band_brackets_point_estimate():
    """The full bootstrap band brackets the point estimate."""
    from chisurf.core.models.deer.deer import DeerGaussianModel

    fit = _make_fit(DeerGaussianModel, r_mean=40.0, sigma=3.0, lam=0.35, noise=0.01)
    fit.xmin, fit.xmax = 0, len(fit.data.y)
    fit.run()

    out = fit.model.compute_uncertainty(n_boot=30, seed=0)
    assert out is not None
    r, best, lo, hi = (np.asarray(a, dtype=float) for a in out)
    assert r.size == best.size == lo.size == hi.size > 0
    assert np.all(np.isfinite(lo)) and np.all(np.isfinite(hi))
    # Band brackets the point estimate
    assert np.all(lo <= best + 1e-9) and np.all(best <= hi + 1e-9)
    # Band has non-negative width somewhere
    assert np.any(hi - lo > 0)


def test_rice_bootstrap_band_brackets_point_estimate():
    """Rice model bootstrap band brackets the point estimate."""
    from chisurf.core.models.deer.deer import DeerRiceModel

    fit = _make_fit(DeerRiceModel, r_mean=40.0, sigma=3.0, lam=0.35, noise=0.01)
    fit.xmin, fit.xmax = 0, len(fit.data.y)
    fit.run()

    out = fit.model.compute_uncertainty(n_boot=30, seed=0)
    assert out is not None
    r, best, lo, hi = (np.asarray(a, dtype=float) for a in out)
    assert r.size == best.size == lo.size == hi.size > 0
    assert np.all(np.isfinite(lo)) and np.all(np.isfinite(hi))
    assert np.all(lo <= best + 1e-9) and np.all(best <= hi + 1e-9)
    assert np.any(hi - lo > 0)


def test_tikhonov_band_returns_none():
    """Tikhonov does not use the C++ director path — it uses fast re-inversion."""
    from chisurf.core.models.deer.deer import DeerTikhonovModel

    fit = _make_fit(DeerTikhonovModel)
    fit.xmin, fit.xmax = 0, len(fit.data.y)
    fit.run()
    model = fit.model

    # The base class returns None — Tikhonov does not override it
    assert model._bootstrap_band([np.zeros(256)]) is None


def test_rice_bootstrap_single_replica_matches_manual_fit():
    """One Rice replica through the C++ director path == one manual fit."""
    from chisurf.core.models.deer.deer import DeerRiceModel
    from chisurf.core.models.deer.kernel import dd_rice, deer_signal

    fit = _make_fit(DeerRiceModel, r_mean=40.0, sigma=3.0, lam=0.35, noise=0.01)
    fit.xmin, fit.xmax = 0, len(fit.data.y)
    fit.run()
    model = fit.model

    v_model = np.asarray(model.y, dtype=float)
    sigma_noise = model._data_sigma()
    rng = np.random.default_rng(99)
    replica = v_model + rng.normal(0.0, sigma_noise, size=v_model.shape)

    band = model._bootstrap_band([replica])
    assert band is not None, "Rice model must support the C++ band path"

    p_director = model._bootstrap_replica(band, replica)
    assert p_director is not None
    p_director = np.asarray(p_director, dtype=float)

    # Manual fit
    from chisurf.core.fitting.minimizer import director_objective

    rc = model.rice
    x0 = [float(rc.nu), float(rc.sigma)]

    t_raw, _ = model._time_and_data()
    t = t_raw - model.modulation.zero_time
    r = model._r
    k_mat = model._get_kernel(t, r)
    mo, bg = model.modulation, model.background

    def resid(x):
        p = dd_rice(r, x[0], abs(x[1]))
        vm = deer_signal(t, r, p, mo.mod_depth, bg.model, bg.k, bg.d, mo.scale, kernel=k_mat)
        return vm - replica

    m, node = director_objective(resid, x0)
    m.set_initial_values(x0)
    m.maxfev = 50
    m.run()
    x_fit = np.asarray(m.x)
    p_manual = dd_rice(r, float(x_fit[0]), abs(float(x_fit[1])))

    np.testing.assert_allclose(p_director, p_manual, rtol=1e-8, atol=1e-10,
                               err_msg="Rice director replica != manual fit")
