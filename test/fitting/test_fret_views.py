"""FRET models described by BFF, against the classic ChiSurf FRET models.

Each family is a donor lifetime spectrum quenched over a distance
distribution, through the same instrument as a lifetime fit. The contract is
the classic model's curve at the same numbers, for every distance family --
Gaussian, discrete, worm-like chain, SAW-nu and the Ising chain.
"""
from __future__ import annotations

import numpy as np
import pytest

import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fitting.fit as fitting
from chisurf.core.models.description import for_family

N = 256
DT = 0.05
PERIOD = 12.5


def _axis():
    return np.arange(N) * DT


def _irf():
    return 1000.0 * np.exp(-0.5 * ((_axis() - 1.0) / 0.08) ** 2)


def _data():
    x = _axis()
    y = np.random.default_rng(3).poisson(2000.0 * np.exp(-np.maximum(x - 1.0, 0) / 2.0) + 20).astype(float)
    return chisurf.core.data.DataCurve(x=x, y=y, ey=np.sqrt(np.maximum(y, 1.0)))


def _set(problem, canonical, value):
    port = problem.get_parameter(canonical)
    held = port.fixed
    port.fixed = False
    port.value = float(value)
    port.fixed = held


def _classic(model_class, configure):
    fit = fitting.Fit(model_class=model_class, data=_data())
    fit.xmin, fit.xmax = 0, N
    model = fit.model
    model.convolve._irf = chisurf.core.curve.Curve(x=_axis(), y=_irf())
    model.convolve.dt = DT
    model.convolve.rep_rate = 1000.0 / PERIOD
    model.convolve._n0.fixed = False
    model.convolve._n0.value = 5000.0
    model.generic._sc.value = 0.01
    model.generic._bg.value = 2.0
    model.lifetimes._lifetimes[0].value = 3.8
    model.fret_parameters.xDOnly = 0.15
    configure(model)
    model.find_parameters()
    model.update()
    return model


def _view(family, structure, values, scalars=None):
    fit = fitting.Fit(model_class=for_family(family), data=_data())
    fit.xmin, fit.xmax = 0, N
    model = fit.model
    model.set_dataset("response", chisurf.core.curve.Curve(x=_axis(), y=_irf()))
    model.set_scalar("period", PERIOD)
    for name, value in (scalars or {}).items():
        model.set_scalar(name, value)
    problem = model.problem
    assert problem is not None, model.missing
    if structure:
        model.structure = structure
    shared = {"donor.amplitude.0": 1.0, "donor.tau.0": 3.8, "fret.x_donly": 0.15,
              "instrument.n0": 5000.0, "instrument.scatter": 0.01, "instrument.background": 2.0}
    for canonical, value in {**shared, **values}.items():
        _set(problem, canonical, value)
    model.update()
    return model


def _assert_same(classic, view):
    np.testing.assert_allclose(np.asarray(view.y), np.asarray(classic.y), rtol=1e-9, atol=1e-9)


def test_gaussian_distances():
    from chisurf.core.models.tcspc.fret import GaussianModel

    def classic(model):
        g = model.gaussians
        g.append(mean=62.0, sigma=9.0, x=0.4)
        g._gaussianMeans[0].value = 41.0
        g._gaussianSigma[0].value = 5.0
        g._gaussianAmplitudes[0].value = 0.6

    view = _view("tcspc_fret_gaussian", "tcspc_fret_gaussian.components.2", {
        "distance.mean.0": 41.0, "distance.sigma.0": 5.0, "distance.shape.0": 0.0, "distance.amplitude.0": 0.6,
        "distance.mean.1": 62.0, "distance.sigma.1": 9.0, "distance.shape.1": 0.0, "distance.amplitude.1": 0.4})
    reference = _classic(GaussianModel, classic)
    _assert_same(reference, view)
    outputs = {p.name: p.value for p in view.parameters_all if getattr(p, "is_output", False)}
    assert outputs["E"] == pytest.approx(reference.fret_efficiency, rel=1e-9)


def test_discrete_distances():
    from chisurf.core.models.tcspc.fret import FRETrateModel

    def classic(model):
        d = model.fret_rates
        d._distances[0].value = 45.0
        d._amplitudes[0].value = 0.7
        d.append(60.0, 0.3)

    view = _view("tcspc_fret_discrete", "tcspc_fret_discrete.components.2", {
        "distance.mean.0": 45.0, "distance.amplitude.0": 0.7,
        "distance.mean.1": 60.0, "distance.amplitude.1": 0.3})
    _assert_same(_classic(FRETrateModel, classic), view)


@pytest.mark.parametrize("linker", [False, True])
def test_worm_like_chain(linker):
    from chisurf.core.models.tcspc.fret import WormLikeChainModel

    def classic(model):
        model.use_dye_linker = linker
        model._chain_length.value = 120.0
        model._persistence_length.value = 25.0
        model._sigma_linker.value = 5.0

    view = _view("tcspc_fret_worm_like_chain", None, {
        "chain.contour_length": 120.0, "chain.persistence_length": 25.0, "chain.linker_width": 5.0},
        scalars={"dye_linker": 1.0 if linker else 0.0})
    _assert_same(_classic(WormLikeChainModel, classic), view)


def test_saw_nu():
    from chisurf.core.models.tcspc.fret import SawNuModel

    def classic(model):
        model._r_rms.value = 48.0
        model._nu.value = 0.55

    view = _view("tcspc_fret_saw_nu", None, {"chain.r_rms": 48.0, "chain.nu": 0.55})
    _assert_same(_classic(SawNuModel, classic), view)


def test_ising_chain():
    from chisurf.core.models.tcspc.fret import IsingChainModel

    def classic(model):
        for name, value in (("_n_residues", 30.0), ("_b_structured", 3.5), ("_b_unstructured", 7.0),
                            ("_coupling", 1.2), ("_field", 0.3)):
            getattr(model, name).value = value

    view = _view("tcspc_fret_ising_chain", None, {
        "chain.n_residues": 30.0, "chain.b_structured": 3.5, "chain.b_unstructured": 7.0,
        "chain.coupling": 1.2, "chain.field": 0.3})
    _assert_same(_classic(IsingChainModel, classic), view)


def test_a_fret_model_can_be_mixed():
    view = _view("tcspc_fret_gaussian", None, {"distance.mean.0": 45.0})
    mixture = fitting.Fit(model_class=for_family("tcspc_mixture"), data=_data()).model
    mixture.append_model(view)
    assert mixture.model_names


@pytest.mark.parametrize("polarization, code", [("vv", 1), ("vh", 2)])
def test_a_polarized_fret_decay(polarization, code):
    from chisurf.core.models.tcspc.fret import GaussianModel

    def classic(model):
        g = model.gaussians
        g._gaussianMeans[0].value = 44.0
        g._gaussianSigma[0].value = 6.0
        model.anisotropy.polarization_type = polarization
        model.anisotropy.add_rotation(b=0.2, rho=2.0)
        model.anisotropy._r0.value = 0.38
        model.anisotropy._g.value = 1.3

    reference = _classic(GaussianModel, classic)
    rotation = {"rotation.amplitude.0": reference.anisotropy._bs[0].value,
                "rotation.time.0": reference.anisotropy._rhos[0].value}
    view = _view("tcspc_fret_gaussian", None, {
        "distance.mean.0": 44.0, "distance.sigma.0": 6.0, "distance.shape.0": 0.0, "distance.amplitude.0": 1.0,
        "anisotropy.r0": 0.38, "anisotropy.g": 1.3,
        "anisotropy.l1": reference.anisotropy._l1.value, "anisotropy.l2": reference.anisotropy._l2.value,
        **rotation}, scalars={"polarization": code})
    _assert_same(reference, view)


def test_static_isotropic_orientation_factors():
    """ChiSurf's 'slow' orientation mode, on its exact path: every (distance, kappa^2) pair."""
    from types import SimpleNamespace
    from chisurf.core.models.tcspc.fret import GaussianModel

    def classic(model):
        model.gaussians._gaussianMeans[0].value = 47.0
        model.gaussians._gaussianSigma[0].value = 6.0
        model.orientation_parameter.mode = "slow"
        model._kappa2_fft_checkbox = SimpleNamespace(isChecked=lambda: False)

    reference = _classic(GaussianModel, classic)
    view = _view("tcspc_fret_gaussian", None, {
        "distance.mean.0": 47.0, "distance.sigma.0": 6.0, "distance.shape.0": 0.0, "distance.amplitude.0": 1.0},
        scalars={"static_orientation": 1.0, "kappa2_bins": 0.0})
    _assert_same(reference, view)
    # Binned by apparent distance, the curve moves by less than the noise of any decay.
    binned = _view("tcspc_fret_gaussian", None, {
        "distance.mean.0": 47.0, "distance.sigma.0": 6.0, "distance.shape.0": 0.0, "distance.amplitude.0": 1.0},
        scalars={"static_orientation": 1.0, "kappa2_bins": 512.0})
    np.testing.assert_allclose(np.asarray(binned.y), np.asarray(reference.y), rtol=2e-3)
