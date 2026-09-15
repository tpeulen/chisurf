"""FRET models described by BFF, against the classic ChiSurf FRET models.

Each family is a donor lifetime spectrum quenched over a distance
distribution, through the same instrument as a lifetime fit. The contract is
the classic model's curve at the same numbers, for every distance family --
Gaussian, discrete, worm-like chain, SAW-nu and the Ising chain. The classic
models are gone; their curves at these numbers are in
``data/classic_tcspc_reference.json``, recorded before they were removed.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fitting.fit as fitting
from chisurf.core.models.description import for_family

CLASSIC = json.loads((pathlib.Path(__file__).parent / "data" / "classic_tcspc_reference.json").read_text())["fret"]

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
    ids = set(problem.get_parameter_ids())
    for canonical, value in {**{k: v for k, v in shared.items() if k in ids}, **values}.items():
        _set(problem, canonical, value)
    model.update()
    return model


def _assert_same(classic, view):
    np.testing.assert_allclose(np.asarray(view.y), np.asarray(classic), rtol=1e-9, atol=1e-9)


def test_gaussian_distances():
    view = _view("tcspc_fret_gaussian", "tcspc_fret_gaussian.components.2", {
        "distance.mean.0": 41.0, "distance.sigma.0": 5.0, "distance.shape.0": 0.0, "distance.amplitude.0": 0.6,
        "distance.mean.1": 62.0, "distance.sigma.1": 9.0, "distance.shape.1": 0.0, "distance.amplitude.1": 0.4})
    _assert_same(CLASSIC["gaussian"], view)
    outputs = {p.name: p.value for p in view.parameters_all if getattr(p, "is_output", False)}
    assert outputs["E"] == pytest.approx(CLASSIC["gaussian_efficiency"], rel=1e-9)


def test_discrete_distances():
    view = _view("tcspc_fret_discrete", "tcspc_fret_discrete.components.2", {
        "distance.mean.0": 45.0, "distance.amplitude.0": 0.7,
        "distance.mean.1": 60.0, "distance.amplitude.1": 0.3})
    _assert_same(CLASSIC["discrete"], view)


@pytest.mark.parametrize("linker", [False, True])
def test_worm_like_chain(linker):
    view = _view("tcspc_fret_worm_like_chain", None, {
        "chain.contour_length": 120.0, "chain.persistence_length": 25.0, "chain.linker_width": 5.0},
        scalars={"dye_linker": 1.0 if linker else 0.0})
    _assert_same(CLASSIC["worm_like_chain"][str(linker)], view)


def test_saw_nu():
    view = _view("tcspc_fret_saw_nu", None, {"chain.r_rms": 48.0, "chain.nu": 0.55})
    _assert_same(CLASSIC["saw_nu"], view)


def test_ising_chain():
    view = _view("tcspc_fret_ising_chain", None, {
        "chain.n_residues": 30.0, "chain.b_structured": 3.5, "chain.b_unstructured": 7.0,
        "chain.coupling": 1.2, "chain.field": 0.3})
    _assert_same(CLASSIC["ising_chain"], view)


def test_a_fret_model_can_be_mixed():
    view = _view("tcspc_fret_gaussian", None, {"distance.mean.0": 45.0})
    mixture = fitting.Fit(model_class=for_family("tcspc_mixture"), data=_data()).model
    mixture.append_model(view)
    assert mixture.model_names


@pytest.mark.parametrize("polarization, code", [("vv", 1), ("vh", 2)])
def test_a_polarized_fret_decay(polarization, code):
    reference = CLASSIC["polarized"][polarization]
    view = _view("tcspc_fret_gaussian", None, {
        "distance.mean.0": 44.0, "distance.sigma.0": 6.0, "distance.shape.0": 0.0, "distance.amplitude.0": 1.0,
        "anisotropy.r0": 0.38, "anisotropy.g": 1.3, "anisotropy.l1": reference["l1"], "anisotropy.l2": reference["l2"],
        "rotation.amplitude.0": reference["b0"], "rotation.time.0": reference["rho0"]},
        scalars={"polarization": code})
    _assert_same(reference["y"], view)


def test_static_isotropic_orientation_factors():
    """ChiSurf's 'slow' orientation mode, on its exact path: every (distance, kappa^2) pair."""
    reference = CLASSIC["static_isotropic"]
    view = _view("tcspc_fret_gaussian", None, {
        "distance.mean.0": 47.0, "distance.sigma.0": 6.0, "distance.shape.0": 0.0, "distance.amplitude.0": 1.0},
        scalars={"static_orientation": 1.0, "kappa2_bins": 0.0})
    _assert_same(reference, view)
    # Binned by apparent distance, the curve moves by less than the noise of any decay.
    binned = _view("tcspc_fret_gaussian", None, {
        "distance.mean.0": 47.0, "distance.sigma.0": 6.0, "distance.shape.0": 0.0, "distance.amplitude.0": 1.0},
        scalars={"static_orientation": 1.0, "kappa2_bins": 512.0})
    np.testing.assert_allclose(np.asarray(binned.y), np.asarray(reference), rtol=2e-3)


@pytest.mark.parametrize("mode, rtol", [(1.0, 1e-9), (0.0, 1e-6)])
def test_pddem(mode, rtol):
    """Energy migration A <-> B through the one transfer-kinetics implementation."""
    reference = CLASSIC["pddem"]
    view = _view("tcspc_pddem", None, {
        "chromophore_a.amplitude.0": 1.0, "chromophore_a.tau.0": 1.2,
        "distance.mean.0": 45.0, "distance.sigma.0": 6.0, "distance.shape.0": 0.0, "distance.amplitude.0": 1.0,
        "pddem.f_ab": 1.0, "pddem.f_ba": 0.3, "pddem.pure_a": 0.1, "pddem.pure_b": 0.05,
        "pddem.excitation_a": 0.9, "pddem.excitation_b": 0.1, "pddem.emission_a": 0.2, "pddem.emission_b": 0.8},
        scalars={"transfer_mode": mode})
    np.testing.assert_allclose(np.asarray(view.y), np.asarray(reference["chisurf"]), rtol=rtol, atol=1e-9)
    # alpha, as the classic group reported it: each chromophore's emission share.
    outputs = {p.name: p.value for p in view.parameters_all if getattr(p, "is_output", False)}
    assert outputs["αA→B"] == pytest.approx(reference["alpha_a"], rel=1e-15)
    assert outputs["αB→A"] == pytest.approx(reference["alpha_b"], rel=1e-15)


@pytest.mark.parametrize("dimension", [1, 2, 3])
@pytest.mark.parametrize("periodic", [False, True])
def test_acceptor_density(dimension, periodic):
    """A donor quenched by acceptors at a density in 1, 2 or 3 dimensions.

    ChiSurf's classic model is gone; its curves at these numbers were stored
    before deletion (data/acceptor_density_reference.json).
    """
    import json
    import pathlib

    reference = json.loads((pathlib.Path(__file__).parent / "data" / "acceptor_density_reference.json")
                           .read_text())["curves"][f"{dimension}-{int(periodic)}"]
    view = _view("tcspc_fret_acceptor_density", f"tcspc_fret_acceptor_density.dimensions.{dimension}",
                 {"acceptor.c_over_c0": 0.8, "fret.tau0": 4.0},
                 scalars={"periodic_excitation": 1.0 if periodic else 0.0})
    np.testing.assert_allclose(np.asarray(view.y), np.asarray(reference), rtol=1e-9, atol=1e-9)


def test_a_structure_ensemble():
    """FRET against the accessible volumes of two structures at equal fractions.

    ChiSurf's classic structure model is replaced; its curve at these numbers
    was stored before (data/fret_structure_reference.json).
    """
    import json
    import pathlib
    import chisurf.core.structure
    from chisurf.core.models.tcspc.fret_structure import FRETStructure

    reference = json.loads((pathlib.Path(__file__).parent / "data" / "fret_structure_reference.json")
                           .read_text())["curve"]
    fit = fitting.Fit(model_class=FRETStructure, data=_data())
    fit.xmin, fit.xmax = 0, N
    model = fit.model
    model.set_dataset("response", chisurf.core.curve.Curve(x=_axis(), y=_irf()))
    model.set_scalar("period", PERIOD)
    model.res_1, model.res_2, model.atom_name_1, model.atom_name_2 = 18, 577, "CB", "CB"
    pdbs = pathlib.Path(__file__).resolve().parents[1] / "data" / "atomic_coordinates" / "pdb_files"
    model.load_structures([pdbs / "hGBP1_closed.pdb", pdbs / "hGBP1_open.pdb"])
    assert model.names and len(model.structure_files) == 2
    problem = model.problem
    assert problem is not None, model.missing
    for canonical, value in {"donor.amplitude.0": 1.0, "donor.tau.0": 3.8, "fret.x_donly": 0.15,
                             "instrument.n0": 5000.0, "instrument.scatter": 0.01, "instrument.background": 2.0,
                             "distance.amplitude.0": 0.5, "distance.amplitude.1": 0.5}.items():
        _set(problem, canonical, value)
    model.update()
    np.testing.assert_allclose(np.asarray(model.y), np.asarray(reference), rtol=1e-9, atol=1e-9)
    # The ensemble and its label settings survive a save and reload.
    restored = fitting.Fit(model_class=FRETStructure, data=_data()).model
    restored.set_dataset("response", chisurf.core.curve.Curve(x=_axis(), y=_irf()))
    restored.set_scalar("period", PERIOD)
    restored.set_state(model.get_state())
    assert restored.res_2 == 577 and restored.structure_files == model.structure_files
